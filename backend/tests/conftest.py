import os
import tempfile
import time
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
REAL_APP_DB = (BACKEND_DIR / "app.db").resolve()
_TEMP_DB_PATH: Path | None = None


def _sqlite_path_from_url(raw: str) -> Path | None:
    if not raw.startswith("sqlite:///"):
        return None
    path_text = raw.removeprefix("sqlite:///")
    path = Path(path_text)
    if path_text.startswith("./"):
        path = BACKEND_DIR / path_text.removeprefix("./")
    return path.resolve()


def _points_to_real_app_db(raw: str | None) -> bool:
    if not raw:
        return False
    sqlite_path = _sqlite_path_from_url(raw)
    return sqlite_path == REAL_APP_DB


def pytest_configure(config):
    global _TEMP_DB_PATH
    os.environ["PROJECT_R_TESTING"] = "1"
    raw_url = os.environ.get("DATABASE_URL")
    if _points_to_real_app_db(raw_url):
        raise RuntimeError("pytest refused to use real backend/app.db; set DATABASE_URL to a temporary SQLite database")
    if not raw_url:
        handle, temp_name = tempfile.mkstemp(prefix="project-r-pytest-", suffix=".db")
        os.close(handle)
        _TEMP_DB_PATH = Path(temp_name)
        os.environ["DATABASE_URL"] = f"sqlite:///{_TEMP_DB_PATH}"


def pytest_runtest_setup(item):
    if _points_to_real_app_db(os.environ.get("DATABASE_URL")):
        raise RuntimeError("pytest refused to use real backend/app.db")


def pytest_sessionfinish(session, exitstatus):
    if _TEMP_DB_PATH and _TEMP_DB_PATH.exists():
        try:
            from models import engine

            engine.dispose()
        except Exception:
            pass
        for attempt in range(5):
            try:
                _TEMP_DB_PATH.unlink()
                break
            except PermissionError:
                if attempt == 4:
                    raise
                time.sleep(0.2)
