FROM python:3.11-slim
WORKDIR /app
COPY processor/requirements.txt .
RUN pip install -r requirements.txt
COPY anomaly_detector.py .
COPY generate_data.py .
COPY processor/main.py .
CMD ["python", "main.py"]
