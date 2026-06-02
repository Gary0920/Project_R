from pathlib import Path
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase

BASE_DIR = Path(__file__).resolve().parent.parent


class Base(DeclarativeBase):
    pass


def get_db_url() -> str:
    from os import getenv
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env")
    raw = getenv("DATABASE_URL", "sqlite:///./app.db")
    # Convert sqlite relative paths to absolute based on BASE_DIR
    if raw.startswith("sqlite:///./"):
        return f"sqlite:///{BASE_DIR / raw.removeprefix('sqlite:///./')}"
    return raw


engine = create_engine(get_db_url(), connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    from models.user import User
    from models.session import ChatSession
    from models.message import ChatMessage
    from models.audit_log import AuditLog
    from models.knowledge_review import KnowledgeReview
    from models.workspace import Workspace, WorkspaceMember, WorkspaceGroupAccess, WorkspaceFile
    from models.notification import Notification
    from models.distillation import DistillationSuggestion
    from models.attachment import SessionAttachment
    from models.agent_run import AgentRun, AgentEvent
    from models.generated_file import GeneratedFile
    from models.skill_run import SkillRun
    from models.client_update import ClientUpdateRelease
    from models.workspace_ingest_job import WorkspaceIngestJob
    Base.metadata.create_all(bind=engine)
    _ensure_sqlite_columns()
    db = SessionLocal()
    try:
        from core.system_accounts import ensure_system_admin

        ensure_system_admin(db)
    finally:
        db.close()


def _ensure_sqlite_columns() -> None:
    if not engine.url.drivername.startswith("sqlite"):
        return
    inspector = inspect(engine)
    columns_by_table = {
        table: {column["name"] for column in inspector.get_columns(table)}
        for table in inspector.get_table_names()
    }
    migrations = [
        ("users", "is_active", "ALTER TABLE users ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT 1"),
        ("users", "work_group", "ALTER TABLE users ADD COLUMN work_group VARCHAR(64) NOT NULL DEFAULT ''"),
        ("users", "last_login_at", "ALTER TABLE users ADD COLUMN last_login_at DATETIME"),
        ("skill_runs", "generated_file_id", "ALTER TABLE skill_runs ADD COLUMN generated_file_id VARCHAR(36)"),
        ("workspace_files", "trash_path", "ALTER TABLE workspace_files ADD COLUMN trash_path VARCHAR(512) NOT NULL DEFAULT ''"),
        ("workspace_files", "rag_status", "ALTER TABLE workspace_files ADD COLUMN rag_status VARCHAR(32) NOT NULL DEFAULT 'pending'"),
        ("workspace_files", "updated_at", "ALTER TABLE workspace_files ADD COLUMN updated_at DATETIME"),
        ("workspace_files", "deleted_at", "ALTER TABLE workspace_files ADD COLUMN deleted_at DATETIME"),
        ("workspace_files", "deleted_by", "ALTER TABLE workspace_files ADD COLUMN deleted_by INTEGER"),
        ("workspaces", "brand", "ALTER TABLE workspaces ADD COLUMN brand VARCHAR(32) NOT NULL DEFAULT 'BFI'"),
        ("workspaces", "workspace_kind", "ALTER TABLE workspaces ADD COLUMN workspace_kind VARCHAR(16) NOT NULL DEFAULT 'project'"),
        ("workspaces", "is_default", "ALTER TABLE workspaces ADD COLUMN is_default BOOLEAN NOT NULL DEFAULT 0"),
        ("workspaces", "is_hidden", "ALTER TABLE workspaces ADD COLUMN is_hidden BOOLEAN NOT NULL DEFAULT 0"),
        ("chat_messages", "is_excluded", "ALTER TABLE chat_messages ADD COLUMN is_excluded BOOLEAN NOT NULL DEFAULT 0"),
        ("chat_messages", "version_group_id", "ALTER TABLE chat_messages ADD COLUMN version_group_id VARCHAR(36)"),
        ("chat_messages", "version_index", "ALTER TABLE chat_messages ADD COLUMN version_index INTEGER NOT NULL DEFAULT 1"),
        ("chat_messages", "active_version", "ALTER TABLE chat_messages ADD COLUMN active_version BOOLEAN NOT NULL DEFAULT 1"),
        ("chat_messages", "context_json", "ALTER TABLE chat_messages ADD COLUMN context_json TEXT NOT NULL DEFAULT '{}'"),
        ("session_attachments", "message_id", "ALTER TABLE session_attachments ADD COLUMN message_id INTEGER"),
        ("session_attachments", "source_scope", "ALTER TABLE session_attachments ADD COLUMN source_scope VARCHAR(64) NOT NULL DEFAULT 'session_upload'"),
        ("session_attachments", "source_label", "ALTER TABLE session_attachments ADD COLUMN source_label VARCHAR(80) NOT NULL DEFAULT '会话临时上传'"),
        ("session_attachments", "authorization_status", "ALTER TABLE session_attachments ADD COLUMN authorization_status VARCHAR(32) NOT NULL DEFAULT 'uploaded'"),
        ("agent_runs", "workspace_id", "ALTER TABLE agent_runs ADD COLUMN workspace_id INTEGER"),
        ("agent_runs", "source_type", "ALTER TABLE agent_runs ADD COLUMN source_type VARCHAR(64) NOT NULL DEFAULT 'chat'"),
        ("agent_runs", "source_id", "ALTER TABLE agent_runs ADD COLUMN source_id VARCHAR(128) NOT NULL DEFAULT ''"),
        ("agent_runs", "result_json", "ALTER TABLE agent_runs ADD COLUMN result_json TEXT NOT NULL DEFAULT '{}'"),
        ("agent_runs", "error_message", "ALTER TABLE agent_runs ADD COLUMN error_message TEXT NOT NULL DEFAULT ''"),
        ("notifications", "category", "ALTER TABLE notifications ADD COLUMN category VARCHAR(32) NOT NULL DEFAULT 'system'"),
        ("notifications", "severity", "ALTER TABLE notifications ADD COLUMN severity VARCHAR(16) NOT NULL DEFAULT 'info'"),
        ("notifications", "action_status", "ALTER TABLE notifications ADD COLUMN action_status VARCHAR(16) NOT NULL DEFAULT 'none'"),
        ("notifications", "action_kind", "ALTER TABLE notifications ADD COLUMN action_kind VARCHAR(64) NOT NULL DEFAULT ''"),
        ("notifications", "action_payload_json", "ALTER TABLE notifications ADD COLUMN action_payload_json TEXT NOT NULL DEFAULT '{}'"),
        ("notifications", "event_key", "ALTER TABLE notifications ADD COLUMN event_key VARCHAR(128) NOT NULL DEFAULT ''"),
        ("notifications", "expires_at", "ALTER TABLE notifications ADD COLUMN expires_at DATETIME"),
    ]
    with engine.begin() as conn:
        for table, column, ddl in migrations:
            if table in columns_by_table and column not in columns_by_table[table]:
                conn.execute(text(ddl))
        if "workspace_files" in columns_by_table and "updated_at" not in columns_by_table["workspace_files"]:
            conn.execute(text("UPDATE workspace_files SET updated_at = created_at WHERE updated_at IS NULL"))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
