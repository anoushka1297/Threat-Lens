"""
Shared SQLite layer for ThreatLens.

Both server.py and detector.py import this. SQLite in WAL mode handles the
two-process access (server writes 'pending' rows, detector updates them to
'done') without locking problems at this scale.

The DB is the single source of truth and persists across restarts — close the
laptop, reopen, every past event is still there.
"""

import sqlite3
import json
from datetime import datetime

DB_PATH = "threatlens.db"


def get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    # WAL lets a reader and a writer work at the same time — needed because
    # server.py and detector.py both touch this file.
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def init_db():
    conn = get_conn()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS events (
            id          TEXT PRIMARY KEY,   -- timestamp-based unique id
            filename    TEXT,               -- file in frames/
            created_at  TEXT,               -- ISO timestamp (sortable)
            time_label  TEXT,               -- HH:MM:SS for display
            status      TEXT DEFAULT 'pending',  -- pending | done | error
            source      TEXT,               -- esp32 | demo
            danger      INTEGER DEFAULT 0,  -- 0/1
            detections  TEXT,               -- JSON list of boxes
            descriptor  TEXT,               -- JSON dict (motion + action context)
            img_width   INTEGER,
            img_height  INTEGER,
            summary     TEXT                -- optional LLM summary, filled later
        )
        """
    )
    conn.commit()
    conn.close()


def add_pending(event_id, filename, source):
    """server.py calls this right after saving a frame to disk."""
    conn = get_conn()
    ts = datetime.now()
    conn.execute(
        "INSERT OR IGNORE INTO events (id, filename, created_at, time_label, status, source) "
        "VALUES (?, ?, ?, ?, 'pending', ?)",
        (event_id, filename, ts.isoformat(), ts.strftime("%H:%M:%S"), source),
    )
    conn.commit()
    conn.close()


def fetch_pending():
    """detector.py grabs everything not yet processed, oldest first."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM events WHERE status='pending' ORDER BY created_at ASC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def mark_done(event_id, danger, detections, descriptor, img_width, img_height, summary=None):
    conn = get_conn()
    conn.execute(
        "UPDATE events SET status='done', danger=?, detections=?, descriptor=?, "
        "img_width=?, img_height=?, summary=? WHERE id=?",
        (
            1 if danger else 0,
            json.dumps(detections),
            json.dumps(descriptor),
            img_width,
            img_height,
            summary,
            event_id,
        ),
    )
    conn.commit()
    conn.close()


def mark_error(event_id):
    conn = get_conn()
    conn.execute("UPDATE events SET status='error' WHERE id=?", (event_id,))
    conn.commit()
    conn.close()


def get_events(limit=50):
    """Dashboard reads this (via server.py). Newest first, only finished ones."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM events WHERE status='done' ORDER BY created_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()

    out = []
    for r in rows:
        d = dict(r)
        d["detections"] = json.loads(d["detections"] or "[]")
        d["descriptor"] = json.loads(d["descriptor"] or "{}")
        out.append(d)
    return out
