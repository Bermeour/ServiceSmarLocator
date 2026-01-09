from bs4.element import Tag


class ZoneHeuristics:
    """
    Heurísticas por zona/layout para penalizar elementos "trampa":
    - header/nav/footer
    - elementos tipo close/cancel
    - botones de barra superior
    - modales (si aplica)

    Devuelve (delta_score, reasons[])
    """

    def evaluate(self, el: Tag):
        score = 0
        reasons = []

        # Penalizar si está dentro de header/nav/footer
        if self._has_ancestor_tag(el, {"header", "nav"}):
            score -= 20
            reasons.append("zona header/nav (-20)")

        if self._has_ancestor_tag(el, {"footer"}):
            score -= 10
            reasons.append("zona footer (-10)")

        # Penalizar si parece "close/cancel" por clase o aria
        cls = self._classes(el)
        aria = (el.get("aria-label") or "").lower()
        text = (el.get_text(strip=True) or "").lower()

        # clases comunes de botones trampa
        trap_classes = {
            "ghost", "secondary", "icon", "link",
            "close", "dismiss", "cancel",
            "navbar", "header", "topbar"
        }

        if any(c in trap_classes for c in cls):
            score -= 10
            reasons.append("clase tipo trampa (-10)")

        # señales textuales de cerrar/cancelar
        trap_words = ["cerrar", "close", "cancelar", "cancel", "dismiss", "x"]
        if any(w in text for w in trap_words) or any(w in aria for w in trap_words):
            score -= 10
            reasons.append("texto/aria tipo cerrar/cancel (-10)")

        # Penalización suave si está dentro de un modal (no siempre es malo)
        # Si luego quieres, puedes hacerlo configurable por context
        if self._has_ancestor_class(el, {"modal", "dialog", "drawer"}):
            score -= 5
            reasons.append("zona modal/dialog/drawer (-5)")

        return score, reasons

    def _has_ancestor_tag(self, el: Tag, tag_names: set[str]) -> bool:
        p = el
        while p is not None and getattr(p, "name", None) is not None:
            if p.name and p.name.lower() in tag_names:
                return True
            p = p.parent
        return False

    def _has_ancestor_class(self, el: Tag, class_names: set[str]) -> bool:
        p = el
        while p is not None and getattr(p, "name", None) is not None:
            cls = self._classes(p)
            if any(c in class_names for c in cls):
                return True
            p = p.parent
        return False

    def _classes(self, el: Tag):
        cls = el.get("class") or []
        return {c.lower() for c in cls}
