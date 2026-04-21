from bs4.element import Tag
from app.scoring.text_utils import normalize_text, is_generic_text, safe_xpath_literal


class AdvancedSelectorBuilder:
    """
    Fallback locators cuando no hay id/testid/aria.

    Incluye:
    - CSS por clases "buenas"
    - XPath por texto (scoped si hay formId/containerId)
    - XPath por clases (scoped si hay formId/containerId)

    Nota importante:
    - Para XPath por texto usamos el texto ORIGINAL (limpio de espacios),
      no el normalize_text(), porque XPath no puede quitar acentos fácilmente.
    - normalize_text() se usa para comparar/decidir si el texto es genérico.
    """

    def build_fallback(self, el: Tag, base_tag: str, base_text: str, context=None):
        locators = []

        tag = (el.name or base_tag or "button").lower().strip()

        visible_text = (el.get_text(strip=True) or "").strip()
        classes = [c.lower() for c in (el.get("class") or [])]
        good_classes = self._select_good_classes(classes)

        # scope prefijo por context (prioriza formId sobre containerId)
        scope_prefix = self._scope_prefix(context)

        # -------------------------
        # 1) CSS por clases útiles
        # -------------------------
        if good_classes:
            # ejemplo: button.btn.primary
            css = tag + "".join([f".{c}" for c in good_classes[:3]])
            locators.append(("css", css, "css por clases (fallback)", 0))

        # -------------------------
        # 2) XPath por texto (SCOPED)
        # -------------------------
        # Preferimos base_text (viene del baseline del elemento original),
        # si no existe usamos el visible_text del candidato.
        candidate_text = (base_text or visible_text or "").strip()
        candidate_text = " ".join(candidate_text.split())  # colapsa espacios

        # criterio: texto corto y NO genérico (usamos normalize_text solo para decidir)
        if candidate_text and len(candidate_text) <= 40:
            if not is_generic_text(candidate_text):
                # literal xpath seguro (maneja comillas)
                lit = safe_xpath_literal(candidate_text)
                xp = f"{scope_prefix}//{tag}[contains(normalize-space(.), {lit})]"
                locators.append(("xpath", xp, "xpath por texto (scoped fallback)", 0))

        # -------------------------
        # 3) XPath por clases (SCOPED)
        # -------------------------
        if good_classes:
            parts = " and ".join([f"contains(@class,{safe_xpath_literal(c)})" for c in good_classes[:2]])
            xp = f"{scope_prefix}//{tag}[{parts}]"
            locators.append(("xpath", xp, "xpath por clases (scoped fallback)", 0))

        return self._dedupe(locators)

    def _scope_prefix(self, context) -> str:
        """
        Si hay formId/containerId, devolvemos un prefijo XPath:
          formId -> //*[@id='formId']
          containerId -> //*[@id='containerId']
        Si no hay nada -> "" (sin scope)

        Importante:
        - Retornamos "" o //*[@id='x'] (sin // al final).
        - Quien lo use concatenará luego con //tag[...]
        """
        if not context:
            return ""

        form_id = getattr(context, "formId", None)
        container_id = getattr(context, "containerId", None)

        # form tiene prioridad porque es más específico
        if form_id and str(form_id).strip():
            return f"//*[@id={safe_xpath_literal(str(form_id).strip())}]"

        if container_id and str(container_id).strip():
            return f"//*[@id={safe_xpath_literal(str(container_id).strip())}]"

        # ✅ containerClass como último recurso de scoping
        container_class = getattr(context, "containerClass", None)
        if container_class and str(container_class).strip():
            expr = str(container_class).strip()
            # toma la primera alternativa (OR) para no explotar el XPath
            first = expr.split(",", 1)[0].strip()
            classes = [c.strip() for c in first.split() if c.strip()]
            if classes:
                cond = " and ".join([
                    f"contains(concat(' ', normalize-space(@class), ' '), {safe_xpath_literal(' ' + c + ' ')})"
                    for c in classes[:3]
                ])
                return f"//*[ {cond} ]"

        return ""

    def _select_good_classes(self, classes: list[str]) -> list[str]:
        """
        Escoge clases "humanas" y relativamente estables.
        Evita clases generadas/hashes largos o cosas típicas de frameworks.
        """
        bad_prefixes = ("ng-", "css-", "sc-", "styled", "chakra", "mui", "ant", "css")
        bad_exact = {
            "active", "disabled", "focus", "hover", "selected", "ng-star-inserted",
            # jqGrid / Siebel: presentes en todos los nodos, no aportan especificidad
            "ui-widget-content", "ui-widget", "ui-state-default", "ui-state-active",
            "ui-corner-all", "ui-jqgrid-btable", "odd", "even", "jqgrow", "ui-row-ltr",
            # Bootstrap genérico
            "row", "col", "container", "form-control", "form-group",
        }

        good = []
        for c in classes:
            if not c:
                continue
            c = c.strip().lower()
            if len(c) < 2:
                continue
            if c in bad_exact:
                continue
            if any(c.startswith(p) for p in bad_prefixes):
                continue
            if len(c) > 25:
                continue
            good.append(c)

        # prioriza clases más “semánticas”
        priority = ["primary", "btn", "button", "submit", "confirm", "save", "login", "pay"]
        good.sort(key=lambda x: (0 if x in priority else 1, len(x)))
        return good

    def _dedupe(self, locators):
        seen = set()
        out = []
        for t, v, r, bonus in locators:
            key = (t, v)
            if key in seen:
                continue
            seen.add(key)
            out.append((t, v, r, bonus))
        return out
