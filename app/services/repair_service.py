import logging
import uuid

from bs4 import BeautifulSoup

from app.config import cfg
from app.models.schemas import FeedbackRequest, RepairRequest, RepairResponse, Suggestion
from app.scoring.anchors import AnchorResolver
from app.scoring.filters import CandidateFilter
from app.scoring.scoring import ScoreEngine
from app.scoring.selectors import SelectorBuilder
from app.scoring.validator import LocatorValidator
from app.scoring.candidates import CandidateProvider
from app.scoring.diversity import SuggestionDiversifier, NodeGroup, SuggestionItem
from app.scoring.text_utils import normalize_text
<<<<<<< HEAD
from app.scoring.visual_scorer import VisualProfile, VisualScorer
from app.learning.tracker import RequestTracker, TRACKED_SIGNALS

log = logging.getLogger(__name__)
=======
from app.learning.weight_adapter import get_multipliers
from app.learning.similarity import find_similar_repairs
from app.learning.feedback_store import save_repair, save_suggestions
from app.learning.session_manager import get_session_quality_stats, increment_session_repairs
>>>>>>> be7d4dfb52b608334adb987da85aab23e3186faa


class RepairService:
    def __init__(self):
        self.anchor_resolver = AnchorResolver()
        self.filter = CandidateFilter()
        self.scorer = ScoreEngine()
        self.selector_builder = SelectorBuilder()
        self.validator = LocatorValidator()
        self.candidates = CandidateProvider()
        self.diversifier = SuggestionDiversifier(top_nodes=5, top_per_node=2)
        self.visual_scorer = VisualScorer()

        # ── Capa de aprendizaje (opcional) ────────────────────────────────────
        self._learning_enabled = cfg("learning.enabled", True)
        self._adaptive_enabled = cfg("learning.adaptive_weights.enabled", True)
        self._ml_enabled = cfg("learning.ml_model.enabled", True)
        self._adaptive_min_feedbacks = cfg("learning.adaptive_weights.min_feedbacks", 20)

        if self._learning_enabled:
            try:
                from app.learning.db import LearningDB
                from app.learning.signal_stats import SignalStatsManager
                from app.learning.model import RepairModelManager

                self._db = LearningDB(cfg("learning.db_path", "learning.db"))
                self._tracker = RequestTracker(self._db)
                self._signal_stats = SignalStatsManager(
                    self._db,
                    precision_scale=cfg("learning.adaptive_weights.precision_scale", 20),
                )
                self._ml_model = RepairModelManager(
                    self._db,
                    min_samples=cfg("learning.ml_model.min_samples", 100),
                    retrain_every=cfg("learning.ml_model.retrain_every", 50),
                    blend_factor=cfg("learning.ml_model.blend_factor", 0.7),
                )
                log.info("Sistema de aprendizaje inicializado (db=%s)", cfg("learning.db_path", "learning.db"))
            except Exception as exc:
                log.error("Error inicializando learning: %s — deshabilitando", exc)
                self._learning_enabled = False
                self._db = self._tracker = self._signal_stats = self._ml_model = None
        else:
            self._db = self._tracker = self._signal_stats = self._ml_model = None

    # ── repair ────────────────────────────────────────────────────────────────

    def repair(self, req: RepairRequest) -> RepairResponse:
        request_id = str(uuid.uuid4())

        soup = BeautifulSoup(req.pageHtml, "lxml")

        base_tag = (req.baseline.tag or "button").strip()
        base_text = (req.baseline.text or "").strip()
        base_intent = (req.baseline.intent or "").strip()
        base_text_contains = list(req.baseline.textContains or [])
        base_meta = dict(req.baseline.meta or {})
        base_attrs = req.baseline.attrs or {}
<<<<<<< HEAD
        app_name = (req.app or "").strip()

        ctx = req.context

        anchors = self.anchor_resolver.resolve(
            soup=soup, base_text=base_text, context=ctx, raw_html=req.pageHtml,
        )

        visual_profile: VisualProfile = self.visual_scorer.analyze(
            req.elementSnapshot or "", req.pageSnapshot or "",
        )

        try:
            dump = ctx.model_dump()
        except Exception:
            dump = ctx.dict() if hasattr(ctx, "dict") else ctx
        print(">>> CONTEXT:", dump)
        print(">>> BASELINE.intent:", base_intent)
        print(">>> BASELINE.textContains:", base_text_contains)
        print(">>> BASELINE.meta:", base_meta)
        try:
            print(">>> ANCHORS_RESOLVED:", [(lbl, w) for _, lbl, w in anchors])
        except Exception:
            pass
=======
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
>>>>>>> be7d4dfb52b608334adb987da85aab23e3186faa

        # ── Capa 2: bonuses adaptativos ───────────────────────────────────────
        adaptive_bonuses: dict = {}
        if self._learning_enabled and self._adaptive_enabled and self._db:
            try:
                total_fb = self._db.get_total_feedbacks()
                if total_fb >= self._adaptive_min_feedbacks:
                    adaptive_bonuses = self._signal_stats.get_adaptive_bonuses()
                    if adaptive_bonuses:
                        log.debug("adaptive_bonuses activos: %s", adaptive_bonuses)
            except Exception as exc:
                log.debug("Error cargando adaptive_bonuses: %s", exc)

        # ── Capa 3: fingerprint para ML ───────────────────────────────────────
        app_fingerprint = ""
        if self._learning_enabled and self._tracker:
            try:
                app_fingerprint = self._tracker.get_page_fingerprint(soup, app_name)
            except Exception as exc:
                log.debug("Error obteniendo fingerprint: %s", exc)

        # ── Loop de candidatos ────────────────────────────────────────────────
        node_groups: list[NodeGroup] = []
        candidates_signals: list[dict] = []

        for el in self.candidates.candidates(soup, base_tag):

            if not self.filter.accept(el, ctx):
                continue

            score, reasons, signals = self.scorer.score(
                el=el, base_tag=base_tag, base_text=base_text,
                base_attrs=base_attrs, anchors=anchors, base_intent=base_intent,
                base_text_contains=base_text_contains, base_meta=base_meta,
            )

            # Visual bonus
            if visual_profile.available:
                el_dom_text = (
                    el.get_text(strip=True) or el.get("value", "")
                    or el.get("placeholder", "") or el.get("aria-label", "")
                )
                vis_bonus, vis_reasons = self.visual_scorer.score_bonus(
                    profile=visual_profile, el_dom_text=el_dom_text,
                    el_classes=el.get("class") or [], base_text=base_text,
                )
                score += vis_bonus
                reasons.extend(vis_reasons)
                signals["visualBonus"] = vis_bonus
                signals["visualColor"] = visual_profile.dominant_color
                signals["visualZone"] = visual_profile.position_zone

            # Capa 2: bonus adaptativo
            if adaptive_bonuses:
                adaptive_delta = sum(
                    bonus for sig, bonus in adaptive_bonuses.items() if signals.get(sig)
                )
                if adaptive_delta:
                    score += adaptive_delta
                    reasons.append(f"adaptive_bonus ({'+'if adaptive_delta>=0 else ''}{adaptive_delta})")
                    signals["adaptiveBonus"] = adaptive_delta

            # Capa 3: blend ML + confidence
            ml_confidence = 0.0
            if self._learning_enabled and self._ml_enabled and self._ml_model and app_fingerprint:
                try:
                    ml_score, ml_reason, ml_confidence = self._ml_model.apply(
                        signals, app_fingerprint, score
                    )
                    if ml_reason:
                        score = ml_score
                        reasons.append(ml_reason)
                        signals["mlConfidence"] = ml_confidence
                        signals["mlActive"] = True
                except Exception as exc:
                    log.debug("ML apply error: %s", exc)

            # Guardar señales para tracker (todos los candidatos, incluso descartados)
            node_key = self._node_key(el, base_tag)
            candidates_signals.append({
                "node_key": node_key,
                "score": score,
                "signals": {k: signals.get(k) for k in TRACKED_SIGNALS},
            })

            if score < 40:
                continue

            locators = self.selector_builder.build_locators(
                el, base_tag, base_text, context=ctx, base_meta=base_meta
            )
            if not locators:
                continue

            group_items: list[SuggestionItem] = []

            for loc_type, loc_value, extra_reason, extra_bonus, selector_quality in locators:

                v = self.validator.validate(
<<<<<<< HEAD
                    soup=soup, raw_html=req.pageHtml,
                    locator_type=loc_type, locator_value=loc_value
=======
                    soup=soup,
                    raw_html=req.pageHtml,
                    locator_type=loc_type,
                    locator_value=loc_value,
>>>>>>> be7d4dfb52b608334adb987da85aab23e3186faa
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
                    "mlConfidence": round(ml_confidence, 3),
                    "mlActive": signals.get("mlActive", False),
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
<<<<<<< HEAD
                        "visualBonus": signals.get("visualBonus", 0),
                        "visualColor": signals.get("visualColor", ""),
                        "visualZone": signals.get("visualZone", ""),
                        "adaptiveBonus": signals.get("adaptiveBonus", 0),
                    }
=======
                    },
>>>>>>> be7d4dfb52b608334adb987da85aab23e3186faa
                }

                group_items.append(
                    SuggestionItem(
<<<<<<< HEAD
                        type=loc_type, value=loc_value, score=final_score,
                        reason=" | ".join(reasons + [
                            f"{extra_reason} (+{extra_bonus})", f"unicidad: {v.note}"
                        ]),
                    )
                )
                group_items[-1].__dict__["meta"] = meta
=======
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
>>>>>>> be7d4dfb52b608334adb987da85aab23e3186faa

            if group_items:
                node_groups.append(NodeGroup(node_key=node_key, suggestions=group_items))

        # ── Tracking del request ──────────────────────────────────────────────
        if self._learning_enabled and self._tracker and candidates_signals:
            try:
                self._tracker.track(
                    request_id=request_id, app_name=app_name, soup=soup,
                    baseline_tag=base_tag, baseline_text=base_text,
                    candidates_signals=candidates_signals,
                )
            except Exception as exc:
                log.error("Error en tracker.track: %s", exc)

        # ── Diversificación y respuesta ───────────────────────────────────────
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
<<<<<<< HEAD
        return RepairResponse(requestId=request_id, suggestions=final_suggestions[:10])

    # ── feedback ──────────────────────────────────────────────────────────────

    def process_feedback(self, req: FeedbackRequest) -> dict:
        if not self._learning_enabled or not self._db:
            return {"status": "learning_disabled"}

        try:
            self._db.save_feedback(
                request_id=req.requestId,
                chosen_node_key=req.chosenNodeKey,
                chosen_type=req.chosenType,
                chosen_value=req.chosenValue,
                success=req.success,
            )
        except Exception as exc:
            log.error("save_feedback error: %s", exc)
            return {"status": "error", "detail": str(exc)}

        # Capa 2: actualizar señales (incluso para feedback negativo)
        if self._adaptive_enabled and self._signal_stats:
            try:
                self._signal_stats.update_from_feedback(req.requestId, req.chosenNodeKey)
            except Exception as exc:
                log.error("update_from_feedback error: %s", exc)

        # Capa 3: reentrenar solo con feedbacks exitosos
        if req.success and self._ml_enabled and self._ml_model:
            try:
                request_row = self._db.get_request(req.requestId)
                fingerprint = (request_row or {}).get("page_fingerprint", "")
                if fingerprint:
                    total = self._db.get_total_feedbacks_by_fingerprint(fingerprint)
                    trained = self._ml_model.train_if_needed(fingerprint, total)
                    if trained:
                        log.info("Modelo reentrenado fp=%s total_fb=%d", fingerprint, total)
            except Exception as exc:
                log.error("train_if_needed error: %s", exc)

        return {"status": "ok", "requestId": req.requestId}

    # ── learning stats ────────────────────────────────────────────────────────

    def get_learning_stats(self) -> dict:
        if not self._learning_enabled or not self._db:
            return {"status": "learning_disabled"}

        try:
            total_feedbacks = self._db.get_total_feedbacks()
            raw_signals = self._db.get_signal_stats()
            raw_models = self._db.get_all_models()

            precision_scale = cfg("learning.adaptive_weights.precision_scale", 20)
            signals = {
                name: {
                    "precision": round(row.get("precision", 0.5), 3),
                    "total_present": row.get("total_present", 0),
                    "total_correct": row.get("total_correct", 0),
                    "bonus_pts": int((row.get("precision", 0.5) - 0.5) * precision_scale),
                    "last_updated": row.get("last_updated", ""),
                }
                for name, row in raw_signals.items()
            }

            models = [
                {
                    "app_fingerprint": m.get("app_fingerprint", ""),
                    "training_samples": m.get("training_samples", 0),
                    "accuracy": round(m.get("accuracy", 0.0), 3),
                    "last_trained": m.get("last_trained", ""),
                }
                for m in raw_models
            ]

            return {
                "status": "ok",
                "total_feedbacks": total_feedbacks,
                "adaptive_weights": {
                    "enabled": self._adaptive_enabled,
                    "min_feedbacks": self._adaptive_min_feedbacks,
                    "active": total_feedbacks >= self._adaptive_min_feedbacks,
                    "signals": signals,
                },
                "ml_model": {
                    "enabled": self._ml_enabled,
                    "min_samples": cfg("learning.ml_model.min_samples", 100),
                    "blend_factor": cfg("learning.ml_model.blend_factor", 0.7),
                    "models": models,
                },
            }
        except Exception as exc:
            log.error("get_learning_stats error: %s", exc)
            return {"status": "error", "detail": str(exc)}

    # ── helpers ───────────────────────────────────────────────────────────────
=======
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
>>>>>>> be7d4dfb52b608334adb987da85aab23e3186faa

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
<<<<<<< HEAD
        cls = el.get("class") or []
        cls = [c.lower() for c in cls][:2]
=======
        cls = [c.lower() for c in (el.get("class") or [])][:2]
>>>>>>> be7d4dfb52b608334adb987da85aab23e3186faa
        return f"fallback:{tag}|{txt[:30]}|{' '.join(cls)}"
