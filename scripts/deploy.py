"""Deploy fabric/ to Test or Prod, or republish its Dataflows Gen2 there (U19).

    deploy.py deploy --environment Test        # GitHub Actions: service principal via OIDC
    deploy.py republish --environment Test     # owner, device code sign-in

The target workspace is FABRIC_WORKSPACE_ID (terraform output workspace_ids).
"""

import argparse
from pathlib import Path

from clinic_chain.deploy import ENVIRONMENTS, credential, deploy, republish_dataflows, required

REPOSITORY = Path(__file__).resolve().parents[1] / "fabric"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("action", choices=["deploy", "republish"])
    parser.add_argument("--environment", required=True, choices=ENVIRONMENTS)
    parser.add_argument("--user", action="store_true", help="sign in as a user (device code)")
    args = parser.parse_args()

    workspace_id = required("FABRIC_WORKSPACE_ID")
    print(f"{args.action} {REPOSITORY} -> {args.environment} workspace {workspace_id}")
    if args.action == "deploy":
        deploy(REPOSITORY, args.environment, workspace_id, credential(user=args.user))
    else:
        # The apply changes job rejects service principals, so republish always signs in a user.
        republish_dataflows(REPOSITORY, workspace_id, credential(user=True))


if __name__ == "__main__":
    main()
