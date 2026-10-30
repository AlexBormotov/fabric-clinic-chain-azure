"""U21: every relative link and image in README.md and docs/**/*.md resolves to a file."""

from pathlib import Path

from clinic_chain.doc_links import broken_links, markdown_files

ROOT = Path(__file__).resolve().parents[1]


def test_docs_links_resolve():
    assert broken_links(markdown_files(ROOT)) == []


def test_checker_finds_broken_links(tmp_path):
    (tmp_path / "ok.md").write_text("x")
    (tmp_path / "img.png").write_bytes(b"")
    doc = tmp_path / "doc.md"
    doc.write_text(
        "[ok](ok.md) [ok anchor](ok.md#part) ![ok](img.png) [web](https://example.com/x)\n"
        "[mail](mailto:a@example.com) [anchor](#section) [dir](./)\n"
        "[gone](missing.md) ![gone](missing.png)\n"
        '<img src="missing.svg" alt="">\n'
        "[ref]: missing-ref.md\n"
        "`[code](missing-in-span.md)`\n"
        "```\n[fenced](missing-in-fence.md)\n```\n"
    )
    assert broken_links([doc]) == [
        f"{doc}: missing.md",
        f"{doc}: missing.png",
        f"{doc}: missing-ref.md",
        f"{doc}: missing.svg",
    ]
