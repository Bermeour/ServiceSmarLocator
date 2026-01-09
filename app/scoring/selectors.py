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

        tag = (el.name or base_tag or "button").lower().strip()

        # ==============
        # SAFE CSS
        # ==============
        if el_id:
            locators.append(("css", f"#{el_id}", "css por id", 8, "SAFE_ID"))
        if el_testid:
            locators.append(("css", f"{tag}[data-testid='{el_testid}']", "css por data-testid", 6, "SAFE_TESTID"))
        if el_aria:
            locators.append(("css", f"{tag}[aria-label='{el_aria}']", "css por aria-label", 4, "SAFE_ARIA"))

        # ==============
        # SAFE XPath
        # ==============
        if el_id:
            locators.append(("xpath", f"//*[@id='{self._esc(el_id)}']", "xpath por id", 8, "SAFE_ID"))
        if el_testid:
            locators.append(("xpath", f"//*[@data-testid='{self._esc(el_testid)}']", "xpath por data-testid", 6, "SAFE_TESTID"))
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
