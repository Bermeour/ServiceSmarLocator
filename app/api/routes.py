from fastapi import APIRouter, Body
from app.models.schemas import RepairRequest, RepairResponse
from app.services.repair_service import RepairService

#router = APIRouter()
#service = RepairService()

#@router.post("/repair", response_model=RepairResponse)
#def repair(req: RepairRequest = Body(...)):
#    return service.repair(req)

from fastapi import APIRouter, Body, Request
from app.models.schemas import RepairRequest, RepairResponse
from app.services.repair_service import RepairService

router = APIRouter()
service = RepairService()

@router.post("/repair", response_model=RepairResponse)
async def repair(request: Request, req: RepairRequest = Body(...)):
    print("CT:", request.headers.get("content-type"))
    raw = await request.body()
    print("RAW LEN:", len(raw))
    return service.repair(req)

