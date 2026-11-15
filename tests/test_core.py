import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.services import highlights, subtitles, video  # noqa: E402


def fake_segments():
    texts = [
        "Halo semua, selamat datang.", "Hari ini kita bahas hal biasa.", "Kenapa banyak orang gagal menabung?",
        "Ternyata kesalahan terbesarnya cuma satu.", "Mereka tidak mencatat pengeluaran.", "Padahal itu penting sekali!",
        "Coba bayangkan kalau kamu mencatat 30 hari.", "Hasilnya pasti berbeda.", "Itu saja untuk bagian ini.",
    ]
    segs, t = [], 0.0
    for i, x in enumerate(texts * 6):
        gap = 2.0 if i % 9 == 0 else 0.2
        segs.append({"start": t + gap, "end": t + gap + 5.0, "text": x})
        t += gap + 5.0
    return segs, t


class TestHighlights(unittest.TestCase):
    def test_candidates_valid(self):
        segs, total = fake_segments()
        c = highlights.find_highlights(segs, total, 3, 20, 60)
        self.assertTrue(1 <= len(c) <= 3)
        for x in c:
            self.assertGreaterEqual(x["end"] - x["start"], 19)
            self.assertLessEqual(x["end"] - x["start"], 61)
            self.assertTrue(x["reason"])
        for a, b in zip(c, c[1:]):
            self.assertLessEqual(a["end"], b["start"])

    def test_short_video_and_empty(self):
        self.assertEqual(highlights.find_highlights([], 10, 3, 20, 60), [])
        c = highlights.find_highlights([{"start": 0, "end": 5, "text": "Halo."}], 10, 3, 20, 60)
        self.assertEqual(len(c), 1)

    def test_adaptive_params(self):
        self.assertEqual(highlights.adaptive_params(60)["clip_count"], 3)
        self.assertEqual(highlights.adaptive_params(10000)["clip_count"], 8)


class TestSubtitles(unittest.TestCase):
    def test_srt_relative_times(self):
        segs = [{"start": 10, "end": 14, "text": "Ini kalimat yang cukup panjang untuk dipecah menjadi dua baris subtitle."}]
        srt = subtitles.build_srt(segs, 10, 14, "9:16")
        self.assertIn("00:00:00,000 -->", srt)
        self.assertIn("\n", srt.split("\n", 2)[2])
        self.assertEqual(subtitles.fmt_ts(3661.5), "01:01:01,500")

    def test_outside_clip_ignored(self):
        self.assertEqual(subtitles.build_srt([{"start": 0, "end": 5, "text": "x"}], 10, 20), "")


@unittest.skipUnless(video.have_ffmpeg(), "FFmpeg tidak tersedia")
class TestVideo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.src = cls.tmp / "src.mp4"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=1280x720:rate=25:duration=12",
                        "-f", "lavfi", "-i", "sine=frequency=440:duration=12", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                        "-c:a", "aac", "-shortest", str(cls.src)], check=True)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_probe(self):
        info = video.probe(self.src)
        self.assertAlmostEqual(info["duration"], 12, delta=1)
        self.assertTrue(info["has_audio"])

    def test_probe_invalid(self):
        bad = self.tmp / "bad.mp4"; bad.write_bytes(b"bukan video")
        with self.assertRaises(video.VideoError):
            video.probe(bad)

    def test_render_vertical_with_subs(self):
        out = self.tmp / "o.mp4"
        r = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True).stdout
        srt = None
        if " subtitles " in r:
            srt = "c.srt"; (self.tmp / srt).write_text(subtitles.build_srt([{"start": 2, "end": 6, "text": "Tes subtitle."}], 2, 8, "9:16"))
        prog = []
        video.render_clip(self.src, out, 2, 8, "9:16", "720p", self.tmp, srt, prog.append)
        info = video.probe(out)
        self.assertEqual((info["width"], info["height"]), (720, 1280))
        self.assertAlmostEqual(info["duration"], 6, delta=0.6)
        self.assertTrue(info["has_audio"])
        self.assertTrue(prog and prog[-1] == 1.0)

    def test_render_square(self):
        out = self.tmp / "sq.mp4"
        video.render_clip(self.src, out, 0, 4, "1:1", "720p", self.tmp)
        info = video.probe(out)
        self.assertEqual((info["width"], info["height"]), (720, 720))


if __name__ == "__main__":
    unittest.main(verbosity=2)
