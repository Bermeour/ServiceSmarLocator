from fastapi import APIRouter, Body, Request
from app.models.schemas import FeedbackRequest, RepairRequest, RepairResponse
from app.services.repair_service import RepairService

router = APIRouter()
service = RepairService()


@router.post("/repair", response_model=RepairResponse)
async def repair(request: Request, req: RepairRequest = Body(...)):
    print("CT:", request.headers.get("content-type"))
    raw = await request.body()
    print("RAW LEN:", len(raw))
    return service.repair(req)


@router.post("/feedback")
def feedback(req: FeedbackRequest = Body(...)):
    return service.process_feedback(req)


@router.get("/learning/stats")
def learning_stats():
    return service.get_learning_stats()
