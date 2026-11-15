# AI Clip Studio

Ubah video panjang menjadi klip pendek (YouTube Shorts / TikTok / Reels) secara otomatis.
Semua berjalan **lokal di server Anda**: tanpa API key, tanpa API berbayar, tanpa layanan AI eksternal.

Stack: FastAPI · HTML/CSS/JS · FFmpeg · faster-whisper (CPU) · SQLite.

## Cara kerja (jujur)
1. Audio diekstrak lalu ditranskripsi oleh Whisper (model `tiny`/`base`, CPU, int8).
2. Highlight dicari dengan **heuristik pada transkrip** (kalimat pembuka kuat, pertanyaan, kata penekanan, jeda/pergantian topik, kalimat utuh). Sistem **tidak memahami visual** video, dan skor bukan prediksi viral.
3. Klip dipotong di batas kalimat/jeda, di-crop ke rasio pilihan, subtitle dibakar (opsional) dengan FFmpeg. Audio asli dipertahankan, tanpa watermark.

## Instalasi di GitHub Codespaces (bisa dari HP Android)
1. Buat repo GitHub baru, unggah isi folder ini (atau unggah ZIP lalu ekstrak di Codespaces: `unzip ai-clip-studio.zip`).
2. Repo → **Code → Codespaces → Create codespace on main** (Ubuntu).
3. Di terminal Codespaces:
   ```bash
   cd ai-clip-studio
   chmod +x setup.sh start.sh
   ./setup.sh      # sekali saja: FFmpeg, venv, paket Python
   ./start.sh      # menjalankan aplikasi di port 8000
   ```
4. Buka tab **PORTS** → baris `8000` → ikon globe/“Open in Browser”. Jika diminta, ubah *Visibility* ke Public hanya bila Anda butuh membuka dari perangkat lain.
5. Model Whisper diunduh otomatis saat pertama dipakai (tiny ±75 MB, base ±145 MB); progres unduhan tampil di halaman Proses. Perlu internet hanya untuk unduhan itu.

## Import URL YouTube
- Tempel URL YouTube pada halaman Upload lalu pilih **Periksa URL** untuk memvalidasi tautan dan melihat metadata publik (judul/thumbnail).
- Aplikasi ini **tidak mengunduh media dari YouTube**. Metadata preview bukan berarti video sudah masuk ke pipeline. Untuk memproses video, gunakan file sumber yang Anda miliki atau memiliki izin untuk gunakan, lalu unggah melalui bagian Upload. Hormati ketentuan platform dan hak cipta.

## Menguji upload & pemrosesan
1. Siapkan video pendek berisi **ucapan** (1–5 menit untuk tes awal; musik saja tidak menghasilkan transkrip).
2. Dashboard harus menampilkan FFmpeg dan faster-whisper “Siap”.
3. Upload → Pengaturan (pilih **Adaptive**, model `tiny`, 720p) → Mulai → tunggu Proses → lihat Hasil, putar preview, unduh klip/ZIP.
4. Coba mode **Professional** untuk memilih kandidat klip sebelum render.
5. Tes otomatis (tanpa Whisper/jaringan): `python -m unittest discover -s tests -t . -v`

## Batas & performa (CPU)
- Upload maks **1024 MB**, video maks **120 menit** (ubah lewat env `MAX_UPLOAD_MB`, `MAX_VIDEO_MINUTES`). Codespaces gratis punya disk terbatas (±32 GB) — hapus pekerjaan lama lewat Riwayat.
- Hanya satu pekerjaan diproses sekali waktu (antre).
- Perkiraan kasar di 2 core CPU: transkripsi `tiny` ≈ 0,3–0,5× durasi audio, `base` ≈ 0,7–1× durasi; render 720p ≈ 0,3–1× durasi klip, 1080p lebih lambat. Ini perkiraan, bukan hasil pengukuran.
- RAM: `tiny` ±0,5–1 GB, `base` ±1–1,5 GB; pastikan Codespace minimal 4 GB RAM untuk video panjang.
- Bahasa: Indonesia & Inggris (atau deteksi otomatis). Akurasi `tiny` lebih rendah, terutama untuk bahasa Indonesia berisik.
- Tidak ada autentikasi: jangan buka port ke publik untuk umum.
- Server di-restart saat pekerjaan berjalan → pekerjaan ditandai gagal, bisa diulang.

## Struktur
```
app/ (main.py, config.py, database.py, models.py, services/{transcription,highlights,video,subtitles,pipeline}.py)
static/ (index.html, style.css, app.js)   storage/ (jobs, models, clipstudio.db)
tests/  setup.sh  start.sh  Dockerfile  requirements.txt
```
Docker (opsional): `docker build -t clipstudio . && docker run -p 8000:8000 -v $PWD/storage:/app/storage clipstudio`
