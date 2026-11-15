"""Tes end-to-end pipeline dengan transkripsi palsu (tanpa Whisper/jaringan). Hanya untuk pengujian."""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tests.test_core import fake_segments  # noqa: E402


class TestPipeline(unittest.TestCase):
    def test_full_flow(self):
        tmp = Path(tempfile.mkdtemp())
        import app.config as cfg
        cfg.STORAGE_DIR, cfg.JOBS_DIR, cfg.DB_PATH = tmp, tmp / "jobs", tmp / "t.db"
        import app.database as db
        db.DB_PATH = cfg.DB_PATH
        from app.services import pipeline, video
        pipeline.JOBS_DIR = cfg.JOBS_DIR
        cfg.JOBS_DIR.mkdir(parents=True)
        db.init_db()
        d = cfg.JOBS_DIR / ("a" * 32)
        d.mkdir()
        src = d / "source.mp4"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=640x360:rate=15:duration=130",
                        "-f", "lavfi", "-i", "sine=duration=130", "-c:v", "libx264", "-preset", "ultrafast",
                        "-c:a", "aac", "-shortest", str(src)], check=True)
        jid = "a" * 32
        db.create_job(jid, "x.mp4", src.stat().st_size, ".mp4", 130.0)
        db.update_job(jid, settings={"mode": "professional", "language": "id", "whisper_model": "tiny", "clip_count": 2,
                                     "min_duration": 20, "max_duration": 40, "aspect": "9:16", "resolution": "720p", "subtitles": True})
        segs, _ = fake_segments()
        segs = [s for s in segs if s["end"] < 130]
        with mock.patch("app.services.transcription.transcribe", return_value=(segs, "id")):
            pipeline.run_analysis(jid)
        job = db.get_job(jid)
        self.assertEqual(job["status"], "awaiting_selection", job)
        cands = db.get_candidates(jid)
        self.assertTrue(cands)
        pipeline.run_render(jid, [c["id"] for c in cands])
        self.assertEqual(db.get_job(jid)["status"], "done")
        clips = db.get_clips(jid)
        self.assertEqual(len(clips), len(cands))
        self.assertTrue(all((d / c["filename"]).exists() for c in clips))
        self.assertFalse(list(d.glob("*.srt")))
        self.assertFalse((d / "audio.wav").exists())
        self.assertEqual(video.probe(d / clips[0]["filename"])["width"], 720)
        db.mark_interrupted()
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
