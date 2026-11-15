#!/usr/bin/env bash
# Menjalankan AI Clip Studio di port 8000.
cd "$(dirname "$0")"
[ -d .venv ] || { echo "Belum dipasang. Jalankan dulu: ./setup.sh"; exit 1; }
command -v ffmpeg >/dev/null && command -v ffprobe >/dev/null || { echo "FFmpeg tidak ditemukan. Jalankan: ./setup.sh"; exit 1; }
. .venv/bin/activate
python -c "import fastapi, uvicorn, faster_whisper" 2>/dev/null || { echo "Dependensi Python kurang. Jalankan: ./setup.sh"; exit 1; }
mkdir -p storage/jobs storage/models
echo "AI Clip Studio berjalan di port 8000. Buka tab PORTS di Codespaces lalu buka alamat port 8000."
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
