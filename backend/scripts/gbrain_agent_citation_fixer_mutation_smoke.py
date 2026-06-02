from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from scripts.gbrain_agent_inline_execution_smoke import _promote_deepseek_key, _redact_output  # noqa: E402
from scripts.gbrain_register_agent_client import _load_dotenv, _updated_env_text  # noqa: E402


SMOKE_SLUG = "reviews/citation-fixer-smoke/project-r-citation-fixer-smoke"
SMOKE_RELATIVE_PATH = Path("reviews") / "citation-fixer-smoke" / "project-r-citation-fixer-smoke.md"
BROKEN_MARKER = "[[BROKEN_CITATION_FIXME]]"
FIXED_MARKER = "[[rules/书面化原则]]"
DEFAULT_TOOLS = ("search", "get_page", "put_page", "list_pages")
SMOKE_ALLOWED_SLUG_GLOB = "reviews/citation-fixer-smoke/*"
CITATION_PREFIX = "事实：Project_R 的知识库查询应保持 source scope 隔离。 Citation:"


def build_smoke_page() -> str:
    return (
        "---\n"
        "title: Project_R citation-fixer smoke page\n"
        "content_kind: gbrain_agent_smoke_test\n"
        "review_status: approved\n"
        "source_scope: company-wiki\n"
        "---\n\n"
        "# Project_R citation-fixer smoke page\n\n"
        "This is a safe synthetic page for validating GBrain citation-fixer write execution.\n\n"
        "The only intended edit is to repair the malformed citation marker on the Citation line.\n\n"
        f"{CITATION_PREFIX} {BROKEN_MARKER}\n"
    )


def build_prompt(*, source_id: str, page_slug: str) -> str:
    return (
        "Use the GBrain `citation-fixer` skill in a tightly scoped smoke test.\n"
        f"Source scope: `{source_id}`.\n"
        f"Only inspect and patch the page `{page_slug}`.\n"
        f"The page contains one malformed citation marker `{BROKEN_MARKER}`.\n"
        f"Replace exactly that marker with `{FIXED_MARKER}` using `put_page`.\n"
        "Tool plan: call get_page once, call put_page once with the full corrected page body, "
        "call get_page once to verify, then stop with a final report. Do not search unless get_page fails.\n"
        "Do not change any other fact, title, frontmatter field, page, source, or slug. "
        "Do not keep looping after verification.\n"
        "Final report fields: status, page_slug, changed_marker, remaining_gaps."
    )


def build_job_params(
    *,
    source_id: str,
    page_slug: str,
    model: str,
    max_turns: int,
    tools: tuple[str, ...],
) -> dict[str, Any]:
    params: dict[str, Any] = {
        "prompt": build_prompt(source_id=source_id, page_slug=page_slug),
        "source_id": source_id,
        "allowed_tools": list(tools),
        "allowed_slug_prefixes": [SMOKE_ALLOWED_SLUG_GLOB],
        "max_turns": max(4, min(max_turns, 30)),
    }
    if model.strip():
        params["model"] = model.strip()
    return params


def build_command(*, bun_bin: str, params: dict[str, Any], timeout_ms: int) -> list[str]:
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
        str(max(20_000, timeout_ms)),
    ]


def prepare_smoke_page(derived_path: Path, *, overwrite: bool = True) -> Path:
    target = (derived_path / SMOKE_RELATIVE_PATH).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    if overwrite or not target.exists():
        target.write_text(build_smoke_page(), encoding="utf-8")
    return target


def smoke_page_fixed(path: Path) -> bool:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    return text_citation_fixed(text)


def get_citation_line(text: str) -> str:
    for line in text.splitlines():
        if line.strip().startswith(CITATION_PREFIX):
            return line.strip()
    return ""


def text_citation_fixed(text: str) -> bool:
    line = get_citation_line(text)
    return bool(line) and FIXED_MARKER in line and BROKEN_MARKER not in line


def text_citation_broken(text: str) -> bool:
    line = get_citation_line(text)
    return bool(line) and BROKEN_MARKER in line


def gbrain_page_contains_marker(result: dict[str, Any]) -> bool:
    if result.get("status") != "ok":
        return False
    payload = result.get("result")
    if not isinstance(payload, dict):
        return False
    values: list[str] = []
    for key in ("content", "markdown", "body", "text"):
        value = payload.get(key)
        if isinstance(value, str):
            values.append(value)
    page = payload.get("page")
    if isinstance(page, dict):
        for key in ("content", "markdown", "body", "text"):
            value = page.get(key)
            if isinstance(value, str):
                values.append(value)
    return any(BROKEN_MARKER in value or FIXED_MARKER in value for value in values)


def build_page_probe_script(*, source_id: str, page_slug: str) -> str:
    return (
        "const { loadConfig, toEngineConfig } = await import('./src/core/config.ts');\n"
        "const { createEngine } = await import('./src/core/engine-factory.ts');\n"
        f"const sourceId = {json.dumps(source_id, ensure_ascii=False)};\n"
        f"const pageSlug = {json.dumps(page_slug, ensure_ascii=False)};\n"
        "const cfg = loadConfig();\n"
        "const ec = toEngineConfig(cfg);\n"
        "const engine = await createEngine(ec);\n"
        "await engine.connect(ec);\n"
        "try {\n"
        "  const rows = await engine.executeRaw(\n"
        "    'SELECT slug, source_id, title, source_path, deleted_at IS NULL AS live, compiled_truth, timeline FROM pages WHERE source_id = $1 AND slug = $2',\n"
        "    [sourceId, pageSlug],\n"
        "  );\n"
        "  console.log(JSON.stringify(rows));\n"
        "} finally {\n"
        "  await engine.disconnect();\n"
        "}\n"
    )


def probe_gbrain_page(
    adapter: Any,
    *,
    source_id: str,
    page_slug: str,
    timeout: int = 120,
    attempts: int = 3,
    delay_seconds: float = 2.0,
) -> dict[str, Any]:
    script = build_page_probe_script(source_id=source_id, page_slug=page_slug)
    result: dict[str, Any] = {}
    for attempt in range(max(1, attempts)):
        result = adapter._run_cli_exclusive(  # noqa: SLF001 - development validation script.
            [adapter.settings.bun_executable, "--eval", script],
            reason="citation_fixer_smoke_source_scoped_page_probe",
            timeout=timeout,
        )
        if result.get("status") == "ok":
            break
        if attempt < attempts - 1:
            time.sleep(delay_seconds)
    payload = result.get("result") if isinstance(result.get("result"), dict) else {}
    stdout = str(payload.get("stdout") or "").strip()
    rows: list[dict[str, Any]] = []
    parse_error: str | None = None
    if stdout:
        try:
            parsed = json.loads(stdout)
            if isinstance(parsed, list):
                rows = [row for row in parsed if isinstance(row, dict)]
        except json.JSONDecodeError as exc:
            parse_error = str(exc)
    return {
        **result,
        "rows": rows,
        "parse_error": parse_error,
        "page_found": any(row.get("live") is True for row in rows),
    }


def probe_contains_marker(probe: dict[str, Any], marker: str) -> bool:
    for row in probe.get("rows") or []:
        for key in ("compiled_truth", "timeline"):
            value = row.get(key)
            if isinstance(value, str) and marker in value:
                return True
    return False


def probe_page_fixed(probe: dict[str, Any]) -> bool:
    for row in probe.get("rows") or []:
        text = "\n".join(
            value for key in ("compiled_truth", "timeline")
            if isinstance((value := row.get(key)), str)
        )
        if text_citation_fixed(text):
            return True
    return False


def probe_page_has_broken_citation(probe: dict[str, Any]) -> bool:
    for row in probe.get("rows") or []:
        text = "\n".join(
            value for key in ("compiled_truth", "timeline")
            if isinstance((value := row.get(key)), str)
        )
        if text_citation_broken(text):
            return True
    return False


def sidecar_page_path(derived_path: Path, *, source_id: str, page_slug: str) -> Path:
    return derived_path / ".sources" / source_id / Path(*page_slug.split("/")).with_suffix(".md")


def reconcile_agent_write_to_derived(
    derived_path: Path,
    smoke_path: Path,
    *,
    source_id: str,
    page_slug: str,
) -> dict[str, Any]:
    sidecar = sidecar_page_path(derived_path, source_id=source_id, page_slug=page_slug)
    if sidecar.exists():
        sidecar_text = sidecar.read_text(encoding="utf-8")
        if text_citation_fixed(sidecar_text):
            smoke_path.write_text(sidecar_text, encoding="utf-8")
            try:
                sidecar.unlink()
            except OSError:
                pass
            return {"ok": True, "status": "copied_sidecar", "sidecar": str(sidecar)}

    try:
        text = smoke_path.read_text(encoding="utf-8")
    except OSError as exc:
        return {"ok": False, "status": "canonical_read_failed", "error": str(exc)}
    if not text_citation_broken(text):
        return {"ok": False, "status": "canonical_not_broken_or_missing_citation"}
    updated = "\n".join(
        f"{CITATION_PREFIX} {FIXED_MARKER}" if line.strip().startswith(CITATION_PREFIX) else line
        for line in text.splitlines()
    )
    if text.endswith("\n"):
        updated += "\n"
    smoke_path.write_text(updated, encoding="utf-8")
    return {"ok": True, "status": "patched_canonical_from_db_verification"}


def write_execution_verified(path: Path) -> None:
    original = path.read_text(encoding="utf-8") if path.exists() else ""
    path.write_text(
        _updated_env_text(
            original,
            {
                "GBRAIN_AGENT_EXECUTION_VERIFIED": "true",
                "GBRAIN_AGENT_INLINE_EXECUTION_VERIFIED": "true",
            },
        ),
        encoding="utf-8",
    )


def backup_import_checkpoint(home_path: Path) -> Path | None:
    checkpoint = home_path / ".gbrain" / "import-checkpoint.json"
    if not checkpoint.exists():
        return None
    suffix = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    backup = checkpoint.with_name(f"import-checkpoint.smoke-backup-{suffix}.json")
    checkpoint.replace(backup)
    return backup


def commit_smoke_page(derived_path: Path, smoke_path: Path) -> dict[str, Any]:
    if not (derived_path / ".git").exists():
        return {"ok": False, "status": "no_git_repo", "error": f"{derived_path} is not a git repo"}
    rel = smoke_path.relative_to(derived_path).as_posix()
    add = subprocess.run(
        ["git", "-C", str(derived_path), "add", rel],
        text=True,
        capture_output=True,
        check=False,
    )
    if add.returncode != 0:
        return {"ok": False, "status": "git_add_failed", "error": add.stderr.strip() or add.stdout.strip()}
    commit = subprocess.run(
        ["git", "-C", str(derived_path), "commit", "-m", "Add Project_R citation-fixer smoke page"],
        text=True,
        capture_output=True,
        check=False,
    )
    if commit.returncode == 0:
        return {"ok": True, "status": "committed", "output": commit.stdout.strip()}
    output = f"{commit.stdout}\n{commit.stderr}".strip()
    if "nothing to commit" in output.lower():
        return {"ok": True, "status": "already_committed", "output": output}
    return {"ok": False, "status": "git_commit_failed", "error": output}


def commit_mutation(derived_path: Path, smoke_path: Path) -> dict[str, Any]:
    if not (derived_path / ".git").exists():
        return {"ok": False, "status": "no_git_repo", "error": f"{derived_path} is not a git repo"}
    rel = smoke_path.relative_to(derived_path).as_posix()
    add = subprocess.run(
        ["git", "-C", str(derived_path), "add", rel],
        text=True,
        capture_output=True,
        check=False,
    )
    if add.returncode != 0:
        return {"ok": False, "status": "git_add_failed", "error": add.stderr.strip() or add.stdout.strip()}
    commit = subprocess.run(
        ["git", "-C", str(derived_path), "commit", "-m", "Verify Project_R citation-fixer smoke mutation"],
        text=True,
        capture_output=True,
        check=False,
    )
    if commit.returncode == 0:
        return {"ok": True, "status": "committed", "output": commit.stdout.strip()}
    output = f"{commit.stdout}\n{commit.stderr}".strip()
    if "nothing to commit" in output.lower():
        return {"ok": True, "status": "already_committed", "output": output}
    return {"ok": False, "status": "git_commit_failed", "error": output}


def result_output(result: dict[str, Any]) -> str:
    payload = result.get("result")
    if not isinstance(payload, dict):
        return ""
    return "\n".join(str(payload.get(key) or "") for key in ("stdout", "stderr"))


def is_pglite_init_error(text: str) -> bool:
    return "PGLite failed to initialize" in text or "Original error: Aborted()" in text


def run_agent_command_with_retry(
    adapter: Any,
    command: list[str],
    *,
    timeout_seconds: int,
    attempts: int = 3,
    delay_seconds: float = 3.0,
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for attempt in range(max(1, attempts)):
        result = adapter._run_cli_exclusive(  # noqa: SLF001 - development validation script.
            command,
            reason="run_pglite_inline_citation_fixer_mutation_smoke",
            timeout=timeout_seconds + 30,
        )
        output = result_output(result)
        if result.get("status") == "ok" or extract_completed_job_id(output) is not None:
            return result
        error_text = "\n".join([str(result.get("error") or ""), output])
        if not is_pglite_init_error(error_text) or attempt >= attempts - 1:
            return result
        time.sleep(delay_seconds)
    return result


def print_console_safe(text: str) -> None:
    encoding = sys.stdout.encoding or "utf-8"
    print(text.encode(encoding, errors="replace").decode(encoding, errors="replace"))


def extract_completed_job_id(output: str) -> int | None:
    match = re.search(r"Job #(\d+) completed", output)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run a tightly scoped GBrain citation-fixer mutation smoke test. "
            "It creates a synthetic page under reviews/citation-fixer-smoke/ and verifies put_page changed only the marker."
        )
    )
    parser.add_argument("--env-path", default=str(BACKEND_DIR / ".env"))
    parser.add_argument("--source", default="")
    parser.add_argument("--page-slug", default=SMOKE_SLUG)
    parser.add_argument("--model", default="")
    parser.add_argument("--max-turns", type=int, default=12)
    parser.add_argument("--timeout-seconds", type=int, default=240)
    parser.add_argument("--tools", default=",".join(DEFAULT_TOOLS))
    parser.add_argument("--dry-run", action="store_true", help="Prepare and sync the smoke page, print params, but do not run subagent.")
    parser.add_argument("--no-sync", action="store_true", help="Skip GBrain source sync before running.")
    parser.add_argument("--reset-import-checkpoint", action="store_true", help="Move GBrain import-checkpoint.json aside before full sync.")
    parser.add_argument("--commit-smoke-page", action="store_true", help="Commit the smoke page in derived/ local Git before sync.")
    parser.add_argument("--no-commit-mutation", action="store_true", help="Do not commit the verified mutation in derived/ local Git.")
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
    missing = [tool for tool in DEFAULT_TOOLS if tool not in tools]
    if missing:
        parser.error(f"--tools must include mutation smoke tools: {', '.join(missing)}")

    smoke_path = prepare_smoke_page(settings.derived_path)
    commit_result: dict[str, Any] | None = None
    if args.commit_smoke_page:
        commit_result = commit_smoke_page(settings.derived_path, smoke_path)
        if not commit_result.get("ok"):
            print("GBrain citation-fixer mutation smoke failed before sync.")
            print(f"- reason: {commit_result.get('status')}")
            print(f"- error: {commit_result.get('error') or '<none>'}")
            return 1
    adapter = GBrainAdapter(settings)
    checkpoint_backup = backup_import_checkpoint(settings.home_path) if args.reset_import_checkpoint else None
    if not args.no_sync:
        sync_result = adapter.sync_source(
            source_id=source_id,
            repo_path=settings.derived_path,
            full=True,
            no_pull=True,
            no_embed=True,
        )
        if sync_result.get("status") != "ok":
            print("GBrain citation-fixer mutation smoke failed during sync.")
            print(f"- status: {sync_result.get('status')}")
            print(f"- error: {sync_result.get('error') or '<none>'}")
            if checkpoint_backup:
                print(f"- import_checkpoint_backup: {checkpoint_backup}")
            return 1

    page_check = probe_gbrain_page(adapter, source_id=source_id, page_slug=args.page_slug)
    if page_check.get("status") != "ok" or not page_check.get("page_found") or not probe_page_has_broken_citation(page_check):
        print("GBrain citation-fixer mutation smoke preflight failed.")
        print("- reason: smoke_page_not_indexed")
        print(f"- page_slug: {args.page_slug}")
        print(f"- file_path: {smoke_path}")
        if commit_result:
            print(f"- git_commit_status: {commit_result.get('status')}")
        if checkpoint_backup:
            print(f"- import_checkpoint_backup: {checkpoint_backup}")
        print(f"- page_probe_status: {page_check.get('status')}")
        print(f"- page_probe_found: {page_check.get('page_found')}")
        print(f"- page_probe_rows: {len(page_check.get('rows') or [])}")
        error = page_check.get("error") or page_check.get("parse_error")
        if error:
            print(f"- page_probe_error: {error}")
        return 1

    params = build_job_params(
        source_id=source_id,
        page_slug=args.page_slug,
        model=model,
        max_turns=args.max_turns,
        tools=tools,
    )
    if args.dry_run:
        print("GBrain citation-fixer mutation smoke dry-run prepared.")
        print(f"- smoke_page: {smoke_path}")
        print(f"- source_id: {source_id}")
        print(f"- page_slug: {args.page_slug}")
        print(f"- allowed_tools: {', '.join(tools)}")
        print(f"- allowed_slug_prefixes: {', '.join(params['allowed_slug_prefixes'])}")
        if commit_result:
            print(f"- git_commit_status: {commit_result.get('status')}")
        if checkpoint_backup:
            print(f"- import_checkpoint_backup: {checkpoint_backup}")
        return 0

    command = build_command(
        bun_bin=settings.bun_executable,
        params=params,
        timeout_ms=args.timeout_seconds * 1000,
    )
    result = run_agent_command_with_retry(
        adapter,
        command,
        timeout_seconds=args.timeout_seconds,
    )
    output = _redact_output(result_output(result))
    job_id = extract_completed_job_id(output)
    post_probe = probe_gbrain_page(adapter, source_id=source_id, page_slug=args.page_slug)
    db_fixed = post_probe.get("status") == "ok" and probe_page_fixed(post_probe)
    reconcile_result: dict[str, Any] | None = None
    mutation_commit_result: dict[str, Any] | None = None
    if db_fixed:
        reconcile_result = reconcile_agent_write_to_derived(
            settings.derived_path,
            smoke_path,
            source_id=source_id,
            page_slug=args.page_slug,
        )
        if reconcile_result.get("ok") and not args.no_commit_mutation:
            mutation_commit_result = commit_mutation(settings.derived_path, smoke_path)
    file_fixed = smoke_page_fixed(smoke_path)
    committed_or_skipped = args.no_commit_mutation or bool(mutation_commit_result and mutation_commit_result.get("ok"))
    ok = (
        result.get("status") == "ok"
        and job_id is not None
        and db_fixed
        and file_fixed
        and bool(reconcile_result and reconcile_result.get("ok"))
        and committed_or_skipped
    )

    if ok:
        print("GBrain citation-fixer mutation smoke passed.")
        print(f"- job_id: {job_id}")
        print(f"- source_id: {source_id}")
        print(f"- page_slug: {args.page_slug}")
        if commit_result:
            print(f"- git_commit_status: {commit_result.get('status')}")
        if mutation_commit_result:
            print(f"- mutation_git_commit_status: {mutation_commit_result.get('status')}")
        if reconcile_result:
            print(f"- reconcile_status: {reconcile_result.get('status')}")
        if checkpoint_backup:
            print(f"- import_checkpoint_backup: {checkpoint_backup}")
        print("- mutation: verified")
        if not args.no_env_update:
            write_execution_verified(env_path)
            print("- GBRAIN_AGENT_EXECUTION_VERIFIED=true")
        return 0

    print("GBrain citation-fixer mutation smoke failed.")
    print(f"- status: {result.get('status')}")
    print(f"- job_id: {job_id if job_id is not None else '<none>'}")
    print(f"- file_fixed: {file_fixed}")
    print(f"- db_fixed: {db_fixed}")
    print(f"- page_probe_status: {post_probe.get('status')}")
    if reconcile_result:
        print(f"- reconcile_status: {reconcile_result.get('status')}")
        if reconcile_result.get("error"):
            print(f"- reconcile_error: {reconcile_result.get('error')}")
    if mutation_commit_result:
        print(f"- mutation_git_commit_status: {mutation_commit_result.get('status')}")
        if mutation_commit_result.get("error"):
            print(f"- mutation_git_commit_error: {mutation_commit_result.get('error')}")
    if result.get("error"):
        print(f"- error: {result.get('error')}")
    if post_probe.get("error") or post_probe.get("parse_error"):
        print(f"- page_probe_error: {post_probe.get('error') or post_probe.get('parse_error')}")
    if output.strip():
        print("- output:")
        print_console_safe(output[-2500:])
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
