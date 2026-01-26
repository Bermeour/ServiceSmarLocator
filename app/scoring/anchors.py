from typing import List, Optional, Tuple, Any
from bs4 import BeautifulSoup
from bs4.element import Tag

from app.scoring.text_utils import normalize_text

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
        context: Any = None
    ) -> List[Tuple[Tag, str, int]]:
        out: List[Tuple[Tag, str, int]] = []

        # -------------------------
        # Defaults
        # -------------------------
        at = find_text_anchor(soup, base_text)
        if at:
            out.append((at, "text", 15))

        au = find_anchor_by_id(soup, "user")
        if au:
            out.append((au, "user", 30))

        ap = find_anchor_by_id(soup, "pass")
        if ap:
            out.append((ap, "pass", 30))

        # -------------------------
        # Custom anchors (context.anchors)
        # -------------------------
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
                # a puede ser dict o Pydantic model
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
                    # BeautifulSoup no soporta XPath completo.
                    # Soportamos un caso común: //*[@id='x']
                    try:
                        v = str(a_value)
                        if "@id" in v and "'" in v:
                            # extrae id entre comillas simples
                            _id = v.split("@id", 1)[1]
                            _id = _id.split("'", 2)
                            if len(_id) >= 2:
                                el = find_anchor_by_id(soup, _id[1])
                            else:
                                el = None
                        else:
                            el = None
                    except Exception:
                        el = None
                    if el:
                        out.append((el, label, a_weight))

        return out
