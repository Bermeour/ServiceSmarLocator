import logging
from typing import Any, List, Optional, Tuple

import lxml.html
from bs4 import BeautifulSoup
from bs4.element import Tag

from app.scoring.text_utils import normalize_text

log = logging.getLogger(__name__)

PREFERRED_TAGS = ["label", "span", "p", "h1", "h2", "h3", "h4", "strong", "small"]


def find_text_anchor(soup: BeautifulSoup, base_text: str) -> Optional[Tag]:
    if not base_text:
        return None

    t = normalize_text(base_text)
    if not t:
        return None

    for tag in PREFERRED_TAGS:
        el = soup.find(tag, string=lambda s: s and t in normalize_text(s))
        if el:
            return el

    txt_node = soup.find(string=lambda s: s and t in normalize_text(s))
    if txt_node and getattr(txt_node, "parent", None):
        return txt_node.parent

    return None


def find_anchor_by_id(soup: BeautifulSoup, el_id: str) -> Optional[Tag]:
    if not el_id:
        return None
    return soup.find(attrs={"id": el_id})


class AnchorResolver:
    """
    Devuelve anchors como lista de tuplas:
      [(anchor_el, label, weight), ...]
    """

    def resolve(
        self,
        soup: BeautifulSoup,
        base_text: str,
        context: Any = None,
        raw_html: str = "",
    ) -> List[Tuple[Tag, str, int]]:
        out: List[Tuple[Tag, str, int]] = []

        # Anchor por texto del baseline (señal estructural débil pero útil)
        at = find_text_anchor(soup, base_text)
        if at:
            out.append((at, "text", 15))

        # Custom anchors (context.anchors)
        custom = None
        try:
            if context is None:
                custom = None
            elif isinstance(context, dict):
                custom = context.get("anchors")
            else:
                custom = getattr(context, "anchors", None)
        except Exception:
            custom = None

        if custom:
            for i, a in enumerate(custom):
                if isinstance(a, dict):
                    a_type = (a.get("type") or "").lower()
                    a_value = a.get("value")
                    a_weight = a.get("weight", 30)
                else:
                    a_type = (getattr(a, "type", "") or "").lower()
                    a_value = getattr(a, "value", None)
                    a_weight = getattr(a, "weight", 30)

                if not a_value:
                    continue

                try:
                    a_weight = int(a_weight or 30)
                except Exception:
                    a_weight = 30

                label = f"custom_{i}:{a_type}"

                if a_type == "id":
                    el = find_anchor_by_id(soup, str(a_value))
                    if el:
                        out.append((el, label, a_weight))

                elif a_type == "text":
                    el = find_text_anchor(soup, str(a_value))
                    if el:
                        out.append((el, label, a_weight))

                elif a_type == "css":
                    try:
                        el = soup.select_one(str(a_value))
                    except Exception:
                        el = None
                    if el:
                        out.append((el, label, a_weight))

                elif a_type == "xpath":
                    el = self._resolve_xpath(soup, raw_html, str(a_value))
                    if el:
                        out.append((el, label, a_weight))

        return out

    def _resolve_xpath(
        self, soup: BeautifulSoup, raw_html: str, xpath_expr: str
    ) -> Optional[Tag]:
        """
        Resuelve un XPath arbitrario usando lxml y localiza el elemento
        equivalente en el árbol BeautifulSoup por atributos estables.
        """
        if not raw_html:
            return None
        try:
            doc = lxml.html.fromstring(raw_html)
            results = doc.xpath(xpath_expr)
            if not results:
                return None

            lxml_el = results[0]

            # Localiza el mismo elemento en soup usando atributos estables
            # (en orden de especificidad)
            el_id = lxml_el.get("id")
            if el_id:
                return soup.find(attrs={"id": el_id})

            testid = lxml_el.get("data-testid")
            if testid:
                return soup.find(attrs={"data-testid": testid})

            aria = lxml_el.get("aria-label")
            if aria:
                return soup.find(attrs={"aria-label": aria})

            name = lxml_el.get("name")
            if name:
                return soup.find(attrs={"name": name})

            # Fallback: tag + primeros 30 chars de texto
            tag = lxml_el.tag if isinstance(lxml_el.tag, str) else None
            if tag:
                text = (lxml_el.text_content() or "").strip()[:30]
                if text:
                    t = normalize_text(text)
                    return soup.find(
                        tag,
                        string=lambda s: s and t in normalize_text(s),
                    )

            return None
        except Exception as exc:
            log.debug("_resolve_xpath error for %r: %s", xpath_expr, exc)
            return None
