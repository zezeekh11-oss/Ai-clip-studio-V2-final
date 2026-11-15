"""Transkripsi lokal dengan faster-whisper (CPU, int8). Model diunduh otomatis saat pertama dipakai."""
import threading
import time
from pathlib import Path

from ..config import MODEL_APPROX_MB, MODELS_DIR


class TranscriptionError(Exception):
    pass


def whisper_installed():
    import importlib.util
    return importlib.util.find_spec("faster_whisper") is not None


def _model_dir(name):
    return MODELS_DIR / f"models--Systran--faster-whisper-{name}"


def model_cached(name):
    d = _model_dir(name) / "snapshots"
    return d.exists() and any((p / "model.bin").exists() for p in d.iterdir())


def _dir_mb(path):
    if not path.exists():
        return 0.0
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) / 1_048_576


def _ensure_model(name, progress_cb, status_cb):
    from faster_whisper.utils import download_model
    if model_cached(name):
        return download_model(name, cache_dir=str(MODELS_DIR), local_files_only=True)
    total = MODEL_APPROX_MB[name]
    stop = threading.Event()

    def watch():
        while not stop.is_set():
            mb = _dir_mb(_model_dir(name))
            status_cb(f"Mengunduh model Whisper '{name}' (sekali saja): {mb:.0f} / ±{total} MB")
            progress_cb(min(mb / total, 0.99))
            time.sleep(1.0)

    t = threading.Thread(target=watch, daemon=True)
    t.start()
    try:
        return download_model(name, cache_dir=str(MODELS_DIR))
    except Exception as e:
        raise TranscriptionError(
            f"Gagal mengunduh model Whisper '{name}'. Periksa koneksi internet server lalu coba lagi. ({e})")
    finally:
        stop.set()
        t.join(timeout=2)


def transcribe(audio_path, model_name, language, duration, progress_cb, status_cb):
    """Mengembalikan (segments, bahasa). segments: [{start,end,text}]. progress_cb(0..1) untuk tahap transkripsi."""
    from faster_whisper import WhisperModel
    model_path = _ensure_model(model_name, progress_cb, status_cb)
    status_cb("Memuat model Whisper...")
    progress_cb(0.0)
    model = WhisperModel(model_path, device="cpu", compute_type="int8")
    status_cb("Mentranskripsi audio (di CPU, bisa memakan waktu)...")
    segs_iter, info = model.transcribe(
        str(audio_path), language=None if language == "auto" else language,
        vad_filter=True, beam_size=1,
    )
    out = []
    for s in segs_iter:
        text = s.text.strip()
        if text:
            out.append({"start": round(s.start, 2), "end": round(s.end, 2), "text": text})
        progress_cb(min(s.end / duration, 1.0) if duration else 0.0)
    return out, info.language
