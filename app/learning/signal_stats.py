"""
signal_stats.py — Capa 2: pesos adaptativos por señal.

Después de cada feedback actualiza la precisión acumulada de cada señal:

  precision = total_correct / total_present
    donde:
      total_present → veces que la señal disparó en CUALQUIER candidato del request
      total_correct → veces que la señal disparó en el candidato ELEGIDO

El bonus adaptativo es aditivo al score DOM existente:

  bonus = (precision - 0.5) * precision_scale
    precision = 0.95  →  bonus = +9 pts   (señal muy confiable para esta app)
    precision = 0.50  →  bonus =  0 pts   (neutro, datos insuficientes)
    precision = 0.20  →  bonus = -6 pts   (señal poco confiable)

Se activa solo cuando hay >= min_feedbacks acumulados (configurable en app-config.yml).
"""

import logging
from typing import Dict

from app.learning.db import LearningDB

log = logging.getLogger(__name__)

# Señales para las que tiene sentido aprender pesos.
# No incluimos señales que ya tienen validación binaria absoluta
# (ej: testid_match ya da +60 — el aprendizaje refina el resto).
ADAPTABLE_SIGNALS = [
    "tag_match",
    "testid_match",
    "datacy_match",
    "dataqa_match",
    "arialabel_match",
    "formcontrol_match",
    "name_match",
    "title_match",
    "datadisplay_match",
    "class_primary",
    "textHit",
    "text_exact",
    "intentBonus",
    "metaBonus",
    "visualBonus",
]


class SignalStatsManager:
    """
    Gestiona la Capa 2: pesos adaptativos basados en historial de feedback.
    """

    def __init__(self, db: LearningDB, precision_scale: int = 20) -> None:
        self._db = db
        self._scale = precision_scale

    def get_adaptive_bonuses(self) -> Dict[str, int]:
        """
        Retorna {signal_name: bonus_pts} para todas las señales con datos.
        Solo incluye señales con bonus != 0 para no contaminar el log.
        """
        try:
            stats = self._db.get_signal_stats()
            bonuses: Dict[str, int] = {}
            for name, row in stats.items():
                if name not in ADAPTABLE_SIGNALS:
                    continue
                precision = row.get("precision", 0.5)
                bonus = int((precision - 0.5) * self._scale)
                if bonus != 0:
                    bonuses[name] = bonus
            return bonuses
        except Exception as exc:
            log.error("get_adaptive_bonuses error: %s", exc)
            return {}

    def update_from_feedback(self, request_id: str, chosen_node_key: str) -> None:
        """
        Actualiza las estadísticas de señales basado en el feedback.

        Para cada señal adaptable:
          - Si disparó en ALGÚN candidato → incrementa total_present
          - Si disparó en el candidato ELEGIDO → incrementa total_correct
        """
        try:
            request = self._db.get_request(request_id)
            if not request:
                log.warning(
                    "update_from_feedback: request_id '%s' no encontrado en BD", request_id
                )
                return

            candidates = request.get("candidates") or []
            if not candidates:
                return

            # Señales del candidato ganador
            winner = next(
                (c for c in candidates if c.get("node_key") == chosen_node_key),
                None,
            )
            winner_signals = winner.get("signals", {}) if winner else {}

            # Carga las estadísticas actuales una sola vez
            current = self._db.get_signal_stats()

            for signal in ADAPTABLE_SIGNALS:
                # ¿Algún candidato disparó esta señal en este request?
                any_fired = any(
                    bool(c.get("signals", {}).get(signal)) for c in candidates
                )
                if not any_fired:
                    continue  # señal irrelevante para este request

                prev = current.get(signal, {})
                total_present = prev.get("total_present", 0) + 1
                winner_fired = bool(winner_signals.get(signal))
                total_correct = prev.get("total_correct", 0) + (1 if winner_fired else 0)

                precision = total_correct / total_present
                # weight_factor: reservado para multiplicación futura (hoy no se usa)
                weight_factor = 0.5 + precision

                self._db.upsert_signal_stat(
                    signal_name=signal,
                    total_present=total_present,
                    total_correct=total_correct,
                    precision=precision,
                    weight_factor=weight_factor,
                )

            log.info(
                "signal_stats actualizadas — request=%s winner=%s",
                request_id, chosen_node_key,
            )

        except Exception as exc:
            log.error("update_from_feedback error: %s", exc)
