#!/usr/bin/env python3
"""
Sample data generator for research sensor readings.
Creates realistic time-series data with controllable anomalies.
Usage:
    python generate_data.py --observations 1000 --output sample_data.csv
    python generate_data.py -n 50000 -o large_dataset.csv --anomaly-rate 0.05
    python generate_data.py --help
The script generates data for multiple sensors with realistic baselines and
injects various types of anomalies (spikes, drifts, sensor failures).
"""

import argparse
import csv
import random
import math
from datetime import datetime, timedelta
from typing import List, Dict, Any
import numpy as np

# Sensor configurations with realistic baselines
SENSOR_CONFIGS = [
    {
        'sensor_id': 'TEMP_001',
        'location': 'lab_a',
        'temp_baseline': 22.0,
        'humid_baseline': 45.0,
        'press_baseline': 1013.25
    },
    {
        'sensor_id': 'TEMP_002',
        'location': 'lab_b',
        'temp_baseline': 21.5,
        'humid_baseline': 50.0,
        'press_baseline': 1012.80
    },
    {
        'sensor_id': 'HUMID_003',
        'location': 'greenhouse',
        'temp_baseline': 26.0,
        'humid_baseline': 75.0,
        'press_baseline': 1011.50
    },
    {
        'sensor_id': 'PRESS_004',
        'location': 'outdoor',
        'temp_baseline': 18.0,
        'humid_baseline': 60.0,
        'press_baseline': 1015.00
    },
    {
        'sensor_id': 'MULTI_005',
        'location': 'server_room',
        'temp_baseline': 20.0,
        'humid_baseline': 35.0,
        'press_baseline': 1013.00
    }
]

class DataGenerator:
    def __init__(self, anomaly_rate: float = 0.03, seed: int = None):
        self.anomaly_rate = anomaly_rate
        if seed is not None:
            random.seed(seed)
            np.random.seed(seed)

        self.anomaly_types = [
            'spike_high',
            'spike_low',
            'drift_up',
            'drift_down',
            'sensor_failure',
            'noise_burst'
        ]

    def generate_normal_reading(self, sensor: Dict, timestamp: datetime,
                              prev_reading: Dict = None) -> Dict[str, Any]:
        temp_noise = np.random.normal(0, 0.5)
        humid_noise = np.random.normal(0, 2.0)
        press_noise = np.random.normal(0, 0.3)

        if prev_reading:
            temp_correlation = 0.7 * (prev_reading['temperature'] - sensor['temp_baseline'])
            humid_correlation = 0.6 * (prev_reading['humidity'] - sensor['humid_baseline'])
            press_correlation = 0.8 * (prev_reading['pressure'] - sensor['press_baseline'])
        else:
            temp_correlation = humid_correlation = press_correlation = 0

        hour_of_day = timestamp.hour
        daily_temp_cycle = 2.0 * math.sin(2 * math.pi * (hour_of_day - 6) / 24)

        return {
            'timestamp': timestamp.isoformat() + 'Z',
            'sensor_id': sensor['sensor_id'],
            'temperature': round(sensor['temp_baseline'] + daily_temp_cycle +
                               temp_correlation * 0.3 + temp_noise, 1),
            'humidity': round(max(0, min(100, sensor['humid_baseline'] +
                                       humid_correlation * 0.3 + humid_noise)), 1),
            'pressure': round(sensor['press_baseline'] +
                            press_correlation * 0.3 + press_noise, 2),
            'location': sensor['location']
        }

    def inject_anomaly(self, normal_reading: Dict, anomaly_type: str) -> Dict[str, Any]:
        reading = normal_reading.copy()

        if anomaly_type == 'spike_high':
            metric = random.choice(['temperature', 'humidity', 'pressure'])
            if metric == 'temperature':
                reading[metric] += random.uniform(10, 25)
            elif metric == 'humidity':
                reading[metric] = min(100, reading[metric] + random.uniform(20, 40))
            else:
                reading[metric] += random.uniform(15, 50)

        elif anomaly_type == 'spike_low':
            metric = random.choice(['temperature', 'humidity', 'pressure'])
            if metric == 'temperature':
                reading[metric] -= random.uniform(8, 20)
            elif metric == 'humidity':
                reading[metric] = max(0, reading[metric] - random.uniform(15, 35))
            else:
                reading[metric] -= random.uniform(20, 60)

        elif anomaly_type == 'sensor_failure':
            reading['temperature'] = -999.0
            reading['humidity'] = 0.0
            reading['pressure'] = 0.0

        elif anomaly_type == 'noise_burst':
            reading['temperature'] += random.uniform(-5, 5)
            reading['humidity'] += random.uniform(-10, 10)
            reading['pressure'] += random.uniform(-8, 8)

        elif anomaly_type in ['drift_up', 'drift_down']:
            multiplier = 1.5 if anomaly_type == 'drift_up' else -1.5
            reading['temperature'] += multiplier * random.uniform(1, 3)
            reading['humidity'] += multiplier * random.uniform(2, 8)
            reading['pressure'] += multiplier * random.uniform(1, 4)

        reading['temperature'] = max(-50, min(60, reading['temperature']))
        reading['humidity'] = max(0, min(100, reading['humidity']))
        reading['pressure'] = max(800, min(1100, reading['pressure']))

        return reading

    def generate_dataset(self, num_observations: int,
                        start_time: datetime = None) -> List[Dict[str, Any]]:
        if start_time is None:
            start_time = datetime.utcnow() - timedelta(hours=24)

        dataset = []
        sensors = SENSOR_CONFIGS.copy()

        readings_per_sensor = num_observations // len(sensors)
        time_interval_minutes = (24 * 60) // readings_per_sensor

        prev_readings = {sensor['sensor_id']: None for sensor in sensors}

        total_anomalies = int(num_observations * self.anomaly_rate)
        anomaly_indices = set(random.sample(range(num_observations), total_anomalies))

        observation_id = 1
        current_time = start_time

        for i in range(num_observations):
            sensor = sensors[i % len(sensors)]

            reading = self.generate_normal_reading(
                sensor, current_time, prev_readings[sensor['sensor_id']]
            )

            if i in anomaly_indices:
                anomaly_type = random.choice(self.anomaly_types)
                reading = self.inject_anomaly(reading, anomaly_type)

            reading['id'] = observation_id
            prev_readings[sensor['sensor_id']] = reading
            dataset.append(reading)
            observation_id += 1

            jitter = random.uniform(-0.3, 0.3) * time_interval_minutes
            current_time += timedelta(minutes=time_interval_minutes + jitter)

        dataset.sort(key=lambda x: x['timestamp'])
        return dataset


def save_to_csv(dataset: List[Dict[str, Any]], filename: str):
    if not dataset:
        print("No data to save!")
        return

    fieldnames = ['id', 'timestamp', 'sensor_id', 'temperature', 'humidity', 'pressure', 'location']

    with open(filename, 'w', newline='') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(dataset)

    print(f"Generated {len(dataset)} observations saved to {filename}")


def main():
    parser = argparse.ArgumentParser(description='Generate sample sensor data with controllable anomalies')

    parser.add_argument('-n', '--observations', type=int, default=1000)
    parser.add_argument('-o', '--output', default='sample_data.csv')
    parser.add_argument('--anomaly-rate', type=float, default=0.03)
    parser.add_argument('--seed', type=int)
    parser.add_argument('--start-time')

    args = parser.parse_args()

    start_time = None
    if args.start_time:
        start_time = datetime.fromisoformat(args.start_time.replace('Z', '+00:00'))

    print(f"Generating {args.observations} observations with {args.anomaly_rate:.1%} anomaly rate...")

    generator = DataGenerator(anomaly_rate=args.anomaly_rate, seed=args.seed)
    dataset = generator.generate_dataset(args.observations, start_time)
    save_to_csv(dataset, args.output)

    print(f"\nDone: {len(dataset)} rows written to {args.output}")


if __name__ == "__main__":
    main()
