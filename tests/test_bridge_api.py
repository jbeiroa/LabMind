import importlib

from fastapi.testclient import TestClient


class FakeResponse:
    def __init__(self, status_code=200, should_raise=False):
        self.status_code = status_code
        self._should_raise = should_raise

    def raise_for_status(self):
        if self._should_raise:
            raise RuntimeError("upstream failed")


def test_bridge_forwards_payload(monkeypatch):
    module = importlib.import_module("api.bridge")
    module = importlib.reload(module)
    client = TestClient(module.app)

    captured = {}

    def fake_post(url, json, timeout):
        captured["url"] = url
        captured["json"] = json
        captured["timeout"] = timeout
        return FakeResponse(status_code=201)

    monkeypatch.setattr(module.requests, "post", fake_post)

    payload = {"device_id": "d1", "timestamp_ms": 1, "value": 2.0}
    response = client.post("/reading", json=payload)

    assert response.status_code == 200
    assert response.json()["upstream_status"] == 201
    assert captured["json"] == payload


def test_bridge_returns_502_on_forward_error(monkeypatch):
    module = importlib.import_module("api.bridge")
    module = importlib.reload(module)
    client = TestClient(module.app)

    def fake_post(url, json, timeout):
        raise module.requests.RequestException("network down")

    monkeypatch.setattr(module.requests, "post", fake_post)

    payload = {"device_id": "d1", "timestamp_ms": 1, "value": 2.0}
    response = client.post("/reading", json=payload)

    assert response.status_code == 502


def test_bridge_forwards_batch_payload(monkeypatch):
    module = importlib.import_module("api.bridge")
    module = importlib.reload(module)
    client = TestClient(module.app)

    captured = {}

    def fake_post(url, json, timeout):
        captured["url"] = url
        captured["json"] = json
        captured["timeout"] = timeout
        return FakeResponse(status_code=202)

    monkeypatch.setattr(module.requests, "post", fake_post)

    payload = [
        {"device_id": "d1", "timestamp_ms": 1, "value": 2.0},
        {"device_id": "d1", "timestamp_ms": 2, "value": 2.1},
    ]
    response = client.post("/readings", json=payload)

    assert response.status_code == 200
    assert response.json()["upstream_status"] == 202
    assert response.json()["count"] == 2
    assert captured["json"] == payload
