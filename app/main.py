from fastapi import FastAPI
from app.api.routes import router as repair_router

app = FastAPI(title="Smart Repair Service", version="1.0.0")
app.include_router(repair_router)

@app.get("/health")
def health():
    return {"status": "ok"}
