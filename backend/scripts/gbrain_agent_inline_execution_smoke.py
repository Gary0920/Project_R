from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from scripts.gbrain_register_agent_client import _load_dotenv, _updated_env_text  # noqa: E402


DEFAULT_TOOLS = ("search", "get_page")


def _first_csv_value(value: str | None) -> str:
    if not value:
        return ""
    for item in value.split(","):
        cleaned = item.strip()
        if cleaned:
            return cleaned
    return ""


def _promote_deepseek_key(env: dict[str, str]) -> None:
    if env.get("DEEPSEEK_API_KEY"):
        return
    first = _first_csv_value(env.get("DEEPSEEK_API_KEYS"))
    if first:
        env["DEEPSEEK_API_KEY"] = first
        os.environ["DEEPSEEK_API_KEY"] = first


def _build_prompt(*, source_id: str, page_slug: str) -> str:
    return (
        "Project_R GBrain subagent inline execution smoke test.\n"
        "You are running in read-only mode. Do not modify any page and do not call put_page.\n"
        f"Use the available brain tools to inspect source `{source_id}` and page `{page_slug}`.\n"
        "Return a short result in Chinese with these fields: status, source_id, page_slug, "
        "tool_check, and one fact from the page. Keep the answer under 120 Chinese characters."
    )


def _build_job_params(
    *,
    source_id: str,
    page_slug: str,
    model: str,
    max_turns: int,
    tools: tuple[str, ...],
) -> dict[str, Any]:
    params: dict[str, Any] = {
        "prompt": _build_prompt(source_id=source_id, page_slug=page_slug),
        "source_id": source_id,
        "allowed_tools": list(tools),
        "max_turns": max(1, min(max_turns, 10)),
    }
    if model.strip():
        params["model"] = model.strip()
    return params


def _build_command(*, bun_bin: str, params: dict[str, Any], timeout_ms: int) -> list[str]:
    return [
        bun_bin,
        "src/cli.ts",
        "jobs",
        "submit",
        "subagent",
        "--params",
        json.dumps(params, ensure_ascii=False, separators=(",", ":")),
        "--follow",
        "--max-attempts",
        "1",
        "--timeout-ms",
        str(max(10_000, timeout_ms)),
    ]


def _extract_completed_job_id(output: str) -> int | None:
    match = re.search(r"Job #(\d+) completed", output)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _redact_output(value: str) -> str:
    redacted = re.sub(r"gbrain_cs_[A-Za-z0-9_\-]+", "gbrain_cs_<redacted>", value)
    redacted = re.sub(r"sk-[A-Za-z0-9_\-]+", "sk-<redacted>", redacted)
    redacted = re.sub(r"(DEEPSEEK_API_KEY\s*=\s*)\S+", r"\1<redacted>", redacted)
    return redacted


def _write_inline_execution_verified(path: Path) -> None:
    original = path.read_text(encoding="utf-8") if path.exists() else ""
    path.write_text(
        _updated_env_text(original, {"GBRAIN_AGENT_INLINE_EXECUTION_VERIFIED": "true"}),
        encoding="utf-8",
    )


def _result_output(result: dict[str, Any]) -> str:
    payload = result.get("result")
    if not isinstance(payload, dict):
        return ""
    return "\n".join(str(payload.get(key) or "") for key in ("stdout", "stderr"))


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run a real GBrain subagent inline with PGLite using read-only tools. "
            "This verifies execution, not mutating citation-fixer readiness."
        )
    )
    parser.add_argument("--env-path", default=str(BACKEND_DIR / ".env"))
    parser.add_argument("--source", default="")
    parser.add_argument("--page-slug", default="rules/书面化原则")
    parser.add_argument("--model", default="")
    parser.add_argument("--max-turns", type=int, default=3)
    parser.add_argument("--timeout-seconds", type=int, default=180)
    parser.add_argument("--tools", default=",".join(DEFAULT_TOOLS))
    parser.add_argument("--no-env-update", action="store_true")
    args = parser.parse_args()

    env_path = Path(args.env_path)
    if not env_path.is_absolute():
        env_path = (Path.cwd() / env_path).resolve()

    _load_dotenv(env_path)
    _promote_deepseek_key(os.environ)

    from core.gbrain import GBrainAdapter, load_gbrain_settings

    settings = load_gbrain_settings()
    source_id = args.source.strip() or settings.company_source_id
    model = args.model.strip() or settings.agent_model or "deepseek:deepseek-chat"
    tools = tuple(item.strip() for item in args.tools.split(",") if item.strip())
    if not tools:
        parser.error("--tools cannot be empty")
    if "put_page" in tools or "brain_put_page" in tools:
        parser.error("inline smoke is read-only; do not include put_page")

    params = _build_job_params(
        source_id=source_id,
        page_slug=args.page_slug,
        model=model,
        max_turns=args.max_turns,
        tools=tools,
    )
    command = _build_command(
        bun_bin=settings.bun_executable,
        params=params,
        timeout_ms=args.timeout_seconds * 1000,
    )

    adapter = GBrainAdapter(settings)
    result = adapter._run_cli_exclusive(  # noqa: SLF001 - development validation script.
        command,
        reason="run_pglite_inline_subagent_execution_smoke",
        timeout=args.timeout_seconds + 30,
    )
    output = _redact_output(_result_output(result))
    job_id = _extract_completed_job_id(output)
    ok = result.get("status") == "ok" and job_id is not None

    if ok:
        print("GBrain inline subagent execution smoke passed.")
        print(f"- job_id: {job_id}")
        print(f"- source_id: {source_id}")
        print(f"- tools: {', '.join(tools)}")
        print("- mutation: disabled")
        if not args.no_env_update:
            _write_inline_execution_verified(env_path)
            print("- GBRAIN_AGENT_INLINE_EXECUTION_VERIFIED=true")
        return 0

    print("GBrain inline subagent execution smoke failed.")
    print(f"- status: {result.get('status')}")
    if result.get("error"):
        print(f"- error: {result.get('error')}")
    if output.strip():
        print("- output:")
        print(output[-2000:])
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
