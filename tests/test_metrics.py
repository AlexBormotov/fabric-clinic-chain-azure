"""U09 metrics. The `stand` test compares the Gold metric views (T-SQL) with reference values
computed independently with pandas from generator output."""

import math
from pathlib import Path

import gold
import pytest
import yaml

from clinic_chain import metric_reference, stand
from clinic_chain.sources import contracts

ROOT = Path(__file__).resolve().parents[1]
WINDOW = yaml.safe_load((ROOT / "config" / "sources.yaml").read_text())["window"]
METRICS = [
    "occupancy_rate",
    "alos_days",
    "bed_turnover_per_year",
    "readmission_30d_rate",
    "ed_wait_median_minutes",
    "revenue_per_bed_per_year",
    "claim_denial_rate",
]
# Gold links readmissions via the MPI, the reference via ground truth; they must still agree.
RELATIVE = 1e-6


def test_glossary_defines_every_metric():
    glossary = (ROOT / "GLOSSARY.md").read_text()
    for metric in [*METRICS, "payer_mix"]:
        assert f"`{metric}`" in glossary, metric


@pytest.fixture(scope="module")
def reference():
    specs = contracts.load(ROOT / "docs" / "contracts")
    return metric_reference.compute(ROOT / "data" / "sources", specs, WINDOW)


@pytest.fixture(scope="module")
def cur():
    with stand.sql(gold.DATABASE) as conn:
        yield conn.cursor()


@pytest.mark.stand
def test_gold_metrics_match_the_reference(reference, cur):
    cur.execute(f"SELECT scope, beds, {', '.join(METRICS)} FROM gold.metric_summary")
    rows = {r[0]: r for r in cur.fetchall()}
    expected = {"ALL": reference["overall"], **reference["by_clinic"]}
    assert set(rows) == set(expected)
    for scope, values in expected.items():
        assert rows[scope][1] == values["beds"], scope
        for i, metric in enumerate(METRICS, start=2):
            actual = float(rows[scope][i])
            assert math.isclose(actual, values[metric], rel_tol=RELATIVE), (
                scope,
                metric,
                actual,
                values[metric],
            )


@pytest.mark.stand
def test_gold_payer_mix_matches_the_reference(reference, cur):
    cur.execute("SELECT scope, payer, claim_share FROM gold.metric_payer_mix")
    actual: dict[str, dict[str, float]] = {}
    for scope, payer, share in cur.fetchall():
        actual.setdefault(scope, {})[payer] = float(share)
    expected = {"ALL": reference["overall"], **reference["by_clinic"]}
    for scope, values in expected.items():
        assert actual[scope].keys() == values["payer_mix"].keys(), scope
        for payer, share in values["payer_mix"].items():
            assert math.isclose(actual[scope][payer], share, rel_tol=RELATIVE), (scope, payer)
