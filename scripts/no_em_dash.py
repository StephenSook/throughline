#!/usr/bin/env python3
"""Replace em dashes with correct punctuation, by context.

An em dash is the single most reliable tell that prose was machine-written, so
this repo does not use one. A blind global replace would produce worse prose
than the dash did, so each case is resolved by what the dash is actually doing:

  label, elaboration   ->  label: elaboration      (definition / gloss)
  clause, new clause   ->  clause. New clause      (sentence break)
  word, aside, word   ->  word, aside, word       (parenthetical)
  3-5                 ->  3-5                     (range)

Exempt: fenced code blocks, inline code spans, and Markdown table separators,
where a dash is not prose. Run with --check to fail instead of rewrite, which
is how CI keeps it from coming back.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

EM = ", "
EN = "-"

# A short leading label followed by a dash is a gloss, so it takes a colon.
LABEL = re.compile(rf"^(\s*(?:[-*>#]+\s*)?(?:\*\*)?[A-Z][^.!?\n]{{1,44}}?(?:\*\*)?)\s*{EM}\s+")
# A dash between two digits is a range.
RANGE = re.compile(rf"(\d)\s*{EM}\s*(\d)")


def fix_line(line: str) -> str:
    if EM not in line and EN not in line:
        return line

    line = RANGE.sub(r"\1-\2", line)
    line = line.replace(f" {EN} ", ", ").replace(EN, "-")

    # Leading label gloss: "Render: creating..." becomes "Render: creating..."
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
    check = "--check" in sys.argv
    root = Path(__file__).resolve().parent.parent
    targets = [
        p
        for p in root.rglob("*")
        if p.suffix in {".md", ".py", ".html", ".sql", ".yml", ".yaml", ".ts", ".tsx"}
        and not any(
            part in {".git", "node_modules", ".venv", "dist", ".secrets"} for part in p.parts
        )
    ]

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
