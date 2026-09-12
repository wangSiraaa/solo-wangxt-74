"""FastAPI 入口。"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .database import engine
from .models import Base
from .routers import germplasm, matings, observations, stats, trials


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    if os.environ.get("SEED_DEMO") == "1":
        from .database import SessionLocal
        from .seed import seed_if_empty

        session = SessionLocal()
        try:
            seed_if_empty(session)
        finally:
            session.close()
    yield


app = FastAPI(title="育种谱系与家系筛选", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(germplasm.router)
app.include_router(matings.router)
app.include_router(trials.router)
app.include_router(observations.router)
app.include_router(stats.router)


@app.get("/api/health")
def health() -> dict:
    return {"ok": True}
