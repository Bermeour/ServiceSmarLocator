from bs4.element import Tag
from app.models.schemas import Context


def is_inside_container(el: Tag, container_id: str) -> bool:
    """
    Busca un ancestro cuyo id sea exactamente container_id.
    Si container_id parece dinámico (empieza con dígito o tiene muchos _),
    acepta también match por sufijo para tolerar cambios de prefijo.
    """
    if not container_id:
        return True
    # heurística: id dinámico si empieza con dígito o tiene >=3 guiones bajos con números
    digits_in_id = sum(ch.isdigit() for ch in container_id)
    is_dynamic = container_id[0].isdigit() or (digits_in_id >= 2 and container_id.count("_") >= 3)

    parent = el
    while parent is not None:
        parent_id = (getattr(parent, "attrs", None) or {}).get("id") or ""
        if parent_id == container_id:
            return True
        if is_dynamic and parent_id and parent_id.endswith(container_id.lstrip("0123456789_")):
            return True
        parent = parent.parent
    return False


def is_inside_container_class(el: Tag, container_class_expr: str) -> bool:
    """
    Similar a la validación en Java:
    - "nav-wrapper"                 -> ancestro con esa clase
    - "nav-wrapper header-zone"     -> ancestro que tenga AMBAS
    - "nav-wrapper,topbar,layout"   -> OR entre alternativas

    Evalúa ancestros (incluye el mismo elemento).
    """
    expr = (container_class_expr or "").strip()
    if not expr:
        return True

    or_parts = [p.strip() for p in expr.split(",") if p.strip()]
    # si no hay comas, lo tratamos como un solo grupo
    if not or_parts:
        or_parts = [expr]

    def has_all_classes(node: Tag, classes_str: str) -> bool:
        req = [c.strip() for c in classes_str.split() if c.strip()]
        if not req:
            return False
        node_classes = set([c.lower() for c in (node.get("class") or [])])
        for c in req:
            if c.lower() not in node_classes:
                return False
        return True

    parent = el
    while parent is not None:
        if getattr(parent, "attrs", None) and parent.get("class"):
            for part in or_parts:
                if has_all_classes(parent, part):
                    return True
        parent = parent.parent

    return False


class CandidateFilter:
    """
    Filtros duros (hard filters):
    - excludeIds
    - containerId
    - formId
    """

    def accept(self, el: Tag, ctx: Context) -> bool:
        el_id = el.get("id")

        # 1) exclusión dura por ID
        exclude_ids = set(ctx.excludeIds or [])
        if el_id and el_id in exclude_ids:
            return False

        # 2) filtro por containerId
        if ctx.containerId and not is_inside_container(el, ctx.containerId):
            return False

        # 2b) filtro por containerClass
        if ctx.containerClass and not is_inside_container_class(el, ctx.containerClass):
            return False

        # 3) filtro por formId
        if ctx.formId and not is_inside_container(el, ctx.formId):
            return False

        return True
