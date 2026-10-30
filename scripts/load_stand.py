"""Load the local source stand: billing into SQL Server, FHIR, lab and ADT files into Azurite.

Also waits for the Event Hubs emulator (U11), which `make up` starts with the stand.

With --sql-server and --blob-endpoint (Terraform outputs) it loads the cloud sources instead, as the
owner signed in with `az login` in the infra container (docs/runbook-cloud.md)."""

import argparse
from pathlib import Path

from clinic_chain import stand
from clinic_chain.sources import contracts

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fhir", type=Path, default=ROOT / "data" / "raw" / "fhir")
    parser.add_argument("--sources", type=Path, default=ROOT / "data" / "sources")
    parser.add_argument("--sql-server", help="Azure SQL server FQDN; omit for the local stand")
    parser.add_argument("--blob-endpoint", help="Azure Blob endpoint; omit for the local stand")
    args = parser.parse_args()
    if bool(args.sql_server) != bool(args.blob_endpoint):
        parser.error("--sql-server and --blob-endpoint go together")
    contracts_dir = ROOT / "docs" / "contracts"
    stand.load_billing(
        args.sources, contracts_dir / "billing.sql", contracts.load(contracts_dir), args.sql_server
    )
    print(f"sql: {stand.DATABASE}")
    stand.upload(stand.blob_files(args.sources, args.fhir), args.blob_endpoint)
    print("blob: fhir, lab, adt")
    if args.sql_server:
        return
    stand.wait_eventhubs()
    print("eventhubs: healthy")


if __name__ == "__main__":
    main()
