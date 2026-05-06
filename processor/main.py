import os
import glob
import csv
import shutil
import logging
from pathlib import Path

import psycopg2
import psycopg2.extras

# anomaly_detector.py is copied into the same /app directory by the Dockerfile
from anomaly_detector import AnomalyDetector

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger(__name__)

DATABASE_URL = os.environ["DATABASE_URL"]
BATCH_SIZE   = 1000

detector = AnomalyDetector(window_size=20, threshold=2.0)


def get_db():
    return psycopg2.connect(DATABASE_URL)


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
            # 1. save readings, get real db ids back
            db_ids = save_readings(cur, batch)

            # 2. update each row's id to the real db id
            #    AnomalyDetector uses row["id"] as the foreign key reference
            for row, db_id in zip(batch, db_ids):
                row["id"] = db_id

            # 3. run the provided AnomalyDetector
            result = detector.process_batch(batch)

            # 4. rename fields to match our db schema:
            #    sensor_data_id -> reading_id, confidence_score -> confidence
            formatted = [
                {
                    "reading_id":   int(a["sensor_data_id"]),    # cast numpy int to python int
                    "anomaly_type": a["anomaly_type"],
                    "confidence":   float(round(a["confidence_score"], 4)),  # cast numpy float
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
    done_dir.mkdir(exist_ok=True)

    csv_files = glob.glob(str(data_dir / "*.csv"))

    if not csv_files:
        log.info("No CSV files found in /app/data — nothing to do")
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
