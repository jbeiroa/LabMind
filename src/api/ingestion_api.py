import json
import os
from pathlib import Path
from threading import Lock
from typing import List

from fastapi import FastAPI, Header
from pydantic import BaseModel

app = FastAPI()


class Reading(BaseModel):
    device_id: str
    timestamp_ms: int
    value: float

RAW_DATA_DIR = Path(os.getenv("RAW_DATA_DIR", "data/raw"))
DEFAULT_RAW_DATA_FILE = Path(
    os.getenv("RAW_DATA_FILE", str(RAW_DATA_DIR / "readings.jsonl"))
)
_write_lock = Lock()


def _resolve_target_file(raw_data_file: str | None) -> Path:
    if raw_data_file and raw_data_file.strip():
        return Path(raw_data_file)
    return DEFAULT_RAW_DATA_FILE


def _persist_reading(reading: Reading, target_file: Path) -> None:
    target_file.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(reading.model_dump(), separators=(",", ":"))
    with _write_lock:
        with target_file.open("a", encoding="utf-8") as file_handle:
            file_handle.write(f"{serialized}\n")


def _persist_readings(readings: List[Reading], target_file: Path) -> None:
    target_file.parent.mkdir(parents=True, exist_ok=True)
    with _write_lock:
        with target_file.open("a", encoding="utf-8") as file_handle:
            for reading in readings:
                serialized = json.dumps(reading.model_dump(), separators=(",", ":"))
                file_handle.write(f"{serialized}\n")


@app.post("/reading")
def ingest_reading(reading: Reading, x_raw_data_file: str | None = Header(default=None)):
    target_file = _resolve_target_file(x_raw_data_file)
    _persist_reading(reading, target_file)
    return {"stored": True, "path": str(target_file)}


@app.post("/readings")
def ingest_readings(
    readings: List[Reading], x_raw_data_file: str | None = Header(default=None)
):
    target_file = _resolve_target_file(x_raw_data_file)
    _persist_readings(readings, target_file)
    return {"stored": len(readings), "path": str(target_file)}
