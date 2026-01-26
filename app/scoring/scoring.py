from bs4.element import Tag
from app.scoring.proximity import proximity_score
from app.scoring.zones import ZoneHeuristics
from app.scoring.text_utils import text_contains, normalize_text, is_generic_text


class ScoreEngine:
    def __init__(self):
        self.zone = ZoneHeuristics()

    def score(
        self,
        el: Tag,
        base_tag: str,
        base_text: str,
        base_attrs: dict,
        anchors,
        base_intent: str = "",
        base_text_contains: list[str] | None = None,
        base_meta: dict | None = None,
    ):
        score = 0
        reasons = ["pasa filtros context (container/form)"]

        meta = {
            "zonePenalty": 0,
            "classSignals": [],
            "textHit": False,
            "anchorHits": [],
            # ✅ Nuevos signals (para 'explain')
            "textContainsMatched": 0,
            "textContainsTotal": 0,
            "intentBonus": 0,
            "metaBonus": 0,
        }

        # 0) match de tag (señal fuerte y estable)
        el_tag = (el.name or "").strip().lower()
        base_tag_norm = (base_tag or "").strip().lower()
        if base_tag_norm and el_tag and el_tag == base_tag_norm:
            score += 10
            reasons.append("tag coincide (+10)")

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

        # 3) atributos estables (data-testid / data-cy / data-qa / name / formcontrolname)
        base_testid = (base_attrs or {}).get("data-testid")
        el_testid = el.get("data-testid")
        if base_testid and el_testid and base_testid == el_testid:
            score += 60
            reasons.append("data-testid coincide (+60)")

        for key, pts, label in [
            ("data-cy", 55, "data-cy"),
            ("data-qa", 55, "data-qa"),
            ("data-testid", 60, "data-testid"),
            ("formcontrolname", 50, "formcontrolname"),
            ("name", 35, "name"),
        ]:
            bv = (base_attrs or {}).get(key)
            ev = el.get(key)
            if bv and ev and str(bv) == str(ev):
                score += pts
                reasons.append(f"{label} coincide (+{pts})")

        # 4) aria-label
        base_aria = (base_attrs or {}).get("aria-label")
        el_aria = el.get("aria-label")
        if base_aria and el_aria and base_aria == el_aria:
            score += 40
            reasons.append("aria-label coincide (+40)")

        # 5) texto visible / texto-usable (inputs, selects, etc.)
        visible_text = self._textish(el)
        if base_text and visible_text:
            if not is_generic_text(base_text) and text_contains(visible_text, base_text):
                score += 15
                meta["textHit"] = True
                reasons.append(f"texto similar '{normalize_text(base_text)}' (+15)")

        # 5b) ✅ textContains (fuerte, AND) - aplica sobre textish
        tc = base_text_contains or []
        if tc and visible_text:
            matched = 0
            for frag in tc:
                if frag and text_contains(visible_text, frag):
                    matched += 1

            total = len(tc)
            meta["textContainsMatched"] = matched
            meta["textContainsTotal"] = total

            if matched == total:
                score += 30
                reasons.append(f"textContains {matched}/{total} (+30)")
            else:
                score -= 40
                reasons.append(f"textContains {matched}/{total} (-40)")

        # 6) proximidad anchors (ya con weight)
        for anchor_el, label, weight in anchors:
            pts, msg = proximity_score(anchor_el, el)
            if pts > 0:
                add = int(pts * (weight or 1.0))
                score += add
                meta["anchorHits"].append(label)
                reasons.append(f"proximidad a {label}: {msg} (+{add})")

        # 7) ✅ intent bonus (pesos por intención)
        intent_bonus = self.intent_bonus(el, base_intent)
        if intent_bonus:
            score += intent_bonus
            meta["intentBonus"] = intent_bonus
            reasons.append(f"intent '{base_intent}' (+{intent_bonus})")

        # 8) ✅ meta bonus (severity/businessCase)
        mb = self.meta_bonus(el, base_meta or {})
        if mb:
            score += mb
            meta["metaBonus"] = mb
            reasons.append(f"meta bonus (+{mb})")

        return score, reasons, meta

    def _textish(self, el: Tag) -> str:
        """Texto que normalmente usaría un humano para identificar el elemento.

        - Para botones/labels/divs: texto visible
        - Para inputs/textarea: value/placeholder/aria-label
        - Para selects: texto de la opción seleccionada o aria-label
        """
        tag = (el.name or "").lower().strip()
        if tag in ("input", "textarea"):
            return (el.get("value") or el.get("placeholder") or el.get("aria-label") or "").strip()
        if tag == "select":
            # selected option
            try:
                opt = el.find("option", selected=True)
                if opt:
                    return (opt.get_text(strip=True) or "").strip()
            except Exception:
                pass
            return (el.get("aria-label") or el.get("name") or "").strip()
        return (el.get_text(strip=True) or "").strip()

    def intent_bonus(self, el: Tag, intent: str) -> int:
        if not intent:
            return 0

        intent = (intent or "").strip()
        role = (el.get("role") or "").strip().lower()
        el_id = (el.get("id") or "").strip().lower()
        cls = " ".join((el.get("class") or [])).lower()
        tag = (el.name or "").strip().lower()

        bonus = 0

        if intent == "permissions_error_message":
            if role == "alert":
                bonus += 8
            if "error" in cls:
                bonus += 6
            if el_id == "statusbar":
                bonus += 10
            if tag == "div":
                bonus += 2

        elif intent == "login_error_message":
            if role == "alert":
                bonus += 6
            if "error" in cls:
                bonus += 6
            if tag == "div":
                bonus += 2

        # -----------------------------
        # Heurísticas genéricas (multi-app)
        # -----------------------------
        # intent estilo "edit_numero_identificacion" o "edit_*" =>
        # suele ser jqGrid/Siebel: td.edit-cell / inputs dentro de grid.
        if intent.startswith("edit_") or intent.endswith("_cell") or "edit" in intent:
            if tag in ("td", "input", "textarea", "select"):
                bonus += 3
            if "edit-cell" in cls or "ui-state-highlight" in cls:
                bonus += 8
            if "jqgrid" in cls or "ui-jqgrid" in cls:
                bonus += 5
            # si el id contiene el nombre de campo, es muy buena señal
            field = intent.replace("edit_", "").strip().lower()
            if field and field in el_id:
                bonus += 12

        # intent estilo "tab_*" o "nav_*" => navegación
        if intent.startswith("tab_") or intent.startswith("nav_"):
            if tag in ("a", "li"):
                bonus += 3
            if role in ("tab", "navigation"):
                bonus += 4

        return bonus

    def meta_bonus(self, el: Tag, meta: dict) -> int:
        if not meta:
            return 0

        role = (el.get("role") or "").strip().lower()
        el_id = (el.get("id") or "").strip().lower()
        cls = " ".join((el.get("class") or [])).lower()

        bonus = 0

        severity = str(meta.get("severity") or "").upper()
        business = str(meta.get("businessCase") or "").upper()

        if severity == "ERROR":
            if role == "alert":
                bonus += 5
            if "error" in cls:
                bonus += 5

        if business == "NO_PERMISSIONS":
            if el_id == "statusbar":
                bonus += 4

        # Genérico: EDIT_CELL suele ser grillas
        if business == "EDIT_CELL":
            if el.name in ("td", "input", "textarea", "select"):
                bonus += 2
            if "gridcell" in (role or ""):
                bonus += 2
            if "jqgrid" in cls or "ui-jqgrid" in cls:
                bonus += 3

        return bonus

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

