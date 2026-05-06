from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

# patch the db before importing the app

from main import app

client = TestClient(app)


def test_health():
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_anomalies_returns_list():
    with patch("main.db.fetch_all", new_callable=AsyncMock, return_value=[]):
        res = client.get("/api/anomalies")
    assert res.status_code == 200
    assert res.json() == []


def test_anomalies_filter_params_accepted():
    with patch("main.db.fetch_all", new_callable=AsyncMock, return_value=[]):
        res = client.get("/api/anomalies?sensor_id=TEMP_001&limit=10")
    assert res.status_code == 200


def test_sensors_returns_list():
    with patch("main.db.fetch_all", new_callable=AsyncMock, return_value=[]):
        res = client.get("/api/sensors")
    assert res.status_code == 200


def test_stats():
    with patch("main.db.fetch_one", new_callable=AsyncMock,
               side_effect=[{"total": 1000}, {"total": 50}]):
        res = client.get("/api/stats")
    assert res.status_code == 200
    data = res.json()
    assert data["total_readings"] == 1000
    assert data["total_anomalies"] == 50
