import uuid
from datetime import datetime, timezone
from app.learning.db import get_db


def create_session(app_domain: str = None) -> dict:
    session_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        conn.execute(
            "INSERT INTO sessions (id, created_at, app_domain) VALUES (?, ?, ?)",
            (session_id, now, app_domain),
        )
    return {"session_id": session_id, "created_at": now, "app_domain": app_domain}


def get_session(session_id: str) -> dict | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
    return dict(row) if row else None


def increment_session_repairs(session_id: str):
    if not session_id:
        return
    with get_db() as conn:
        conn.execute(
            "UPDATE sessions SET total_repairs = total_repairs + 1 WHERE id = ?",
            (session_id,),
        )


def get_session_quality_stats(session_id: str) -> dict[str, dict]:
    """Retorna tasas de éxito por selector_quality dentro de esta sesión."""
    if not session_id:
        return {}
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT s.selector_quality,
                   SUM(f.success)  AS successes,
                   COUNT(f.id)     AS total
            FROM feedback f
            JOIN suggestions s ON f.suggestion_id = s.id
            WHERE f.session_id = ?
            GROUP BY s.selector_quality
            """,
            (session_id,),
        ).fetchall()
    return {
        row["selector_quality"]: {
            "successes": row["successes"] or 0,
            "total": row["total"] or 0,
        }
        for row in rows
        if row["selector_quality"]
    }
