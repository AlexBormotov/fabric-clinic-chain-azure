"""Generate the synthetic FHIR population: one Synthea run per clinic."""

import argparse
import hashlib
import shutil
import subprocess
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "synthea.yaml"
CACHE = ROOT / "data" / "cache"
OUT = ROOT / "data" / "raw" / "fhir"


def load_config(path: Path = CONFIG) -> dict:
    return yaml.safe_load(path.read_text())


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_jar(cfg: dict, cache: Path = CACHE) -> Path:
    synthea = cfg["synthea"]
    jar = cache / f"synthea-{synthea['version']}.jar"
    if not jar.exists():
        cache.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(synthea["url"], jar)
    actual = sha256(jar)
    if actual != synthea["sha256"]:
        jar.unlink()
        raise RuntimeError(f"{jar.name}: sha256 {actual} does not match the pinned hash")
    return jar


def run_clinic(jar: Path, cfg: dict, clinic: dict, out_root: Path) -> Path:
    out = (out_root / clinic["id"]).resolve()
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    seed = str(clinic["seed"])
    cmd = [
        "java", "-jar", str(jar),
        "-s", seed,
        "-cs", seed,
        "-r", cfg["reference_date"].replace("-", ""),
        "-e", cfg["reference_date"].replace("-", ""),
        "-p", str(clinic["patients"]),
        f"--exporter.years_of_history={cfg['years_of_history']}",
        "--generate.only_alive_patients=true",
        "--generate.thread_pool_size=1",
        f"--exporter.baseDirectory={out}/",
        cfg["state"], clinic["city"],
    ]  # fmt: skip
    # Synthea writes logs relative to the working directory, so run it inside the output folder.
    subprocess.run(cmd, check=True, cwd=out, stdout=subprocess.DEVNULL)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()
    cfg = load_config()
    jar = ensure_jar(cfg)
    for clinic in cfg["clinics"]:
        print(f"{clinic['id']}: {run_clinic(jar, cfg, clinic, args.out)}")


if __name__ == "__main__":
    main()
