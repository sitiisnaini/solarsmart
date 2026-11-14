# SolarSmart

**Solar PV Planning, Simulation & Investment Analysis** — aplikasi web untuk perencanaan PLTS atap, simulasi energi, analisis jaringan menggunakan **pandapower**, dan kelayakan investasi.

## Jalankan di Windows (cara termudah)

1. Instal Python 3.10, 3.11, atau 3.12 (disarankan 3.11).
2. Ekstrak ZIP ini.
3. Buka folder `SolarSmart`.
4. Klik dua kali `run_windows.bat`.
5. Tunggu pemasangan paket selesai. Buka `http://localhost:8501` bila browser tidak terbuka otomatis.

Pertama kali dijalankan, komputer perlu terhubung ke internet untuk mengunduh dependensi.

## Jalankan melalui VS Code

Buka folder ini di VS Code, lalu jalankan di terminal Windows:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m streamlit run app.py
```

macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
streamlit run app.py
```

## Deploy agar bisa diakses melalui internet

Folder ini sudah disiapkan sebagai proyek Streamlit yang dapat diunggah ke GitHub dan dideploy melalui Streamlit Community Cloud:

1. Buat repository GitHub baru.
2. Unggah seluruh isi folder `SolarSmart` ke repository (termasuk `app.py`, folder `solarsmart`, `requirements.txt`, dan `.streamlit`).
3. Masuk ke https://share.streamlit.io/ dan login dengan GitHub.
4. Pilih **Create app**, lalu pilih repository, branch, dan file utama `app.py`.
5. Klik **Deploy**. Tunggu instalasi `requirements.txt` selesai.

Setelah deploy berhasil, Streamlit akan memberikan URL publik untuk aplikasi. Jangan mengunggah data jaringan atau data pelanggan yang bersifat rahasia ke aplikasi publik.

## Fitur aplikasi

- Simulasi profil beban dan produksi PV per jam selama 365 hari (8.760 titik waktu).
- Perbandingan PV tanpa baterai dan PV + baterai.
- Model baterai sederhana dengan batas DoD, efisiensi, dan C-rate.
- Indikator produksi PV, impor/ekspor energi, self-consumption, dan self-sufficiency.
- Estimasi CAPEX dari komponen yang dapat diedit.
- Proyeksi O&M, degradasi PV, eskalasi tarif, dan penggantian komponen.
- Simple payback, discounted payback, ROI, NPV, dan IRR.
- Pemindaian beberapa kapasitas PV untuk membandingkan NPV dengan batas luas atap.
- Analisis Power Flow pandapower pada jaringan contoh 20 kV / 0,4 kV.
- Ekspor hasil energi, keuangan, dan power flow ke CSV.

## Struktur proyek

```text
SolarSmart/
├── app.py
├── requirements.txt
├── Procfile
├── run_windows.bat
├── start.sh
├── .streamlit/config.toml
├── solarsmart/
│   ├── __init__.py
│   ├── energy.py
│   ├── economics.py
│   └── grid.py
└── tests/test_energy.py
```

## Catatan teknis dan batasan

- Pandapower digunakan untuk membangun feeder contoh dan menjalankan analisis power flow; perhitungan energi surya per jam dan analisis finansial dilakukan oleh modul Python terpisah.
- Jaringan pandapower memakai feeder contoh seimbang 20 kV/0,4 kV. Ganti impedansi kabel, panjang saluran, kapasitas trafo, dan beban dengan data survei aktual sebelum mengambil keputusan teknis.
- Profil beban dan produksi surya merupakan model representatif. Untuk studi nyata, gunakan data interval meter dan data iradiasi lokasi.
- Model baterai belum mensimulasikan BMS, temperatur, degradasi, dan dinamika inverter secara detail.
- Harga komponen merupakan asumsi yang harus diganti dengan penawaran vendor aktual.
- Tarif awal dapat diedit pengguna. Kredit ekspor default Rp0/kWh mengikuti asumsi skema PLTS atap baru berdasarkan Permen ESDM No. 2 Tahun 2024; periksa ketentuan yang berlaku untuk setiap proyek.
- Aplikasi ini merupakan prototipe perencanaan awal, bukan pengganti studi teknis resmi, survei lokasi, atau persetujuan penyedia listrik.

## Pengujian

```bash
python -m unittest discover -s tests -v
```

## Referensi

- Pandapower: https://pandapower.readthedocs.io/
- Streamlit deployment: https://docs.streamlit.io/deploy/streamlit-community-cloud
- PVGIS: https://re.jrc.ec.europa.eu/pvg_tools/en/
- Permen ESDM No. 2 Tahun 2024: https://peraturan.bpk.go.id/Details/288519/permen-esdm-no-2-tahun-2024
