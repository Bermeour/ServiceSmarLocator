import hashlib
import uuid
from datetime import datetime, timezone

from app.learning.db import get_db


def save_repair(
    session_id: str | None,
    page_html: str,
    baseline_tag: str,
    baseline_text: str,
    baseline_intent: str,
) -> str:
    repair_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    page_hash = hashlib.sha256(page_html.encode()).hexdigest()[:16]
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO repairs
                (id, session_id, page_hash, baseline_tag, baseline_text, baseline_intent, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (repair_id, session_id, page_hash, baseline_tag, baseline_text, baseline_intent, now),
        )
    return repair_id


def save_suggestions(repair_id: str, session_id: str | None, suggestions: list[dict]) -> list[str]:
    """
    suggestions: lista de dicts con keys:
        type, value, score, selector_quality, rank
    Retorna lista de UUIDs asignados a cada sugerencia.
    """
    ids: list[str] = []
    with get_db() as conn:
        for s in suggestions:
            sid = str(uuid.uuid4())
            conn.execute(
                """
                INSERT INTO suggestions
                    (id, repair_id, session_id, locator_type, locator_value, score, selector_quality, rank)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    sid,
                    repair_id,
                    session_id,
                    s.get("type"),
                    s.get("value"),
                    s.get("score"),
                    s.get("selector_quality"),
                    s.get("rank"),
                ),
            )
            ids.append(sid)
    return ids


def save_feedback(suggestion_id: str, session_id: str | None, success: bool) -> dict:
    """
    Registra feedback para una sugerencia.
    Retorna el selector_quality asociado (necesario para actualizar weights).
    Lanza ValueError si suggestion_id no existe.
    """
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        row = conn.execute(
            "SELECT selector_quality FROM suggestions WHERE id = ?",
            (suggestion_id,),
        ).fetchone()
        if not row:
            raise ValueError(f"suggestion_id '{suggestion_id}' no encontrado")

        quality = row["selector_quality"]

        conn.execute(
            """
            INSERT INTO feedback (id, suggestion_id, session_id, success, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (str(uuid.uuid4()), suggestion_id, session_id, int(success), now),
        )

        if session_id:
            conn.execute(
                "UPDATE sessions SET total_feedback = total_feedback + 1 WHERE id = ?",
                (session_id,),
            )

    return {"selector_quality": quality, "success": success}
