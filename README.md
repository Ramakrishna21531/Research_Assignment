# Sensor Pipeline

Reads sensor CSV files, finds anomalies, shows them on a dashboard.


#generate test data first (needs Python + numpy/pandas):

* pip install numpy pandas
* python generate_data.py -n 10000 -o data/sample.csv

#After generating csv file, we can start with this 

* cp .env.example .env
* docker compose up --build

Open http://localhost

## What each service does

- **db** — postgres, stores everything
- **processor** — reads CSVs, saves to db, flags anomalies
- **api** — serves the data as JSON
- **frontend** — the dashboard
- **nginx** — routes `/api/*` to the api, everything else to the frontend

## API

```
GET /api/anomalies              all anomalies
GET /api/anomalies?sensor_id=X  filter by sensor
GET /api/anomalies?start=...    filter by date (ISO format)
GET /api/sensors                list of sensor IDs
GET /api/stats                  total counts
GET /health                     health check
```

## How anomaly detection works

For each sensor, for each metric (temp/humidity/pressure), we look at the
last 20 readings and calculate the average and standard deviation. If the
new reading is more than 2 standard deviations away, it gets flagged.

The confidence score is the z-score — how many standard deviations away it was.
A score of 2.1 is mildly suspicious. A score of 15 means the sensor is probably broken.

## Deploying to AWS

You'll need: AWS account, Terraform installed, AWS CLI configured.

**1. Create the infrastructure**

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars
# edit terraform.tfvars — set a real db_password

terraform init
terraform apply
```

we can output of app URL and ECR repo URLs.

**2. Add one GitHub secret**

| `AWS_ROLE_ARN` | IAM role ARN that GitHub Actions can assume |
* Make sure you to check whether you have or created a OIDC provider.
* The role needs permissions to push ECR images and update ECS services. It uses OIDC — GitHub proves its identity to AWS and gets a short-lived token instead of storing a long-lived access key. Safer, no key rotation needed.

**3. Push to main — it deploys automatically**

* GitHub Actions will test -> build images ->push to ECR -> deploy to ECS.
* PRs only run the tests, not the deploy step.

---

## Folder structure

```
api/                    FastAPI app
processor/              CSV ingestion + anomaly detection
frontend/               Dashboard (single HTML file)
nginx/                  Reverse proxy config (local only)
db/                     SQL schema (runs automatically on first start)
terraform/              AWS infrastructure as code
.github/workflows/      CI/CD pipeline
data/                   Drop CSVs here (gitignored)
```

## About the provided scripts

**`generate_data.py`** — Use this to create test CSV files. Drop the output into `data/` and restart the processor.

```bash
# generate 10k rows with 3% anomaly rate
python generate_data.py -n 10000 -o data/sample.csv

# generate with a fixed seed so results are reproducible
python generate_data.py -n 5000 --seed 42 -o data/test.csv

# crank up anomalies for testing
python generate_data.py -n 1000 --anomaly-rate 0.15 -o data/lots_of_anomalies.csv
```

**`anomaly_detector.py`** — The processor imports `AnomalyDetector` from this file directly. No changes were made to it. The processor just handles the database parts (reading CSVs, saving results) and hands the actual detection off to this script.
