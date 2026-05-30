"""One-shot migration: add new columns and tables introduced in Phase 10 workspace/notification/distillation.

Run this ONCE from the backend directory:
    python migrate_phase10.py
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "app.db"


def migrate():
    if not DB_PATH.exists():
        print(f"Database not found at {DB_PATH}, skipping migration.")
        return

    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    # 1) Add workspace_id to chat_sessions (nullable FK)
    try:
        cursor.execute("ALTER TABLE chat_sessions ADD COLUMN workspace_id INTEGER")
        print("  + chat_sessions.workspace_id")
    except sqlite3.OperationalError:
        print("  ~ chat_sessions.workspace_id already exists, skipping")

    # 1b) Add is_archived to chat_sessions
    try:
        cursor.execute("ALTER TABLE chat_sessions ADD COLUMN is_archived BOOLEAN NOT NULL DEFAULT 0")
        print("  + chat_sessions.is_archived")
    except sqlite3.OperationalError:
        print("  ~ chat_sessions.is_archived already exists, skipping")

    # 1c) Add is_pinned to chat_sessions
    try:
        cursor.execute("ALTER TABLE chat_sessions ADD COLUMN is_pinned BOOLEAN NOT NULL DEFAULT 0")
        print("  + chat_sessions.is_pinned")
    except sqlite3.OperationalError:
        print("  ~ chat_sessions.is_pinned already exists, skipping")

    # 1d) Add RAG metadata to chat_messages
    try:
        cursor.execute("ALTER TABLE chat_messages ADD COLUMN rag_used BOOLEAN NOT NULL DEFAULT 0")
        print("  + chat_messages.rag_used")
    except sqlite3.OperationalError:
        print("  ~ chat_messages.rag_used already exists, skipping")

    try:
        cursor.execute("ALTER TABLE chat_messages ADD COLUMN sources_json TEXT NOT NULL DEFAULT '[]'")
        print("  + chat_messages.sources_json")
    except sqlite3.OperationalError:
        print("  ~ chat_messages.sources_json already exists, skipping")

    # 2) Create workspaces table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS workspaces (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name VARCHAR(128) NOT NULL,
            slug VARCHAR(128) NOT NULL UNIQUE,
            description TEXT NOT NULL DEFAULT '',
            created_by INTEGER NOT NULL REFERENCES users(id),
            storage_path VARCHAR(512) NOT NULL DEFAULT '',
            is_archived BOOLEAN NOT NULL DEFAULT 0,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL
        )
    """)
    print("  + workspaces table")

    # 3) Create workspace_members table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS workspace_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id),
            role VARCHAR(16) NOT NULL DEFAULT 'member',
            joined_at DATETIME NOT NULL
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS ix_workspace_members_workspace_id ON workspace_members(workspace_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS ix_workspace_members_user_id ON workspace_members(user_id)")
    print("  + workspace_members table")

    # 4) Create notifications table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            type VARCHAR(32) NOT NULL DEFAULT 'system',
            title VARCHAR(256) NOT NULL,
            content TEXT NOT NULL DEFAULT '',
            is_read BOOLEAN NOT NULL DEFAULT 0,
            link VARCHAR(512) NOT NULL DEFAULT '',
            created_at DATETIME NOT NULL
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS ix_notifications_user_id ON notifications(user_id)")
    print("  + notifications table")

    # 5) Create distillation_suggestions table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS distillation_suggestions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            session_id INTEGER REFERENCES chat_sessions(id) ON DELETE SET NULL,
            suggested_by INTEGER REFERENCES users(id),
            title VARCHAR(256) NOT NULL,
            content TEXT NOT NULL,
            source_message_ids TEXT NOT NULL DEFAULT '',
            status VARCHAR(16) NOT NULL DEFAULT 'pending',
            reviewer_id INTEGER REFERENCES users(id),
            review_comment TEXT NOT NULL DEFAULT '',
            created_at DATETIME NOT NULL,
            reviewed_at DATETIME
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS ix_distillation_suggestions_workspace_id ON distillation_suggestions(workspace_id)")
    print("  + distillation_suggestions table")

    conn.commit()
    conn.close()
    print("\nMigration complete. You can now restart the backend.")


if __name__ == "__main__":
    migrate()
