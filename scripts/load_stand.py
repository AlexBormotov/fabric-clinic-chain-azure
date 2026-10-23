"""Load the local source stand: billing into SQL Server, FHIR, lab and ADT files into Azurite."""

import argparse
from pathlib import Path

from clinic_chain import stand
from clinic_chain.sources import contracts

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fhir", type=Path, default=ROOT / "data" / "raw" / "fhir")
    parser.add_argument("--sources", type=Path, default=ROOT / "data" / "sources")
    args = parser.parse_args()
    contracts_dir = ROOT / "docs" / "contracts"
    stand.load_billing(args.sources, contracts_dir / "billing.sql", contracts.load(contracts_dir))
    print(f"sql: {stand.DATABASE}")
    stand.upload(stand.blob_files(args.sources, args.fhir))
    print("blob: fhir, lab, adt")


if __name__ == "__main__":
    main()
