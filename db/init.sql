CREATE TABLE sensor_readings (
    id          SERIAL PRIMARY KEY,
    sensor_id   VARCHAR(50) NOT NULL,
    location    VARCHAR(100),
    temperature FLOAT,
    humidity    FLOAT,
    pressure    FLOAT,
    timestamp   TIMESTAMPTZ NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE anomalies (
    id               SERIAL PRIMARY KEY,
    reading_id       INT REFERENCES sensor_readings(id) ON DELETE CASCADE,
    anomaly_type     VARCHAR(50),   -- e.g. "temperature_anomaly"
    confidence       FLOAT,         -- the z-score, higher = more suspicious
    flagged_at       TIMESTAMPTZ DEFAULT NOW()
);

-- so queries by sensor + date don't crawl
CREATE INDEX ON sensor_readings (sensor_id, timestamp DESC);
CREATE INDEX ON anomalies (flagged_at DESC);
