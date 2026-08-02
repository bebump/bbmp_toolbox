# `pzg-install-z2m` — design record and as-built notes

**Status: implemented and working as of 2026-08-01.**

The Zigbee2MQTT installer is now a single self-contained shell script with no
Python dependency, no git dependency, no pyziggy coupling, and a containment
story that has been measured rather than asserted.

This document is both the reasoning behind the design (§1–§6, §9) and the
record of what was actually built and verified (§7, §8, §10). Sections 1–6
were written before the rewrite and describe findings that drove it; sections
7, 8 and 10 were written after, and describe what shipped.

Findings were verified against Zigbee2MQTT 2.6.1, Node 22.22.0, and macOS 15
(Darwin 24.6.0) unless marked otherwise.

**If you are here to do something rather than read, skip to §10.**

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
  containment one.** pnpm links rather than copies from its store into
  `node_modules`, and that linking cannot cross filesystems. Co-locating them
  guarantees same-volume.

  Measured afterwards: on this APFS volume pnpm does *not* use hardlinks —
  sampled `node_modules` files have a link count of 1 — it uses APFS
  copy-on-write clones, which is `package-import-method: auto`'s behaviour on
  macOS. The same-volume requirement holds either way, since `clonefile` also
  cannot cross volumes. But it means `du` double-counts: the store and
  `node_modules` report 171M + 177M as though they were independent, while
  their blocks are largely shared until something writes to them. Do not read
  the 622M total for a full installation as 622M of consumed disk.
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

Found while reading the old script. Independent of the migration, but the
rewrite should not carry them forward.

**All eight are fixed in the rewrite.** Line references below point at the old
version, recoverable with `git show 8e0262f:scripts/pzg-install-z2m`.

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

## 7. What was built

Phases 1–9 are done. Phase 10 was deliberately skipped — see below.

| Phase | Work | Status |
|---|---|---|
| 1 | Single-file skeleton, `set -euo pipefail`, Darwin + arch guard, `--help`, `--force`, existing-install guard | done |
| 2 | Contained Node: arch map, download, SHA-256 verify, unpack | done |
| 3 | `env.sh` + all six cache redirections | done |
| 4 | Contained pnpm via corepack, driven by `packageManager` | done |
| 5 | z2m release tarball, no git, `engines.node` gate | done |
| 6 | `pnpm install --store-dir` + explicit `pnpm run build` | done |
| 7 | Generated `pzg-run-z2m`, `pzg-check-mqtt`, service install/uninstall, local logs | done |
| 8 | Generated `UNINSTALL.md` with resolved paths | done |
| 9 | `bootstrap-z2m-installation.sh` down to one `curl` | done |
| 10 | `HOME` override hardening (§4.4) | **skipped — not needed**, see §8 |

Phase 10 was a belt-and-braces catch-all for cache locations the explicit
redirections might have missed. Measurement (§8) showed zero writes to any
`$HOME` cache during a full install, including the native-compile path that
was most likely to leak. Adding a `HOME` override would have bought nothing
and made the run environment harder to reason about.

`pzg-setup-venv` still exists and is untouched — it may serve the rest of the
repo. It is simply no longer on this script's critical path.

### What the installer produces

```
<install-dir>/
├── env.sh                    # PATH + all cache redirections; sourced by every script
├── node/                     # Node 22.22.0, checksum-verified
├── zigbee2mqtt/              # z2m 2.6.1, built, with data/ underneath
├── .pnpm-store/              # pnpm store (same volume as node_modules, so hardlinks work)
├── .cache/                   # corepack, npm, node-gyp
├── logs/                     # launchd stdout/stderr
├── pzg-check-mqtt            # Node + js-yaml; broker reachability gate
├── pzg-run-z2m               # sources env.sh, gates on the above, execs node
├── pzg-service-install       # LaunchDaemon, needs sudo
├── pzg-service-uninstall     # LaunchDaemon removal, needs sudo
└── UNINSTALL.md              # generated, paths resolved, contained vs leaking
```

### Deviations from the plan

Five things ended up different from §1–§6, all discovered during
implementation or testing:

1. **`pzg-run-z2m` ends in `exec node index.js`, not `pnpm start`.** They are
   equivalent commands, but `exec`-ing node directly means launchd's SIGTERM
   lands on Zigbee2MQTT itself. An intervening shell or pnpm process would
   swallow it, and z2m needs that signal to close the Zigbee database cleanly.
2. **The daemon plist is `chown root:wheel` / `chmod 644`.** launchd silently
   refuses to load a LaunchDaemon plist that is not owned by root.
3. **Every path in generated output is quoted.** The first version substituted
   `$PZG_ROOT` bare into `UNINSTALL.md`, so an install directory containing a
   space produced `rm -rf /Users/ati/Downloads/bery best` — two arguments,
   deleting the wrong things. Found by testing in a directory with a space in
   the name. `UNINSTALL.md` also gains a note that the quotes are load-bearing
   when the path actually contains whitespace.
4. **`env.sh` resolves its own location in both bash and zsh.**
   `${BASH_SOURCE[0]}` is empty under zsh — the default macOS interactive
   shell — which made `dirname` return `.` and silently resolved `PZG_ROOT` to
   the current directory. It now handles both and fails loudly in anything
   else.
5. **`UNINSTALL.md`'s native-compile section is evidence-based.** It used to
   say "the installer prints a message when it hits this, so if you do not
   remember seeing one, it did not happen." That is wrong: the message only
   prints on *failure*. A successful compile is silent, and one did in fact
   happen (§8). It now tells you to look for `.cache/node-gyp/` instead.

---

## 8. Verification record

### Static and unit checks

| What | Result |
|---|---|
| `bash -n` on the installer | passes |
| `bash -n` on all five generated scripts, extracted from their heredocs | passes |
| `node --check` on generated `pzg-check-mqtt` | passes |
| `pzg-check-mqtt` behaviour, 6 cases | 6/6 — see below |
| MQTT URL parsing, 8 forms | correct, incl. per-scheme default ports and credentials in the URL |
| `engines.node` gate, 5 cases | correct for z2m's `^20 \|\| ^22 \|\| ^24` form |
| Generated-command tokenisation with a spacey path | all four commands receive the path as **one** argument |
| `env.sh` sourced from a foreign cwd | correct `PZG_ROOT` under both bash and zsh |

The six precheck cases: missing config → proceed; `network_key: GENERATE` →
proceed; `js-yaml` unavailable → proceed; broker listening → proceed; broker
refusing → block; unroutable host → block after a 5s timeout. The three
"cannot tell" cases fail open by design, so an unconfigured install is never
prevented from starting.

The `engines.node` gate has one known limitation, commented in the script: it
compares the set of major versions found in the range string, so an open form
like `>=20` would false-fail every newer Node. z2m does not use that form.

### Live install

A full install was run into a directory whose name contains a space
(`~/Downloads/urkh` after an earlier `bery best` test), and inspected
afterwards:

| Check | Result |
|---|---|
| Node | v22.22.0, from the checksum-verified tarball |
| pnpm | 10.12.1 — exactly the `packageManager` pin, via corepack |
| Zigbee2MQTT | 2.6.1, `dist/` built at install time |
| `dist/.hash` | `unknown` |
| `pnpm store path` | `<install>/.pnpm-store/v10` |
| Sizes | node 189M, zigbee2mqtt 177M, store 171M, cache 86M |

`dist/.hash` containing `unknown` is §2.3 confirmed in practice: no git, so
z2m's `currentHash()` resolves to `"unknown"`, the hash-changed rebuild path
is never taken, and the build done at install time stands.

### Containment — measured

The install window was bracketed from file mtimes (`logs/` creation through
`UNINSTALL.md` write; the whole install landed inside one minute). Nothing was
written to any `$HOME` cache inside that window:

| Path | Entries written during install |
|---|---|
| `~/Library/pnpm` | 0 |
| `~/.npm` | 0 |
| `~/Library/Caches/node-gyp` | 0 |
| `~/.cache` | 0 |

Those directories do exist on this machine and are large, which looks alarming
until you check timestamps — they predate the install and belong to unrelated
Node work. `~/Library/Caches/node-gyp` holds headers for 20.14.0, 24.3.0,
24.7.0, 25.6.0 and 25.6.1, none of them ours.

**The strongest result is that the riskiest leak was actually triggered.**
`unix-dgram` had no usable prebuild and compiled from source, so node-gyp ran
— and its headers went to `<install>/.cache/node-gyp/22.22.0`, not to
`~/Library/Caches/node-gyp/22.22.0`. `@serialport/bindings-cpp` used its
shipped prebuilds and did not compile, as predicted in §2.6.

Method caveat: this is an after-the-fact "nothing written during the window"
test derived from mtimes, not a before/after snapshot. It is good evidence,
not proof.

### Not verified

Worth knowing before relying on any of it:

- **The service path has never been run.** No plist exists at
  `/Library/LaunchDaemons/io.zigbee2mqtt.plist`. `pzg-service-install`,
  `pzg-service-uninstall`, `launchctl bootstrap`/`bootout`, the root:wheel
  ownership requirement, and the precheck running under launchd are all
  unexercised.
- **No fresh-machine test.** This machine has full Xcode, so the §2.1
  CLT-stub finding — the thing that motivated dropping git and Python — is
  verified by inspection (identical hashes, 78 hardlinks) but not by watching
  the old script fail on a clean VM.
- **`--force` has not been exercised**, including its refusal to run when
  `zigbee2mqtt/data` exists.
- **Zigbee2MQTT has not been run against a real broker or coordinator** from
  this installation.

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
The generated `UNINSTALL.md` says so before it says anything about deleting
the install directory.

---

## 10. Operating it

### Installing

```sh
mkdir ~/zigbee2mqtt && cd ~/zigbee2mqtt
curl -fLO https://raw.githubusercontent.com/bebump/bbmp_toolbox/main/scripts/pzg-install-z2m
chmod +x pzg-install-z2m
./pzg-install-z2m
```

Or `scripts/bootstrap-z2m-installation.sh`, which is those three lines.

Then either `./pzg-run-z2m` to run it in the foreground, or
`sudo ./pzg-service-install` to install it as a boot-time daemon. Read §8's
"not verified" list before trusting the second one.

### Changing the Zigbee2MQTT version

Edit one line at the top of `scripts/pzg-install-z2m`:

```sh
ZIGBEE2MQTT_VERSION="2.6.1"
```

Then install into a **fresh directory** and copy `zigbee2mqtt/data/` across
from the old one. There is no in-place upgrade (§9), and `--force` refuses to
run while `zigbee2mqtt/data` exists precisely so this cannot happen by
accident.

If the new release needs a newer Node, the installer says so and stops, naming
both the required range and the pinned version — bump `USE_NODE_VERSION` to a
release that satisfies it. That check is a major-version comparison, so see
the limitation noted in §8 if it ever refuses a version you believe is fine.

### Uninstalling

Follow the generated `UNINSTALL.md` in the install directory — it has the
paths resolved and quoted for that specific installation. In short: `sudo
./pzg-service-uninstall`, then delete the directory. Back up
`zigbee2mqtt/data/` first.

### If something breaks

- **Service won't start.** `logs/stdout.log` and `logs/stderr.log` in the
  install directory. `sudo launchctl print system/io.zigbee2mqtt`.
- **"MQTT broker is not reachable"** — `pzg-check-mqtt` did its job; the
  broker in `zigbee2mqtt/data/configuration.yaml` isn't accepting connections.
  Run `./node/bin/node ./pzg-check-mqtt` by hand to see the address it tried.
- **A rebuild happens on every start.** `zigbee2mqtt/dist/.hash` is missing.
  Re-run `pnpm run build` in `zigbee2mqtt/` with `env.sh` sourced.
- **`pnpm: command not found` after sourcing `env.sh`.** Sourcing works from
  bash and zsh; anything else makes it exit with a message rather than
  silently misresolve.

### Reverting the whole rewrite

The pre-rewrite script is at `git show 8e0262f:scripts/pzg-install-z2m`.
