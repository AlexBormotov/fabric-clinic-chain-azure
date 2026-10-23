"""Derive the source systems (billing, lab, ADT, SharePoint) and ground truth from Synthea FHIR."""

import argparse
from pathlib import Path

import yaml

from clinic_chain.sources.derive import derive

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fhir", type=Path, default=ROOT / "data" / "raw" / "fhir")
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "sources")
    parser.add_argument("--config", type=Path, default=ROOT / "config" / "sources.yaml")
    args = parser.parse_args()
    derive(args.fhir, args.out, yaml.safe_load(args.config.read_text()))
    print(f"sources: {args.out}")


if __name__ == "__main__":
    main()
