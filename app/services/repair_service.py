from bs4 import BeautifulSoup

from app.models.schemas import RepairRequest, RepairResponse, Suggestion
from app.scoring.anchors import AnchorResolver
from app.scoring.filters import CandidateFilter
from app.scoring.scoring import ScoreEngine
from app.scoring.selectors import SelectorBuilder
from app.scoring.validator import LocatorValidator
from app.scoring.candidates import CandidateProvider
from app.scoring.diversity import SuggestionDiversifier, NodeGroup, SuggestionItem
from app.scoring.text_utils import normalize_text


class RepairService:
    def __init__(self):
        self.anchor_resolver = AnchorResolver()
        self.filter = CandidateFilter()
        self.scorer = ScoreEngine()
        self.selector_builder = SelectorBuilder()
        self.validator = LocatorValidator()
        self.candidates = CandidateProvider()
        self.diversifier = SuggestionDiversifier(top_nodes=5, top_per_node=2)

    def repair(self, req: RepairRequest) -> RepairResponse:
        soup = BeautifulSoup(req.pageHtml, "lxml")

        base_tag = (req.baseline.tag or "button").strip()
        base_text = (req.baseline.text or "").strip()
        base_intent = (getattr(req.baseline, "intent", None) or "").strip()
        base_text_contains = list(getattr(req.baseline, "textContains", None) or [])
        base_meta = dict(getattr(req.baseline, "meta", None) or {})
        base_attrs = req.baseline.attrs or {}

        ctx = req.context

        # ✅ Anchors (FORMATO NUEVO)
        # devuelve: List[Tuple[Tag, label, weight]]
        anchors = self.anchor_resolver.resolve(soup=soup, base_text=base_text, context=ctx)

        # logs básicos
        try:
            dump = ctx.model_dump()
        except Exception:
            dump = ctx.dict() if hasattr(ctx, "dict") else ctx

        print(">>> CONTEXT:", dump)
        print(">>> BASELINE.intent:", base_intent)
        print(">>> BASELINE.textContains:", base_text_contains)
        print(">>> BASELINE.meta:", base_meta)
        print(">>> BASELINE_INTENT:", base_intent)
        print(">>> BASELINE_TEXT_CONTAINS:", base_text_contains)
        print(">>> BASELINE_META:", base_meta)
        # opcional: log rápido de anchors resueltos
        try:
            print(">>> ANCHORS_RESOLVED:", [(lbl, w) for _, lbl, w in anchors])
        except Exception:
            pass

        node_groups: list[NodeGroup] = []

        for el in self.candidates.candidates(soup, base_tag):

            # 1) filtros duros
            if not self.filter.accept(el, ctx):
                continue

            # 2) score + meta
            score, reasons, signals = self.scorer.score(
                el=el,
                base_tag=base_tag,
                base_text=base_text,
                base_attrs=base_attrs,
                anchors=anchors,
                base_intent=base_intent,
                base_text_contains=base_text_contains,
                base_meta=base_meta,
            )

            if score < 40:
                continue

            locators = self.selector_builder.build_locators(el, base_tag, base_text, context=ctx)
            if not locators:
                continue

            node_key = self._node_key(el, base_tag)
            group_items: list[SuggestionItem] = []

            for loc_type, loc_value, extra_reason, extra_bonus, selector_quality in locators:

                v = self.validator.validate(
                    soup=soup,
                    raw_html=req.pageHtml,
                    locator_type=loc_type,
                    locator_value=loc_value
                )
                if not v.ok:
                    continue

                final_score = int(score + (extra_bonus or 0) + (v.bonus or 0))

                # ✅ META estructurado (Paso 10)
                meta = {
                    "nodeKey": node_key,
                    "selectorQuality": selector_quality,
                    "context": {
                        "containerId": getattr(ctx, "containerId", None),
                        "formId": getattr(ctx, "formId", None),
                        "excludeIdsCount": len(getattr(ctx, "excludeIds", []) or [])
                    },
                    "uniqueness": {
                        "matches": v.matches,
                        "bonus": v.bonus,
                        "note": v.note
                    },
                    "signals": {
                        "zonePenalty": signals.get("zonePenalty", 0),
                        "classSignals": signals.get("classSignals", []),
                        "textHit": signals.get("textHit", False),
                        "anchorHits": signals.get("anchorHits", [])
                        ,
                        # ✅ Nuevos: evidencian uso de intent/textContains/meta
                        "textContainsMatched": signals.get("textContainsMatched", 0),
                        "textContainsTotal": signals.get("textContainsTotal", 0),
                        "intentBonus": signals.get("intentBonus", 0),
                        "metaBonus": signals.get("metaBonus", 0),
                        "baselineIntent": base_intent,
                        "baselineTextContains": base_text_contains,
                        "baselineMeta": base_meta,
                    }
                }

                group_items.append(
                    SuggestionItem(
                        type=loc_type,
                        value=loc_value,
                        score=final_score,
                        reason=" | ".join(reasons + [
                            f"{extra_reason} (+{extra_bonus})",
                            f"unicidad: {v.note}"
                        ]),
                    )
                )

                # hack para meta sin cambiar diversity.py
                group_items[-1].__dict__["meta"] = meta

            if group_items:
                node_groups.append(NodeGroup(node_key=node_key, suggestions=group_items))

        diversified = self.diversifier.diversify(node_groups)

        # convertir a Suggestion incluyendo meta
        final_suggestions: list[Suggestion] = []
        for s in diversified:
            meta = getattr(s, "meta", {})
            final_suggestions.append(
                Suggestion(type=s.type, value=s.value, score=s.score, reason=s.reason, meta=meta)
            )

        final_suggestions.sort(key=lambda s: s.score, reverse=True)
        return RepairResponse(suggestions=final_suggestions[:10])

    def _node_key(self, el, base_tag: str) -> str:
        el_id = el.get("id")
        if el_id:
            return f"id:{el_id}"

        testid = el.get("data-testid")
        if testid:
            return f"testid:{testid}"

        aria = el.get("aria-label")
        if aria:
            return f"aria:{normalize_text(aria)}"

        tag = (el.name or base_tag or "button").lower().strip()
        txt = normalize_text(el.get_text(strip=True) or "")
        cls = el.get("class") or []
        cls = [c.lower() for c in cls][:2]

        return f"fallback:{tag}|{txt[:30]}|{' '.join(cls)}"

