# Migrating `pzg-install-z2m` off Python

Plan for rewriting the Zigbee2MQTT installer as a single self-contained shell
script with no Python dependency, no pyziggy coupling, and an explicit
containment story.

Written 2026-08-01. Findings below were verified against Zigbee2MQTT 2.6.1,
Node 22.22.0, and macOS 15 (Darwin 24.6.0) unless marked otherwise.

---

## 1. Goals

1. **The installer is one file.** `curl` it into an empty directory, run it, get
   a working Zigbee2MQTT. No `pzg-setup-venv`, no second download.
2. **The installation is contained to that one directory** as far as is
   physically possible.
3. **Uninstall instructions state exactly what is contained and what leaks.**
   No hand-waving — every path outside the install directory is named.
4. **The Zigbee2MQTT version is one obvious line to edit** at the top.
5. **No pyziggy dependency, in either direction.** pyziggy is leaving Python;
   this script must not care what it becomes.
6. **Works on a brand-new Mac.** Homebrew dependency acceptable if unavoidable.

### Non-goals

- **Linux support.** macOS is the only target. Rock-solid on macOS beats
  portable-but-hedged. The installer hard-errors on non-Darwin at startup
  (§5.1) rather than half-working.
- **Upgrading an existing installation.** Out of scope. Installing is
  install-into-empty-directory only.

---

## 2. Verified findings

These drove the design. Each was checked, not assumed.

### 2.1 `git` and `python3` are unavailable on a fresh Mac — this is the blocker

```
$ shasum -a 256 /usr/bin/git /usr/bin/python3
7f30f076...ad39e  /usr/bin/git
7f30f076...ad39e  /usr/bin/python3
```

Identical hash, 78 hardlinks to one binary. These are Xcode Command Line Tools
**stubs**. On a machine without CLT installed, invoking either pops a GUI
"install command line developer tools" dialog and exits nonzero — fatal for an
unattended install.

The current script depends on both:

- `git clone` at [pzg-install-z2m:105](pzg-install-z2m#L105)
- `#!/usr/bin/env python3` for the generated `check-if-z2m-mqtt-is-listening`
  at [pzg-install-z2m:129](pzg-install-z2m#L129)

Note the second one is a *runtime* dependency, not just install-time — it runs
on every service start. Removing Python from the installer without also
rewriting the MQTT precheck would leave the goal half-met.

**Both must go.** Sections 2.3 and 5.4 cover how.

### 2.2 Everything else the script needs is in the macOS base system

| Tool | Path | Base OS? |
|---|---|---|
| `curl` | `/usr/bin/curl` | yes |
| `tar` | `/usr/bin/tar` | yes — bsdtar 3.5.3, links liblzma **and** zlib |
| `shasum` | `/usr/bin/shasum` | yes |
| `uname` | `/usr/bin/uname` | yes |

**Consequence: Homebrew is not needed.** You offered it as a compromise; the
plan doesn't spend it. Adding brew would actively work against goal 2 —
`/opt/homebrew` is shared, versioned loosely, and would become the single
largest leak in the uninstall document.

The only conceivable system dependency left is Xcode CLT for native module
compilation — see §4.3.

### 2.3 Zigbee2MQTT can be installed without `git`, and tolerates its absence

The release tarball exists and needs no git:

```
https://github.com/Koenkk/zigbee2mqtt/archive/refs/tags/2.6.1.tar.gz   → 302 → 200
```

More importantly, z2m *itself* degrades gracefully when git is missing.
`index.js` → `currentHash()`:

```js
exec("git rev-parse --short=8 HEAD", (error, stdout) => {
    const commitHash = stdout.trim();
    if (error || commitHash === "") { resolve("unknown"); }
    else { resolve(commitHash); }
});
```

With no git, `hash === "unknown"`, and `checkDist()`'s rebuild branch
(`hash !== "unknown" && distHash !== hash`) is never taken. For a pinned
tarball install that never changes, that is exactly the behaviour we want.

### 2.4 The TypeScript build happens on first *start*, not on install

There is **no `prepare` script** in z2m 2.6.1 — only `prepack`. So
`pnpm install --frozen-lockfile` does not build anything. Instead:

```
pnpm start → node index.js → start() → checkDist()
    → dist/.hash missing? → build("initial build") → exec("pnpm run prepack")
```

`prepack` is `clean && build`, and `build` is `tsc && node index.js writehash`.

This has three consequences the current script silently lives with:

- **First launchd start runs a full `tsc` compile.** Combined with
  `KeepAlive: true` and no `dist/`, a build failure becomes a restart loop that
  recompiles every cycle.
- **A build failure surfaces at 3am under launchd**, not during installation
  where someone is watching.
- **`pnpm` must be on `PATH` at runtime**, because `index.js` shells out to it.

**Fix: run `pnpm run build` explicitly at install time.** That writes `dist/`
and `dist/.hash`, so `checkDist()` finds the hash and skips building at every
subsequent start. Build failures then happen in front of the user.

### 2.5 Version pinning metadata is already in the package

```json
"packageManager": "pnpm@10.12.1",
"engines": { "node": "^20 || ^22 || ^24" }
```

Both are useful:

- `packageManager` lets **corepack** install the exact pnpm upstream tested
  with, instead of `npm install pnpm --save-dev` floating to latest
  ([pzg-install-z2m:94](pzg-install-z2m#L94)).
- `engines.node` gives the script a **preflight check**: after downloading z2m,
  compare the pinned `USE_NODE_VERSION` against `engines.node` and fail loudly
  on mismatch. This directly serves goal 4 — bumping the z2m version becomes
  safe, because a node incompatibility is reported at install time with a clear
  message instead of a warning buried in the service log.

### 2.6 Native modules are the one real risk

```json
"onlyBuiltDependencies": ["@biomejs/biome", "@serialport/bindings-cpp",
                          "esbuild", "unix-dgram"],
"optionalDependencies": { "unix-dgram": "^2.0.7" }
```

pnpm will run build scripts for these. `@serialport/bindings-cpp` uses
`node-gyp-build`, which prefers shipped prebuilds and only compiles as a
fallback. `biome` and `esbuild` ship platform binaries. `unix-dgram` is
*optional* (syslog transport) so its failure is non-fatal.

So the common path needs no compiler — but it is not guaranteed. See §4.3.

---

## 3. Target layout

Run the installer in an empty directory. Everything below lives inside it.

```
<install-dir>/
├── env.sh                            # single source of truth for PATH + cache env
├── node/                             # official Node tarball, unpacked
│   └── bin/{node,npm,npx,corepack,pnpm}
├── zigbee2mqtt/                      # release tarball, unpacked
│   ├── data/                         # ← YOUR CONFIG AND PAIRINGS LIVE HERE
│   ├── dist/                         # built at install time (§2.4)
│   └── node_modules/
├── .pnpm-store/                      # pnpm content-addressable store
├── .cache/                           # npm / corepack / node-gyp caches
├── logs/                             # launchd stdout + stderr
├── pzg-run-z2m
├── pzg-check-mqtt                    # renamed, no longer Python
├── pzg-service-install
├── pzg-service-uninstall
└── UNINSTALL.md                      # generated, with resolved paths
```

Two notes on this shape:

- **`.pnpm-store` inside the install dir is a performance win, not just a
  containment one.** pnpm hardlinks from the store into `node_modules`, and
  hardlinks cannot cross filesystems. Co-locating them guarantees same-volume.
- **`env.sh` replaces `source .venv/bin/activate`.** It is four exports you
  wrote and can read, instead of a generated venv script plus the
  deactivate/reactivate dance at
  [pzg-install-z2m:90-91](pzg-install-z2m#L90-L91) needed to pick up nodeenv's
  `PATH` mutation.

---

## 4. Containment inventory

This becomes the skeleton of the generated `UNINSTALL.md`.

### 4.1 Contained — deleting the install directory removes these

| What | Where | How it's contained |
|---|---|---|
| Node toolchain | `./node/` | unpacked tarball, nothing installed globally |
| z2m source + deps | `./zigbee2mqtt/` | release tarball + local `node_modules` |
| pnpm store | `./.pnpm-store/` | `--store-dir` flag (default: `~/Library/pnpm/store`) |
| pnpm global dir | `./.cache/pnpm/` | `PNPM_HOME` (default: `~/Library/pnpm`) |
| npm cache | `./.cache/npm/` | `npm_config_cache` (default: `~/.npm`) |
| corepack cache | `./.cache/corepack/` | `COREPACK_HOME` (default: `~/.cache/node/corepack`) |
| node-gyp cache | `./.cache/node-gyp/` | `npm_config_devdir` (default: `~/Library/Caches/node-gyp`) |
| z2m config + DB | `./zigbee2mqtt/data/` | z2m default; **back this up before deleting** |
| z2m logs | `./zigbee2mqtt/data/log/` | z2m default |
| Service logs | `./logs/` | currently leaks to `/tmp/io.zigbee2mqtt/` — §6 |

Every default in that right-hand column is a leak the current script has.
`pnpm store path` at [pzg-install-z2m:398](pzg-install-z2m#L398) documents one
of them; the other five are undocumented.

### 4.2 Leaks — genuinely outside the directory, must be documented

| What | Where | Why it can't be contained |
|---|---|---|
| launchd service definition | `/Library/LaunchDaemons/io.zigbee2mqtt.plist` | launchd only reads from fixed locations. Unavoidable if you want a service. Removed by `pzg-service-uninstall`. |
| launchd job registration | launchd's internal state | Removed by `launchctl bootout`. |

That's the whole list — which is the point of doing this properly. Two entries,
both removed by one script.

### 4.3 Conditional — only if native compilation is triggered

If a prebuild is missing for your platform (§2.6), `node-gyp` needs a C++
toolchain, which means Xcode Command Line Tools — a ~1.5GB system-wide install
that **no shell script can contain**.

Recommended handling: don't preflight it (CLT is usually present, and probing
for it risks triggering the GUI stub dialog described in §2.1). Instead, catch
the `pnpm install` failure and emit a specific message:

```
Dependency installation failed. This usually means a native module had no
prebuilt binary for your platform and tried to compile.

If the log above mentions node-gyp, gyp, or clang, install the Xcode Command
Line Tools and re-run this script:

    xcode-select --install

Note: this is a system-wide install (~1.5GB) that this script cannot contain
or remove.
```

### 4.4 Optional hardening: override `HOME` during install

Setting `HOME="$SELF_DIR/.home"` for the duration of the install catches every
cache location you *didn't* think of. This was risky while the script used
`git clone` (it would hide the user's git and ssh config); with git gone
(§2.3), the objection disappears.

Recommend as a **phase 2** item — get the explicit redirections working and
verified first, then add this as a belt-and-braces catch-all. It also makes the
verification in §7 trivial: if `.home/` is empty after an install, nothing
leaked.

---

## 5. Design decisions

### 5.1 Node acquisition — official tarball, checksum-verified

Verified working:

```
https://nodejs.org/dist/v22.22.0/node-v22.22.0-darwin-arm64.tar.gz     → 200
https://nodejs.org/dist/v22.22.0/SHASUMS256.txt                        → 200
  5ed4db0f...02640  node-v22.22.0-darwin-arm64.tar.gz
```

Use `.tar.gz` rather than `.tar.xz`. Base macOS `tar` handles both, but `.gz`
removes any liblzma question on older systems for zero cost.

macOS only — two architectures, and anything else is a hard error:

```
Darwin-arm64  → darwin-arm64
Darwin-x86_64 → darwin-x64
*             → error out
```

Put the Darwin guard at the **top of the installer**, not just in the generated
service scripts where it lives today. A non-Darwin machine should be told so
before anything is downloaded, not after node is unpacked. (And it must be
`exit 1`, not `return 0` — bug 3 in §6.)

Verify the checksum before unpacking. `nodeenv` never did this; it's two lines
and this is a binary that will run as a daemon.

### 5.2 pnpm acquisition — corepack

```sh
export COREPACK_HOME="$SELF_DIR/.cache/corepack"
export COREPACK_ENABLE_DOWNLOAD_PROMPT=0        # required: non-interactive
"$SELF_DIR/node/bin/corepack" enable --install-directory "$SELF_DIR/node/bin"
```

corepack then reads `packageManager: "pnpm@10.12.1"` from z2m's `package.json`
and fetches exactly that version.

**Caveats to record in the script comments:**

- `COREPACK_ENABLE_DOWNLOAD_PROMPT=0` is not optional — corepack prompts before
  downloading and will hang an unattended install.
- corepack's status as a bundled Node component has been under discussion
  upstream. Since node is pinned to an exact version here, that risk is
  deferred rather than live — but note it next to `USE_NODE_VERSION` so whoever
  bumps node knows to re-check.
- **Never run `pnpm config set` without `--location=project`.** The global form
  writes to `~/Library/Preferences/pnpm/rc` — a leak. Prefer explicit CLI flags
  and env vars over any config file.

*Fallback if corepack is ever dropped:* `node/bin/npm install -g pnpm@10.12.1`
with `npm_config_prefix="$SELF_DIR/node"`. Loses the automatic sync with
`packageManager` — the version becomes a second thing to bump by hand.

### 5.3 Install and build sequence

```sh
pnpm install --frozen-lockfile --store-dir "$SELF_DIR/.pnpm-store"
pnpm run build          # tsc && node index.js writehash  — see §2.4
```

The explicit build is the important change from the current script.

Pass `--store-dir` as a **CLI flag** rather than writing an `.npmrc`: z2m ships
its own `.npmrc`, so writing one into the project directory risks clobbering
it, and npm/pnpm config precedence between project and global files is an easy
thing to get subtly wrong.

### 5.4 MQTT precheck rewrite — Node with z2m's own `js-yaml`

The current script is Python ([pzg-install-z2m:128-197](pzg-install-z2m#L128-L197))
with a hand-rolled 25-line YAML parser. Replace it with a Node script run by
the contained `./node/bin/node`, using `js-yaml` — a direct z2m dependency
(`^4.1.0`), so it is guaranteed present in `zigbee2mqtt/node_modules/`.

Why this over a bash + `awk` + `nc` version:

- **Real YAML parsing.** Kills a whole class of bugs the current parser has:
  quoted values (`server: "mqtt://x:1883"`), inline comments, `mqtt:` nested
  under another key, CRLF line endings.
- **No new dependency.** It uses the node we already contain, and `net`
  from the standard library replaces the `nc` probe.
- The one thing bash would buy — working when `node_modules` is damaged — is
  worth nothing here, because the very next thing the run script does is start
  z2m out of that same `node_modules`.

Carry over two behaviours from the Python version, with corrections:

- The `network_key: GENERATE` early-out (unconfigured install → don't block) is
  good logic. Keep it, but note it depends on parsing the *raw text*, so do
  that check before the YAML parse.
- The trailing `sleep 5; exit 1` is a hand-rolled backoff. launchd already
  throttles restarts to 10s minimum (`ThrottleInterval`), so this is mostly
  redundant — drop it or make it explicit via the plist.

### 5.5 Service: LaunchDaemon, and fix the path mismatch

The current scripts disagree: install writes to
`/Library/LaunchDaemons/` ([:226](pzg-install-z2m#L226)), uninstall looks in
`~/Library/LaunchAgents/` ([:324](pzg-install-z2m#L324)). Since install calls
uninstall first ([:266](pzg-install-z2m#L266)), the cleanup step has never
found anything.

**Pick LaunchDaemon** and make both agree. A Zigbee coordinator should come up
at boot without anyone logging in, which LaunchAgent does not give you. Costs a
`sudo` — document it in the script's `--help` and error clearly if not root.

Use `launchctl bootstrap system` / `bootout` rather than the deprecated
`load`/`unload`.

Also decide: launchd `KeepAlive` **or** z2m's own `Z2M_WATCHDOG` env var — not
both. Two independent restart supervisors will fight. Recommend launchd
`KeepAlive` alone, since it's the one that survives a hard process kill.

---

## 6. Bugs to fix in passing

Found while reading the current script. Independent of the migration, but the
rewrite should not carry them forward.

| # | Location | Issue |
|---|---|---|
| 1 | [:226](pzg-install-z2m#L226) / [:324](pzg-install-z2m#L324) | LaunchDaemons vs LaunchAgents mismatch — §5.5 |
| 2 | [:66](pzg-install-z2m#L66) | No `set -e`, no check on venv setup. On failure, `source .venv/bin/activate` fails too and the script proceeds against *system* pip/npm. |
| 3 | [:263](pzg-install-z2m#L263), [:360](pzg-install-z2m#L360) | `return 0` outside a function in a non-sourced script — errors and falls through, so the non-Darwin guard doesn't guard. Should be `exit 1`. |
| 4 | [:296-299](pzg-install-z2m#L296-L299) | plist points `StandardOutPath` at `/tmp/io.zigbee2mqtt/stdout.log`, but nothing creates that directory. launchd creates files, not intermediate dirs — service logging likely fails silently today. Moving logs to `./logs/` fixes and un-leaks it in one step. |
| 5 | [:47](pzg-install-z2m#L47) etc. | `trap "rm -f "$COMMAND_BUFFER EXIT` — works only because `mktemp` paths contain no spaces. Should be `trap 'rm -f "$COMMAND_BUFFER"' EXIT`. |
| 6 | [:398](pzg-install-z2m#L398) | Stray `."` at the end of the generated UNINSTALL.md. |
| 7 | [:307](pzg-install-z2m#L307), [:311-312](pzg-install-z2m#L311-L312) | Generated service script prints `[pyziggy-setup]` while every other line uses `$SCRIPT_NAME` — and it's exactly the pyziggy coupling goal 5 wants gone. |
| 8 | [:94](pzg-install-z2m#L94) | `npm install pnpm --save-dev` floats to latest pnpm and writes a stray `package.json`/`package-lock.json` into the install root. §5.2 replaces this. |

---

## 7. Migration phases

Ordered so each phase leaves something testable.

All design decisions are locked (§9) — this starts at phase 1.

| Phase | Work | Done when |
|---|---|---|
| 1 | Single-file skeleton: config block, `set -euo pipefail`, Darwin guard, logging helpers, `--help`, `--force`, non-empty-directory guard | `--help` works, exits 1 on non-Darwin, refuses to clobber a non-empty dir |
| 2 | Contained node: arch map, download, checksum verify, unpack (§5.1) | `./node/bin/node --version` prints the pinned version |
| 3 | `env.sh` + all cache redirections (§4.1) | Sourcing it gives node + the redirected cache vars |
| 4 | Contained pnpm via corepack (§5.2) | `pnpm --version` prints 10.12.1, `.cache/corepack/` is populated, `~/Library/pnpm` was never created |
| 5 | z2m acquisition via release tarball, `engines.node` preflight (§2.3, §2.5) | `zigbee2mqtt/` unpacked, version check passes, no git invoked |
| 6 | `pnpm install --store-dir` + explicit `pnpm run build` (§5.3) | `zigbee2mqtt/dist/.hash` exists; `~/Library/pnpm/store` was never created |
| 7 | Generated runtime artifacts: `pzg-run-z2m`, `pzg-check-mqtt` (§5.4), service install/uninstall with matching paths and local logs (§5.5) | `./pzg-run-z2m` starts z2m with **zero** rebuild output |
| 8 | Generated `UNINSTALL.md` from the §4 inventory, with paths resolved at install time | Doc names every path in §4.1 and §4.2 concretely |
| 9 | Update `bootstrap-z2m-installation.sh` — one file, drop `pzg-setup-venv` | One `curl` |
| 10 | Optional: `HOME` override hardening (§4.4) | `.home/` empty after a full install |

`pzg-setup-venv` is not deleted by this — it may still serve the rest of the
repo. It just stops being on this script's critical path.

---

## 8. Verification

The containment claim is testable, so test it rather than asserting it.

**Before installing**, record which of these exist:

```sh
~/Library/pnpm  ~/Library/pnpm/store  ~/.npm
~/.cache/node/corepack  ~/Library/Caches/node/corepack
~/Library/Caches/node-gyp  ~/Library/Preferences/pnpm
```

**After a full install + service start + service stop**, re-check. Any path
that appeared is a leak the script missed — either redirect it or add it to
`UNINSTALL.md`. There is no third option; an undocumented leak is the specific
failure this rewrite exists to prevent.

**Then test the uninstall claim end to end:**

```sh
./pzg-service-uninstall
cd .. && rm -rf <install-dir>
```

Re-check the list. A clean run means goals 2 and 3 are actually met.

**Fresh-machine test.** The strongest check is a VM with no Xcode CLT and no
Homebrew. If §2.1 is right, the current script fails there twice (git clone,
then python3 at every service start) and the rewrite doesn't fail at all. Worth
doing once, because it's the difference between believing the CLT-stub finding
and knowing it.

---

## 9. Locked decisions

Recorded so they don't get relitigated mid-rewrite.

| Question | Decision |
|---|---|
| MQTT precheck language | **Node + z2m's `js-yaml`** (§5.4). Not bash/awk/nc. |
| Linux support | **No.** macOS only; hard error on non-Darwin at the top of the installer (§5.1). |
| Service type | **LaunchDaemon**, `/Library/LaunchDaemons/`, requires `sudo` (§5.5). Not LaunchAgent. |
| Homebrew | **Not used.** The macOS base system is sufficient (§2.2). |
| Node acquisition | **Official tarball + SHA-256 verification** (§5.1). Not nodeenv, not brew. |
| pnpm acquisition | **corepack**, driven by z2m's `packageManager` field (§5.2). |
| Upgrade path | **Out of scope.** Install into an empty directory only. |
| File location / `pzg-` prefix | **Left as-is.** Both trivially changed later; not worth spending decisions on now. |

One consequence of dropping the upgrade path is worth keeping visible: since
reinstalling is the only way forward, `zigbee2mqtt/data/` — config, pairings,
and the device database — is the one directory a user genuinely cannot lose.
The generated `UNINSTALL.md` (phase 8) must say so before it says anything
about deleting the install directory.
