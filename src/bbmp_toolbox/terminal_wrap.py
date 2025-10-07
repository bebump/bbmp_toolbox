# MIT No Attribution
# Copyright (c) 2025 Attila Szarvas

# This module has no external dependencies. It requires Python 3.9 or greater.
# You can copy and paste this entire file into a standalone script.

import shutil
from argparse import HelpFormatter
from typing import Union


class LineIndentation80:
    """
    Starting at the given index, looks ahead at most 80 characters to determine
    the indentation that this, and the next line uses.
    """

    def __init__(self, text: str):
        self.for_line = 0
        self.for_next_line = 0

        for i in range(0, min(80, len(text))):
            char = text[i]

            if char == "\n" or not char.isspace():
                self.for_line = i
                self.for_next_line = self.for_line
                break

        self.for_next_line = self.for_line

        for i in range(self.for_line, min(80, len(text))):
            char = text[i]

            if char.isspace() and i > 0 and text[i - 1].isspace():
                self.for_next_line = i + 1


def get_terminal_columns(fallback: int = 80) -> int:
    return shutil.get_terminal_size(fallback=(fallback, 20)).columns


class BreakInhibitor:
    def __init__(self) -> None:
        self._quote_state = {'"': False, "'": False, "`": False}

    def update(self, text: str, index: int) -> None:
        char = text[index]

        if char in '"`' and char in self._quote_state:
            self._quote_state[char] = not self._quote_state[char]

        if (
            self._quote_state["'"]
            and not char.isalnum()
            and index > 0
            and text[index - 1] == "'"
        ):
            self._quote_state["'"] = not self._quote_state["'"]

        if (
            not self._quote_state["'"]
            and char == "'"
            and index < len(text) - 1
            and text[index - 1] == " "
        ):
            self._quote_state["'"] = not self._quote_state["'"]

    def active(self) -> bool:
        return any(self._quote_state.values())


class Paragraph:
    def __init__(
        self, indentation: LineIndentation80, text: str, verbatim: bool = False
    ):
        self.indentation = indentation
        self.text = text
        self.is_verbatim = verbatim


class Block:
    def __init__(self, text: str, is_verbatim: bool = False):
        self.text = text
        self.is_verbatim = is_verbatim
        self.indentation = 0


def process_multiline_verbatim_blocks(text: str) -> list[Block]:
    blocks: list[Block] = []

    for i, b in enumerate(text.split("```")):
        blocks.append(Block(b, i % 2 == 1))

    for i, block in enumerate(blocks):
        if block.is_verbatim and i > 0:
            previous_block = blocks[i - 1]
            previous_line = previous_block.text.rsplit("\n", 1)[-1]
            trailing_whitespaces = len(previous_line) - len(previous_line.rstrip(" "))
            block.indentation = trailing_whitespaces

    return blocks


def process_multiple_newlines(blocks_in: list[Block]) -> list[Block]:
    """
    Breaks up the text into kind-of-paragraphs, but these paragraphs can still
    contain newlines, however they can't contain contains sequences of newlines
    longer than one.
    """
    blocks_out: list[Block] = []

    for block in blocks_in:
        if block.is_verbatim:
            blocks_out.append(block)
            continue

        text = block.text
        start = 0

        i = 0
        while i < len(text):
            if text[i] == "\n":
                j = i + 1

                while j < len(text) and text[j] == "\n":
                    j += 1

                num_newlines = j - i

                if num_newlines > 1:
                    blocks_out.append(Block(text[start:i].rstrip()))
                    start = i + num_newlines

                    for k in range(1, num_newlines):
                        blocks_out.append(Block(""))

                i += num_newlines
            else:
                i += 1

        if start < len(text):
            blocks_out.append(Block(text[start:].rstrip()))

    return blocks_out


def wrap_paragraph(p: Paragraph, width: int) -> list[str]:
    inhibitor = BreakInhibitor()
    lines: list[str] = []

    start = 0
    last_break_opportunity = -1

    for i, char in enumerate(p.text):
        indent = p.indentation.for_line if not lines else p.indentation.for_next_line

        current_width = i - start + indent
        inhibitor.update(p.text, i)

        if current_width > width and last_break_opportunity != -1:
            lines.append(" " * indent + p.text[start:last_break_opportunity].strip())
            start = last_break_opportunity
            last_break_opportunity = -1

        if char.isspace() and not inhibitor.active():
            last_break_opportunity = i

    if start < len(p.text):
        indent = p.indentation.for_line if not lines else p.indentation.for_next_line
        lines.append(" " * indent + p.text[start:].strip())

    return lines


def terminal_wrap(text: str, width: Union[int, None] = None) -> str:
    if width is None:
        width = get_terminal_columns(fallback=1000000)

    blocks = process_multiline_verbatim_blocks(text)
    blocks = process_multiple_newlines(blocks)
    paragraphs: list[Paragraph] = []

    for block in blocks:
        if block.is_verbatim:
            indent = LineIndentation80(block.text)
            indent.for_line += block.indentation

            paragraphs.append(Paragraph(indent, block.text, True))
            continue

        maybe_paragraphs: list[Paragraph] = []

        for chunk in block.text.split("\n"):
            maybe_paragraphs.append(Paragraph(LineIndentation80(chunk), chunk.strip()))

        for i, p in enumerate(maybe_paragraphs):
            if i == 0 or (
                not paragraphs
                or paragraphs[-1].indentation.for_next_line != p.indentation.for_line
            ):
                paragraphs.append(p)
            else:
                paragraphs[-1].text += " " + p.text.strip()

    lines: list[str] = []
    previous_was_verbatim = False

    for i, p in enumerate(paragraphs):
        wrapped = (
            wrap_paragraph(p, width)
            if not p.is_verbatim
            else [" " * p.indentation.for_line + p.text]
        )

        if not wrapped:
            wrapped = [""]

        if i > 0 and paragraphs[i - 1].is_verbatim and not wrapped[0]:
            wrapped[0] = lines[-1] + wrapped[0]
            lines.pop()

        if p.is_verbatim and lines and not lines[-1]:
            wrapped[0] = lines[-1] + wrapped[0]
            lines.pop()

        lines.extend(wrapped)

    return "\n".join(lines)


class BbmpHelpFormatter(HelpFormatter):
    def _fill_text(self, text, width, indent):
        return terminal_wrap(indent + text, width)
