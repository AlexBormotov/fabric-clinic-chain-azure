"""Local Spark 4.1 + Delta 4.2, standing in for Fabric Runtime 2.0, and loading Fabric notebooks."""

import importlib.util
from pathlib import Path
from types import ModuleType

from delta import configure_spark_with_delta_pip
from pyspark.sql import SparkSession

FABRIC = Path(__file__).resolve().parents[2] / "fabric"


def session() -> SparkSession:
    builder = (
        SparkSession.builder.master("local[2]")
        .appName("clinic-chain")
        .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension")
        .config(
            "spark.sql.catalog.spark_catalog", "org.apache.spark.sql.delta.catalog.DeltaCatalog"
        )
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.sql.shuffle.partitions", "4")
        .config("spark.ui.enabled", "false")
        .config("spark.ui.showConsoleProgress", "false")
        .config("spark.driver.memory", "2g")
        .config("spark.databricks.delta.snapshotPartitions", "2")
    )
    return configure_spark_with_delta_pip(builder).getOrCreate()


def notebook(name: str) -> ModuleType:
    """Import `fabric/<name>.Notebook/notebook-content.py`; its Fabric-only run cell stays idle."""
    path = FABRIC / f"{name}.Notebook" / "notebook-content.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
