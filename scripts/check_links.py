"""Fail when a relative link or image in README.md or docs/**/*.md does not resolve (U21)."""

import sys
from pathlib import Path

from clinic_chain.doc_links import broken_links, markdown_files

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    broken = broken_links(markdown_files(ROOT))
    for line in broken:
        print(line)
    return 1 if broken else 0


if __name__ == "__main__":
    sys.exit(main())
