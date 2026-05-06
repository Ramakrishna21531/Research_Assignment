import os
import glob
import csv
import shutil
import logging
import subprocess
from pathlib import Path

import psycopg2
import psycopg2.extras

from anomaly_detector import AnomalyDetector

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger(__name__)

DATABASE_URL = os.environ["DATABASE_URL"]
BATCH_SIZE   = 1000

detector = AnomalyDetector(window_size=20, threshold=2.0)


def get_db():
    return psycopg2.connect(DATABASE_URL)


def generate_data(data_dir):
    """
    Generate sample sensor data inside the container.
    Uses generate_data.py which is copied in by the Dockerfile.
    No S3 or external file uploads needed.
    """
    output = data_dir / "sample_data.csv"
    observations = os.environ.get("NUM_OBSERVATIONS", "10000")

    log.info(f"Generating {observations} sensor readings...")
    subprocess.run([
        "python", "generate_data.py",
        "-n", observations,
        "--seed", "42",
        "--anomaly-rate", "0.03",
        "-o", str(output)
    ], check=True)

    log.info(f"Generated data saved to {output}")


def load_csv(path):
    """Read a CSV file, return list of row dicts. Skips bad rows silently."""
    rows = []
    with open(path) as f:
        for row in csv.DictReader(f):
            try:
                rows.append({
                    "id":          int(row["id"]),
                    "sensor_id":   row["sensor_id"],
                    "location":    row.get("location"),
                    "temperature": float(row["temperature"]),
                    "humidity":    float(row["humidity"]),
                    "pressure":    float(row["pressure"]),
                    "timestamp":   row["timestamp"],
                })
            except (KeyError, ValueError):
                pass
    return rows


def save_readings(cur, batch):
    """Bulk insert readings, return new db ids in same order."""
    rows = [
        (r["sensor_id"], r["location"], r["temperature"],
         r["humidity"], r["pressure"], r["timestamp"])
        for r in batch
    ]
    result = psycopg2.extras.execute_values(cur, """
        INSERT INTO sensor_readings (sensor_id, location, temperature, humidity, pressure, timestamp)
        VALUES %s RETURNING id
    """, rows, fetch=True)
    return [r[0] for r in result]


def save_anomalies(cur, anomalies):
    if not anomalies:
        return
    rows = [(a["reading_id"], a["anomaly_type"], a["confidence"]) for a in anomalies]
    psycopg2.extras.execute_values(cur, """
        INSERT INTO anomalies (reading_id, anomaly_type, confidence)
        VALUES %s
    """, rows)


def process_file(path, conn):
    log.info(f"Processing {path}")
    rows = load_csv(path)

    if not rows:
        log.info("No valid rows, skipping")
        return

    total_anomalies = 0

    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i:i + BATCH_SIZE]

        with conn.cursor() as cur:
            db_ids = save_readings(cur, batch)

            for row, db_id in zip(batch, db_ids):
                row["id"] = db_id

            result = detector.process_batch(batch)

            formatted = [
                {
                    "reading_id":   int(a["sensor_data_id"]),
                    "anomaly_type": a["anomaly_type"],
                    "confidence":   float(round(a["confidence_score"], 4)),
                }
                for a in result["anomalies"]
            ]

            save_anomalies(cur, formatted)

        conn.commit()
        total_anomalies += len(formatted)
        log.info(f"  rows {i+1}-{i+len(batch)}: {len(formatted)} anomalies")

    log.info(f"Finished: {len(rows)} readings, {total_anomalies} anomalies total")


def main():
    data_dir = Path("/app/data")
    done_dir = data_dir / "processed"
    data_dir.mkdir(exist_ok=True)
    done_dir.mkdir(exist_ok=True)

    # generate data inside the container — no S3 needed
    generate_data(data_dir)

    csv_files = glob.glob(str(data_dir / "*.csv"))

    if not csv_files:
        log.info("No CSV files found — nothing to do")
        return

    conn = get_db()

    for path in csv_files:
        try:
            process_file(path, conn)
            shutil.move(path, done_dir / Path(path).name)
            log.info(f"Moved to processed/")
        except Exception as e:
            log.error(f"Failed on {path}: {e}")
            conn.rollback()

    conn.close()
    log.info("All done")


if __name__ == "__main__":
    main()
