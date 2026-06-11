from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from scripts.gbrain_register_agent_client import (  # noqa: E402
    _gbrain_subprocess_env,
    _load_dotenv,
    _updated_env_text,
)


def _build_command(bun_bin: str) -> list[str]:
    return [
        bun_bin,
        "run",
        "src/cli.ts",
        "config",
        "set",
        "agent.use_gateway_loop",
        "true",
        "--force",
    ]


def _write_gateway_verified(path: Path) -> None:
    original = path.read_text(encoding="utf-8") if path.exists() else ""
    path.write_text(
        _updated_env_text(original, {"GBRAIN_AGENT_GATEWAY_LOOP_VERIFIED": "true"}),
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Enable GBrain agent.use_gateway_loop and mark Project_R agent gateway readiness."
    )
    parser.add_argument("--env-path", default=str(BACKEND_DIR / ".env"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-env-update", action="store_true")
    args = parser.parse_args()

    env_path = Path(args.env_path)
    if not env_path.is_absolute():
        env_path = (Path.cwd() / env_path).resolve()

    _load_dotenv(env_path)
    sys.path.insert(0, str(BACKEND_DIR))

    from app.features.knowledge.gbrain import load_gbrain_settings

    settings = load_gbrain_settings()
    command = _build_command(settings.bun_executable)

    print("GBrain agent gateway loop plan:")
    print("- config: agent.use_gateway_loop=true")
    print(f"- env target: {env_path}")

    if args.dry_run:
        print("\nDry run only. GBrain config and .env were not changed.")
        return 0

    try:
        completed = subprocess.run(
            command,
            cwd=settings.cli_workdir,
            env=_gbrain_subprocess_env(os.environ, settings.home_path),
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=45,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"\nGateway loop config failed before GBrain returned output: {exc}", file=sys.stderr)
        return 1

    output = "\n".join(part for part in (completed.stdout, completed.stderr) if part)
    if completed.returncode != 0:
        print("\nGBrain config set failed:", file=sys.stderr)
        print(output, file=sys.stderr)
        print(
            "\nIf this is a PGLite lock error, stop the local GBrain HTTP service, "
            "rerun this script, then restart GBrain.",
            file=sys.stderr,
        )
        return completed.returncode or 1

    if not args.no_env_update:
        _write_gateway_verified(env_path)

    print("\nGBrain agent gateway loop enabled.")
    print("- GBRAIN_AGENT_GATEWAY_LOOP_VERIFIED=true" if not args.no_env_update else "- .env not changed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
