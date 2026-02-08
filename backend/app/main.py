"""FastAPI entry point, CORS, lifespan."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import init_db
from app.api import auth, accounts, audiences, recommendations, settings as settings_api, ingestion

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    from app.services.scheduler import start_scheduler
    scheduler = start_scheduler()
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(
    title="ROAS Audience Recommendation Engine",
    description="Semi-automated audience-level decisions for Meta Ads with ROAS-first recommendations.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url, "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api")
app.include_router(accounts.router, prefix="/api")
app.include_router(audiences.router, prefix="/api")
app.include_router(recommendations.router, prefix="/api")
app.include_router(settings_api.router, prefix="/api")
app.include_router(ingestion.router, prefix="/api")


@app.get("/health")
def health():
    return {"status": "ok"}
