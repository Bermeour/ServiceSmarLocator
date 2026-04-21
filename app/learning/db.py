<<<<<<< HEAD
"""
db.py — Gestión del SQLite de aprendizaje.

Tablas:
  repair_requests  → cada request con las señales por candidato
  repair_feedback  → feedback del cliente Java (qué localizador funcionó)
  signal_stats     → precisión acumulada por señal (Capa 2)
  app_models       → modelos ML entrenados por fingerprint de app (Capa 3)
"""

import json
import logging
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

# DDL completo — ejecutado una sola vez al iniciar
_SCHEMA = """
CREATE TABLE IF NOT EXISTS repair_requests (
    request_id       TEXT PRIMARY KEY,
    timestamp        TEXT NOT NULL,
    app_name         TEXT,
    page_fingerprint TEXT,
    baseline_tag     TEXT,
    baseline_text    TEXT,
    -- JSON: [{node_key, score, signals:{...}}]
    candidates_json  TEXT
);

CREATE TABLE IF NOT EXISTS repair_feedback (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id       TEXT    NOT NULL,
    timestamp        TEXT    NOT NULL,
    chosen_node_key  TEXT,
    chosen_type      TEXT,
    chosen_value     TEXT,
    success          INTEGER DEFAULT 1,  -- 1 = exitoso, 0 = fallido
    FOREIGN KEY (request_id) REFERENCES repair_requests(request_id)
);

CREATE TABLE IF NOT EXISTS signal_stats (
    signal_name    TEXT PRIMARY KEY,
    total_present  INTEGER DEFAULT 0,   -- veces que disparó en cualquier candidato
    total_correct  INTEGER DEFAULT 0,   -- veces que disparó en el candidato elegido
    precision      REAL    DEFAULT 0.5, -- total_correct / total_present
    weight_factor  REAL    DEFAULT 1.0, -- para uso futuro de multiplicación
    last_updated   TEXT
);

CREATE TABLE IF NOT EXISTS app_models (
    app_fingerprint  TEXT PRIMARY KEY,
    model_blob       BLOB,              -- modelo serializado con pickle
    training_samples INTEGER DEFAULT 0,
    accuracy         REAL    DEFAULT 0.0,
    last_trained     TEXT
=======
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
>>>>>>> be7d4dfb52b608334adb987da85aab23e3186faa
);
"""


<<<<<<< HEAD
class LearningDB:
    """
    Acceso centralizado a la base de datos SQLite de aprendizaje.
    Thread-safe mediante lock por escritura y WAL mode.
    """

    def __init__(self, db_path: str) -> None:
        self._path = db_path
        self._lock = threading.Lock()
        self._init_db()

    # ── Inicialización ────────────────────────────────────────────────────────

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")   # permite lecturas concurrentes
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self) -> None:
        """Crea las tablas si no existen. Se llama una sola vez al construir."""
        Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            conn = self._connect()
            try:
                conn.executescript(_SCHEMA)
                conn.commit()
                log.info("LearningDB inicializada en '%s'", self._path)
            finally:
                conn.close()

    # ── repair_requests ───────────────────────────────────────────────────────

    def save_request(
        self,
        request_id: str,
        app_name: str,
        page_fingerprint: str,
        baseline_tag: str,
        baseline_text: str,
        candidates: List[Dict[str, Any]],
    ) -> None:
        """Guarda el request con las señales de cada candidato evaluado."""
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """INSERT OR REPLACE INTO repair_requests
                       (request_id, timestamp, app_name, page_fingerprint,
                        baseline_tag, baseline_text, candidates_json)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        request_id,
                        datetime.utcnow().isoformat(),
                        app_name or "",
                        page_fingerprint or "",
                        baseline_tag or "",
                        baseline_text or "",
                        json.dumps(candidates, default=str),
                    ),
                )
                conn.commit()
            except Exception as exc:
                log.error("save_request error: %s", exc)
            finally:
                conn.close()

    def get_request(self, request_id: str) -> Optional[Dict]:
        """Retorna el request con su lista de candidatos deserializada."""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM repair_requests WHERE request_id = ?", (request_id,)
            ).fetchone()
            if row:
                d = dict(row)
                d["candidates"] = json.loads(d.get("candidates_json") or "[]")
                return d
            return None
        finally:
            conn.close()

    # ── repair_feedback ───────────────────────────────────────────────────────

    def save_feedback(
        self,
        request_id: str,
        chosen_node_key: str,
        chosen_type: str,
        chosen_value: str,
        success: bool = True,
    ) -> None:
        """Registra qué localizador usó finalmente el cliente Java."""
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """INSERT INTO repair_feedback
                       (request_id, timestamp, chosen_node_key,
                        chosen_type, chosen_value, success)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        request_id,
                        datetime.utcnow().isoformat(),
                        chosen_node_key or "",
                        chosen_type or "",
                        chosen_value or "",
                        1 if success else 0,
                    ),
                )
                conn.commit()
            except Exception as exc:
                log.error("save_feedback error: %s", exc)
            finally:
                conn.close()

    def get_total_feedbacks(self) -> int:
        """Cuenta feedbacks exitosos acumulados (para decidir si activar capas)."""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM repair_feedback WHERE success = 1"
            ).fetchone()
            return row["cnt"] if row else 0
        finally:
            conn.close()

    # ── signal_stats ──────────────────────────────────────────────────────────

    def get_signal_stats(self) -> Dict[str, Dict]:
        """Retorna todas las filas de signal_stats como {signal_name: {...}}."""
        conn = self._connect()
        try:
            rows = conn.execute("SELECT * FROM signal_stats").fetchall()
            return {r["signal_name"]: dict(r) for r in rows}
        finally:
            conn.close()

    def upsert_signal_stat(
        self,
        signal_name: str,
        total_present: int,
        total_correct: int,
        precision: float,
        weight_factor: float,
    ) -> None:
        """Inserta o actualiza la estadística de una señal."""
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """INSERT INTO signal_stats
                       (signal_name, total_present, total_correct,
                        precision, weight_factor, last_updated)
                       VALUES (?, ?, ?, ?, ?, ?)
                       ON CONFLICT(signal_name) DO UPDATE SET
                           total_present = excluded.total_present,
                           total_correct = excluded.total_correct,
                           precision     = excluded.precision,
                           weight_factor = excluded.weight_factor,
                           last_updated  = excluded.last_updated""",
                    (
                        signal_name,
                        total_present,
                        total_correct,
                        precision,
                        weight_factor,
                        datetime.utcnow().isoformat(),
                    ),
                )
                conn.commit()
            except Exception as exc:
                log.error("upsert_signal_stat error: %s", exc)
            finally:
                conn.close()

    # ── training data ─────────────────────────────────────────────────────────

    def get_training_data(self, app_fingerprint: Optional[str] = None) -> List[Dict]:
        """
        Retorna pares (request, feedback) para entrenamiento ML.
        Si app_fingerprint se especifica, filtra por esa app.
        """
        conn = self._connect()
        try:
            if app_fingerprint:
                rows = conn.execute(
                    """SELECT r.candidates_json, r.page_fingerprint, f.chosen_node_key
                       FROM repair_requests r
                       JOIN repair_feedback f ON r.request_id = f.request_id
                       WHERE r.page_fingerprint = ? AND f.success = 1""",
                    (app_fingerprint,),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT r.candidates_json, r.page_fingerprint, f.chosen_node_key
                       FROM repair_requests r
                       JOIN repair_feedback f ON r.request_id = f.request_id
                       WHERE f.success = 1"""
                ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    # ── app_models ────────────────────────────────────────────────────────────

    def save_model(
        self,
        app_fingerprint: str,
        model_blob: bytes,
        training_samples: int,
        accuracy: float,
    ) -> None:
        """Persiste un modelo entrenado serializado con pickle."""
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """INSERT INTO app_models
                       (app_fingerprint, model_blob, training_samples,
                        accuracy, last_trained)
                       VALUES (?, ?, ?, ?, ?)
                       ON CONFLICT(app_fingerprint) DO UPDATE SET
                           model_blob       = excluded.model_blob,
                           training_samples = excluded.training_samples,
                           accuracy         = excluded.accuracy,
                           last_trained     = excluded.last_trained""",
                    (
                        app_fingerprint,
                        model_blob,
                        training_samples,
                        accuracy,
                        datetime.utcnow().isoformat(),
                    ),
                )
                conn.commit()
            except Exception as exc:
                log.error("save_model error: %s", exc)
            finally:
                conn.close()

    def get_model(self, app_fingerprint: str) -> Optional[Dict]:
        """Retorna la fila de app_models para el fingerprint dado."""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM app_models WHERE app_fingerprint = ?",
                (app_fingerprint,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def get_all_models(self) -> List[Dict]:
        """Retorna resumen de todos los modelos entrenados (sin el blob)."""
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT app_fingerprint, training_samples, accuracy, last_trained FROM app_models"
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_total_feedbacks_by_fingerprint(self, app_fingerprint: str) -> int:
        """Cuenta feedbacks exitosos para una app específica."""
        conn = self._connect()
        try:
            row = conn.execute(
                """SELECT COUNT(*) AS cnt FROM repair_feedback f
                   JOIN repair_requests r ON f.request_id = r.request_id
                   WHERE f.success = 1 AND r.page_fingerprint = ?""",
                (app_fingerprint,),
            ).fetchone()
            return row["cnt"] if row else 0
        finally:
            conn.close()
=======
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
>>>>>>> be7d4dfb52b608334adb987da85aab23e3186faa
