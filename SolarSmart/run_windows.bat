@echo off
setlocal
cd /d "%~dp0"
title SolarSmart - Solar PV Planner

echo ==============================================
echo   SolarSmart - menjalankan aplikasi web lokal
echo ==============================================

set PYTHON_CMD=
where py >nul 2>nul
if not errorlevel 1 (
  py -3.11 --version >nul 2>nul && set PYTHON_CMD=py -3.11
  if not defined PYTHON_CMD py -3.12 --version >nul 2>nul && set PYTHON_CMD=py -3.12
  if not defined PYTHON_CMD py -3.10 --version >nul 2>nul && set PYTHON_CMD=py -3.10
)
if not defined PYTHON_CMD (
  where python >nul 2>nul
  if not errorlevel 1 set PYTHON_CMD=python
)
if not defined PYTHON_CMD (
  echo Python 3.10, 3.11, atau 3.12 tidak ditemukan.
  echo Instal Python dari https://www.python.org/downloads/
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo [1/3] Membuat virtual environment...
  %PYTHON_CMD% -m venv .venv
  if errorlevel 1 goto error
)

echo [2/3] Memasang dependensi aplikasi...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto error
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto error

echo [3/3] Menjalankan SolarSmart...
echo Aplikasi akan tersedia di http://localhost:8501
echo Tutup jendela ini untuk menghentikan aplikasi.
".venv\Scripts\python.exe" -m streamlit run app.py
if errorlevel 1 goto error
goto end

:error
echo.
echo Gagal menyiapkan atau menjalankan aplikasi.
echo Periksa koneksi internet dan pesan error di atas.
pause
exit /b 1

:end
endlocal
