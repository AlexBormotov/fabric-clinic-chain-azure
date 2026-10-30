"""Structural TMDL reader: tables, columns, measures, partitions, relationships, roles and shared
expressions of a semantic model `definition/` folder. Enough to check the model in tests; it is not
a general TMDL parser (no backtick expressions, cultures, hierarchies or calculation groups).

Syntax: Microsoft Learn, "Tabular Model Definition Language (TMDL)", read 2026-10-28."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

# Keywords that declare an object; any other line is a property (`key: value` or a bare flag).
OBJECTS = {
    "database",
    "model",
    "table",
    "column",
    "measure",
    "partition",
    "source",
    "relationship",
    "role",
    "tablePermission",
    "expression",
    "annotation",
    "ref",
}


class TmdlError(ValueError):
    pass


@dataclass
class Node:
    keyword: str
    name: str
    value: str
    depth: int
    children: list[Node] = field(default_factory=list)

    def props(self) -> dict[str, str]:
        return {c.keyword: c.value for c in self.children if c.keyword not in OBJECTS}

    def objects(self, keyword: str) -> list[Node]:
        return [c for c in self.children if c.keyword == keyword]


@dataclass
class Table:
    name: str
    columns: dict[str, dict[str, str]] = field(default_factory=dict)
    measures: dict[str, str] = field(default_factory=dict)
    partitions: list[dict[str, str]] = field(default_factory=list)


@dataclass
class Role:
    name: str
    permission: str
    filters: dict[str, str] = field(default_factory=dict)  # table -> DAX row filter


@dataclass
class Model:
    tables: dict[str, Table] = field(default_factory=dict)
    relationships: list[dict[str, str]] = field(default_factory=list)
    roles: dict[str, Role] = field(default_factory=dict)
    expressions: dict[str, str] = field(default_factory=dict)


def _name(rest: str) -> tuple[str, str]:
    """Split `'quoted name' = value` or `bare = value` into the name and what follows it."""
    if rest.startswith("'"):
        i = 1
        while i < len(rest):
            if rest[i] == "'":
                if rest[i + 1 : i + 2] == "'":
                    i += 2
                    continue
                return rest[1:i].replace("''", "'"), rest[i + 1 :].strip()
            i += 1
        raise TmdlError(f"unclosed quote: {rest!r}")
    name, _, tail = rest.partition("=")
    if tail or rest.rstrip().endswith("="):
        return name.strip(), "=" + tail
    return rest.strip(), ""


def _node(text: str, depth: int) -> Node:
    keyword, _, rest = text.partition(" ")
    if keyword in OBJECTS:
        name, tail = _name(rest.strip())
        if tail and not tail.startswith("="):
            raise TmdlError(f"expected '=' after the name: {text!r}")
        return Node(keyword, name, tail[1:].strip(), depth)
    key, colon, value = text.partition(":")
    if not colon:
        return Node(text.strip(), "", "true", depth)  # boolean flag such as `isHidden`
    return Node(key.strip(), "", value.strip(), depth)


def _lines(text: str) -> list[tuple[int, str]]:
    items = []
    for number, raw in enumerate(text.splitlines(), start=1):
        if not raw.strip() or raw.lstrip().startswith("///"):
            continue
        body = raw.lstrip("\t")
        if "```" in body:
            raise TmdlError(f"line {number}: backtick expressions are not supported")
        items.append((len(raw) - len(body), body.rstrip()))
    return items


def _build(items: list[tuple[int, str]], i: int, depth: int) -> tuple[list[Node], int]:
    nodes = []
    while i < len(items):
        d, text = items[i]
        if d < depth:
            break
        if d > depth or text.startswith(" "):
            raise TmdlError(f"unexpected indentation (TMDL indents with tabs): {text!r}")
        node = _node(text, d)
        i += 1
        if node.keyword in OBJECTS and text.endswith("="):
            # Multi-line expression: every following line two or more levels deeper.
            lines = []
            while i < len(items) and items[i][0] >= d + 2:
                lines.append("\t" * (items[i][0] - d - 2) + items[i][1])
                i += 1
            if not lines:
                raise TmdlError(f"empty expression: {text!r}")
            node.value = "\n".join(lines)
        node.children, i = _build(items, i, d + 1)
        nodes.append(node)
    return nodes, i


def parse(text: str) -> list[Node]:
    nodes, _ = _build(_lines(text), 0, 0)
    return nodes


def load(definition: Path) -> Model:
    model = Model()
    for path in sorted(definition.rglob("*.tmdl")):
        try:
            nodes = parse(path.read_text(encoding="utf-8"))
        except TmdlError as e:
            raise TmdlError(f"{path.name}: {e}") from e
        for node in nodes:
            if node.keyword == "table":
                table = model.tables.setdefault(node.name, Table(node.name))
                for c in node.objects("column"):
                    table.columns[c.name] = c.props()
                for m in node.objects("measure"):
                    table.measures[m.name] = m.value
                for p in node.objects("partition"):
                    props = {"type": p.value, **p.props()}
                    for s in p.objects("source"):
                        props.update(s.props())
                    table.partitions.append(props)
            elif node.keyword == "relationship":
                model.relationships.append({"name": node.name, **node.props()})
            elif node.keyword == "role":
                filters = {t.name: t.value for t in node.objects("tablePermission")}
                permission = node.props().get("modelPermission", "")
                model.roles[node.name] = Role(node.name, permission, filters)
            elif node.keyword == "expression":
                model.expressions[node.name] = node.value
            elif node.keyword not in {"database", "model", "ref", "annotation"}:
                raise TmdlError(f"{path.name}: unexpected top-level {node.keyword!r}")
    return model
