import importlib
import json

from fastapi.testclient import TestClient


def test_ingest_reading_persists_jsonl(tmp_path, monkeypatch):
    monkeypatch.setenv("RAW_DATA_DIR", str(tmp_path))
    module = importlib.import_module("api.ingestion_api")
    module = importlib.reload(module)
    client = TestClient(module.app)

    payload = {
        "device_id": "HC-SR04",
        "timestamp_ms": 1234,
        "value": 12.5,
    }
    response = client.post("/reading", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["stored"] is True

    raw_file = tmp_path / "readings.jsonl"
    assert raw_file.exists()
    rows = raw_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(rows) == 1
    assert json.loads(rows[0]) == payload


def test_ingest_reading_custom_file_path_header(tmp_path, monkeypatch):
    monkeypatch.setenv("RAW_DATA_DIR", str(tmp_path))
    module = importlib.import_module("api.ingestion_api")
    module = importlib.reload(module)
    client = TestClient(module.app)

    custom_file = tmp_path / "custom" / "run-001.jsonl"
    payload = {
        "device_id": "HC-SR04",
        "timestamp_ms": 1234,
        "value": 12.5,
    }
    response = client.post(
        "/reading", json=payload, headers={"X-Raw-Data-File": str(custom_file)}
    )

    assert response.status_code == 200
    assert response.json()["path"] == str(custom_file)
    rows = custom_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(rows) == 1
    assert json.loads(rows[0]) == payload


def test_ingest_readings_batch_persists_jsonl(tmp_path, monkeypatch):
    monkeypatch.setenv("RAW_DATA_DIR", str(tmp_path))
    module = importlib.import_module("api.ingestion_api")
    module = importlib.reload(module)
    client = TestClient(module.app)

    payload = [
        {"device_id": "d1", "timestamp_ms": 1, "value": 1.0},
        {"device_id": "d1", "timestamp_ms": 2, "value": 2.0},
    ]
    response = client.post("/readings", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["stored"] == 2

    raw_file = tmp_path / "readings.jsonl"
    rows = raw_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(rows) == 2
    assert [json.loads(row) for row in rows] == payload


def test_ingest_readings_batch_custom_file_path_header(tmp_path, monkeypatch):
    monkeypatch.setenv("RAW_DATA_DIR", str(tmp_path))
    module = importlib.import_module("api.ingestion_api")
    module = importlib.reload(module)
    client = TestClient(module.app)

    custom_file = tmp_path / "custom" / "batch-run.jsonl"
    payload = [
        {"device_id": "d1", "timestamp_ms": 1, "value": 1.0},
        {"device_id": "d1", "timestamp_ms": 2, "value": 2.0},
    ]
    response = client.post(
        "/readings", json=payload, headers={"X-Raw-Data-File": str(custom_file)}
    )

    assert response.status_code == 200
    assert response.json()["path"] == str(custom_file)
    rows = custom_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(rows) == 2
    assert [json.loads(row) for row in rows] == payload
