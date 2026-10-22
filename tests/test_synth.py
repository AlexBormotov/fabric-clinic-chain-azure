"""U02 Synthea population. Tests marked `slow` run Synthea (`make test-slow`, CI job `synth`)."""

import hashlib
import json
from datetime import date, timedelta
from pathlib import Path

import pytest
import synth

CFG = synth.load_config()
END = date.fromisoformat(CFG["reference_date"])
# Analytical window: the last `years_of_history` years up to and including the reference date.
START = END.replace(year=END.year - CFG["years_of_history"]) + timedelta(days=1)
WINDOW_START, WINDOW_END = START.isoformat(), END.isoformat()


def test_config_sizes_and_seeds():
    clinics = CFG["clinics"]
    assert [c["patients"] for c in clinics] == [300, 400, 500]
    assert len({c["seed"] for c in clinics}) == len(clinics)
    assert len({c["id"] for c in clinics}) == len(clinics)


def test_config_pins_jar():
    pinned = CFG["synthea"]
    assert pinned["version"] in pinned["url"]
    assert len(pinned["sha256"]) == 64
    int(pinned["sha256"], 16)


def fhir_hashes(clinic_dir: Path) -> dict[str, str]:
    """Hash every exported file except `metadata/`, which holds the run timestamp."""
    return {
        str(p.relative_to(clinic_dir)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(clinic_dir.rglob("*.json"))
        if p.relative_to(clinic_dir).parts[0] != "metadata"
    }


def clinic_stats(clinic_dir: Path) -> tuple[int, list[str]]:
    patients, starts = 0, []
    for f in (clinic_dir / "fhir").glob("*.json"):
        for entry in json.loads(f.read_bytes())["entry"]:
            resource = entry["resource"]
            if resource["resourceType"] == "Patient":
                patients += 1
            elif resource["resourceType"] == "Encounter":
                starts.append(resource["period"]["start"][:10])
    return patients, starts


@pytest.fixture(scope="module")
def population(tmp_path_factory):
    out = tmp_path_factory.mktemp("fhir")
    jar = synth.ensure_jar(CFG)
    return {c["id"]: synth.run_clinic(jar, CFG, c, out) for c in CFG["clinics"]}


@pytest.fixture(scope="module")
def stats(population):
    return {clinic: clinic_stats(path) for clinic, path in population.items()}


@pytest.mark.slow
def test_patient_counts(stats):
    expected = {c["id"]: c["patients"] for c in CFG["clinics"]}
    assert {clinic: patients for clinic, (patients, _) in stats.items()} == expected


@pytest.mark.slow
def test_no_encounter_after_end_date(stats):
    for clinic, (_, starts) in stats.items():
        assert max(starts) <= WINDOW_END, clinic


@pytest.mark.slow
def test_each_clinic_has_encounters_in_window(stats):
    # Older linked history is kept on purpose; the window is applied downstream (PLAN-U02, 3a).
    for clinic, (_, starts) in stats.items():
        assert any(WINDOW_START <= s <= WINDOW_END for s in starts), clinic


@pytest.mark.slow
def test_rerun_is_identical(population, tmp_path):
    # One clinic re-run keeps the test under ~7 min; all clinics share the same code path.
    clinic = CFG["clinics"][0]
    rerun = synth.run_clinic(synth.ensure_jar(CFG), CFG, clinic, tmp_path)
    first = fhir_hashes(population[clinic["id"]])
    assert first
    assert fhir_hashes(rerun) == first
