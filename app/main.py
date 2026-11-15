import re
import shutil
import uuid
import zipfile
import json
from urllib.parse import urlparse, parse_qs
from urllib.request import Request as URLRequest, urlopen
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import database as db
from .config import (ALLOWED_EXT, JOBS_DIR, MAX_UPLOAD_MB, MAX_VIDEO_MINUTES, STATIC_DIR,
                     WHISPER_MODELS, ensure_dirs)
from .models import RenderRequest, Settings
from .services import pipeline, transcription, video

ID_RE = re.compile(r"[0-9a-f]{32}")


@asynccontextmanager
async def lifespan(app):
    ensure_dirs()
    db.init_db()
    db.mark_interrupted()
    for part in JOBS_DIR.glob("*/source.part"):  # sisa upload yang gagal
        shutil.rmtree(part.parent, ignore_errors=True)
    for j in db.list_jobs():  # folder hilang -> bersihkan baris DB
        if not (JOBS_DIR / j["id"]).exists():
            db.delete_job(j["id"])
    yield


app = FastAPI(title="AI Clip Studio", lifespan=lifespan)


def _job(job_id):
    job = db.get_job(job_id) if ID_RE.fullmatch(job_id) else None
    if not job:
        raise HTTPException(404, "Pekerjaan tidak ditemukan.")
    return job


def _detail(job):
    d = dict(job)
    d["candidates"] = db.get_candidates(job["id"])
    d["clips"] = db.get_clips(job["id"])
    d["has_transcript"] = (JOBS_DIR / job["id"] / "transcript.json").exists()
    return d


@app.get("/api/health")
def health():
    return {
        "ffmpeg": video.have_ffmpeg(),
        "faster_whisper": transcription.whisper_installed(),
        "models_cached": {m: transcription.model_cached(m) for m in WHISPER_MODELS},
        "max_upload_mb": MAX_UPLOAD_MB,
        "max_video_minutes": MAX_VIDEO_MINUTES,
        "formats": sorted(ALLOWED_EXT),
    }


@app.put("/api/upload")
async def upload(request: Request, filename: str = "video.mp4"):
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(400, "Format tidak didukung. Gunakan MP4, MOV, atau MKV.")
    limit = MAX_UPLOAD_MB * 1024 * 1024
    cl = request.headers.get("content-length")
    if cl and cl.isdigit() and int(cl) > limit:
        raise HTTPException(413, f"File terlalu besar. Batas upload {MAX_UPLOAD_MB} MB.")
    job_id = uuid.uuid4().hex
    job_dir = JOBS_DIR / job_id
    job_dir.mkdir(parents=True)
    part, dest, size = job_dir / "source.part", job_dir / f"source{ext}", 0
    try:
        with open(part, "wb") as f:
            async for chunk in request.stream():
                size += len(chunk)
                if size > limit:
                    raise HTTPException(413, f"File terlalu besar. Batas upload {MAX_UPLOAD_MB} MB.")
                f.write(chunk)
        if size == 0:
            raise HTTPException(400, "File kosong.")
        part.rename(dest)
        info = await run_in_threadpool(video.probe, dest)
        if info["duration"] > MAX_VIDEO_MINUTES * 60:
            raise HTTPException(400, f"Video terlalu panjang. Batas {MAX_VIDEO_MINUTES} menit.")
    except HTTPException:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise
    except video.VideoError as e:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise HTTPException(400, str(e))
    except Exception:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise HTTPException(500, "Upload gagal atau terputus. Silakan coba lagi.")
    db.create_job(job_id, Path(filename).name[:200], size, ext, info["duration"])
    return _detail(db.get_job(job_id))



@app.post("/api/youtube/preview")
async def youtube_preview(request: Request):
    """Validate a YouTube URL and fetch public oEmbed metadata only.

    This endpoint deliberately does not download YouTube media. Users should
    upload a source file they own or are authorized to process.
    """
    try:
        body = await request.json()
        raw_url = str(body.get("url", "")).strip()
    except Exception:
        raise HTTPException(400, "Kirim URL YouTube yang valid.")
    parsed = urlparse(raw_url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or host not in {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be", "www.youtu.be"}:
        raise HTTPException(400, "Gunakan URL https://youtube.com/watch atau https://youtu.be.")
    if host.endswith("youtu.be"):
        video_id = parsed.path.strip("/").split("/")[0]
    else:
        video_id = parse_qs(parsed.query).get("v", [""])[0]
        if not video_id and parsed.path.startswith("/shorts/"):
            video_id = parsed.path.split("/shorts/", 1)[1].split("/", 1)[0]
    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id or ""):
        raise HTTPException(400, "ID video YouTube tidak dikenali.")
    oembed = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
    try:
        req = URLRequest(oembed, headers={"User-Agent": "AI-Clip-Studio/1.0"})
        with urlopen(req, timeout=8) as response:
            data = json.loads(response.read(512 * 1024).decode("utf-8"))
        return {"video_id": video_id, "url": f"https://www.youtube.com/watch?v={video_id}",
                "title": data.get("title", "Video YouTube"),
                "author": data.get("author_name", ""),
                "thumbnail": data.get("thumbnail_url", ""),
                "media_imported": False,
                "notice": "Metadata berhasil dibaca. Video YouTube belum diunduh. Untuk memprosesnya, unggah file sumber yang Anda miliki atau berhak gunakan."}
    except Exception:
        raise HTTPException(422, "Metadata tidak dapat diakses. Video mungkin privat, dibatasi, atau tidak tersedia. Anda dapat mengunggah file video secara langsung.")


@app.get("/api/jobs")
def jobs():
    return db.list_jobs()


@app.get("/api/jobs/{job_id}")
def job_detail(job_id: str):
    return _detail(_job(job_id))


@app.delete("/api/jobs/{job_id}")
def delete(job_id: str):
    job = _job(job_id)
    if job["status"] in db.RUNNING:
        raise HTTPException(409, "Pekerjaan sedang diproses dan belum bisa dihapus.")
    db.delete_job(job_id)
    pipeline.remove_job_files(job_id)
    return {"ok": True}


@app.post("/api/jobs/{job_id}/start")
def start(job_id: str, settings: Settings):
    job = _job(job_id)
    if job["status"] not in ("uploaded", "error"):
        raise HTTPException(409, "Pekerjaan ini sudah dimulai.")
    if not transcription.whisper_installed():
        raise HTTPException(503, "faster-whisper belum terpasang. Jalankan ./setup.sh")
    db.update_job(job_id, status="queued", progress=0, message="Menunggu giliran...", error=None,
                  settings=settings.model_dump())
    pipeline.submit_analysis(job_id)
    return _detail(db.get_job(job_id))


@app.get("/api/jobs/{job_id}/transcript")
def transcript(job_id: str):
    _job(job_id)
    f = JOBS_DIR / job_id / "transcript.json"
    if not f.exists():
        raise HTTPException(404, "Transkrip belum tersedia.")
    return FileResponse(f, media_type="application/json")


@app.post("/api/jobs/{job_id}/render")
def render(job_id: str, body: RenderRequest):
    job = _job(job_id)
    if job["status"] not in ("awaiting_selection", "done"):
        raise HTTPException(409, "Pekerjaan belum siap untuk dirender.")
    valid = {c["id"] for c in db.get_candidates(job_id)}
    ids = list(dict.fromkeys(body.candidate_ids))
    if not set(ids) <= valid:
        raise HTTPException(400, "Ada kandidat klip yang tidak valid.")
    db.update_job(job_id, status="rendering", progress=0, message="Menunggu giliran render...", error=None)
    pipeline.submit_render(job_id, ids)
    return _detail(db.get_job(job_id))


def _clip_file(job_id, clip_id):
    _job(job_id)
    clip = next((c for c in db.get_clips(job_id) if c["id"] == clip_id), None)
    path = JOBS_DIR / job_id / clip["filename"] if clip else None
    if not clip or not path.exists():
        raise HTTPException(404, "Klip tidak ditemukan.")
    return clip, path


def _stem(job):
    return re.sub(r"[^\w\-]+", "_", Path(job["filename"]).stem)[:50] or "video"


@app.get("/api/jobs/{job_id}/clips/{clip_id}/preview")
def preview(job_id: str, clip_id: int):
    _, path = _clip_file(job_id, clip_id)
    return FileResponse(path, media_type="video/mp4")


@app.get("/api/jobs/{job_id}/clips/{clip_id}/download")
def download(job_id: str, clip_id: int):
    clip, path = _clip_file(job_id, clip_id)
    name = f"{_stem(_job(job_id))}_clip_{clip['number']:02d}.mp4"
    return FileResponse(path, media_type="video/mp4", filename=name)


@app.get("/api/jobs/{job_id}/download.zip")
def download_zip(job_id: str):
    job = _job(job_id)
    clips = db.get_clips(job_id)
    if not clips:
        raise HTTPException(404, "Belum ada klip.")
    zpath = JOBS_DIR / job_id / "clips.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_STORED) as z:
        for c in clips:
            z.write(JOBS_DIR / job_id / c["filename"], f"{_stem(job)}_clip_{c['number']:02d}.mp4")
    return FileResponse(zpath, media_type="application/zip", filename=f"{_stem(job)}_clips.zip")


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
