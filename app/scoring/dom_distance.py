def dom_distance(a, b, max_depth=60) -> int:
    """
    Distancia simple por ancestros en el DOM:
    - construye lista de ancestros de a y b
    - busca primer ancestro común y suma distancias
    """
    def ancestors(el):
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

    b_set = set(b_anc)
    for i, node in enumerate(a_anc):
        if node in b_set:
            j = b_anc.index(node)
            return i + j

    return 999
