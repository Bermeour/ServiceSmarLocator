"""
visual_scorer.py
================
Scoring visual completamente local — sin APIs externas.

Dependencias (wheels de Python puro, instalables via pip):
  - Pillow                   → decodificación de imágenes y análisis de color
  - opencv-python-headless   → template matching (posición del elemento en la página)
"""

from __future__ import annotations

import base64
import io
import logging
import re
import unicodedata
from dataclasses import dataclass
from typing import List, Optional, Tuple

log = logging.getLogger(__name__)

# ─── importaciones opcionales ─────────────────────────────────────────────────

try:
    from PIL import Image
    _PIL = True
except ImportError:
    _PIL = False
    log.warning("visual_scorer: Pillow no instalado — visual scoring deshabilitado")

try:
    import cv2
    import numpy as np
    _CV2 = True
except ImportError:
    _CV2 = False
    log.warning("visual_scorer: opencv-python-headless no instalado — template matching deshabilitado")



# ─── modelos de datos ─────────────────────────────────────────────────────────

@dataclass
class VisualProfile:
    """Resultado del análisis visual de un elementSnapshot."""
    available: bool = False
    dominant_color: str = ""          # blue | red | green | yellow | gray | white | unknown
    position_zone: str = ""           # top-left | top-center | middle-center | etc.
    match_confidence: float = 0.0     # 0..1 del template matching
    element_rect: Optional[Tuple[int, int, int, int]] = None  # x, y, w, h en pageSnapshot


# ─── scorer principal ─────────────────────────────────────────────────────────

class VisualScorer:
    """
    Analiza capturas de pantalla del elemento y de la página para producir
    señales que complementan el scoring DOM existente.

    Uso:
        scorer = VisualScorer()
        profile = scorer.analyze(element_b64, page_b64)           # una vez por request
        bonus, reasons = scorer.score_bonus(profile, el_dom_text, el_classes)  # por candidato
    """

    def __init__(self) -> None:
        pass

    # ── API pública ───────────────────────────────────────────────────────────

    def analyze(self, element_b64: str, page_b64: str = "") -> VisualProfile:
        """
        Analiza elementSnapshot y (opcionalmente) pageSnapshot.
        Retorna VisualProfile con todas las señales extraídas.
        Si Pillow no está instalado retorna VisualProfile(available=False).
        """
        profile = VisualProfile()

        if not _PIL:
            return profile

        element_img = self._decode(element_b64)
        if element_img is None:
            return profile

        profile.available = True

        # 1) Color dominante — para correlacionar con clases CSS
        profile.dominant_color = self._dominant_color(element_img)

        # 2) Template matching — posición en la página completa
        if page_b64 and _CV2:
            page_img = self._decode(page_b64)
            if page_img is not None:
                rect, conf = self._template_match(element_img, page_img)
                profile.element_rect = rect
                profile.match_confidence = conf
                if rect is not None:
                    profile.position_zone = self._zone(rect, page_img.size)

        log.debug(
            "VisualProfile — color=%s zone=%s confidence=%.2f",
            profile.dominant_color,
            profile.position_zone,
            profile.match_confidence,
        )
        return profile

    def score_bonus(
        self,
        profile: VisualProfile,
        el_dom_text: str,
        el_classes: List[str],
        base_text: str = "",
    ) -> Tuple[int, List[str]]:
        """
        Calcula el bonus visual para UN candidato DOM.

        Señales (por candidato):
          - Color dominante vs clases CSS  →  confirma que el candidato tiene el estilo correcto
          - Confianza template match       →  bonus si el elemento fue encontrado visualmente en la página

        Returns: (bonus_total, [reasons])
        """
        if not profile.available:
            return 0, []

        bonus = 0
        reasons: List[str] = []

        # ── Color dominante vs clases CSS ────────────────────────────────────
        color_bonus = self._color_class_bonus(profile.dominant_color, el_classes)
        if color_bonus:
            bonus += color_bonus
            reasons.append(
                f"visual: color '{profile.dominant_color}' refuerza clase CSS (+{color_bonus})"
            )

        # ── Bonus si template match encontró el elemento con alta confianza ──
        if profile.match_confidence >= 0.85:
            bonus += 10
            reasons.append(
                f"visual: elemento encontrado en página (confianza {profile.match_confidence:.2f}) (+10)"
            )
        elif profile.match_confidence >= 0.70:
            bonus += 5
            reasons.append(
                f"visual: elemento probablemente en página (confianza {profile.match_confidence:.2f}) (+5)"
            )

        return bonus, reasons

    # ── privados ──────────────────────────────────────────────────────────────

    def _decode(self, b64: str) -> Optional["Image.Image"]:
        """Decodifica base64 → PIL Image. Acepta formato raw o data-URL."""
        if not b64:
            return None
        try:
            raw = b64.split(",", 1)[1] if "," in b64 else b64
            data = base64.b64decode(raw)
            return Image.open(io.BytesIO(data)).convert("RGB")
        except Exception as exc:
            log.debug("_decode error: %s", exc)
            return None

    def _dominant_color(self, img: "Image.Image") -> str:
        """Clasifica el color dominante del elemento en una etiqueta semántica."""
        try:
            small = img.resize((50, 50))
            pixels = list(small.getdata())
            r = sum(p[0] for p in pixels) / len(pixels)
            g = sum(p[1] for p in pixels) / len(pixels)
            b = sum(p[2] for p in pixels) / len(pixels)
            return _classify_color(r, g, b)
        except Exception as exc:
            log.debug("_dominant_color error: %s", exc)
            return "unknown"

    def _template_match(
        self,
        element_img: "Image.Image",
        page_img: "Image.Image",
    ) -> Tuple[Optional[Tuple[int, int, int, int]], float]:
        """
        Busca element_img dentro de page_img usando OpenCV template matching.
        Retorna (rect=(x,y,w,h), confidence). rect=None si confianza < 0.5.
        """
        try:
            el_arr = np.array(element_img.convert("L"), dtype=np.uint8)
            pg_arr = np.array(page_img.convert("L"), dtype=np.uint8)

            # el template no puede ser más grande que la imagen
            if el_arr.shape[0] > pg_arr.shape[0] or el_arr.shape[1] > pg_arr.shape[1]:
                return None, 0.0

            result = cv2.matchTemplate(pg_arr, el_arr, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(result)

            if max_val < 0.5:
                return None, float(max_val)

            x, y = max_loc
            h, w = el_arr.shape[:2]
            return (x, y, w, h), float(max_val)
        except Exception as exc:
            log.debug("_template_match error: %s", exc)
            return None, 0.0

    def _zone(
        self,
        rect: Tuple[int, int, int, int],
        page_size: Tuple[int, int],
    ) -> str:
        """Clasifica la posición del elemento en la página en una zona (ej: 'middle-center')."""
        x, y, w, h = rect
        pw, ph = page_size
        cx = (x + w / 2) / max(pw, 1)
        cy = (y + h / 2) / max(ph, 1)
        vert = "top" if cy < 0.33 else ("bottom" if cy > 0.66 else "middle")
        horiz = "left" if cx < 0.33 else ("right" if cx > 0.66 else "center")
        return f"{vert}-{horiz}"

    def _color_class_bonus(self, color: str, classes: List[str]) -> int:
        """Bonus cuando el color dominante visual coincide con clases CSS semánticas."""
        if not color or not classes:
            return 0
        cls_str = " ".join(c.lower() for c in classes)
        _MAP = {
            "blue":   (["primary", "btn-primary", "blue"],               10),
            "red":    (["danger", "error", "btn-danger", "alert", "red"], 8),
            "green":  (["success", "btn-success", "green", "confirm"],    6),
            "yellow": (["warning", "btn-warning", "yellow", "warn"],      5),
            "gray":   (["secondary", "btn-secondary", "disabled", "ghost"], 4),
        }
        hints, pts = _MAP.get(color, ([], 0))
        for hint in hints:
            if hint in cls_str:
                return pts
        return 0


# ─── helpers internos ─────────────────────────────────────────────────────────

def _norm(text: str) -> str:
    """Normaliza texto para comparación (lower, sin acentos, colapsa espacios)."""
    if not text:
        return ""
    s = text.strip().lower()
    s = " ".join(s.split())
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return s


def _classify_color(r: float, g: float, b: float) -> str:
    """Clasifica un color RGB promedio en una etiqueta semántica."""
    mx = max(r, g, b)
    mn = min(r, g, b)
    saturation = (mx - mn) / mx if mx > 0 else 0

    if saturation < 0.15:
        return "white" if mx > 200 else "gray"

    if r > g and r > b:
        return "red"
    if g > r and g > b:
        return "green"
    if b > r and b > g:
        return "blue"
    if r > 180 and g > 140 and b < 100:
        return "yellow"
    return "unknown"
