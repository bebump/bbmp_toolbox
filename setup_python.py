import re
import logging
import sys
from argparse import ArgumentParser, ArgumentTypeError

from bbmp_toolbox import BbmpHelpFormatter, terminal_wrap


_SCRIPT_NAME = "setup_python.py"
_VERSION = "1.0.0"
_HELP_MESSAGE = f"""This script can set up the current working directory for
Python development. It uses pyenv to ensure that a requested Python version
is installed, and uses it to create a .venv subdirectory. Using this virtual
environment, it updates pip to the latest version, installs the dependencies
in the requirements.txt file, if present, and creates a .gitignore file
appropriate for a basic Python project.

EXAMPLE:

    ```{_SCRIPT_NAME} 3.10```

        This will set up the .venv using version 3.10 of Python. It will use
        any 3.10.x version of Python that's already installed by pyenv. If no
        such version is installed yet, it will install the latest minor version
        of 3.10.

        If the version number is ommitted, {_SCRIPT_NAME} will default to 3.12.
"""


class BbmpLogFormatter(logging.Formatter):
    def __init__(self, format: str):
        super().__init__(format)

    def formatMessage(self, record):
        return terminal_wrap(super().formatMessage(record))


def setup_logger(verbose: bool = False) -> logging.Logger:
    """Set up and configure the module logger."""
    logger = logging.getLogger(_SCRIPT_NAME)
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.DEBUG if verbose else logging.INFO)

    formatter = BbmpLogFormatter(f"[%(name)s]: %(levelname)s:  %(message)s")
    handler.setFormatter(formatter)

    logger.addHandler(handler)
    return logger


def make_parser() -> ArgumentParser:
    parser = ArgumentParser(
        description=_HELP_MESSAGE,
        formatter_class=BbmpHelpFormatter,
    )

    parser.add_argument(
        "--version", action="version", version=f"{_SCRIPT_NAME} {_VERSION}"
    )

    parser.add_argument(
        "-v", "--verbose", help="makes the script verbose", action="store_true"
    )

    def validate_python_version(x: str) -> str:
        if not re.match(r"^\d+\.\d+(\.\d+)?$", x):
            raise ArgumentTypeError(
                f"Invalid python version format: {x}. Expected format: X.Y or X.Y.Z"
            )
        return x

    parser.add_argument(
        "python_version", nargs="?", default="3.12", type=validate_python_version
    )

    return parser


def main(raw_args: list[str] = None) -> None:
    parser = make_parser()
    args = parser.parse_args(raw_args)

    import shutil

    logger = setup_logger(args.verbose)

    current_interpreter = sys.executable

    if shutil.which("pyemv") is None:
        logger.warning(
            f"""pyenv doesn't seem to be installed. Attempting to use the
interpreter \"{current_interpreter}\" to set up the local environment. Note,
that if this is managed by brew, it can disappear during any brew upgrade."""
        )
        exit(1)


if __name__ == "__main__":
    main()
