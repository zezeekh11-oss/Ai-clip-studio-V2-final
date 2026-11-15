#!/usr/bin/env bash
# Pemasangan dependensi untuk AI Clip Studio (Ubuntu / GitHub Codespaces).
set -e
cd "$(dirname "$0")"

echo "==> Memeriksa Python..."
command -v python3 >/dev/null || { echo "Python 3 tidak ditemukan."; exit 1; }
python3 - <<'PY'
import sys
assert sys.version_info >= (3, 10), "Dibutuhkan Python 3.10 atau lebih baru (disarankan 3.11)."
PY

echo "==> Memeriksa FFmpeg..."
if ! command -v ffmpeg >/dev/null || ! command -v ffprobe >/dev/null; then
  echo "FFmpeg belum ada, memasang (butuh sudo)..."
  SUDO=""; [ "$(id -u)" -ne 0 ] && SUDO="sudo"
  $SUDO apt-get update -y && $SUDO apt-get install -y ffmpeg
fi
ffmpeg -hide_banner -filters 2>/dev/null | grep -qw subtitles || echo "PERINGATAN: FFmpeg ini tanpa filter 'subtitles' (libass); subtitle tidak bisa dibakar."

echo "==> Membuat virtualenv dan memasang paket Python..."
[ -d .venv ] || python3 -m venv .venv
. .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo "==> Pemeriksaan akhir..."
python - <<'PY'
import importlib
for m in ("fastapi", "uvicorn", "pydantic", "faster_whisper"):
    importlib.import_module(m); print("  OK", m)
PY
mkdir -p storage/jobs storage/models
echo
echo "Selesai. Jalankan aplikasi dengan: ./start.sh"
