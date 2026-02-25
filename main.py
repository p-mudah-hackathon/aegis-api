"""
AegisNode API — Gateway Service
Routes: transactions, fraud reasoning, attack simulation, dashboard, system.
DB: SQLite + SQLAlchemy async. Error handling: consistent JSON. Logging: structured.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv(override=True)

from config import settings
from database import init_db
from errors import register_error_handlers
from routers.fraud import router as fraud_router
from routers.attack import router as attack_router
from routers.dashboard import router as dashboard_router
from routers.transactions import router as transactions_router
from routers.system import router as system_router
from routers.filler import router as filler_router
from routers.chat import router as chat_router

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("aegis")


# ── Lifespan (startup/shutdown) ──────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing database...")
    await init_db()
    logger.info("Database ready (SQLite)")
    logger.info(f"aegis-ai URL: {settings.aegis_ai_url}")
    logger.info(f"DashScope key: {'configured' if settings.dashscope_api_key else 'NOT SET'}")
    yield
    logger.info("Shutting down...")


# ── App ──────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="AegisNode — API Gateway",
    description=(
        "Main API gateway for the Aegis fraud detection platform.\n\n"
        "**Endpoints:**\n"
        "- **Transactions** — CRUD, pagination, filtering, analyst review\n"
        "- **Fraud Reasoning** — Qwen AI explanations for flagged transactions\n"
        "- **Attack Simulation** — Generate & score synthetic transactions\n"
        "- **Dashboard** — Live WebSocket stream + stats\n"
        "- **System** — Health, model status, WebSocket schema docs\n\n"
        "Calls aegis-ai (ML model service) for HTGNN inference."
    ),
    version="1.1.0",
    lifespan=lifespan,
)

# ── Middleware ───────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Lock down in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Error handlers ───────────────────────────────────────────────────────────
register_error_handlers(app)

# ── Routers ──────────────────────────────────────────────────────────────────
app.include_router(transactions_router)
app.include_router(fraud_router)
app.include_router(attack_router)
app.include_router(dashboard_router)
app.include_router(system_router)
app.include_router(filler_router)
app.include_router(chat_router)


@app.get("/health", tags=["System"])
async def health():
    return {"status": "ok", "service": "aegis-api-gateway"}


# ── Entry point ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)
