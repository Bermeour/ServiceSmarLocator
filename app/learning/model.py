"""
model.py — Capa 3: modelo ML local (scikit-learn LogisticRegression).

Ciclo de vida:
  1. Se activa cuando hay >= min_samples feedbacks por app (configurable).
  2. Cada retrain_every feedbacks nuevos re-entrena el modelo.
  3. El score ML se mezcla con el score DOM: final = (1-blend)*dom + blend*(prob*100)
  4. El modelo serializado se guarda en SQLite (tabla app_models).

Feature vector (FEATURE_NAMES — orden fijo, no cambiar sin migrar):
  Ver constante FEATURE_NAMES más abajo.

Thread-safety: el cache de modelos en memoria usa dict por fingerprint.
  Los writes van a SQLite con lock en LearningDB.
"""

import io
import logging
import pickle
from typing import Dict, List, Optional, Tuple

from app.learning.db import LearningDB

log = logging.getLogger(__name__)

# Orden fijo de features.
# CRÍTICO: no reordenar sin migrar los modelos guardados en BD.
FEATURE_NAMES = [
    "tag_match",           # bool → 0/1
    "testid_match",        # bool → 0/1
    "datacy_match",        # bool → 0/1
    "dataqa_match",        # bool → 0/1
    "arialabel_match",     # bool → 0/1
    "formcontrol_match",   # bool → 0/1
    "name_match",          # bool → 0/1
    "title_match",         # bool → 0/1
    "textHit",             # bool → 0/1
    "text_exact",          # bool → 0/1
    "fuzzyScore",          # int 0-100 → normalizado 0.0-1.0
    "textContainsMatched", # int 0-N  → normalizado 0.0-1.0
    "intentBonus",         # int → bool (> 0)
    "metaBonus",           # int → bool (> 0)
    "visualBonus",         # int → bool (> 0)
    "class_primary",       # bool → 0/1
    "zone_negative",       # bool: True si zonePenalty < 0
]


def signals_to_features(signals: Dict) -> List[float]:
    """
    Convierte el dict de señales en un vector numérico para el modelo.
    Normaliza valores continuos al rango [0, 1].
    """
    tc_matched = int(signals.get("textContainsMatched", 0))
    tc_total = max(int(signals.get("textContainsTotal", 1)), 1)

    return [
        float(bool(signals.get("tag_match"))),
        float(bool(signals.get("testid_match"))),
        float(bool(signals.get("datacy_match"))),
        float(bool(signals.get("dataqa_match"))),
        float(bool(signals.get("arialabel_match"))),
        float(bool(signals.get("formcontrol_match"))),
        float(bool(signals.get("name_match"))),
        float(bool(signals.get("title_match"))),
        float(bool(signals.get("textHit"))),
        float(bool(signals.get("text_exact"))),
        min(float(signals.get("fuzzyScore", 0)), 100.0) / 100.0,
        tc_matched / tc_total,
        float(int(signals.get("intentBonus", 0)) > 0),
        float(int(signals.get("metaBonus", 0)) > 0),
        float(int(signals.get("visualBonus", 0)) > 0),
        float(bool(signals.get("class_primary"))),
        float(int(signals.get("zonePenalty", 0)) < 0),
    ]


class RepairModelManager:
    """
    Gestiona la Capa 3: modelo ML por app.

    - Decide cuándo entrenar (min_samples + retrain_every).
    - Aplica el blend entre score DOM y score ML.
    - Cachea modelos en memoria para evitar deserializar en cada request.
    """

    def __init__(
        self,
        db: LearningDB,
        min_samples: int = 100,
        retrain_every: int = 50,
        blend_factor: float = 0.7,
    ) -> None:
        self._db = db
        self._min_samples = min_samples
        self._retrain_every = retrain_every
        self._blend = blend_factor
        # Cache en memoria: {app_fingerprint: sklearn_pipeline}
        self._cache: Dict[str, object] = {}

    def apply(
        self,
        signals: Dict,
        app_fingerprint: str,
        dom_score: int,
    ) -> Tuple[int, Optional[str], float]:
        """
        Aplica el modelo ML si está disponible para esta app.

        Retorna (final_score, reason_or_None, confidence).
          confidence: probabilidad 0.0-1.0 de que el candidato sea correcto.
                      0.0 si el modelo no está disponible.
        """
        model = self._get_model(app_fingerprint)
        if model is None:
            return dom_score, None, 0.0

        try:
            features = [signals_to_features(signals)]
            # predict_proba retorna [[prob_clase_0, prob_clase_1]]
            prob_correct = float(model.predict_proba(features)[0][1])
            ml_score = int(prob_correct * 100)
            final = int((1.0 - self._blend) * dom_score + self._blend * ml_score)
            delta = final - dom_score
            reason = (
                f"ml_score={ml_score} blend={self._blend:.1f} "
                f"({'+'}{delta} vs DOM)"
            )
            return final, reason, round(prob_correct, 3)
        except Exception as exc:
            log.debug("RepairModelManager.apply predict error: %s", exc)
            return dom_score, None, 0.0

    def train_if_needed(self, app_fingerprint: str, total_feedbacks: int) -> bool:
        """
        Entrena el modelo si se cumplen los dos criterios:
          1. total_feedbacks >= min_samples
          2. total_feedbacks es múltiplo de retrain_every

        Retorna True si se entrenó.
        """
        if total_feedbacks < self._min_samples:
            return False
        if total_feedbacks % self._retrain_every != 0:
            return False
        return self._train(app_fingerprint)

    # ── privados ──────────────────────────────────────────────────────────────

    def _train(self, app_fingerprint: str) -> bool:
        """
        Entrena un Pipeline(StandardScaler + LogisticRegression) con los
        datos históricos de la app.

        Framing del problema: clasificación binaria por candidato.
          label = 1  si el candidato fue el elegido por la probe
          label = 0  si fue descartado
        """
        try:
            from sklearn.linear_model import LogisticRegression
            from sklearn.pipeline import Pipeline
            from sklearn.preprocessing import StandardScaler
            import numpy as np

            data = self._db.get_training_data(app_fingerprint)
            if len(data) < self._min_samples:
                log.info(
                    "_train: datos insuficientes para '%s' (%d < %d)",
                    app_fingerprint, len(data), self._min_samples,
                )
                return False

            X, y = [], []
            for record in data:
                candidates = record.get("candidates") or []
                # candidates_json puede venir como string si viene directo de la BD
                if isinstance(candidates, str):
                    import json
                    candidates = json.loads(candidates)
                chosen_key = record.get("chosen_node_key", "")

                for candidate in candidates:
                    signals = candidate.get("signals", {})
                    X.append(signals_to_features(signals))
                    y.append(1 if candidate.get("node_key") == chosen_key else 0)

            if len(set(y)) < 2:
                log.info(
                    "_train: solo una clase en los datos de '%s', no se entrena",
                    app_fingerprint,
                )
                return False

            X_arr = np.array(X, dtype=float)
            y_arr = np.array(y, dtype=int)

            pipeline = Pipeline([
                ("scaler", StandardScaler()),
                # class_weight='balanced' compensa el desbalance 1:N (pocos ganadores)
                ("clf", LogisticRegression(max_iter=500, class_weight="balanced")),
            ])
            pipeline.fit(X_arr, y_arr)

            # Accuracy aproximada sobre los mismos datos de entrenamiento
            acc = float(pipeline.score(X_arr, y_arr))

            # Serializar y persistir
            buf = io.BytesIO()
            pickle.dump(pipeline, buf)
            self._db.save_model(
                app_fingerprint=app_fingerprint,
                model_blob=buf.getvalue(),
                training_samples=len(data),
                accuracy=acc,
            )

            # Invalida cache para que el próximo request cargue el modelo nuevo
            self._cache.pop(app_fingerprint, None)

            log.info(
                "Modelo entrenado para '%s': muestras=%d accuracy=%.2f",
                app_fingerprint, len(data), acc,
            )
            return True

        except ImportError:
            log.warning(
                "scikit-learn no disponible — Capa 3 (ML) deshabilitada"
            )
            return False
        except Exception as exc:
            log.error("_train error para '%s': %s", app_fingerprint, exc)
            return False

    def _get_model(self, app_fingerprint: str):
        """
        Obtiene el modelo desde cache en memoria o desde la BD.
        Retorna None si no existe o si no cumple min_samples.
        """
        if app_fingerprint in self._cache:
            return self._cache[app_fingerprint]

        try:
            row = self._db.get_model(app_fingerprint)
            if not row or not row.get("model_blob"):
                return None
            if row.get("training_samples", 0) < self._min_samples:
                return None

            model = pickle.loads(row["model_blob"])
            self._cache[app_fingerprint] = model
            log.debug(
                "Modelo cargado desde BD para '%s' (samples=%d acc=%.2f)",
                app_fingerprint,
                row.get("training_samples", 0),
                row.get("accuracy", 0.0),
            )
            return model
        except Exception as exc:
            log.debug("_get_model error para '%s': %s", app_fingerprint, exc)
            return None
