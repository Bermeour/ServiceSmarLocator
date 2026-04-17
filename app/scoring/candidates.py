from bs4 import BeautifulSoup
from bs4.element import Tag


# Tags que actúan como botón cuando tienen role="button"
_ROLE_BUTTON_TAGS = ("span", "li", "img", "div", "a", "td")

# Tags que actúan como ítem de lista/menú
_ROLE_OPTION_TAGS = ("li", "div", "span", "td")
_ROLE_OPTION_VALUES = ("option", "menuitem", "menuitemcheckbox", "menuitemradio")


class CandidateProvider:
    """
    Devuelve candidatos a evaluar según el base_tag.

    Cobertura por base_tag:
      button → <button>, <input type=submit|button>, <a|div|span|li|img role=button>
      input  → <input> (todos los tipos)
      a      → <a> (todos), <span|div role=button>
      select → <select>
      li     → <li>, <li role=option|menuitem>
      otros  → el tag exacto + elementos con role=button
    """

    def candidates(self, soup: BeautifulSoup, base_tag: str):
        base_tag = (base_tag or "button").lower().strip()

        seen = set()
        out: list[Tag] = []

        def add_all(elements):
            for el in elements:
                if el is None:
                    continue
                key = id(el)
                if key in seen:
                    continue
                seen.add(key)
                out.append(el)

        if base_tag == "button":
            add_all(soup.find_all("button"))
            add_all(soup.find_all("input", attrs={"type": "submit"}))
            add_all(soup.find_all("input", attrs={"type": "button"}))
            # cualquier tag que se comporte como botón
            for tag in _ROLE_BUTTON_TAGS:
                add_all(soup.find_all(tag, attrs={"role": "button"}))
            return out

        if base_tag == "input":
            add_all(soup.find_all("input"))
            return out

        if base_tag == "a":
            add_all(soup.find_all("a"))
            for tag in ("span", "div"):
                add_all(soup.find_all(tag, attrs={"role": "button"}))
            return out

        if base_tag == "select":
            add_all(soup.find_all("select"))
            return out

        if base_tag == "li":
            add_all(soup.find_all("li"))
            for role in _ROLE_OPTION_VALUES:
                for tag in _ROLE_OPTION_TAGS:
                    add_all(soup.find_all(tag, attrs={"role": role}))
            return out

        # Default: tag exacto + elementos con role=button del mismo tipo
        add_all(soup.find_all(base_tag))
        add_all(soup.find_all(attrs={"role": "button"}))
        return out
