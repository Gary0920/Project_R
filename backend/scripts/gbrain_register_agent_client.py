from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


BACKEND_DIR = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class RegistrationResult:
    client_id: str
    client_secret: str


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


def _csv(items: Iterable[str]) -> str:
    return ",".join(item.strip() for item in items if item.strip())


def _parse_registration_output(output: str) -> RegistrationResult:
    client_id_match = re.search(r"Client ID:\s*(\S+)", output)
    client_secret_match = re.search(r"Client Secret:\s*(\S+)", output)
    if not client_id_match:
        raise ValueError("GBrain output did not include a Client ID.")
    if not client_secret_match or client_secret_match.group(1).startswith("<"):
        raise ValueError("GBrain output did not include a confidential Client Secret.")
    return RegistrationResult(
        client_id=client_id_match.group(1).strip(),
        client_secret=client_secret_match.group(1).strip(),
    )


def _redact_registration_output(output: str) -> str:
    return re.sub(r"(Client Secret:\s*)\S+", r"\1<redacted>", output)


def _updated_env_text(original: str, updates: dict[str, str]) -> str:
    remaining = dict(updates)
    lines = original.splitlines()
    new_lines: list[str] = []
    key_pattern = re.compile(r"^(\s*)([A-Za-z_][A-Za-z0-9_]*)(\s*=).*$")
    for line in lines:
        match = key_pattern.match(line)
        if match and match.group(2) in remaining:
            key = match.group(2)
            new_lines.append(f"{key}={remaining.pop(key)}")
        else:
            new_lines.append(line)
    if remaining:
        if new_lines and new_lines[-1].strip():
            new_lines.append("")
        new_lines.append("# === GBrain Agent / Citation-Fixer ===")
        for key, value in remaining.items():
            new_lines.append(f"{key}={value}")
    return "\n".join(new_lines).rstrip() + "\n"


def _write_env_updates(path: Path, updates: dict[str, str]) -> None:
    original = path.read_text(encoding="utf-8") if path.exists() else ""
    path.write_text(_updated_env_text(original, updates), encoding="utf-8")


def _build_command(
    *,
    bun_bin: str,
    name: str,
    source_id: str,
    tools: tuple[str, ...],
    slug_prefixes: tuple[str, ...],
    max_concurrent: int,
    budget_usd_per_day: float,
) -> list[str]:
    return [
        bun_bin,
        "run",
        "src/commands/auth.ts",
        "register-client",
        name,
        "--grant-types",
        "client_credentials",
        "--scopes",
        "agent",
        "--source",
        source_id,
        "--federated-read",
        source_id,
        "--bound-tools",
        _csv(tools),
        "--bound-source",
        source_id,
        "--bound-slug-prefixes",
        _csv(slug_prefixes),
        "--bound-max-concurrent",
        str(max_concurrent),
        "--budget-usd-per-day",
        str(budget_usd_per_day),
    ]


def _gbrain_subprocess_env(base_env: dict[str, str], gbrain_home: Path) -> dict[str, str]:
    run_env = dict(base_env)
    run_env["GBRAIN_HOME"] = str(gbrain_home.resolve())
    # Project_R's own FastAPI DATABASE_URL is usually sqlite:///./app.db.
    # GBrain also reads DATABASE_URL, so remove it here and let GBRAIN_HOME
    # select the local .gbrain/config.json PGLite brain.
    run_env.pop("DATABASE_URL", None)
    run_env.pop("GBRAIN_DATABASE_URL", None)
    return run_env


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Register a GBrain agent-bound OAuth client for Project_R "
            "citation-fixer without printing the client secret."
        )
    )
    parser.add_argument("--name", default="project-r-citation-fixer")
    parser.add_argument("--source", default="")
    parser.add_argument("--tools", default="search,get_page,put_page,list_pages")
    parser.add_argument("--slug-prefixes", default="rules/,reviews/,standards/,meetings/")
    parser.add_argument("--max-concurrent", type=int, default=1)
    parser.add_argument("--budget-usd-per-day", type=float, default=1.0)
    parser.add_argument("--model", default="deepseek:deepseek-chat")
    parser.add_argument("--env-path", default=str(BACKEND_DIR / ".env"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-env-update", action="store_true")
    args = parser.parse_args()

    if args.max_concurrent < 1:
        parser.error("--max-concurrent must be >= 1")
    if args.budget_usd_per_day < 0:
        parser.error("--budget-usd-per-day must be >= 0")

    env_path = Path(args.env_path)
    if not env_path.is_absolute():
        env_path = (Path.cwd() / env_path).resolve()

    _load_dotenv(env_path)
    sys.path.insert(0, str(BACKEND_DIR))

    from core.gbrain import load_gbrain_settings

    settings = load_gbrain_settings()
    source_id = args.source.strip() or settings.company_source_id
    tools = tuple(item.strip() for item in args.tools.split(",") if item.strip())
    slug_prefixes = tuple(item.strip() for item in args.slug_prefixes.split(",") if item.strip())
    if not tools:
        parser.error("--tools cannot be empty")
    if not slug_prefixes:
        parser.error("--slug-prefixes cannot be empty")

    command = _build_command(
        bun_bin=settings.bun_executable,
        name=args.name,
        source_id=source_id,
        tools=tools,
        slug_prefixes=slug_prefixes,
        max_concurrent=args.max_concurrent,
        budget_usd_per_day=args.budget_usd_per_day,
    )

    print("GBrain agent client registration plan:")
    print(f"- name: {args.name}")
    print(f"- source: {source_id}")
    print(f"- tools: {_csv(tools)}")
    print(f"- slug prefixes: {_csv(slug_prefixes)}")
    print(f"- max concurrent: {args.max_concurrent}")
    print(f"- budget USD/day: {args.budget_usd_per_day:g}")
    print(f"- env target: {env_path}")

    if args.dry_run:
        print("\nDry run only. No GBrain client was registered and .env was not changed.")
        return 0

    run_env = _gbrain_subprocess_env(os.environ, settings.home_path)

    try:
        completed = subprocess.run(
            command,
            cwd=settings.cli_workdir,
            env=run_env,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=45,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"\nRegistration failed before GBrain returned output: {exc}", file=sys.stderr)
        return 1

    combined_output = "\n".join(part for part in (completed.stdout, completed.stderr) if part)
    redacted_output = _redact_registration_output(combined_output)
    if completed.returncode != 0:
        print("\nGBrain register-client failed. Redacted output:", file=sys.stderr)
        print(redacted_output, file=sys.stderr)
        print(
            "\nIf this is a PGLite lock error, stop the local GBrain HTTP service, "
            "rerun this script, then restart GBrain.",
            file=sys.stderr,
        )
        return completed.returncode or 1

    try:
        result = _parse_registration_output(combined_output)
    except ValueError as exc:
        print(f"\nRegistration output could not be parsed: {exc}", file=sys.stderr)
        print(redacted_output, file=sys.stderr)
        return 1

    if not args.no_env_update:
        updates = {
            "GBRAIN_AGENT_ENABLED": "true",
            "GBRAIN_AGENT_OAUTH_CLIENT_ID": result.client_id,
            "GBRAIN_AGENT_OAUTH_CLIENT_SECRET": result.client_secret,
            "GBRAIN_AGENT_OAUTH_SCOPE": "agent",
            "GBRAIN_AGENT_OAUTH_TOKEN_AUTH_METHOD": "client_secret_post",
            "GBRAIN_AGENT_MODEL": args.model.strip() or "deepseek:deepseek-chat",
            "GBRAIN_AGENT_GATEWAY_LOOP_VERIFIED": "false",
            "GBRAIN_AGENT_BINDING_SUBMIT_VERIFIED": "false",
            "GBRAIN_AGENT_EXECUTION_VERIFIED": "false",
            "GBRAIN_CITATION_FIXER_TOOLS": _csv(tools),
        }
        _write_env_updates(env_path, updates)

    print("\nGBrain agent OAuth client registered.")
    print(f"- client_id: {result.client_id}")
    print("- client_secret: <redacted; written to .env>" if not args.no_env_update else "- client_secret: <redacted>")
    print("- execution verified: false")
    print("\nNext: run scripts/gbrain_agent_preflight.py, then verify gateway loop and a real citation-fixer run.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
