from typing import Optional, Tuple
from bs4.element import Tag


def dom_distance(a: Optional[Tag], b: Optional[Tag], max_depth: int = 120) -> int:
    """
    Distancia simple en el DOM:
    suma de los pasos desde a -> LCA + b -> LCA
    (LCA = lowest common ancestor)
    """
    def ancestors(el: Optional[Tag]):
        res = []
        depth = 0
        while el is not None and getattr(el, "name", None) is not None and depth < max_depth:
            res.append(el)
            el = el.parent
            depth += 1
        return res

    a_anc = ancestors(a)
    b_anc = ancestors(b)

    if not a_anc or not b_anc:
        return 999

    b_index = {id(node): j for j, node in enumerate(b_anc)}
    for i, node in enumerate(a_anc):
        j = b_index.get(id(node))
        if j is not None:
            return i + j

    return 999


def proximity_score(anchor_el: Optional[Tag], candidate_el: Optional[Tag]) -> Tuple[int, str]:
    """
    Retorna (puntos_base, mensaje)
    OJO: el multiplicador (peso por anchor) lo aplicas en ScoreEngine con weights.
    """
    if anchor_el is None or candidate_el is None:
        return 0, "no anchor"

    d = dom_distance(anchor_el, candidate_el)

    if d <= 3:
        return 30, f"muy cerca (dist={d})"
    if d <= 6:
        return 15, f"cerca (dist={d})"
    if d <= 10:
        return 5, f"algo cerca (dist={d})"

    return 0, f"lejos (dist={d})"
