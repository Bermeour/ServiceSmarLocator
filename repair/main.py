from fastapi import FastAPI
from bs4 import BeautifulSoup

app = FastAPI()

def dom_distance(a, b, max_depth=60):
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


def find_text_anchor(soup, base_text: str):
    if not base_text:
        return None

    t = base_text.strip().lower()
    if not t:
        return None

    preferred_tags = ["label", "span", "p", "h1", "h2", "h3", "h4", "strong", "small"]

    for tag in preferred_tags:
        el = soup.find(tag, string=lambda s: s and t in s.strip().lower())
        if el:
            return el

    txt_node = soup.find(string=lambda s: s and t in s.strip().lower())
    if txt_node and txt_node.parent:
        return txt_node.parent

    return None


def proximity_score(anchor_el, candidate_el):
    if anchor_el is None or candidate_el is None:
        return 0, None

    d = dom_distance(anchor_el, candidate_el)

    if d <= 3:
        return 30, f"muy cerca (dist={d})"
    if d <= 6:
        return 15, f"cerca (dist={d})"
    if d <= 10:
        return 5, f"algo cerca (dist={d})"

    return 0, f"lejos (dist={d})"


def is_inside_container(el, container_id: str):
    parent = el
    while parent is not None:
        if getattr(parent, "attrs", None) and parent.attrs.get("id") == container_id:
            return True
        parent = parent.parent
    return False


# ✅ NUEVO: buscar ancla por id (inputs clave)
def find_anchor_by_id(soup, el_id: str):
    if not el_id:
        return None
    return soup.find(attrs={"id": el_id})


# ✅ NUEVO: heurística por clases (más “humana”)
def class_score(el):
    cls = el.get("class") or []
    cls = [c.lower() for c in cls]

    score = 0
    reason = []

    # En tu HTML: botón bueno = btn primary, trampa header = btn ghost
    if "primary" in cls:
        score += 25
        reason.append("class primary (+25)")

    if "ghost" in cls:
        score -= 25
        reason.append("class ghost (-25)")

    return score, reason


@app.post("/repair")
def repair(req: dict):

    soup = BeautifulSoup(req["pageHtml"], "lxml")
    baseline = req.get("baseline", {})
    context = req.get("context", {})  # ✅

    base_tag = baseline.get("tag", "button")
    base_text = (baseline.get("text", "") or "").strip()
    base_attrs = baseline.get("attrs", {}) or {}

    # ✅ CONTEXTO
    container_id = context.get("containerId")  # ej: "loginArea"
    form_id = context.get("formId")            # ej: "loginForm"
    exclude_ids = set(context.get("excludeIds", []))

    # ✅ ANCLAS
    anchor_text = find_text_anchor(soup, base_text)
    anchor_user = find_anchor_by_id(soup, "user")
    anchor_pass = find_anchor_by_id(soup, "pass")

    suggestions = []

    # logs (solo si llega request)
    print(">>> CONTEXT:", context)
    print(">>> containerId:", container_id)
    print(">>> formId:", form_id)
    print(">>> excludeIds:", exclude_ids)

    for el in soup.find_all(base_tag):

        el_id = el.get("id")

        # 1) EXCLUSIÓN DURA POR ID
        if el_id and el_id in exclude_ids:
            continue

        # 2) FILTRO DURO: debe estar dentro del containerId (si aplica)
        if container_id and not is_inside_container(el, container_id):
            continue

        # ✅ 3) FILTRO DURO: debe estar dentro del formId (si aplica)
        if form_id and not is_inside_container(el, form_id):
            continue

        score = 0
        reason = []
        reason.append("pasa filtros context (container/form)")

        # ✅ 4) clases (primary vs ghost)
        cs, cr = class_score(el)
        score += cs
        reason.extend(cr)

        # 5) data-testid
        base_testid = base_attrs.get("data-testid")
        el_testid = el.get("data-testid")
        if base_testid and el_testid and base_testid == el_testid:
            score += 60
            reason.append("data-testid coincide (+60)")

        # 6) aria-label
        base_aria = base_attrs.get("aria-label")
        el_aria = el.get("aria-label")
        if base_aria and el_aria and base_aria == el_aria:
            score += 40
            reason.append("aria-label coincide (+40)")

        # 7) texto visible
        visible_text = el.get_text(strip=True)
        if base_text and visible_text and base_text.lower() in visible_text.lower():
            score += 15
            reason.append("texto similar (+15)")

        # ✅ 8) proximidad por anclas (más IA)
        #    user/pass valen más que el texto
        for anchor, label in [(anchor_user, "user"), (anchor_pass, "pass"), (anchor_text, "text")]:
            if anchor is None:
                continue
            prox_pts, prox_msg = proximity_score(anchor, el)
            if prox_pts > 0:
                mult = 2.0 if label in ("user", "pass") else 1.0
                add = int(prox_pts * mult)
                score += add
                reason.append(f"proximidad a {label}: {prox_msg} (+{add})")

        # ✅ umbral
        if score >= 40:
            if el_id:
                selector = f"#{el_id}"
            elif el_testid:
                selector = f"{base_tag}[data-testid='{el_testid}']"
            elif el_aria:
                selector = f"{base_tag}[aria-label='{el_aria}']"
            else:
                continue

            suggestions.append({
                "type": "css",
                "value": selector,
                "score": score,
                "reason": " | ".join(reason)
            })

    suggestions.sort(key=lambda x: x["score"], reverse=True)
    return {"suggestions": suggestions[:5]}
