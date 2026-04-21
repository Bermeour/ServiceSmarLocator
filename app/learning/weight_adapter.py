"""
Pesos adaptativos por selector_quality usando distribución Beta bayesiana.

- alpha: éxitos acumulados + 1  (suavizado de Laplace)
- beta:  fallos acumulados  + 1
- tasa esperada = alpha / (alpha + beta)
- sin datos: alpha=1, beta=1 → tasa=0.5 → multiplicador=1.0  (neutro)
- muchos éxitos → tasa→1 → multiplicador→2.0  (boost fuerte)
- muchos fallos → tasa→0 → multiplicador→0.5  (penalización)

El multiplicador se aplica sobre el extra_bonus del selector en repair_service.
"""
from datetime import datetime, timezone

from app.learning.db import get_db

# Calidades conocidas (deben coincidir con selectors.py)
KNOWN_QUALITIES = {
    "SAFE_ID",
    "SAFE_TESTID",
    "SAFE_DATA_CY",
    "SAFE_DATA_QA",
    "SAFE_FORMCONTROL",
    "SAFE_NAME",
    "SAFE_ARIA",
    "SAFE_DATA_DISPLAY",
    "SAFE_TITLE",
    "ROLE",
    "DYNAMIC_ID_SUFFIX",
    "SCOPED_DYNAMIC_ID_SUFFIX",
    "FALLBACK_TEXT",
    "FALLBACK_CLASS",
}


def get_multipliers(
    app_domain: str = "global",
    session_stats: dict[str, dict] | None = None,
) -> dict[str, float]:
    """
    Retorna un multiplicador [0.5 .. 2.0] por cada selector_quality.
    Combina el prior global (DB) con las observaciones de la sesión activa.
    """
    global_weights = _load_global_weights(app_domain)
    multipliers: dict[str, float] = {}

    for quality in KNOWN_QUALITIES:
        alpha, beta = global_weights.get(quality, (1.0, 1.0))

        # Blend: prior global + observaciones de sesión (converge más rápido)
        if session_stats and quality in session_stats:
            s = session_stats[quality]
            alpha += s["successes"]
            beta += s["total"] - s["successes"]

        rate = alpha / (alpha + beta)          # 0 .. 1
        multiplier = 0.5 + (rate * 1.5)       # 0.5 .. 2.0
        multipliers[quality] = round(multiplier, 3)

    return multipliers


def update_weights(selector_quality: str, success: bool, app_domain: str = "global"):
    """Actualiza los parámetros bayesianos tras recibir feedback."""
    if not selector_quality or selector_quality not in KNOWN_QUALITIES:
        return

    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        row = conn.execute(
            "SELECT alpha, beta FROM weights WHERE selector_quality = ? AND app_domain = ?",
            (selector_quality, app_domain),
        ).fetchone()

        if row:
            alpha = row["alpha"] + (1.0 if success else 0.0)
            beta = row["beta"] + (0.0 if success else 1.0)
            conn.execute(
                "UPDATE weights SET alpha=?, beta=?, updated_at=? WHERE selector_quality=? AND app_domain=?",
                (alpha, beta, now, selector_quality, app_domain),
            )
        else:
            alpha = 2.0 if success else 1.0
            beta = 1.0 if success else 2.0
            conn.execute(
                "INSERT INTO weights (selector_quality, app_domain, alpha, beta, updated_at) VALUES (?,?,?,?,?)",
                (selector_quality, app_domain, alpha, beta, now),
            )


def get_all_weights(app_domain: str = "global") -> list[dict]:
    """Devuelve el estado actual de todos los pesos para inspección."""
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT selector_quality, alpha, beta, updated_at
            FROM weights
            WHERE app_domain = ?
            ORDER BY selector_quality
            """,
            (app_domain,),
        ).fetchall()

    result = []
    for row in rows:
        alpha, beta = row["alpha"], row["beta"]
        rate = alpha / (alpha + beta)
        result.append(
            {
                "selector_quality": row["selector_quality"],
                "alpha": alpha,
                "beta": beta,
                "success_rate": round(rate, 3),
                "multiplier": round(0.5 + rate * 1.5, 3),
                "updated_at": row["updated_at"],
            }
        )
    return result


# ---------------------------------------------------------------------------
# Interno
# ---------------------------------------------------------------------------

def _load_global_weights(app_domain: str) -> dict[str, tuple[float, float]]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT selector_quality, alpha, beta FROM weights WHERE app_domain = ?",
            (app_domain,),
        ).fetchall()
    return {row["selector_quality"]: (row["alpha"], row["beta"]) for row in rows}
