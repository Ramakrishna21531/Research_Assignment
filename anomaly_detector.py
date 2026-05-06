#!/usr/bin/env python3
"""
Simple anomaly detection algorithm for sensor data.
Algorithm: Flags readings that are >2 standard deviations from the rolling mean
Rolling window: 20 readings per sensor per metric
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Any
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AnomalyDetector:
    def __init__(self, window_size: int = 20, threshold: float = 2.0):
        self.window_size = window_size
        self.threshold = threshold
        self.metrics = ['temperature', 'humidity', 'pressure']

    def detect_anomalies(self, sensor_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not sensor_data:
            return []

        df = pd.DataFrame(sensor_data)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df = df.sort_values(['sensor_id', 'timestamp'])

        anomalies = []

        for sensor_id in df['sensor_id'].unique():
            sensor_df = df[df['sensor_id'] == sensor_id].copy()

            for metric in self.metrics:
                if metric not in sensor_df.columns:
                    continue

                rolling_mean = sensor_df[metric].rolling(
                    window=self.window_size,
                    min_periods=1
                ).mean()

                rolling_std = sensor_df[metric].rolling(
                    window=self.window_size,
                    min_periods=1
                ).std()

                z_scores = (sensor_df[metric] - rolling_mean) / rolling_std
                anomaly_mask = np.abs(z_scores) > self.threshold

                for idx in sensor_df[anomaly_mask].index:
                    row = sensor_df.loc[idx]
                    z_score = z_scores.loc[idx]

                    if pd.isna(z_score):
                        continue

                    anomaly = {
                        'sensor_data_id': row['id'],
                        'anomaly_type': f'{metric}_anomaly',
                        'confidence_score': abs(z_score),
                        'detected_at': pd.Timestamp.now().isoformat()
                    }
                    anomalies.append(anomaly)

        logger.info(f"Detected {len(anomalies)} anomalies in {len(sensor_data)} readings")
        return anomalies

    def process_batch(self, sensor_data: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        anomalies = self.detect_anomalies(sensor_data)
        anomalous_ids = {a['sensor_data_id'] for a in anomalies}

        return {
            'data': sensor_data,
            'anomalies': anomalies,
            'anomalous_reading_ids': list(anomalous_ids)
        }
