"""Pekerjaan latar belakang: transkripsi -> highlight -> render. Satu pekerja (CPU terbatas)."""
import json
import logging
import shutil
from concurrent.futures import ThreadPoolExecutor

from .. import database as db
from ..config import JOBS_DIR
from . import highlights, subtitles, transcription, video

log = logging.getLogger("clipstudio")
_executor = ThreadPoolExecutor(max_workers=1)


class PipelineError(Exception):
    pass


def submit_analysis(job_id):
    _executor.submit(run_analysis, job_id)


def submit_render(job_id, ids):
    _executor.submit(run_render_safe, job_id, ids)


def _throttled(job_id):
    last = {"v": -1.0}

    def cb(p):
        if abs(p - last["v"]) >= 0.01 or p >= 1.0:
            last["v"] = p
            db.update_job(job_id, progress=round(p, 3))
    return cb


def _friendly(e):
    if isinstance(e, (PipelineError, video.VideoError, transcription.TranscriptionError)):
        return str(e)
    return "Terjadi kesalahan tak terduga saat memproses video. Lihat log server untuk detailnya."


def _clean_outputs(job_dir):
    for f in job_dir.glob("clip_*"):
        f.unlink(missing_ok=True)
    (job_dir / "clips.zip").unlink(missing_ok=True)


def run_analysis(job_id):
    try:
        job = db.get_job(job_id)
        st = job["settings"]
        d = JOBS_DIR / job_id
        src = d / f"source{job['ext']}"
        db.clear_results(job_id)
        _clean_outputs(d)
        db.update_job(job_id, status="transcribing", progress=0, message="Menyiapkan audio...", error=None)
        audio = d / "audio.wav"
        video.extract_audio(src, audio)
        try:
            segs, lang = transcription.transcribe(
                audio, st["whisper_model"], st["language"], job["duration"],
                _throttled(job_id), lambda m: db.update_job(job_id, message=m))
        finally:
            audio.unlink(missing_ok=True)
        if not segs:
            raise PipelineError("Tidak ada ucapan yang terdeteksi di video ini.")
        (d / "transcript.json").write_text(json.dumps({"language": lang, "segments": segs}, ensure_ascii=False))

        db.update_job(job_id, status="analyzing", progress=0.5, language=lang,
                      message="Mencari momen menarik dari transkrip...")
        if st["mode"] == "adaptive":
            p = highlights.adaptive_params(job["duration"])
            st = {**st, **p}
            db.update_job(job_id, settings=st)
        cands = highlights.find_highlights(segs, job["duration"], st["clip_count"],
                                           st["min_duration"], st["max_duration"])
        if not cands:
            raise PipelineError("Tidak ditemukan kandidat klip. Coba durasi yang berbeda.")
        ids = db.add_candidates(job_id, cands)
        if st["mode"] == "adaptive":
            run_render(job_id, ids)
        else:
            db.update_job(job_id, status="awaiting_selection", progress=1,
                          message="Pilih kandidat klip yang ingin dirender.")
    except Exception as e:
        log.exception("Analisis gagal untuk job %s", job_id)
        db.update_job(job_id, status="error", error=_friendly(e), message="Gagal")


def run_render_safe(job_id, ids):
    try:
        run_render(job_id, ids)
    except Exception as e:
        log.exception("Render gagal untuk job %s", job_id)
        db.update_job(job_id, status="error", error=_friendly(e), message="Gagal")


def run_render(job_id, candidate_ids):
    job = db.get_job(job_id)
    st = job["settings"]
    d = JOBS_DIR / job_id
    src = d / f"source{job['ext']}"
    segs = json.loads((d / "transcript.json").read_text())["segments"]
    cands = {c["id"]: c for c in db.get_candidates(job_id)}
    chosen = sorted((cands[i] for i in candidate_ids), key=lambda c: c["start_s"])
    db.clear_clips(job_id)
    _clean_outputs(d)
    total = len(chosen)
    db.update_job(job_id, status="rendering", progress=0, error=None, message=f"Merender klip 1 dari {total}")
    for n, c in enumerate(chosen, 1):
        srt_name = None
        if st["subtitles"]:
            srt = subtitles.build_srt(segs, c["start_s"], c["end_s"], st["aspect"])
            if srt.strip():
                srt_name = f"clip_{n:02d}.srt"
                (d / srt_name).write_text(srt, encoding="utf-8")
        out = d / f"clip_{n:02d}.mp4"
        cb = _throttled(job_id)
        db.update_job(job_id, message=f"Merender klip {n} dari {total}")
        video.render_clip(src, out, c["start_s"], c["end_s"], st["aspect"], st["resolution"], d,
                          srt_name, lambda f, n=n: cb((n - 1 + f) / total))
        if srt_name:
            (d / srt_name).unlink(missing_ok=True)
        db.add_clip(job_id, c["id"], n, out.name, c["start_s"], c["end_s"], out.stat().st_size)
    db.update_job(job_id, status="done", progress=1, message="Selesai")


def remove_job_files(job_id):
    shutil.rmtree(JOBS_DIR / job_id, ignore_errors=True)
