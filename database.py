import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone

from .config import DB_PATH

_lock = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs(
  id TEXT PRIMARY KEY, filename TEXT, size INTEGER, ext TEXT, duration REAL,
  status TEXT, progress REAL DEFAULT 0, message TEXT, error TEXT,
  language TEXT, settings TEXT, created_at TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS candidates(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id TEXT REFERENCES jobs(id) ON DELETE CASCADE,
  start_s REAL, end_s REAL, score REAL, reason TEXT, text TEXT);
CREATE TABLE IF NOT EXISTS clips(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id TEXT REFERENCES jobs(id) ON DELETE CASCADE,
  candidate_id INTEGER, number INTEGER, filename TEXT,
  start_s REAL, end_s REAL, size INTEGER);
"""
JOB_FIELDS = {"status", "progress", "message", "error", "language", "settings", "duration"}
RUNNING = ("queued", "transcribing", "analyzing", "rendering")


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def db():
    with _lock:
        conn = sqlite3.connect(DB_PATH, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()


def init_db():
    with db() as c:
        c.execute("PRAGMA journal_mode=WAL")
        c.executescript(SCHEMA)


def _job(row):
    if row is None:
        return None
    d = dict(row)
    d["settings"] = json.loads(d["settings"]) if d.get("settings") else {}
    return d


def create_job(job_id, filename, size, ext, duration):
    with db() as c:
        c.execute(
            "INSERT INTO jobs(id,filename,size,ext,duration,status,progress,message,created_at,updated_at)"
            " VALUES(?,?,?,?,?,?,?,?,?,?)",
            (job_id, filename, size, ext, duration, "uploaded", 0, "Video siap diproses", _now(), _now()),
        )


def get_job(job_id):
    with db() as c:
        return _job(c.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone())


def list_jobs():
    with db() as c:
        return [_job(r) for r in c.execute("SELECT * FROM jobs ORDER BY created_at DESC").fetchall()]


def update_job(job_id, **fields):
    bad = set(fields) - JOB_FIELDS
    if bad:
        raise ValueError(f"Kolom tidak valid: {bad}")
    if "settings" in fields:
        fields["settings"] = json.dumps(fields["settings"])
    cols = ", ".join(f"{k}=?" for k in fields)
    with db() as c:
        c.execute(f"UPDATE jobs SET {cols}, updated_at=? WHERE id=?", (*fields.values(), _now(), job_id))


def delete_job(job_id):
    with db() as c:
        c.execute("DELETE FROM jobs WHERE id=?", (job_id,))


def mark_interrupted():
    with db() as c:
        q = ",".join("?" * len(RUNNING))
        c.execute(
            f"UPDATE jobs SET status='error', error=?, message='Gagal' WHERE status IN ({q})",
            ("Proses terhenti karena server dimulai ulang. Silakan coba lagi.", *RUNNING),
        )


def clear_results(job_id):
    with db() as c:
        c.execute("DELETE FROM candidates WHERE job_id=?", (job_id,))
        c.execute("DELETE FROM clips WHERE job_id=?", (job_id,))


def clear_clips(job_id):
    with db() as c:
        c.execute("DELETE FROM clips WHERE job_id=?", (job_id,))


def add_candidates(job_id, cands):
    ids = []
    with db() as c:
        for x in cands:
            cur = c.execute(
                "INSERT INTO candidates(job_id,start_s,end_s,score,reason,text) VALUES(?,?,?,?,?,?)",
                (job_id, x["start"], x["end"], x["score"], x["reason"], x["text"]),
            )
            ids.append(cur.lastrowid)
    return ids


def get_candidates(job_id):
    with db() as c:
        rows = c.execute("SELECT * FROM candidates WHERE job_id=? ORDER BY start_s", (job_id,)).fetchall()
        return [dict(r) for r in rows]


def add_clip(job_id, candidate_id, number, filename, start, end, size):
    with db() as c:
        c.execute(
            "INSERT INTO clips(job_id,candidate_id,number,filename,start_s,end_s,size) VALUES(?,?,?,?,?,?,?)",
            (job_id, candidate_id, number, filename, start, end, size),
        )


def get_clips(job_id):
    with db() as c:
        rows = c.execute("SELECT * FROM clips WHERE job_id=? ORDER BY number", (job_id,)).fetchall()
        return [dict(r) for r in rows]
