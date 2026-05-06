import sys
from pathlib import Path
from datetime import datetime, timedelta

# point at project root so anomaly_detector.py can be found
sys.path.insert(0, str(Path(__file__).parent.parent))

from anomaly_detector import AnomalyDetector

detector = AnomalyDetector(window_size=20, threshold=2.0)


def make_rows(values, sensor="S1"):
    base = datetime(2024, 1, 1)
    return [
        {
            "id": i + 1,
            "sensor_id": sensor,
            "temperature": v,
            "humidity": 50.0,
            "pressure": 1013.0,
            "timestamp": (base + timedelta(minutes=i)).isoformat(),
        }
        for i, v in enumerate(values)
    ]


def test_stable_data_no_anomalies():
    result = detector.process_batch(make_rows([22.0] * 30))
    assert result["anomalies"] == []


def test_spike_is_flagged():
    result = detector.process_batch(make_rows([22.0] * 25 + [99.0]))
    assert any(a["anomaly_type"] == "temperature_anomaly" for a in result["anomalies"])


def test_confidence_is_positive():
    result = detector.process_batch(make_rows([22.0] * 25 + [99.0]))
    for a in result["anomalies"]:
        assert a["confidence_score"] > 0


def test_empty_input():
    result = detector.process_batch([])
    assert result["anomalies"] == []


def test_10k_records_under_5_seconds():
    import time
    rows = make_rows([22.0] * 9990 + [99.0] * 10)
    t = time.time()
    result = detector.process_batch(rows)
    assert time.time() - t < 5
    assert len(result["anomalies"]) > 0
