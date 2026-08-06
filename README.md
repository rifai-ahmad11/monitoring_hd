# HD Machine Monitoring - Railway PostgreSQL

Versi produksi Flask untuk deployment Railway melalui GitHub. Database dimulai
dari PostgreSQL baru; data dari SQLite atau database lama tidak dipindahkan.

## File deployment

- `Dockerfile`: membangun container Python dan menjalankan Gunicorn.
- `railway.json`: memilih Dockerfile, healthcheck `/health`, dan restart policy.
- `.dockerignore`: mencegah file lokal, test, SQL, dan rahasia masuk image.
- `database/schema.sql`: membuat delapan tabel dan index PostgreSQL tanpa data demo.
- `.env.example`: daftar variable yang harus diatur di Railway; bukan file rahasia.

## Urutan deployment

### 1. Buat PostgreSQL di Railway

Di project Railway, pilih `+ New` -> `Database` -> `Add PostgreSQL`. Dalam contoh
ini nama service database adalah `Postgres`.

### 2. Buat tabel dari database kosong

Jalankan seluruh isi `database/schema.sql` pada service PostgreSQL. Salah satu
cara resmi adalah memakai Railway CLI dan `psql`:

```bash
railway login
railway link
railway connect Postgres
```

Setelah masuk ke prompt `psql`, jalankan isi SQL atau gunakan perintah `\i`
terhadap path file pada komputer Anda:

```sql
\i database/schema.sql
```

Script hanya membuat struktur tabel dan index. Script tidak memasukkan mesin,
metadata, maintenance, humidity, voltage, error, atau data demo.

### 3. Upload folder ini ke GitHub

Pastikan isi repository dimulai langsung dari file berikut:

```text
Dockerfile
app.py
railway.json
requirements.txt
database/
static/
templates/
```

Jika folder `HD_Machine_Monitoring_Railway` dijadikan subfolder repository,
atur `Root Directory` service Railway ke folder tersebut. Cara paling mudah
adalah menjadikan isi folder ini sebagai root repository.

### 4. Hubungkan repository GitHub

Di Railway pilih `+ New` -> `GitHub Repo`, lalu pilih repository dan branch.
Railway otomatis menggunakan `Dockerfile` di root.

### 5. Isi Variables pada service aplikasi

Masukkan variable berikut pada service Flask, bukan pada service PostgreSQL:

```text
APP_ENV=production
DATABASE_URL=${{Postgres.DATABASE_URL}}
SECRET_KEY=<nilai-acak-panjang>
ADMIN_USERNAME=admin
ADMIN_PASSWORD=<password-admin-kuat>
DEVICE_API_KEY=<kunci-api-perangkat-acak>
BOOTSTRAP_ADMIN=1
AUTO_CREATE_TABLES=0
VALIDATE_DATABASE_SCHEMA=1
SEED_DEMO_DATA=0
ERROR_LOG_LIMIT=300
HEARTBEAT_TIMEOUT_SECONDS=390
PUMP_HEARTBEAT_TIMEOUT_SECONDS=180
ACTIVE_SESSION_THRESHOLD_SECONDS=60
DIALYSIS_SESSION_THRESHOLD_SECONDS=14400
GUNICORN_WORKERS=2
GUNICORN_THREADS=2
GUNICORN_TIMEOUT=60
```

`DATABASE_URL=${{Postgres.DATABASE_URL}}` adalah reference variable. Jika nama
service database berbeda, ganti `Postgres` dengan nama service yang sebenarnya,
misalnya `${{PostgreSQL-HD.DATABASE_URL}}`.

Untuk membuat secret secara lokal:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Jalankan dua kali dan gunakan hasil berbeda untuk `SECRET_KEY` dan
`DEVICE_API_KEY`. Jangan menyimpan nilai aslinya di `.env`, source code, atau
GitHub.

### 6. Deploy dan buat domain

Setelah variables diterapkan, Railway akan redeploy. Buka logs dan pastikan
Gunicorn aktif serta healthcheck `/health` berhasil. Setelah itu buka
`Settings` -> `Networking` -> `Generate Domain`.

## Admin pertama dan database kosong

Saat pertama kali startup, aplikasi membuat tepat satu akun admin dari
`ADMIN_USERNAME` dan `ADMIN_PASSWORD` jika tabel `users` masih kosong. Ini bukan
data demo. Password disimpan sebagai hash Werkzeug, bukan teks biasa.

`BOOTSTRAP_ADMIN=1` bersifat idempotent: restart atau deploy berikutnya tidak
membuat admin baru dan tidak mengganti password admin yang sudah ada. Setelah
berhasil login, variable `ADMIN_PASSWORD` boleh dihapus dan
`BOOTSTRAP_ADMIN` boleh diubah ke `0`.

Semua tabel lain tetap kosong sampai perangkat mengirim data atau admin mengisi
metadata/konfigurasi maintenance melalui aplikasi.

## Pengamanan yang diterapkan

- Produksi menolak startup jika `DATABASE_URL` atau `SECRET_KEY` tidak diisi.
- Environment Railway otomatis diperlakukan sebagai production meskipun
  `APP_ENV` tidak sengaja terlupa.
- Produksi tidak menjalankan `db.create_all()` otomatis.
- Produksi memeriksa bahwa seluruh tabel dari `schema.sql` sudah tersedia.
- `SEED_DEMO_DATA=1` ditolak pada production.
- Cookie sesi memakai `HttpOnly`, `SameSite=Lax`, dan `Secure` pada production.
- Endpoint perangkat memakai header `X-API-Key` jika `DEVICE_API_KEY` diisi.
- Error log dipertahankan maksimal 300 entri terbaru per mesin.

## Endpoint perangkat

- `POST /update`
- `POST /pump-status`
- `POST /error-log`
- `POST /humidity`
- `POST /voltage`

Contoh:

```bash
curl -X POST https://DOMAIN-ANDA/update \
  -H "Content-Type: application/json" \
  -H "X-API-Key: DEVICE_API_KEY_ANDA" \
  -d '{"machine_id":"HD-UNIT-XT2310030","status":"running"}'
```

ID dinormalisasi menjadi segmen terakhir setelah tanda `-`, lalu diubah menjadi
huruf kapital.

## Uji lokal tanpa PostgreSQL

Untuk pengujian lokal, jangan gunakan `APP_ENV=production`. Jika `DATABASE_URL`
kosong, aplikasi memakai SQLite lokal dan membuat tabel otomatis. Data demo
tetap tidak dibuat kecuali `SEED_DEMO_DATA=1` sengaja diaktifkan.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Pada Windows, aktivasi environment dengan:

```powershell
.venv\Scripts\activate
```
