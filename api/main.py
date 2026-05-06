import os
from datetime import datetime
from typing import Optional
from contextlib import asynccontextmanager

import databases
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://user:pass@localhost/db")
db = databases.Database(DATABASE_URL)
@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.connect()
    yield
    await db.disconnect()

app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])



@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/api/anomalies")
async def get_anomalies(
    sensor_id: Optional[str] = None,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    limit: int = 100,
):
    # build up filters depending on what was passed in
    filters = []
    values = {}

    if sensor_id:
        filters.append("r.sensor_id = :sensor_id")
        values["sensor_id"] = sensor_id

    if start:
        filters.append("r.timestamp >= :start")
        values["start"] = start

    if end:
        filters.append("r.timestamp <= :end")
        values["end"] = end

    where = ("WHERE " + " AND ".join(filters)) if filters else ""

    query = f"""
        SELECT
            a.id,
            a.anomaly_type,
            a.confidence,
            a.flagged_at,
            r.sensor_id,
            r.location,
            r.temperature,
            r.humidity,
            r.pressure,
            r.timestamp
        FROM anomalies a
        JOIN sensor_readings r ON r.id = a.reading_id
        {where}
        ORDER BY a.flagged_at DESC
        LIMIT :limit
    """
    values["limit"] = limit

    rows = await db.fetch_all(query=query, values=values)
    return [dict(r) for r in rows]


@app.get("/api/sensors")
async def get_sensors():
    rows = await db.fetch_all("SELECT DISTINCT sensor_id FROM sensor_readings ORDER BY sensor_id")
    return [r["sensor_id"] for r in rows]


@app.get("/api/stats")
async def get_stats():
    readings = await db.fetch_one("SELECT COUNT(*) as total FROM sensor_readings")
    anomalies = await db.fetch_one("SELECT COUNT(*) as total FROM anomalies")
    return {
        "total_readings": readings["total"],
        "total_anomalies": anomalies["total"],
    }
