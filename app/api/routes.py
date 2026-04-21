from fastapi import APIRouter, Body, HTTPException

from app.models.schemas import (
    RepairRequest,
    RepairResponse,
    SessionCreateRequest,
    SessionResponse,
    FeedbackRequest,
    FeedbackResponse,
)
from app.services.repair_service import RepairService
from app.learning.session_manager import create_session, get_session
from app.learning.feedback_store import save_feedback
from app.learning.weight_adapter import update_weights, get_all_weights, get_multipliers

router = APIRouter()
service = RepairService()


@router.post("/repair", response_model=RepairResponse)
def repair(req: RepairRequest = Body(...)):
    return service.repair(req)


@router.post("/session", response_model=SessionResponse)
def new_session(req: SessionCreateRequest = Body(default=SessionCreateRequest())):
    return create_session(app_domain=req.app_domain)


@router.get("/session/{session_id}")
def session_info(session_id: str):
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Sesión no encontrada")
    return session


@router.post("/feedback", response_model=FeedbackResponse)
def feedback(req: FeedbackRequest = Body(...)):
    try:
        result = save_feedback(
            suggestion_id=req.suggestion_id,
            session_id=req.session_id,
            success=req.success,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    app_domain = req.app_domain or "global"
    quality = result["selector_quality"]
    update_weights(selector_quality=quality, success=req.success, app_domain=app_domain)

    # Calcular nuevo multiplicador para informar al cliente
    mults = get_multipliers(app_domain=app_domain)
    new_mult = mults.get(quality)

    return FeedbackResponse(ok=True, selector_quality=quality, new_multiplier=new_mult)


@router.get("/weights")
def weights(app_domain: str = "global"):
    return {"app_domain": app_domain, "weights": get_all_weights(app_domain)}
