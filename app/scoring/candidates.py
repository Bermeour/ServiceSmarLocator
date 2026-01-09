from bs4 import BeautifulSoup
from bs4.element import Tag


class CandidateProvider:
    """
    Devuelve candidatos a evaluar.

    - Si base_tag es 'button' => incluye:
        * <button>
        * <input type='submit'|'button'>
        * <a role='button'>
        * <div role='button'>
    - Si base_tag es 'input' => incluye:
        * <input> (y opcionalmente role/button si baseline lo sugiere)
    - Si base_tag es otro => devuelve esos tags + roles si aplica
    """

    def candidates(self, soup: BeautifulSoup, base_tag: str):
        base_tag = (base_tag or "button").lower().strip()

        # conjunto para evitar duplicados
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

        # Caso más común: baseline button
        if base_tag == "button":
            add_all(soup.find_all("button"))

            # inputs que actúan como botones
            add_all(soup.find_all("input", attrs={"type": "submit"}))
            add_all(soup.find_all("input", attrs={"type": "button"}))

            # roles button modernos
            add_all(soup.find_all("a", attrs={"role": "button"}))
            add_all(soup.find_all("div", attrs={"role": "button"}))

            return out

        # Baseline input: inputs y también submit/button
        if base_tag == "input":
            add_all(soup.find_all("input"))
            add_all(soup.find_all("input", attrs={"type": "submit"}))
            add_all(soup.find_all("input", attrs={"type": "button"}))
            return out

        # Default: el tag + roles button si base_tag no es button
        add_all(soup.find_all(base_tag))
        add_all(soup.find_all(attrs={"role": "button"}))
        return out
