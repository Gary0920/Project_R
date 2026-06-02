from __future__ import annotations

import json
import os
import sys
from pathlib import Path


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


def main() -> int:
    _load_dotenv(BACKEND_DIR / ".env")
    sys.path.insert(0, str(BACKEND_DIR))

    from core.gbrain_customer_sources import compile_customer_reference_sources, ensure_and_sync_customer_reference

    manifest = compile_customer_reference_sources()
    print(json.dumps({"manifest_summary": manifest.get("summary")}, ensure_ascii=False, indent=2))

    sync_result = ensure_and_sync_customer_reference(full=True)
    safe_result = {
        "ok": sync_result.get("ok"),
        "source_id": sync_result.get("source_id"),
        "registration_status": (sync_result.get("registration") or {}).get("registration", {}).get("status"),
        "sync_status": (sync_result.get("sync") or {}).get("status"),
        "think_client_status": (sync_result.get("think_client") or {}).get("status"),
        "error": (
            (sync_result.get("registration") or {}).get("registration", {}).get("error")
            or (sync_result.get("sync") or {}).get("error")
            or (sync_result.get("think_client") or {}).get("error")
        ),
    }
    print(json.dumps(safe_result, ensure_ascii=False, indent=2))
    return 0 if sync_result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
