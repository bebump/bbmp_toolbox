# MIT No Attribution
# Copyright (c) 2025 Attila Szarvas

import unittest

from bbmp_toolbox import terminal_wrap


class TestTerminalWrap(unittest.TestCase):
    def test_terminal_wrap(self):
        text = """Ordinary paragraphs can be freely wrapped along word boundaries.
The resulting lines can be no longer than the specified wrap width. Single newlines
do not create separate paragraphs, they are generally ignored. This means that you
can use them to wrap text inside source code to a comfortable width. The lines
will be joined into a single paragraph, and re-wrapped according to the requested
width.

While single newlines will be mostly ignored, two or more consecutive newlines will
be be preserved.

Sometimes, even single newlines are preserved. Spaces after newlines are treated as
indentation. When the indentation changes, the newline is preserved.
  This is some indented text. Indented text is also wrapped, and during wrapping the
  indentation is maintained.
Let's reduce the indentation to zero again! Observe, that even though these lines
are only separated by single newlines, they will still be present in the wrapped
output, where the indentation changes.

This wrapping algorithm has the concept of two kinds of indentation. One at the
beginning of the line, and a secondary, in the middle of the line. The middle one
can be activated by multiple consecutive whitespaces. The last consecutive
whitespace run inside the line will mark the secondary indentation. I know this
sounds complicated, so just look at the example:

  first indentation is 2 spaces  -  followed by however much this is.
                                    This is specifically meant to support
                                    writing command line argument help texts.                          

Wrapping is sometimes inhibited. Text quoted in one of the three possible ways:
"are guaranteed to not be wrapped". 'This is to ensure that if you are displaying a command',
`it will be displayed verbatim, without any inserted newlines`.

This way you can copy-paste these commands into a terminal.

Finally there is a third way to display text without any wrapping: that is to use
tripple backticks.
```
  such blocks will be printed exactly
    as they are with indentation, and guaranteed no wrapping inside lines
```
As you can see, the triple backticks will be omitted from the output.
"""

        expected_80 = """Ordinary paragraphs can be freely wrapped along word boundaries. The resulting
lines can be no longer than the specified wrap width. Single newlines do not
create separate paragraphs, they are generally ignored. This means that you can
use them to wrap text inside source code to a comfortable width. The lines will
be joined into a single paragraph, and re-wrapped according to the requested
width.

While single newlines will be mostly ignored, two or more consecutive newlines
will be be preserved.

Sometimes, even single newlines are preserved. Spaces after newlines are treated
as indentation. When the indentation changes, the newline is preserved.
  This is some indented text. Indented text is also wrapped, and during wrapping
  the indentation is maintained.
Let's reduce the indentation to zero again! Observe, that even though these
lines are only separated by single newlines, they will still be present in the
wrapped output, where the indentation changes.

This wrapping algorithm has the concept of two kinds of indentation. One at the
beginning of the line, and a secondary, in the middle of the line. The middle
one can be activated by multiple consecutive whitespaces. The last consecutive
whitespace run inside the line will mark the secondary indentation. I know this
sounds complicated, so just look at the example:

  first indentation is 2 spaces  -  followed by however much this is. This is
                                    specifically meant to support writing
                                    command line argument help texts.

Wrapping is sometimes inhibited. Text quoted in one of the three possible ways:
"are guaranteed to not be wrapped".
'This is to ensure that if you are displaying a command',
`it will be displayed verbatim, without any inserted newlines`.

This way you can copy-paste these commands into a terminal.

Finally there is a third way to display text without any wrapping: that is to
use tripple backticks.

  such blocks will be printed exactly
    as they are with indentation, and guaranteed no wrapping inside lines

As you can see, the triple backticks will be omitted from the output."""

        self.assertEqual(expected_80, terminal_wrap(text, 80))

        expected_60 = """Ordinary paragraphs can be freely wrapped along word
boundaries. The resulting lines can be no longer than the
specified wrap width. Single newlines do not create
separate paragraphs, they are generally ignored. This means
that you can use them to wrap text inside source code to a
comfortable width. The lines will be joined into a single
paragraph, and re-wrapped according to the requested width.

While single newlines will be mostly ignored, two or more
consecutive newlines will be be preserved.

Sometimes, even single newlines are preserved. Spaces after
newlines are treated as indentation. When the indentation
changes, the newline is preserved.
  This is some indented text. Indented text is also wrapped,
  and during wrapping the indentation is maintained.
Let's reduce the indentation to zero again! Observe, that
even though these lines are only separated by single
newlines, they will still be present in the wrapped output,
where the indentation changes.

This wrapping algorithm has the concept of two kinds of
indentation. One at the beginning of the line, and a
secondary, in the middle of the line. The middle one can be
activated by multiple consecutive whitespaces. The last
consecutive whitespace run inside the line will mark the
secondary indentation. I know this sounds complicated, so
just look at the example:

  first indentation is 2 spaces  -  followed by however much
                                    this is. This is
                                    specifically meant to
                                    support writing command
                                    line argument help
                                    texts.

Wrapping is sometimes inhibited. Text quoted in one of the
three possible ways: "are guaranteed to not be wrapped".
'This is to ensure that if you are displaying a command',
`it will be displayed verbatim, without any inserted newlines`.

This way you can copy-paste these commands into a terminal.

Finally there is a third way to display text without any
wrapping: that is to use tripple backticks.

  such blocks will be printed exactly
    as they are with indentation, and guaranteed no wrapping inside lines

As you can see, the triple backticks will be omitted from
the output."""

        self.assertEqual(expected_60, terminal_wrap(text, 60))

    def test_terminal_wrap_2(self):
        text = f"""This script can set up the current working directory for
Python development. It uses pyenv to ensure that a requested Python version
is installed, and uses it to create a .venv subdirectory. Using this virtual
environment, it updates pip to the latest version, installs the dependencies
in the requirements.txt file, if present, and creates a .gitignore file
appropriate for a basic Python project.

EXAMPLE:

    ```something 3.10```

        This will set up the .venv using version 3.10 of Python. It will use
        any 3.10.x version of Python that's already installed by pyenv. If no
        such version is installed yet, it will install the latest minor version
        of 3.10.

        If the version number is ommitted, something will default to 3.12.
"""

        expected_72 = """This script can set up the current working directory for Python
development. It uses pyenv to ensure that a requested Python version is
installed, and uses it to create a .venv subdirectory. Using this
virtual environment, it updates pip to the latest version, installs the
dependencies in the requirements.txt file, if present, and creates a
.gitignore file appropriate for a basic Python project.

EXAMPLE:


    something 3.10

        This will set up the .venv using version 3.10 of Python. It will
        use any 3.10.x version of Python that's already installed by
        pyenv. If no such version is installed yet, it will install the
        latest minor version of 3.10.

        If the version number is ommitted, something will default to
        3.12."""

        self.assertEqual(expected_72, terminal_wrap(text, 72))


if __name__ == "__main__":
    unittest.main()
