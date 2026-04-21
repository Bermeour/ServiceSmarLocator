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
from app.learning.weight_adapter import get_multipliers
from app.learning.similarity import find_similar_repairs
from app.learning.feedback_store import save_repair, save_suggestions
from app.learning.session_manager import get_session_quality_stats, increment_session_repairs


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
        base_intent = (req.baseline.intent or "").strip()
        base_text_contains = list(req.baseline.textContains or [])
        base_meta = dict(req.baseline.meta or {})
        base_attrs = req.baseline.attrs or {}
        session_id = req.session_id
        app_domain = req.app_domain or "global"

        ctx = req.context
        anchors = self.anchor_resolver.resolve(soup=soup, base_text=base_text, context=ctx)

        # ---- Aprendizaje: pesos adaptativos + similitud ----
        session_stats = get_session_quality_stats(session_id) if session_id else {}
        multipliers = get_multipliers(app_domain=app_domain, session_stats=session_stats)

        similar = find_similar_repairs(base_tag, base_text, base_intent)
        # max +15 puntos por similitud con reparaciones pasadas exitosas
        similarity_boost = {
            s["selector_quality"]: int(s["similarity"] * 15)
            for s in similar
        }

        node_groups: list[NodeGroup] = []

        for el in self.candidates.candidates(soup, base_tag):

            if not self.filter.accept(el, ctx):
                continue

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

            locators = self.selector_builder.build_locators(
                el, base_tag, base_text, context=ctx, base_meta=base_meta
            )
            if not locators:
                continue

            node_key = self._node_key(el, base_tag)
            group_items: list[SuggestionItem] = []

            for loc_type, loc_value, extra_reason, extra_bonus, selector_quality in locators:

                v = self.validator.validate(
                    soup=soup,
                    raw_html=req.pageHtml,
                    locator_type=loc_type,
                    locator_value=loc_value,
                )
                if not v.ok:
                    continue

                # Aplicar multiplicador aprendido sobre el bonus del selector
                quality_mult = multipliers.get(selector_quality, 1.0)
                sim_boost = similarity_boost.get(selector_quality, 0)
                adjusted_bonus = int((extra_bonus or 0) * quality_mult)
                final_score = int(score + adjusted_bonus + (v.bonus or 0) + sim_boost)

                meta = {
                    "nodeKey": node_key,
                    "selectorQuality": selector_quality,
                    "context": {
                        "containerId": getattr(ctx, "containerId", None),
                        "formId": getattr(ctx, "formId", None),
                        "excludeIdsCount": len(ctx.excludeIds or []),
                    },
                    "uniqueness": {
                        "matches": v.matches,
                        "bonus": v.bonus,
                        "note": v.note,
                    },
                    "learning": {
                        "qualityMultiplier": quality_mult,
                        "similarityBoost": sim_boost,
                        "appDomain": app_domain,
                    },
                    "signals": {
                        "zonePenalty": signals.get("zonePenalty", 0),
                        "classSignals": signals.get("classSignals", []),
                        "textHit": signals.get("textHit", False),
                        "anchorHits": signals.get("anchorHits", []),
                        "textContainsMatched": signals.get("textContainsMatched", 0),
                        "textContainsTotal": signals.get("textContainsTotal", 0),
                        "intentBonus": signals.get("intentBonus", 0),
                        "metaBonus": signals.get("metaBonus", 0),
                        "baselineIntent": base_intent,
                        "baselineTextContains": base_text_contains,
                        "baselineMeta": base_meta,
                    },
                }

                group_items.append(
                    SuggestionItem(
                        type=loc_type,
                        value=loc_value,
                        score=final_score,
                        reason=" | ".join(
                            reasons
                            + [
                                f"{extra_reason} (+{adjusted_bonus})",
                                f"unicidad: {v.note}",
                            ]
                        ),
                        meta=meta,
                    )
                )

            if group_items:
                node_groups.append(NodeGroup(node_key=node_key, suggestions=group_items))

        diversified = self.diversifier.diversify(node_groups)

        final_suggestions: list[Suggestion] = []
        for s in diversified:
            final_suggestions.append(
                Suggestion(
                    type=s.type,
                    value=s.value,
                    score=s.score,
                    reason=s.reason,
                    meta=s.meta,
                )
            )

        final_suggestions.sort(key=lambda s: s.score, reverse=True)
        top = final_suggestions[:10]

        # ---- Persistir para aprendizaje futuro ----
        repair_id = save_repair(session_id, req.pageHtml, base_tag, base_text, base_intent)
        if session_id:
            increment_session_repairs(session_id)

        suggestion_records = [
            {
                "type": s.type,
                "value": s.value,
                "score": s.score,
                "selector_quality": s.meta.get("selectorQuality"),
                "rank": i,
            }
            for i, s in enumerate(top)
        ]
        suggestion_ids = save_suggestions(repair_id, session_id, suggestion_records)

        # Inyectar IDs en meta para que el cliente pueda enviar feedback
        for s, sid in zip(top, suggestion_ids):
            s.meta["suggestionId"] = sid
            s.meta["repairId"] = repair_id

        return RepairResponse(suggestions=top, repair_id=repair_id)

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
        cls = [c.lower() for c in (el.get("class") or [])][:2]
        return f"fallback:{tag}|{txt[:30]}|{' '.join(cls)}"
