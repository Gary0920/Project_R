from pathlib import Path
import logging

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api import admin, auth, chat, distillation, documents, health, notifications, prompts, rag, skills, updates, workspaces
from core.gbrain import ensure_gbrain_environment
from app.features.knowledge.gbrain.maintenance.worker import start_gbrain_maintenance_worker, stop_gbrain_maintenance_worker
from models import init_db

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")
logger = logging.getLogger(__name__)

app = FastAPI(title="Project_R Backend", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(admin.router)
app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(workspaces.router)
app.include_router(notifications.router)
app.include_router(distillation.router)
app.include_router(prompts.router)
app.include_router(rag.router)
app.include_router(documents.router)
app.include_router(skills.router)
app.include_router(updates.router)


@app.on_event("startup")
def on_startup():
    init_db()
    gbrain_environment = ensure_gbrain_environment()
    if not gbrain_environment["ok"]:
        logger.warning("GBrain environment is not fully ready: %s", gbrain_environment["errors"])
    chat.cleanup_inactive_session_attachments()
    worker_status = start_gbrain_maintenance_worker()
    if not worker_status.get("enabled"):
        logger.info("GBrain maintenance worker is disabled by environment.")


@app.on_event("shutdown")
def on_shutdown():
    stop_gbrain_maintenance_worker()


@app.get("/")
def root():
    return {"app": "Project_R", "status": "running"}
