## Q3.1 — Idempotency

Selain menggunakan `INSERT ... ON CONFLICT DO UPDATE`, saya akan menambahkan beberapa safeguard agar pipeline aman untuk di-run ulang pada periode yang sama:

* Menggunakan `data_sync_logs` untuk menyimpan status per periode (`RUNNING`, `COMPLETED`, `FAILED`). Saat DAG dijalankan ulang, pipeline akan mengecek apakah periode tersebut sudah selesai diproses dan skip jika statusnya `COMPLETED`.
* Menggunakan transaction per batch agar proses insert/update bersifat atomic. Jika task gagal di tengah proses, seluruh batch akan di-rollback sehingga tidak ada partial data.
* Menggunakan staging table sebelum merge ke tabel utama untuk validasi schema, deduplication, dan data quality check sebelum data masuk ke production table.
* Menambahkan concurrency protection (misalnya Airflow concurrency limit atau distributed lock) agar dua DAG tidak memproses periode yang sama secara bersamaan.
* Menyimpan checksum/hash source file atau response API untuk mencegah reprocessing data yang identik.

---

## Q3.2 — Backfill

Saya akan membuat DAG backfill menggunakan dynamic task mapping di Airflow, di mana setiap task merepresentasikan satu tanggal dalam range 90 hari. Pendekatan ini membuat proses lebih parallel, granular, dan mudah di-resume jika gagal.

Untuk menghindari rate limit TikTok API (10 request/min per token):

* Gunakan Airflow Pool khusus TikTok API dengan concurrency kecil.
* Tambahkan rate limiter atau delay di API client agar total request tetap berada di bawah batas API.
* Gunakan retry dengan exponential backoff untuk transient failure seperti timeout atau HTTP 429.

Agar resumable:

* Setiap task akan menulis status ke `data_sync_logs`.
* Saat DAG di-run ulang, task akan mengecek apakah tanggal tersebut sudah memiliki status `COMPLETED`.
* Jika sudah selesai, task di-skip; jika status `FAILED` atau belum ada, task diproses ulang.

Dengan pendekatan ini, jika proses gagal di hari ke-45, pipeline cukup melanjutkan dari tanggal yang gagal tanpa mengulang dari hari pertama.

---

## Q3.3 — Slow Dashboard Query

1. **Tambahkan composite index pada `(report_date, creator_id)`**
   Query melakukan filter berdasarkan `report_date`, sehingga index ini membantu PostgreSQL mengurangi jumlah row yang perlu discan sebelum aggregation dilakukan.

2. **Gunakan materialized view untuk pre-aggregation**
   Karena dashboard selalu menghitung agregasi 90 hari terakhir, hasil agregasi dapat disimpan di materialized view dan di-refresh secara berkala (misalnya setiap jam atau setiap hari). Ini mengurangi beban query berat pada tabel dengan jutaan row.

3. **Tambahkan caching di application layer (Redis)**
   Hasil query dashboard dapat di-cache beberapa menit karena data tidak berubah setiap detik. Ini mengurangi query berulang ke database dan menurunkan latency secara signifikan pada traffic tinggi.
