from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .db import create_db_and_tables
from .routers import escalations, mock_target, runs
from .storage import LocalStorage

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    LocalStorage().ensure_ready()
    yield


app = FastAPI(title="Migration Agent", version="0.1.0", lifespan=lifespan)
app.include_router(runs.router)
app.include_router(escalations.router)
app.include_router(mock_target.router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "db": settings.database_url.split("://")[0],
        "llm": settings.llm_provider or "mock",
    }
