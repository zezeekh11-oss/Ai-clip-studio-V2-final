import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
STORAGE_DIR = Path(os.environ.get("CLIP_STORAGE", BASE_DIR / "storage"))
JOBS_DIR = STORAGE_DIR / "jobs"
MODELS_DIR = STORAGE_DIR / "models"
DB_PATH = STORAGE_DIR / "clipstudio.db"
STATIC_DIR = BASE_DIR / "static"

MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "1024"))
MAX_VIDEO_MINUTES = int(os.environ.get("MAX_VIDEO_MINUTES", "120"))
ALLOWED_EXT = {".mp4", ".mov", ".mkv"}
WHISPER_MODELS = ("tiny", "base")
# Perkiraan ukuran unduhan model (MB), hanya untuk menampilkan progres unduhan
MODEL_APPROX_MB = {"tiny": 75, "base": 145}


def ensure_dirs():
    for d in (STORAGE_DIR, JOBS_DIR, MODELS_DIR):
        d.mkdir(parents=True, exist_ok=True)
