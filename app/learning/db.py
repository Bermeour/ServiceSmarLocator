import os
import sqlite3
from contextlib import contextmanager

DB_PATH = os.environ.get("REPAIR_DB_PATH", "repair_learning.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id          TEXT PRIMARY KEY,
    created_at  TEXT NOT NULL,
    app_domain  TEXT,
    total_repairs  INTEGER DEFAULT 0,
    total_feedback INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS repairs (
    id              TEXT PRIMARY KEY,
    session_id      TEXT,
    page_hash       TEXT,
    baseline_tag    TEXT,
    baseline_text   TEXT,
    baseline_intent TEXT,
    created_at      TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE TABLE IF NOT EXISTS suggestions (
    id               TEXT PRIMARY KEY,
    repair_id        TEXT NOT NULL,
    session_id       TEXT,
    locator_type     TEXT,
    locator_value    TEXT,
    score            INTEGER,
    selector_quality TEXT,
    rank             INTEGER,
    FOREIGN KEY (repair_id) REFERENCES repairs(id)
);

CREATE TABLE IF NOT EXISTS feedback (
    id            TEXT PRIMARY KEY,
    suggestion_id TEXT NOT NULL,
    session_id    TEXT,
    success       INTEGER NOT NULL,
    created_at    TEXT NOT NULL,
    FOREIGN KEY (suggestion_id) REFERENCES suggestions(id)
);

CREATE TABLE IF NOT EXISTS weights (
    selector_quality TEXT NOT NULL,
    app_domain       TEXT NOT NULL DEFAULT 'global',
    alpha            REAL NOT NULL DEFAULT 1.0,
    beta             REAL NOT NULL DEFAULT 1.0,
    updated_at       TEXT NOT NULL,
    PRIMARY KEY (selector_quality, app_domain)
);
"""


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
