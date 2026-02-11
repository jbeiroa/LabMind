import os
from typing import List

import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI()

INGESTION_API_URL = os.getenv("INGESTION_API_URL", "http://host.docker.internal:8002/reading")
REQUEST_TIMEOUT_S = float(os.getenv("BRIDGE_REQUEST_TIMEOUT_S", "3"))


class Reading(BaseModel):
    device_id: str
    timestamp_ms: int
    value: float


@app.post("/reading")
def forward_reading(reading: Reading):
    try:
        response = requests.post(
            INGESTION_API_URL,
            json=reading.model_dump(),
            timeout=REQUEST_TIMEOUT_S,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"Forwarding failed: {exc}") from exc

    return {"status": "forwarded", "upstream_status": response.status_code}


@app.post("/readings")
def forward_readings(readings: List[Reading]):
    if not readings:
        return {"status": "forwarded", "upstream_status": 200, "count": 0}

    batch_url = INGESTION_API_URL.replace("/reading", "/readings")
    try:
        response = requests.post(
            batch_url,
            json=[reading.model_dump() for reading in readings],
            timeout=REQUEST_TIMEOUT_S,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"Batch forwarding failed: {exc}") from exc

    return {
        "status": "forwarded",
        "upstream_status": response.status_code,
        "count": len(readings),
    }
