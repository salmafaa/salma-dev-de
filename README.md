# Entro.ly Data Engineering Test

Skill test submission for Entro.ly — TikTok Creator Agency Data Engineering position.

## Stack

| Component | Version |
|---|---|
| Python | 3.11.9 |
| PostgreSQL | 15 |
| Apache Airflow | 2.11.2 |
| Docker & Docker Compose | latest |
| Playwright | latest |
| Pytest | latest |

---

## Struktur Folder

```
entroly-de-test/
├── answers/
│   ├── part1.sql                         # Q1.1–Q1.5 SQL queries
│   └── part3.md                          # Q3.1–Q3.3 written answers
├── src/
│   ├── __init__.py
│   ├── ingestion.py                      # Q2.1 — Excel ingestion
│   ├── commission.py                     # Q2.2 — Commission calculator
│   ├── scraper.py                        # Q2.4 — Hotel image scraper
│   └── dags/
│       ├── __init__.py
│       └── agency_ingestion_dag.py       # Q2.3 — Airflow DAG
├── tests/
│   ├── __init__.py
│   ├── test_ingestion.py                 # 5 unit tests Q2.1
│   ├── test_commission.py                # 4 unit tests Q2.2
│   ├── test_dag.py                       # 3 unit tests Q2.3
│   └── test_scraper.py                   # 3 unit tests Q2.4
├── migrations/
│   └── 001_create_creator_performance_tables.sql  # DDL semua tabel
├── docker/
│   └── init-db.sql                       # Inisialisasi database entroly_db
├── data/                                 # file .xlsx di sini
├── output_images/                        # Output gambar dari scraper
├── docker-compose.yml
├── Dockerfile
├── .env
├── requirements.txt
├── run_scraper.py                        # Script untuk jalankan scraper manual
└── README.md
```

---

## Prerequisites

- Python 3.11.9
- Docker Desktop (sudah include Docker Compose)
- Git

---

## Setup & Instalasi

### 1. Clone Repository

```bash
git clone <repo_url>
cd entroly-de-test
```

### 2. Install Python Dependencies

```bash
pip install -r requirements.txt
```

### 3. Install Playwright Browser

```bash
playwright install chromium
```

### 4. Siapkan Environment Variables

Buat file `.env` di root folder

Generate Fernet Key:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

---

## Menjalankan Unit Tests

Jalankan semua tests sekaligus:

```bash
pytest tests/ -v
```

Atau per modul:

```bash
# Test Excel ingestion (Q2.1)
pytest tests/test_ingestion.py -v

# Test commission calculator (Q2.2)
pytest tests/test_commission.py -v

# Test Airflow DAG (Q2.3)
pytest tests/test_dag.py -v

# Test scraper (Q2.4)
pytest tests/test_scraper.py -v
```

---

## Menjalankan Airflow via Docker

### 1. Build & Start

```bash
# Build image
docker compose build --no-cache

# Inisialisasi database Airflow
docker compose up airflow-init

# Jalankan semua service
docker compose up -d
```

### 2. Cek Status Container

```bash
docker compose ps
```

Semua service harus berstatus `healthy`.

### 3. Buka Airflow UI

Buka browser: **http://localhost:8080**

### 4. Setup Koneksi di Airflow UI

Masuk ke **Admin → Connections**, tambahkan dua koneksi:

**`postgres_entropi`** — koneksi ke database entroly_db:

| Field | Value |
|---|---|
| Connection Id | `postgres_entropi` |
| Connection Type | `Postgres` |
| Host | `postgres` |
| Database | `entroly_db` |
| Login | `salma_dev` |
| Password | `airflow` |
| Port | `5432` |

**`fs_default`** — koneksi untuk FileSensor:

| Field | Value |
|---|---|
| Connection Id | `fs_default` |
| Connection Type | `File (path)` |
| Host | `/opt/airflow/data` |

### 5. Setup Database

Konek ke PostgreSQL via DBeaver atau psql

Jalankan DDL:

```bash
psql -h localhost -p 5433 -U salma_dev -d entroly_db -f migrations/001_create_creator_performance_tables.sql
```

Tambahkan kolom `sales_power`:

```sql
ALTER TABLE creators ADD COLUMN sales_power VARCHAR(20) NOT NULL DEFAULT 'Bronze';
```

Buat materialized view:

```sql
CREATE MATERIALIZED VIEW mv_weekly_gmv_by_tier AS
SELECT
    DATE_TRUNC('week', p.report_date)::DATE AS week_start,
    c.sales_power,
    COUNT(DISTINCT c.id)                    AS creator_count,
    SUM(p.total_gmv)                        AS total_gmv,
    SUM(p.affiliate_live_gmv)               AS total_live_gmv,
    SUM(p.total_orders)                     AS total_orders
FROM creators c
JOIN creator_daily_performance p ON p.creator_id = c.id
GROUP BY DATE_TRUNC('week', p.report_date), c.sales_power
WITH DATA;

CREATE UNIQUE INDEX idx_mv_weekly_gmv_tier_pk
    ON mv_weekly_gmv_by_tier (week_start, sales_power);
```

---

## Menjalankan DAG

1. Taruh file `.xlsx` di folder `data/` dengan format sheet **Agency**:

| Period | Creator Username | GMV (IDR) | Live GMV | Video GMV | Orders | CTR | CVR |
|---|---|---|---|---|---|---|---|
| 2025-W03 | @budi_cooks | 15750000 | 9000000 | 6750000 | 87 | 0.0421 | 0.0727 |

2. Di Airflow UI, aktifkan DAG `agency_ingestion` (toggle ON)
3. Klik tombol **Trigger DAG** (▶) untuk jalankan manual
4. Pantau progress di tab **Graph** — semua task harus hijau

**Task flow:**

```
wait_for_xlsx → extract_excel → validate_rows → load_to_postgres → refresh_matview
```

5. Verifikasi data masuk:

```sql
SELECT * FROM creator_daily_performance ORDER BY created_at DESC LIMIT 10;
SELECT * FROM data_sync_logs ORDER BY started_at DESC LIMIT 5;
SELECT * FROM mv_weekly_gmv_by_tier;
```

---

## Menjalankan Hotel Image Scraper

```bash
python run_scraper.py
```

Scraper akan otomatis:

1. Membuka browser Traveloka
2. Mengisi form pencarian dengan nama hotel dan kota
3. Mengambil 3 gambar thumbnail pertama
4. Menyimpan ke folder `output_images/`

Format nama file: `<slugified-hotel-name>_<n>.jpg`

Contoh output:

```
output_images/
├── grand-hyatt-jakarta_1.jpg
├── grand-hyatt-jakarta_2.jpg
├── grand-hyatt-jakarta_3.jpg
```

Untuk mengubah daftar hotel yang di-scrape, edit bagian ini di `run_scraper.py`:

```python
hotels = [
    ("Grand Hyatt Jakarta", "Jakarta"),
    ("Vio Cihampelas", "Bandung"),
    ("The Westin Resort Nusa Dua", "Bali"),
]
```

---

## Menghentikan Docker

```bash
docker compose down
```

Untuk menghapus semua data (reset total):

```bash
docker compose down --volumes
```

---

## Catatan Teknis

- **Scraper** menggunakan `headless=False` karena Traveloka mendeteksi dan memblokir headless browser. Browser akan terbuka saat scraper berjalan.
- **DAG schedule** diset setiap hari Senin 09:00 WIB (`0 2 * * 1` UTC). Bisa diubah di `agency_ingestion_dag.py`.
- **FileSensor** akan menunggu maksimal 6 jam untuk file `.xlsx` baru di folder `data/` sebelum timeout.
- **Materialized view** harus dibuat manual sekali sebelum DAG pertama kali dijalankan.
