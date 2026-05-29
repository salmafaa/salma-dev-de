# Entro.ly Data Engineering Test

## Prerequisites
- Python Python 3.11.9
- Postgres 15
- Airflow 2.11.2
- Docker & Docker Compose
- Playwright
- Pytest

## Setup

```bash
# 1. Clone & masuk ke direktori
git clone <repo>
cd entroly-de-test

# 2. Install dependencies Python
pip install -r requirements.txt

# 3. Install Playwright browsers
playwright install chromium

# 4. Jalankan tests
pytest tests/ -v

# 5. Jalankan Airflow + PostgreSQL via Docker
cp .env   # isi FERNET_KEY dan variabel lain
docker compose up -d

# Airflow UI → http://localhost:8080 (user: airflow / pass: airflow)
```

## Menjalankan DAG

1. Taruh file `.xlsx` di folder `data/`
2. Di Airflow UI, aktifkan DAG `agency_ingestion`
3. Trigger manual atau tunggu jadwal

## Menjalankan Sraping
1. python run_scraper.py

## Struktur Folder

