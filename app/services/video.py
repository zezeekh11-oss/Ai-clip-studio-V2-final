"""Pemrosesan video via FFmpeg/FFprobe. Semua perintah dipanggil sebagai list argumen (tanpa shell)."""
import json
import shutil
import subprocess
from collections import deque
from pathlib import Path


class VideoError(Exception):
    pass


OUT_SIZES = {
    "9:16": {"720p": (720, 1280), "1080p": (1080, 1920)},
    "16:9": {"720p": (1280, 720), "1080p": (1920, 1080)},
    "1:1": {"720p": (720, 720), "1080p": (1080, 1080)},
}
# Ukuran font untuk skala ASS 384x288 (libass menskalakan ke tinggi video)
SUB_STYLE = {
    "9:16": "FontSize=11,MarginV=45",
    "1:1": "FontSize=14,MarginV=20",
    "16:9": "FontSize=15,MarginV=15",
}


def have_ffmpeg():
    return bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


def probe(path):
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
            capture_output=True, text=True, timeout=60,
        )
    except FileNotFoundError:
        raise VideoError("FFprobe tidak ditemukan. Jalankan ./setup.sh")
    except subprocess.TimeoutExpired:
        raise VideoError("Pemeriksaan file video melebihi batas waktu.")
    if r.returncode != 0:
        raise VideoError("File bukan video yang valid atau rusak.")
    data = json.loads(r.stdout or "{}")
    streams = data.get("streams", [])
    v = next((s for s in streams if s.get("codec_type") == "video"), None)
    a = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if v is None:
        raise VideoError("Tidak ditemukan aliran video pada file ini.")
    dur = float(data.get("format", {}).get("duration") or v.get("duration") or 0)
    if dur <= 0:
        raise VideoError("Durasi video tidak terbaca.")
    return {"duration": dur, "width": int(v.get("width", 0)), "height": int(v.get("height", 0)),
            "has_audio": a is not None}


def extract_audio(src, dst):
    r = subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(src), "-vn", "-ac", "1", "-ar", "16000",
         "-c:a", "pcm_s16le", str(dst)],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        raise VideoError("Gagal mengekstrak audio. Pastikan video memiliki suara.")


def render_clip(src, out, start, end, aspect, resolution, workdir, srt_name=None, progress_cb=None):
    """Potong + crop/scale + (opsional) bakar subtitle. srt_name = nama file SRT di dalam workdir."""
    w, h = OUT_SIZES[aspect][resolution]
    dur = max(0.1, end - start)
    vf = f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1"
    if srt_name:
        style = "Alignment=2,Bold=1,Outline=2,Shadow=0,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000," + SUB_STYLE[aspect]
        vf += f",subtitles={srt_name}:force_style='{style}'"
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-ss", f"{start:.3f}", "-i", str(Path(src).resolve()), "-t", f"{dur:.3f}",
        "-map", "0:v:0", "-map", "0:a:0?", "-vf", vf,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart",
        "-progress", "pipe:1", "-nostats", str(Path(out).resolve()),
    ]
    tail = deque(maxlen=8)
    try:
        p = subprocess.Popen(cmd, cwd=str(workdir), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    except FileNotFoundError:
        raise VideoError("FFmpeg tidak ditemukan. Jalankan ./setup.sh")
    for line in p.stdout:
        line = line.strip()
        if line.startswith("out_time_us=") or line.startswith("out_time_ms="):
            try:
                t = int(line.split("=")[1]) / 1_000_000
                if progress_cb:
                    progress_cb(min(t / dur, 1.0))
            except ValueError:
                pass
        elif "=" not in line:
            tail.append(line)
    p.stdout.close()
    if p.wait() != 0:
        raise VideoError("FFmpeg gagal merender klip: " + " | ".join(tail)[-300:])
    if progress_cb:
        progress_cb(1.0)
