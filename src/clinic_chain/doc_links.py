"""Relative links and images in Markdown that do not resolve to a file (U21).

External URLs, mail links and in-page anchors are skipped; nothing is fetched. Links inside fenced
code blocks and code spans are ignored.
"""

import re
from pathlib import Path
from urllib.parse import unquote

FENCE = re.compile(r"^(```|~~~).*?^\1", re.MULTILINE | re.DOTALL)
CODE_SPAN = re.compile(r"(`+)[^`].*?\1", re.DOTALL)
INLINE = re.compile(r"!?\[[^\]]*\]\(\s*(<[^>]*>|[^)\s]+)")
REFERENCE = re.compile(r"^ {0,3}\[[^\]]+\]:\s*(<[^>]*>|\S+)", re.MULTILINE)
HTML = re.compile(r"<(?:img|a)\b[^>]*?\b(?:src|href)\s*=\s*[\"']([^\"']+)[\"']", re.IGNORECASE)
EXTERNAL = re.compile(r"^([a-z][a-z0-9+.-]*:|//|#)", re.IGNORECASE)


def targets(text: str) -> list[str]:
    text = CODE_SPAN.sub("", FENCE.sub("", text))
    found = INLINE.findall(text) + REFERENCE.findall(text) + HTML.findall(text)
    return [t.strip("<>") for t in found]


def broken_links(files: list[Path]) -> list[str]:
    """`file: target` for every relative target that does not exist."""
    broken = []
    for md in files:
        for target in targets(md.read_text(encoding="utf-8")):
            if EXTERNAL.match(target):
                continue
            path = unquote(target.split("#", 1)[0].split("?", 1)[0])
            if not (md.parent / path).exists():
                broken.append(f"{md}: {target}")
    return broken


def markdown_files(root: Path) -> list[Path]:
    """README.md and every Markdown file under docs/."""
    return [root / "README.md", *sorted((root / "docs").rglob("*.md"))]
