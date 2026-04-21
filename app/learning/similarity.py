"""
Motor de similitud local usando TF-IDF sobre fingerprints de elementos.
Sin APIs externas — solo scikit-learn.

Encuentra reparaciones pasadas similares al request actual y retorna
qué selector_qualities tuvieron éxito, para aplicar un boost de similitud.
"""
from app.learning.db import get_db

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False

MIN_SIMILARITY = 0.2   # umbral mínimo para considerar similitud útil
MAX_HISTORY   = 200    # límite de reparaciones pasadas a cargar


def _fingerprint(tag: str, text: str, intent: str) -> str:
    """
    Construye un texto de fingerprint para TF-IDF a partir del baseline.
    Cada campo se prefija para evitar colisiones entre vocabularios.
    """
    parts = [
        f"tag_{(tag or 'unknown').lower()}",
        f"intent_{(intent or 'none').lower().replace(' ', '_')}",
    ]
    for word in (text or "").lower().split():
        if len(word) >= 3:
            parts.append(f"txt_{word}")
    return " ".join(parts)


def find_similar_repairs(
    baseline_tag: str,
    baseline_text: str,
    baseline_intent: str,
    top_k: int = 5,
) -> list[dict]:
    """
    Retorna hasta top_k selector_qualities de reparaciones pasadas similares,
    ordenadas por similitud descendente.

    Formato de cada elemento:
      {
        "selector_quality": "SAFE_TESTID",
        "similarity": 0.87,
        "successes": 12,
      }
    """
    if not SKLEARN_AVAILABLE:
        return []

    query_fp = _fingerprint(baseline_tag, baseline_text, baseline_intent)

    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT r.baseline_tag, r.baseline_text, r.baseline_intent,
                   s.selector_quality,
                   COUNT(f.id) AS successes
            FROM repairs r
            JOIN suggestions s ON s.repair_id = r.id
            JOIN feedback f    ON f.suggestion_id = s.id
            WHERE f.success = 1
              AND s.selector_quality IS NOT NULL
            GROUP BY r.id, s.selector_quality
            ORDER BY successes DESC
            LIMIT ?
            """,
            (MAX_HISTORY,),
        ).fetchall()

    if not rows:
        return []

    past_fps = [
        _fingerprint(r["baseline_tag"], r["baseline_text"], r["baseline_intent"])
        for r in rows
    ]
    all_fps = [query_fp] + past_fps

    try:
        vec = TfidfVectorizer(min_df=1)
        matrix = vec.fit_transform(all_fps)
        sims = cosine_similarity(matrix[0:1], matrix[1:])[0]

        top_idx = sims.argsort()[::-1][:top_k]

        results: list[dict] = []
        seen: set[str] = set()

        for i in top_idx:
            if sims[i] < MIN_SIMILARITY:
                break
            quality = rows[i]["selector_quality"]
            if quality in seen:
                continue
            seen.add(quality)
            results.append(
                {
                    "selector_quality": quality,
                    "similarity": round(float(sims[i]), 3),
                    "successes": rows[i]["successes"],
                }
            )

        return results

    except Exception:
        return []
