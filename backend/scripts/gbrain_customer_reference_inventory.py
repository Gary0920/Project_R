from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any


BACKEND_DIR = Path(__file__).resolve().parents[1]


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.split("#", 1)[0].strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _path_summary(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "path": str(path.resolve()),
            "exists": False,
            "files": 0,
            "bytes": 0,
            "markdown_files": 0,
        }
    files = [item for item in path.rglob("*") if item.is_file() and ".git" not in item.parts]
    return {
        "path": str(path.resolve()),
        "exists": True,
        "files": len(files),
        "bytes": sum(item.stat().st_size for item in files),
        "markdown_files": sum(1 for item in files if item.suffix.lower() in {".md", ".markdown"}),
    }


def _manifest_client(manifest_path: Path, source_id: str) -> dict[str, Any]:
    if not manifest_path.exists():
        return {"path": str(manifest_path.resolve()), "exists": False, "client": None}
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"path": str(manifest_path.resolve()), "exists": True, "error": str(exc), "client": None}
    clients = payload.get("clients") if isinstance(payload, dict) else None
    client = clients.get(source_id) if isinstance(clients, dict) else None
    if not isinstance(client, dict):
        return {"path": str(manifest_path.resolve()), "exists": True, "client": None}
    return {
        "path": str(manifest_path.resolve()),
        "exists": True,
        "client": {
            key: value
            for key, value in client.items()
            if key not in {"client_secret"}
        },
    }


def main() -> int:
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    _load_dotenv(BACKEND_DIR / ".env")
    sys.path.insert(0, str(BACKEND_DIR))

    from app.features.knowledge.gbrain import (
        CUSTOMER_REFERENCE_SOURCE_ID,
        GBrainAdapter,
        load_gbrain_settings,
    )

    settings = load_gbrain_settings()
    adapter = GBrainAdapter(settings)
    reference_root = BACKEND_DIR / "workspace_data" / "customer" / "reference"
    legacy_ready = reference_root / "derived"
    legacy_manifests = reference_root / "manifests"

    source_plan = {
        "source_id": CUSTOMER_REFERENCE_SOURCE_ID,
        "name": "Project_R Legacy Customer Reference",
        "path": str(legacy_ready.resolve()),
        "federated": False,
    }
    source_status = adapter.source_status(source_plan)
    client_manifest = _manifest_client(settings.think_source_clients_path, CUSTOMER_REFERENCE_SOURCE_ID)

    payload = {
        "ok": True,
        "source_id": CUSTOMER_REFERENCE_SOURCE_ID,
        "note": "Read-only inventory. No files, sources, OAuth clients, graph pages, or regression fixtures were deleted.",
        "gbrain_source": {
            key: value
            for key, value in source_status.items()
            if key not in {"result"}
        },
        "oauth_client_manifest": client_manifest,
        "artifacts": {
            "legacy_root": _path_summary(reference_root),
            "legacy_derived": _path_summary(legacy_ready),
            "legacy_manifests": _path_summary(legacy_manifests),
            "crm_raw_preserved": _path_summary(BACKEND_DIR / "workspace_data" / "customer" / "CRM" / "raw"),
            "crm_gbrain_ready": _path_summary(
                BACKEND_DIR / "workspace_data" / "_preprocessed" / "customer" / "crm" / "gbrain-ready"
            ),
            "crm_manifests": _path_summary(
                BACKEND_DIR / "workspace_data" / "_preprocessed" / "customer" / "crm" / "manifests"
            ),
        },
        "cleanup_candidates": [
            "GBrain source customer-reference",
            "source-scoped OAuth client entry for customer-reference",
            str(legacy_ready.resolve()),
            str(legacy_manifests.resolve()),
            "customer-reference regression fixtures/scripts after CRM regression is verified",
        ],
        "preserve": [
            str((BACKEND_DIR / "workspace_data" / "customer").resolve()),
            str((BACKEND_DIR / "workspace_data" / "customer" / "CRM" / "raw").resolve()),
            str((BACKEND_DIR / "workspace_data" / "_preprocessed" / "customer" / "crm").resolve()),
        ],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
