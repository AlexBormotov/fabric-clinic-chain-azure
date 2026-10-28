"""Deploy fabric/ to a Fabric workspace with fabric-cicd, and republish Dataflows Gen2 (U19).

Identity:
- in GitHub Actions, the deployer service principal through GitHub OIDC (a federated credential,
  no client secret): each Entra token is exchanged for a fresh GitHub ID token;
- `--user`, the owner through the device code flow. Republishing a dataflow needs it: the Fabric
  "apply changes" job does not accept service principals (Microsoft Learn, read 2026-10-28).
"""

import json
import os
import shutil
import time
import urllib.parse
import urllib.request
from email.message import Message
from pathlib import Path

from azure.core.credentials import TokenCredential
from azure.identity import ClientAssertionCredential, DeviceCodeCredential

ENVIRONMENTS = ("Test", "Prod")

# Items from fabric/. Lakehouses, the warehouse and the eventhouse belong to Terraform; keeping
# their types out of scope keeps unpublish_all_orphan_items from deleting them. KQL databases are in
# scope (U12 kqldb_beds); fabric-cicd unpublishes them only with a feature flag never set here, and
# TERRAFORM_ITEMS also guards the eventhouse's default database, named eh_beds like its parent.
ITEM_TYPES = ("Notebook", "DataPipeline", "Dataflow", "SemanticModel", "Report", "KQLDatabase")
TERRAFORM_ITEMS = r"^(lh_bronze|lh_silver|wh_gold|eh_beds)$"

# Values parameter.yml takes from the environment ($ENV:<name>), set per GitHub environment.
PARAMETER_VARIABLES = (
    "FABRIC_SQL_CONNECTION_ID",
    "FABRIC_BLOB_CONNECTION_ID",
    "SHAREPOINT_SITE_URL",
)

FABRIC_API = "https://api.fabric.microsoft.com/v1"
FABRIC_SCOPE = "https://api.fabric.microsoft.com/.default"
GITHUB_AUDIENCE = "api://AzureADTokenExchange"


def required(name: str) -> str:
    """An environment variable that must be set and non-empty (compose passes unset ones as "")."""
    value = os.environ.get(name, "")
    if not value:
        raise RuntimeError(f"environment variable {name} is not set")
    return value


def github_oidc_credential(tenant_id: str, client_id: str) -> TokenCredential:
    """Service principal credential backed by the GitHub Actions OIDC token (id-token: write)."""
    audience = urllib.parse.quote(GITHUB_AUDIENCE, safe="")
    url = required("ACTIONS_ID_TOKEN_REQUEST_URL") + f"&audience={audience}"
    request_token = required("ACTIONS_ID_TOKEN_REQUEST_TOKEN")

    def assertion() -> str:
        request = urllib.request.Request(url, headers={"Authorization": f"bearer {request_token}"})
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)["value"]

    return ClientAssertionCredential(tenant_id, client_id, assertion)


def credential(user: bool) -> TokenCredential:
    if user:
        return DeviceCodeCredential(tenant_id=os.environ.get("AZURE_TENANT_ID") or None)
    return github_oidc_credential(required("AZURE_TENANT_ID"), required("AZURE_CLIENT_ID"))


def deploy(repository: Path, environment: str, workspace_id: str, token: TokenCredential) -> None:
    """Publish every code item, then delete code items no longer in the repository."""
    from fabric_cicd import (
        FabricWorkspace,
        append_feature_flag,
        publish_all_items,
        unpublish_all_orphan_items,
    )

    if environment not in ENVIRONMENTS:
        raise ValueError(f"environment must be one of {ENVIRONMENTS}, got {environment!r}")
    missing = [name for name in PARAMETER_VARIABLES if not os.environ.get(name)]
    if missing:
        raise RuntimeError(f"parameter.yml needs these environment variables: {missing}")

    # fabric-cicd uploads every file in an item folder; tests leave bytecode in the notebooks.
    for cache in repository.rglob("__pycache__"):
        shutil.rmtree(cache)

    append_feature_flag("enable_environment_variable_replacement")
    workspace = FabricWorkspace(
        workspace_id=workspace_id,
        repository_directory=str(repository),
        item_type_in_scope=list(ITEM_TYPES),
        environment=environment,
        token_credential=token,
    )
    publish_all_items(workspace)
    unpublish_all_orphan_items(workspace, item_name_exclude_regex=TERRAFORM_ITEMS)


def _call(token: TokenCredential, method: str, url: str) -> tuple[int, Message, dict]:
    bearer = token.get_token(FABRIC_SCOPE).token
    request = urllib.request.Request(
        url,
        method=method,
        headers={"Authorization": f"Bearer {bearer}"},
        data=b"" if method == "POST" else None,
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        body = response.read()
        return response.status, response.headers, json.loads(body) if body else {}


def repository_dataflows(repository: Path) -> list[str]:
    return sorted(p.name.removesuffix(".Dataflow") for p in repository.glob("*.Dataflow"))


def republish_dataflows(repository: Path, workspace_id: str, token: TokenCredential) -> None:
    """Run the "apply changes" job for every repository dataflow and wait for each to finish."""
    names = set(repository_dataflows(repository))
    items, url = [], f"{FABRIC_API}/workspaces/{workspace_id}/items"
    while url:
        _, _, page = _call(token, "GET", url)
        items += page.get("value", [])
        url = page.get("continuationUri")
    # Listing with ?type=Dataflow is documented as unreliable, so filter here.
    targets = {i["displayName"]: i["id"] for i in items if i["type"] == "Dataflow"}
    absent = names - targets.keys()
    if absent:
        raise RuntimeError(f"dataflows not deployed in {workspace_id}: {sorted(absent)}")

    for name in sorted(names):
        start = f"{FABRIC_API}/workspaces/{workspace_id}/dataflows/{targets[name]}"
        _, headers, _ = _call(token, "POST", f"{start}/jobs/applyChanges/instances")
        job_url, wait = headers["Location"], int(headers.get("Retry-After", 10))
        status, job = "NotStarted", {}
        while status in ("NotStarted", "InProgress", "Accepted"):
            time.sleep(wait)
            _, _, job = _call(token, "GET", job_url)
            status = job.get("status", "Failed")
        print(f"{name}: apply changes {status}")
        if status != "Completed":
            raise RuntimeError(f"{name}: apply changes ended {status}: {job.get('failureReason')}")
