from bs4.element import Tag
from app.models.schemas import Context


def is_inside_container(el: Tag, container_id: str) -> bool:
    parent = el
    while parent is not None:
        if getattr(parent, "attrs", None) and parent.attrs.get("id") == container_id:
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

        # 3) filtro por formId
        if ctx.formId and not is_inside_container(el, ctx.formId):
            return False

        return True
