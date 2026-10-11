from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.api.auth import router as auth_router
from app.api.matches import router as matches_router
from app.api.analytics import router as analytics_router
from app.core.database import create_tables


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_tables()
    yield


app = FastAPI(
    title="ShuttleVision API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(matches_router, prefix="/matches", tags=["matches"])
app.include_router(analytics_router, prefix="/matches", tags=["analytics"])


@app.get("/health")
async def health():
    return {"status": "ok", "service": "shuttlevision-api"}
