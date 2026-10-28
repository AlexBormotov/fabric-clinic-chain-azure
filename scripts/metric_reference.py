"""Compute the eight metrics from generator output into docs/evidence/metric-reference.json."""

import json
from pathlib import Path

import yaml

from clinic_chain import metric_reference
from clinic_chain.sources import contracts

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    window = yaml.safe_load((ROOT / "config" / "sources.yaml").read_text())["window"]
    specs = contracts.load(ROOT / "docs" / "contracts")
    result = metric_reference.compute(ROOT / "data" / "sources", specs, window)
    out = ROOT / "docs" / "evidence" / "metric-reference.json"
    out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result["overall"], indent=2))


if __name__ == "__main__":
    main()
