from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.api.routes import router as repair_router
from app.learning.db import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Smart Repair Service", version="2.0.0", lifespan=lifespan)
app.include_router(repair_router)


@app.get("/health")
def health():
    return {"status": "ok"}
