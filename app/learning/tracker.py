"""
tracker.py — Seguimiento de requests y generación de fingerprints de app.

El RequestTracker:
  1. Genera un fingerprint ligero de la página (identifica la app sin guardar HTML).
  2. Persiste el request con el vector de señales de cada candidato evaluado.
     Esos datos son los que usa SignalStatsManager y RepairModelManager para aprender.
"""

import hashlib
import logging
from typing import Any, Dict, List

from bs4 import BeautifulSoup

from app.learning.db import LearningDB

log = logging.getLogger(__name__)

# Señales que se almacenan por candidato.
# Deben coincidir con las claves del meta dict en ScoreEngine.score().
TRACKED_SIGNALS = [
    "tag_match", "testid_match", "datacy_match", "dataqa_match",
    "arialabel_match", "formcontrol_match", "name_match", "title_match",
    "datadisplay_match", "class_primary",
    "textHit", "text_exact", "fuzzyScore",
    "textContainsMatched", "textContainsTotal",
    "intentBonus", "metaBonus", "visualBonus",
    "zonePenalty",
]


class RequestTracker:
    """
    Registra cada request de repair con sus candidatos y señales,
    para que el sistema de aprendizaje pueda correlacionar con el feedback posterior.
    """

    def __init__(self, db: LearningDB) -> None:
        self._db = db

    def track(
        self,
        request_id: str,
        app_name: str,
        soup: BeautifulSoup,
        baseline_tag: str,
        baseline_text: str,
        candidates_signals: List[Dict[str, Any]],
    ) -> None:
        """
        Guarda el request en la BD.

        candidates_signals: lista de dicts con estructura:
          {
            "node_key": "id:btn-login",
            "score":    85,
            "signals":  { "tag_match": True, "testid_match": True, ... }
          }
        """
        try:
            fingerprint = self.get_page_fingerprint(soup, app_name)
            self._db.save_request(
                request_id=request_id,
                app_name=app_name,
                page_fingerprint=fingerprint,
                baseline_tag=baseline_tag,
                baseline_text=baseline_text,
                candidates=candidates_signals,
            )
            log.debug(
                "Request %s tracked: app=%s fp=%s candidates=%d",
                request_id, app_name, fingerprint, len(candidates_signals),
            )
        except Exception as exc:
            # El tracking nunca debe romper el flujo principal
            log.error("RequestTracker.track error: %s", exc)

    def get_page_fingerprint(self, soup: BeautifulSoup, app_name: str = "") -> str:
        """
        Genera un fingerprint MD5 de 12 chars a partir de:
          - app_name
          - título de la página
          - tags de primer nivel dentro de <body>
          - conteo de botones, inputs y formularios

        Es estable entre visitas a la misma página y no guarda contenido sensible.
        """
        try:
            parts = [app_name or ""]

            # Título de la página
            title_el = soup.find("title")
            parts.append(title_el.get_text(strip=True) if title_el else "")

            # Estructura de primer nivel del body (máx 10 tags)
            body = soup.find("body")
            if body:
                top_tags = [
                    child.name
                    for child in body.children
                    if hasattr(child, "name") and child.name
                ][:10]
                parts.append(",".join(top_tags))

            # Conteo de elementos interactivos — diferencia entre tipos de UI
            parts.append(f"btn={len(soup.find_all('button'))}")
            parts.append(f"inp={len(soup.find_all('input'))}")
            parts.append(f"frm={len(soup.find_all('form'))}")

            raw = "|".join(parts)
            return hashlib.md5(raw.encode("utf-8")).hexdigest()[:12]

        except Exception as exc:
            log.debug("get_page_fingerprint error: %s", exc)
            # Fallback: fingerprint solo por app_name
            return hashlib.md5((app_name or "unknown").encode()).hexdigest()[:12]
