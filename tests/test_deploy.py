"""fabric/parameter.yml covers every placeholder in fabric/ for each environment (U19).

The resolver below applies the rules offline with fabric-cicd 1.4.0 semantics (read from its
source, FabricWorkspace._replace_parameters): key_value_replace by JSONPath first, then
find_replace, where a regex replaces only capture group 1. Dynamic values become fake IDs, after
checking that the item they name exists in fabric/ or is created by Terraform.
"""

import json
import re
import uuid
from pathlib import Path

import pytest
import yaml
from jsonpath_ng.ext import parse

from clinic_chain import deploy

ENVIRONMENTS, ITEM_TYPES = deploy.ENVIRONMENTS, deploy.ITEM_TYPES
PARAMETER_VARIABLES = deploy.PARAMETER_VARIABLES

FABRIC = Path(__file__).resolve().parents[1] / "fabric"
PARAMETERS = yaml.safe_load((FABRIC / "parameter.yml").read_text(encoding="utf-8"))

# Values that must never reach a workspace.
PLACEHOLDERS = (
    "00000000-0000-0000-0000-000000000000",
    "example.sharepoint.com",
    "example.kusto.fabric.microsoft.com",
    "alerts@example.com",
)

# Items infra/modules/fabric creates in every workspace (U18), outside fabric/. The eventhouse
# comes with a default KQL database of the same name.
TERRAFORM_ITEMS = {
    ("Lakehouse", "lh_bronze"),
    ("Lakehouse", "lh_silver"),
    ("Warehouse", "wh_gold"),
    ("Eventhouse", "eh_beds"),
    ("KQLDatabase", "eh_beds"),
}


def repository_items() -> dict[Path, tuple[str, str]]:
    """Item folder -> (type, name), from each .platform file."""
    items = {}
    for platform in FABRIC.glob("*/.platform"):
        meta = json.loads(platform.read_text(encoding="utf-8"))["metadata"]
        items[platform.parent] = (meta["type"], meta["displayName"])
    return items


ITEMS = repository_items()


def item_files():
    for folder, (item_type, name) in sorted(ITEMS.items()):
        for path in sorted(folder.rglob("*")):
            # Tests import the notebooks, which leaves git-ignored __pycache__ behind.
            if path.is_file() and path.name != ".platform" and "__pycache__" not in path.parts:
                yield path, item_type, name


def as_list(value) -> list[str] | None:
    return None if value is None else [value] if isinstance(value, str) else list(value)


def applies(rule: dict, item_type: str, name: str) -> bool:
    types, names = as_list(rule.get("item_type")), as_list(rule.get("item_name"))
    return (types is None or item_type in types) and (names is None or name in names)


def resolve_value(value: str, environment: str) -> str:
    """Stand-in for fabric-cicd's dynamic replacement, failing on names it could not resolve."""
    if value == "$workspace.$id":
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"workspace/{environment}"))
    if value.startswith("$items."):
        item_type, name, attribute = value.removeprefix("$items.").split(".")
        known = set(ITEMS.values()) | TERRAFORM_ITEMS
        assert (item_type, name) in known, f"{value}: no such item in fabric/ or Terraform"
        fake = uuid.uuid5(uuid.NAMESPACE_URL, f"{environment}/{item_type}/{name}")
        if attribute == "$queryserviceuri":  # fabric-cicd 1.4.0 has it for eventhouses only
            assert item_type == "Eventhouse", value
            return f"https://trd-{fake.hex[:12]}.z0.kusto.fabric.microsoft.com"
        assert attribute == "$id", value
        return str(fake)
    if value.startswith("$ENV:"):
        variable = value.removeprefix("$ENV:")
        assert variable in PARAMETER_VARIABLES, f"{value}: not in PARAMETER_VARIABLES"
        return f"https://{variable.lower()}.test" if "URL" in variable else str(uuid.uuid4())
    assert not value.startswith("$"), f"unsupported variable {value}"
    return value


def resolve(environment: str, parameters: dict) -> tuple[dict[Path, str], list[int]]:
    """Resolved text of every item file, and the hit count of each rule (key_value, then find)."""
    rules = parameters.get("key_value_replace", []) + parameters.get("find_replace", [])
    hits = [0] * len(rules)
    resolved = {}
    for path, item_type, name in item_files():
        text = path.read_text(encoding="utf-8")
        for index, rule in enumerate(rules):
            if not applies(rule, item_type, name) or environment not in rule["replace_value"]:
                continue
            value = resolve_value(rule["replace_value"][environment], environment)
            if "find_key" in rule:
                try:
                    data = json.loads(text)
                except json.JSONDecodeError:
                    continue
                matches = parse(rule["find_key"]).find(data)
                for match in matches:
                    match.full_path.update(data, value)
                hits[index] += len(matches)
                text = json.dumps(data, indent=2)
            elif rule.get("is_regex") in ("true", "True"):
                text, count = re.subn(
                    rule["find_value"],
                    lambda m, v=value: (
                        m.group(0)[: m.start(1) - m.start(0)]
                        + v
                        + m.group(0)[m.end(1) - m.start(0) :]
                    ),
                    text,
                )
                hits[index] += count
            else:
                hits[index] += text.count(rule["find_value"])
                text = text.replace(rule["find_value"], value)
        resolved[path] = text
    return resolved, hits


def leftovers(resolved: dict[Path, str]) -> list[str]:
    return [
        f"{path.relative_to(FABRIC)}:{n}: {line.strip()[:100]}"
        for path, text in resolved.items()
        for n, line in enumerate(text.splitlines(), 1)
        if any(p in line for p in PLACEHOLDERS)
    ]


def test_fabric_has_placeholders_to_cover():
    """Guards the coverage test against passing on an empty or misread fabric/."""
    raw = {path: path.read_text(encoding="utf-8") for path, _, _ in item_files()}
    assert len(leftovers(raw)) >= 30


@pytest.mark.parametrize("environment", ENVIRONMENTS)
def test_every_placeholder_is_resolved(environment):
    resolved, _ = resolve(environment, PARAMETERS)
    assert leftovers(resolved) == []


@pytest.mark.parametrize("environment", ENVIRONMENTS)
def test_every_rule_matches_something(environment):
    """No dead rule, except one whose target items are not in fabric/ yet (U10 model)."""
    rules = PARAMETERS["key_value_replace"] + PARAMETERS["find_replace"]
    _, hits = resolve(environment, PARAMETERS)
    names = {name for _, name in ITEMS.values()}
    dead = [
        rule.get("find_key") or rule["find_value"]
        for rule, count in zip(rules, hits, strict=True)
        if count == 0 and set(as_list(rule.get("item_name")) or names) & names
    ]
    assert dead == []


def test_every_rule_names_each_environment_and_nothing_else():
    for rule in PARAMETERS["key_value_replace"] + PARAMETERS["find_replace"]:
        assert set(rule["replace_value"]) == set(ENVIRONMENTS), rule


def test_rule_filters_name_deployed_item_types():
    for rule in PARAMETERS["key_value_replace"] + PARAMETERS["find_replace"]:
        assert set(as_list(rule["item_type"])) <= set(ITEM_TYPES), rule


def test_orphan_cleanup_cannot_delete_terraform_items():
    """Repository types are in scope; Terraform-only types are not; every Terraform name is
    excluded from the cleanup (the eventhouse's default KQL database shares a scoped type)."""
    assert {item_type for item_type, _ in ITEMS.values()} <= set(ITEM_TYPES)
    assert not {"Lakehouse", "Warehouse", "Eventhouse"} & set(ITEM_TYPES)
    assert all(re.search(deploy.TERRAFORM_ITEMS, name) for _, name in TERRAFORM_ITEMS)
    assert not any(re.search(deploy.TERRAFORM_ITEMS, name) for _, name in ITEMS.values())


@pytest.mark.parametrize("environment", ENVIRONMENTS)
def test_fabric_cicd_accepts_the_parameter_file(environment, monkeypatch):
    import fabric_cicd.constants as constants
    from fabric_cicd._parameter._utils import validate_parameter_file

    for variable in PARAMETER_VARIABLES:
        monkeypatch.setenv(variable, "x")
    monkeypatch.setattr(constants, "FEATURE_FLAG", {"enable_environment_variable_replacement"})
    assert validate_parameter_file(
        repository_directory=str(FABRIC),
        item_type_in_scope=list(ITEM_TYPES),
        environment=environment,
    )


def test_deploy_workflow_is_manual_and_uses_no_secret():
    path = FABRIC.parent / ".github" / "workflows" / "deploy.yml"
    text = path.read_text(encoding="utf-8")
    workflow = yaml.safe_load(text)
    triggers = workflow.get("on", workflow.get(True))  # PyYAML reads the key `on` as True
    assert set(triggers) == {"workflow_dispatch"}
    assert "secrets." not in text
    assert workflow["permissions"] == {"contents": "read"}
    environments = {job["environment"] for job in workflow["jobs"].values()}
    assert environments == set(ENVIRONMENTS)
