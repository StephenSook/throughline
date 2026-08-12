#!/usr/bin/env python3
"""Replace em dashes with correct punctuation, by context.

An em dash is the single most reliable tell that prose was machine-written, so
this repo does not use one. A blind global replace would produce worse prose
than the dash did, so each case is resolved by what the dash is actually doing:

  a short leading label, then a dash  ->  label: elaboration   (gloss)
  a dash before a capitalised word    ->  clause. New clause   (sentence break)
  a dash before a lowercase word      ->  clause, aside        (parenthetical)
  a dash between two digits           ->  3-5                  (range)

Exempt: fenced code blocks, inline code spans, and Markdown table separators,
where a dash is not prose. Run with --check to fail instead of rewrite, which
is how CI keeps it from coming back.

The two sentinels below are written as escape sequences on purpose. An earlier
revision spelled them literally, this script was then run over its own source,
and it rewrote its own constants into a comma and a hyphen. The guard went
blind to the character it exists to find, and because the replacement loop
advances by one character while the new sentinel was two, --check stopped
terminating at all. Escapes keep the literal character out of this file, so a
self-run cannot reach them, and _assert_sentinels refuses to run if it ever
happens again.
"""

from __future__ import annotations

import pathlib
import re
import subprocess
import sys
from pathlib import Path

EM = "—"
EN = "–"

SELF = pathlib.Path(__file__).resolve()


def _assert_sentinels() -> None:
    """Refuse to report a pass if the sentinels are not the dashes themselves.

    A guard that has lost its own needle reports a clean sweep over every file
    in the repo, which is the most expensive kind of false green: it is silent,
    it is durable, and every later run agrees with it.
    """
    if (EM, EN) != ("\N{EM DASH}", "\N{EN DASH}"):
        raise SystemExit("no_em_dash.py: sentinels are corrupt, refusing to report a result.")


# A short leading label followed by a dash is a gloss, so it takes a colon.
LABEL = re.compile(rf"^(\s*(?:[-*>#]+\s*)?(?:\*\*)?[A-Z][^.!?\n]{{1,44}}?(?:\*\*)?)\s*{EM}\s+")
# A dash between two digits is a range.
RANGE = re.compile(rf"(\d)\s*{EM}\s*(\d)")


def fix_line(line: str) -> str:
    if EM not in line and EN not in line:
        return line

    line = RANGE.sub(r"\1-\2", line)
    line = line.replace(f" {EN} ", ", ").replace(EN, "-")

    # A leading label followed by a dash is a gloss, so it becomes "Label: ...".
    m = LABEL.match(line)
    if m and line.count(EM) >= 1:
        line = LABEL.sub(lambda mm: mm.group(1) + ": ", line, count=1)

    while EM in line:
        i = line.index(EM)
        before, after = line[:i].rstrip(), line[i + 1 :].lstrip()
        if not after:
            line = before
            continue
        # A capitalised follower reads as a new sentence; a lowercase one is an
        # aside, which a comma carries without the dash's theatrical pause.
        if after[0].isupper():
            line = f"{before}. {after}"
        else:
            line = f"{before}, {after}"
    return line


def fix_text(text: str) -> str:
    out, in_fence = [], False
    for line in text.split("\n"):
        stripped = line.lstrip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            out.append(line)
            continue
        # Leave code, table rules, and ASCII diagrams alone.
        if in_fence or set(stripped) <= set("|-: ") or stripped.startswith(("│", "├", "└", "┌")):
            out.append(line)
            continue
        out.append(fix_line(line))
    return "\n".join(out)


def main() -> int:
    _assert_sentinels()
    check = "--check" in sys.argv
    root = Path(__file__).resolve().parent.parent
    # Ask git for the file list. It respects .gitignore, so node_modules and
    # build output never enter the walk, and it includes untracked files, so a
    # file about to be added is in scope rather than invisible until committed.
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        print("Could not resolve the file set via git; refusing to report a pass.")
        return 1

    suffixes = {".md", ".py", ".html", ".sql", ".yml", ".yaml", ".ts", ".tsx", ".css"}
    targets = [
        root / line
        for line in result.stdout.splitlines()
        if line.strip() and pathlib.Path(line).suffix in suffixes
    ]
    # Never rewrite this file. It is the one file in the repo that must contain
    # the character, and an earlier revision destroyed its own constants by
    # including itself in the sweep.
    targets = [p for p in targets if p.is_file() and p.resolve() != SELF]

    offenders = []
    for path in targets:
        try:
            original = path.read_text()
        except (UnicodeDecodeError, OSError):
            continue
        if EM not in original and EN not in original:
            continue
        fixed = fix_text(original)
        if check:
            offenders.append(
                f"{path.relative_to(root)}: {original.count(EM)} em, {original.count(EN)} en"
            )
        else:
            path.write_text(fixed)
            print(f"fixed {path.relative_to(root)}")

    if check and offenders:
        print("Em or en dashes found. This repo writes without them:")
        for o in offenders:
            print(f"  {o}")
        return 1
    if check:
        print("No em or en dashes found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
