from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from scripts.gbrain_register_agent_client import _load_dotenv, _updated_env_text  # noqa: E402


def _extract_job_id(result: dict[str, Any]) -> int | None:
    candidates = [
        result.get("job_id"),
        result.get("id"),
        (result.get("result") or {}).get("id") if isinstance(result.get("result"), dict) else None,
        (result.get("data") or {}).get("id") if isinstance(result.get("data"), dict) else None,
    ]
    for candidate in candidates:
        try:
            if candidate is not None:
                return int(candidate)
        except (TypeError, ValueError):
            continue
    return None


def _write_binding_submit_verified(path: Path) -> None:
    original = path.read_text(encoding="utf-8") if path.exists() else ""
    path.write_text(
        _updated_env_text(original, {"GBRAIN_AGENT_BINDING_SUBMIT_VERIFIED": "true"}),
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Submit a Project_R citation-fixer agent smoke job through GBrain MCP, "
            "then cancel it by default so PGLite does not accumulate waiting jobs."
        )
    )
    parser.add_argument("--env-path", default=str(BACKEND_DIR / ".env"))
    parser.add_argument("--page-slug", default="rules/书面化原则")
    parser.add_argument("--allowed-slug-prefix", default="rules/")
    parser.add_argument("--max-turns", type=int, default=1)
    parser.add_argument("--no-cancel", action="store_true", help="Leave the submitted job waiting/running.")
    parser.add_argument("--no-env-update", action="store_true")
    args = parser.parse_args()

    env_path = Path(args.env_path)
    if not env_path.is_absolute():
        env_path = (Path.cwd() / env_path).resolve()

    _load_dotenv(env_path)
    sys.path.insert(0, str(BACKEND_DIR))

    from core.gbrain import GBrainAdapter

    adapter = GBrainAdapter()
    result = adapter.submit_citation_fixer(
        page_slug=args.page_slug,
        allowed_slug_prefixes=[args.allowed_slug_prefix],
        max_turns=args.max_turns,
        notes="Project_R binding smoke test: verify submit_agent accepts OAuth bindings; do not rewrite content unless citation syntax is malformed.",
    )
    if result.get("status") != "ok":
        print("GBrain submit_agent binding smoke failed.")
        print(f"- status: {result.get('status')}")
        print(f"- error: {result.get('error') or result.get('message') or '<none>'}")
        return 1

    job_id = _extract_job_id(result)
    print("GBrain submit_agent binding smoke passed.")
    print(f"- job_id: {job_id if job_id is not None else '<unknown>'}")

    if job_id is not None and not args.no_cancel:
        cancel_result = adapter.cancel_job(job_id)
        print(f"- cancel_status: {cancel_result.get('status') or cancel_result.get('ok') or 'unknown'}")

    if not args.no_env_update:
        _write_binding_submit_verified(env_path)
        print("- GBRAIN_AGENT_BINDING_SUBMIT_VERIFIED=true")

    print("- execution verified: false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
