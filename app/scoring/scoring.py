from bs4.element import Tag
from app.scoring.proximity import proximity_score
from app.scoring.zones import ZoneHeuristics
from app.scoring.text_utils import text_contains, normalize_text, is_generic_text


class ScoreEngine:
    def __init__(self):
        self.zone = ZoneHeuristics()

    def score(self, el: Tag, base_tag: str, base_text: str, base_attrs: dict, anchors):
        score = 0
        reasons = ["pasa filtros context (container/form)"]

        meta = {
            "zonePenalty": 0,
            "classSignals": [],
            "textHit": False,
            "anchorHits": []
        }

        # 1) clases
        cs, cr, class_meta = self.class_score(el)
        score += cs
        reasons.extend(cr)
        meta["classSignals"] = class_meta.get("classSignals", [])

        # 2) zonas/layout penalty
        zs, zr = self.zone.evaluate(el)
        score += zs
        reasons.extend(zr)
        meta["zonePenalty"] = zs  # negativo o 0

        # 3) data-testid
        base_testid = (base_attrs or {}).get("data-testid")
        el_testid = el.get("data-testid")
        if base_testid and el_testid and base_testid == el_testid:
            score += 60
            reasons.append("data-testid coincide (+60)")

        # 4) aria-label
        base_aria = (base_attrs or {}).get("aria-label")
        el_aria = el.get("aria-label")
        if base_aria and el_aria and base_aria == el_aria:
            score += 40
            reasons.append("aria-label coincide (+40)")

        # 5) texto visible (normalizado para decisión)
        visible_text = (el.get_text(strip=True) or "").strip()
        if base_text and visible_text:
            if not is_generic_text(base_text) and text_contains(visible_text, base_text):
                score += 15
                meta["textHit"] = True
                reasons.append(f"texto similar '{normalize_text(base_text)}' (+15)")

        # 6) proximidad anchors (ya con weight)
        for anchor_el, label, weight in anchors:
            pts, msg = proximity_score(anchor_el, el)
            if pts > 0:
                add = int(pts * (weight or 1.0))
                score += add
                meta["anchorHits"].append(label)
                reasons.append(f"proximidad a {label}: {msg} (+{add})")

        return score, reasons, meta

    def class_score(self, el: Tag):
        cls = el.get("class") or []
        cls = [c.lower() for c in cls]

        score = 0
        reasons = []
        class_signals = []

        if "primary" in cls:
            score += 25
            reasons.append("class primary (+25)")
            class_signals.append("primary")

        if "ghost" in cls:
            score -= 25
            reasons.append("class ghost (-25)")
            class_signals.append("ghost")

        return score, reasons, {"classSignals": class_signals}

