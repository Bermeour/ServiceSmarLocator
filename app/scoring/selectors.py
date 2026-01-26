from bs4.element import Tag
from app.scoring.advanced_selectors import AdvancedSelectorBuilder


class SelectorBuilder:
    def __init__(self):
        self.advanced = AdvancedSelectorBuilder()

    def build_locators(self, el: Tag, base_tag: str, base_text: str = "", context=None):
        locators = []

        el_id = el.get("id")
        el_testid = el.get("data-testid")
        el_aria = el.get("aria-label")

        # attrs adicionales (multi-app)
        el_name = el.get("name")
        el_fcn = el.get("formcontrolname")
        el_datacy = el.get("data-cy")
        el_dataqa = el.get("data-qa")
        el_role = el.get("role")

        tag = (el.name or base_tag or "button").lower().strip()

        # ==============
        # SAFE CSS (con heurística anti-id dinámico)
        # ==============
        if el_id:
            if self._is_stable_id(el_id):
                locators.append(("css", f"#{el_id}", "css por id", 8, "SAFE_ID"))
            else:
                # id dinámico tipo Siebel/jqGrid: genera selector por sufijo
                suf = self._id_stable_suffix(el_id)
                if suf:
                    locators.append(("css", f"{tag}[id$='{suf}']", "css por id$=sufijo (anti-dinámico)", 3, "DYNAMIC_ID_SUFFIX"))
        if el_testid:
            locators.append(("css", f"{tag}[data-testid='{el_testid}']", "css por data-testid", 6, "SAFE_TESTID"))
        if el_datacy:
            locators.append(("css", f"{tag}[data-cy='{el_datacy}']", "css por data-cy", 6, "SAFE_DATA_CY"))
        if el_dataqa:
            locators.append(("css", f"{tag}[data-qa='{el_dataqa}']", "css por data-qa", 6, "SAFE_DATA_QA"))
        if el_fcn:
            locators.append(("css", f"{tag}[formcontrolname='{el_fcn}']", "css por formcontrolname", 6, "SAFE_FORMCONTROL"))
        if el_name:
            locators.append(("css", f"{tag}[name='{el_name}']", "css por name", 5, "SAFE_NAME"))
        if el_aria:
            locators.append(("css", f"{tag}[aria-label='{el_aria}']", "css por aria-label", 4, "SAFE_ARIA"))
        if el_role:
            locators.append(("css", f"{tag}[role='{el_role}']", "css por role", 1, "ROLE"))

        # ==============
        # SAFE XPath
        # ==============
        if el_id:
            if self._is_stable_id(el_id):
                locators.append(("xpath", f"//*[@id='{self._esc(el_id)}']", "xpath por id", 8, "SAFE_ID"))
            else:
                suf = self._id_stable_suffix(el_id)
                if suf:
                    locators.append(("xpath", f"//*[@id and substring(@id,string-length(@id)-{len(suf)-1})='{self._esc(suf)}']", "xpath por id sufijo (anti-dinámico)", 3, "DYNAMIC_ID_SUFFIX"))
        if el_testid:
            locators.append(("xpath", f"//*[@data-testid='{self._esc(el_testid)}']", "xpath por data-testid", 6, "SAFE_TESTID"))
        if el_datacy:
            locators.append(("xpath", f"//*[@data-cy='{self._esc(el_datacy)}']", "xpath por data-cy", 6, "SAFE_DATA_CY"))
        if el_dataqa:
            locators.append(("xpath", f"//*[@data-qa='{self._esc(el_dataqa)}']", "xpath por data-qa", 6, "SAFE_DATA_QA"))
        if el_fcn:
            locators.append(("xpath", f"//*[@formcontrolname='{self._esc(el_fcn)}']", "xpath por formcontrolname", 6, "SAFE_FORMCONTROL"))
        if el_name:
            locators.append(("xpath", f"//*[@name='{self._esc(el_name)}']", "xpath por name", 5, "SAFE_NAME"))
        if el_aria:
            locators.append(("xpath", f"//*[@aria-label='{self._esc(el_aria)}']", "xpath por aria-label", 4, "SAFE_ARIA"))

        # fallback advanced + scoped xpath
        if not locators:
            fallback = self.advanced.build_fallback(el, base_tag, base_text, context=context)
            # advanced retorna 4-tuples, aquí les agregamos quality:
            for t, v, r, b in fallback:
                quality = "FALLBACK_TEXT" if "texto" in (r or "").lower() else "FALLBACK_CLASS"
                locators.append((t, v, r, b, quality))

        return self._dedupe(locators)

    def _is_stable_id(self, el_id: str) -> bool:
        """Heurística genérica: evita ids con prefijos numéricos/estructurales comunes en Siebel/jqGrid."""
        if not el_id:
            return False
        s = str(el_id)
        # prefijos tipo "1_s_1_l_" o "s_1_2_130_0_icon"
        if s[0].isdigit():
            return False
        if s.startswith("s_") and any(p in s for p in ["_l_", "_icon", "_ctl", "_sctrl_"]):
            return False
        # muchos guiones bajos con números suele ser dinámico
        digits = sum(ch.isdigit() for ch in s)
        if digits >= 4 and s.count("_") >= 3:
            return False
        return True

    def _id_stable_suffix(self, el_id: str) -> str | None:
        """Devuelve un sufijo estable (ej: '_Numero_identificacion') si parece id dinámico."""
        if not el_id:
            return None
        s = str(el_id)
        # toma desde los últimos tokens si parecen semánticos
        if "_" in s:
            parts = [p for p in s.split("_") if p]
            if len(parts) >= 2:
                last = parts[-1]
                prev = parts[-2]
                # si el último es muy genérico, intenta usar 2 tokens
                if last and prev and not last.isdigit() and not prev.isdigit():
                    # caso Siebel/jqGrid: "..._Numero_identificacion" (últimos 2 tokens semánticos)
                    if len(prev) >= 3 and len(last) >= 3 and prev.lower() not in {"s", "l", "ctl", "ctrl"}:
                        return "_" + prev + "_" + last
                    return "_" + last
            # fallback 1 token
            token = parts[-1]
            if token and len(token) >= 3 and not token.isdigit():
                return "_" + token
        return None

    def _dedupe(self, locators):
        seen = set()
        out = []
        for t, v, r, bonus, q in locators:
            key = (t, v)
            if key in seen:
                continue
            seen.add(key)
            out.append((t, v, r, bonus, q))
        return out

    def _esc(self, s: str) -> str:
        return (s or "").replace("'", "\\'")
