from __future__ import annotations

import argparse
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


def _check_agent_status(status: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if not status.get("enabled"):
        failures.append("GBRAIN_AGENT_ENABLED is not true.")
    if not status.get("oauth_configured"):
        failures.append("GBRAIN_AGENT_OAUTH_CLIENT_ID/SECRET are not both configured.")
    missing_tools = status.get("citation_fixer_missing_tools") or []
    if missing_tools:
        failures.append(f"GBRAIN_CITATION_FIXER_TOOLS is missing: {', '.join(missing_tools)}.")
    if status.get("model_requires_gateway_loop") and status.get("gateway_loop_status") != "verified":
        failures.append("Non-Anthropic agent model requires GBrain agent.use_gateway_loop=true; not verified.")
    if not status.get("binding_submit_verified"):
        failures.append("GBrain submit_agent binding has not been smoke-verified.")
    if not status.get("inline_execution_verified"):
        failures.append("GBrain PGLite inline subagent execution has not been smoke-verified.")
    if not status.get("execution_verified"):
        failures.append("GBRAIN_AGENT_EXECUTION_VERIFIED is not true; no real citation-fixer/subagent run has been accepted.")
    worker = status.get("worker") or {}
    if worker.get("persistent_worker_supported") is False:
        failures.append("Current GBrain engine is PGLite; persistent worker daemon is not supported.")
    return failures


def _redacted_status(status: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": status.get("status"),
        "enabled": status.get("enabled"),
        "oauth_configured": status.get("oauth_configured"),
        "client_configured": status.get("client_configured"),
        "scope": status.get("scope"),
        "model_configured": status.get("model_configured"),
        "model_requires_gateway_loop": status.get("model_requires_gateway_loop"),
        "gateway_loop_status": status.get("gateway_loop_status"),
        "binding_submit_verified": status.get("binding_submit_verified"),
        "inline_execution_verified": status.get("inline_execution_verified"),
        "execution_verified": status.get("execution_verified"),
        "execution_ready": status.get("execution_ready"),
        "citation_fixer_tools": status.get("citation_fixer_tools"),
        "citation_fixer_missing_tools": status.get("citation_fixer_missing_tools"),
        "binding_requirements": status.get("binding_requirements"),
        "binding_status": status.get("binding_status"),
        "worker": status.get("worker"),
        "timeout_seconds": status.get("timeout_seconds"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Project_R -> GBrain agent/citation-fixer readiness.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero when readiness is not complete.")
    args = parser.parse_args()

    _load_dotenv(BACKEND_DIR / ".env")
    sys.path.insert(0, str(BACKEND_DIR))

    from app.features.knowledge.gbrain import GBrainAdapter

    status = _redacted_status(GBrainAdapter().agent_status())
    failures = _check_agent_status(status)
    payload = {
        "ok": not failures,
        "status": status,
        "failures": failures,
    }

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"GBrain agent status: {status.get('status')}")
        print(f"OAuth configured: {status.get('oauth_configured')}")
        print(f"Inline execution verified: {status.get('inline_execution_verified')}")
        print(f"Execution verified: {status.get('execution_verified')}")
        worker = status.get("worker") or {}
        print(f"Worker mode: {worker.get('mode')} ({worker.get('engine') or 'unknown engine'})")
        if failures:
            print("\nReadiness gaps:")
            for failure in failures:
                print(f"- {failure}")
        else:
            print("\nGBrain agent/citation-fixer readiness is complete.")

    if args.strict and failures:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
