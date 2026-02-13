from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, TypedDict


SourceMode = Literal["live", "file"]
InputFormat = Literal["jsonl", "csv", "parquet"]


CANONICAL_COLUMNS: tuple[str, ...] = (
    "timestamp_ms",
    "value",
    "experiment_id",
    "trial_id",
    "sensor_id",
    "unit",
    "source",
    "ingested_at",
)

REQUIRED_RAW_FIELDS: tuple[str, ...] = ("timestamp_ms", "value")


class IngestionMetadata(TypedDict):
    source_mode: SourceMode
    source_snapshot_path: str
    experiment_id: str
    trial_id: str
    sensor_id: str
    unit: str
    strict_schema: bool
    row_count: int
    dropped_row_count: int
    duration_s: float | None
    serial_port: str | None
    serial_baud: int | None
    ingest_url: str | None
    started_at_utc: str
    finished_at_utc: str


@dataclass(frozen=True)
class IngestionContract:
    experiment_id: str
    trial_id: str
    sensor_id: str
    unit: str = "cm"


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def build_parquet_path(
    output_dir: str | Path,
    experiment_id: str,
    trial_id: str,
    sensor_id: str,
    run_id: str,
    dt: datetime | None = None,
) -> Path:
    now = dt or datetime.now(UTC)
    date_str = now.date().isoformat()
    base = Path(output_dir)
    return (
        base
        / f"experiment_id={experiment_id}"
        / f"trial_id={trial_id}"
        / f"sensor_id={sensor_id}"
        / f"date={date_str}"
        / f"part-{run_id}.parquet"
    )
