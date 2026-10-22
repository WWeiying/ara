"""Classify VCS UCLI source echoes without suppressing runtime diagnostics.

VCS V-2023.12-SP1 prints ``ucli% `` before a complete source command,
but NOT before each continuation line. Command results follow its final line.
Only exact, complete commands from caller-supplied, pin-verified Tcl sources
are echoes. Unknown prompts, truncated commands and mismatches fail closed.
This is classification only: callers must retain their existing failure regexes
on every non-echo line and must not infer semantic PASS from a clean log.

Requires Python's tkinter/Tcl (no display needed). ``info complete`` parses
braces, quotes, brackets, comments and continuations; source is NEVER evaluated.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Iterator, Mapping


@dataclass(frozen=True)
class LogLine:
    number: int
    text: str
    source_echo: bool = False
    source: str | None = None


def classify_ucli_lines(
    lines: Iterable[str], source_texts: Mapping[str, str],
) -> Iterator[LogLine]:
    """Stream numbered lines, marking only exact source-backed echo blocks.

    ``source_texts`` must come from trusted frozen inputs after hash validation,
    not from log text. Only CR/LF terminators are normalized, not whitespace.
    A mismatch preserves the entire candidate as runtime text. This deliberately
    under-classifies unfamiliar UCLI formats instead of masking real failures.
    """
    import tkinter

    tcl = tkinter.Tcl()
    commands: dict[str, list[tuple[str, tuple[str, ...]]]] = {}
    for name, source in source_texts.items():
        pending: list[str] = []
        for line in source.splitlines():
            if not pending and not line.strip():
                continue
            pending.append(line)
            if tcl.call('info', 'complete', '\n'.join(pending) + '\n'):
                block = tuple(pending)
                commands.setdefault(block[0], []).append((name, block))
                pending = []
        # Incomplete source tails are never admitted as echo commands.

    stream = iter(enumerate(lines, 1))
    for number, text in stream:
        first = text.rstrip('\r\n')
        candidates = commands.get(first[len('ucli% '):], []) if first.startswith('ucli% ') else []
        buffered = [(number, text)]
        offset = 1
        while candidates and not any(len(block) == offset for _, block in candidates):
            following = next(stream, None)
            if following is None:
                candidates = []
                break
            buffered.append(following)
            value = following[1].rstrip('\r\n')
            candidates = [(name, block) for name, block in candidates
                          if len(block) > offset and block[offset] == value]
            offset += 1
        matched = next((name for name, block in candidates if len(block) == offset), None)
        for line_number, value in buffered:
            yield LogLine(line_number, value, matched is not None, matched)


def iter_runtime_lines(lines: Iterable[str], source_texts: Mapping[str, str]) -> Iterator[str]:
    """Drop verified source echoes only; retain every other line verbatim."""
    for line in classify_ucli_lines(lines, source_texts):
        if not line.source_echo:
            yield line.text
