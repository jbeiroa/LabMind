import json
import os
from pathlib import Path
from threading import Lock
from typing import List

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()


class Reading(BaseModel):
    device_id: str
    timestamp_ms: int
    value: float

RAW_DATA_DIR = Path(os.getenv("RAW_DATA_DIR", "data/raw"))
RAW_DATA_FILE = RAW_DATA_DIR / "readings.jsonl"
_write_lock = Lock()


def _persist_reading(reading: Reading) -> None:
    RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(reading.model_dump(), separators=(",", ":"))
    with _write_lock:
        with RAW_DATA_FILE.open("a", encoding="utf-8") as file_handle:
            file_handle.write(f"{serialized}\n")


def _persist_readings(readings: List[Reading]) -> None:
    RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
    with _write_lock:
        with RAW_DATA_FILE.open("a", encoding="utf-8") as file_handle:
            for reading in readings:
                serialized = json.dumps(reading.model_dump(), separators=(",", ":"))
                file_handle.write(f"{serialized}\n")


@app.post("/reading")
def ingest_reading(reading: Reading):
    _persist_reading(reading)
    return {"stored": True, "path": str(RAW_DATA_FILE)}


@app.post("/readings")
def ingest_readings(readings: List[Reading]):
    _persist_readings(readings)
    return {"stored": len(readings), "path": str(RAW_DATA_FILE)}
