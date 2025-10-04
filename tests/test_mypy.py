# MIT No Attribution
# Copyright (c) 2025 Attila Szarvas

import os
import subprocess
import sys
import unittest
from pathlib import Path


def run_mypy(python_script_path: Path) -> bool:
    env = os.environ.copy()

    # mypy bug: Errors aren't shown in imports when the PYTHONPATH is set. This isn't just true
    # for excluded folders, but in general.
    # https://github.com/python/mypy/issues/16973
    if "PYTHONPATH" in env:
        del env["PYTHONPATH"]

    print(f"[{Path(__file__).name}]: Running mypy on {python_script_path} ...")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "mypy",
            "--check-untyped-defs",
            "--strict-equality",
            str(python_script_path),
        ],
        env=env,
    )

    return result.returncode == 0


# Interprets the provided path constituents relative to the location of this
# script, and returns an absolute Path to the resulting location.
#
# E.g. rel_to_py(".") returns an absolute path to the directory containing this
# script.
def rel_to_py(*paths) -> Path:
    return Path(
        os.path.realpath(
            os.path.join(os.path.realpath(os.path.dirname(__file__)), *paths)
        )
    )


class TestSourcesWithMypy(unittest.TestCase):
    def test_sources_with_mypy(self):
        self.assertTrue(run_mypy(rel_to_py("..", "src")))
