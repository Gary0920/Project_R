from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter
from types import SimpleNamespace
from pathlib import Path
from typing import Any


BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent
FIXTURE_PATH = BACKEND_DIR / "tests" / "fixtures" / "gbrain_project_quality_regression_cases.json"
APP_DB_PATH = BACKEND_DIR / "app.db"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

ALLOWED_FILE_KINDS = {
    "pdf_drawing",
    "pdf_schedule",
    "image",
    "meeting_transcript_docx",
    "meeting_media",
    "email",
    "spreadsheet",
    "office_doc",
}
ALLOWED_EXPECTED_STATUSES = {"should_pass", "known_gap"}
ALLOWED_LOCATION_TYPES = {"page", "sheet", "region", "timestamp", "text_span", "unknown"}


# ── Fixture loading & validation (same as before) ────────────────────────


def load_fixture(path: Path = FIXTURE_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _require_mapping(value: Any, label: str, failures: list[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        failures.append(f"{label} must be an object")
        return {}
    return value


def _require_list(value: Any, label: str, failures: list[str]) -> list[Any]:
    if not isinstance(value, list):
        failures.append(f"{label} must be a list")
        return []
    return value


def validate_fixture(data: dict[str, Any], *, project_root: Path = PROJECT_ROOT) -> dict[str, Any]:
    failures: list[str] = []
    warnings: list[str] = []

    scope = _require_mapping(data.get("fixture_scope"), "fixture_scope", failures)
    workspace_path = str(scope.get("workspace_path") or "")
    if not workspace_path:
        failures.append("fixture_scope.workspace_path is required")
        workspace = project_root
    else:
        workspace = project_root / workspace_path
        if not workspace.exists():
            failures.append(f"workspace_path does not exist: {workspace_path}")
        if "backend/workspace_data/project/TEST/TEST" not in workspace_path.replace("\\", "/"):
            failures.append("fixture_scope.workspace_path must point to backend/workspace_data/project/TEST/TEST")
    if scope.get("uses_real_project_files") is not True:
        warnings.append("fixture_scope.uses_real_project_files should be true for 8.D samples")
    if scope.get("requires_same_project_identity") is not False:
        warnings.append("fixture_scope.requires_same_project_identity should be false for mixed real samples")

    cases = _require_list(data.get("cases"), "cases", failures)
    ids: set[str] = set()
    missing_sources: list[dict[str, str]] = []
    file_kind_counts: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()

    for index, raw_case in enumerate(cases):
        label = f"case[{index}]"
        case = _require_mapping(raw_case, label, failures)
        case_id = str(case.get("id") or "")
        if not case_id:
            failures.append(f"{label}.id is required")
        elif case_id in ids:
            failures.append(f"duplicate case id: {case_id}")
        ids.add(case_id)

        file_kind = str(case.get("file_kind") or "")
        if file_kind not in ALLOWED_FILE_KINDS:
            failures.append(f"{case_id or label}: invalid file_kind {file_kind!r}")
        else:
            file_kind_counts[file_kind] += 1

        expected_status = str(case.get("expected_status") or "")
        if expected_status not in ALLOWED_EXPECTED_STATUSES:
            failures.append(f"{case_id or label}: invalid expected_status {expected_status!r}")
        else:
            status_counts[expected_status] += 1

        source_file = str(case.get("source_file") or "")
        if not source_file:
            failures.append(f"{case_id or label}: source_file is required")
        elif ".." in Path(source_file).parts or Path(source_file).is_absolute():
            failures.append(f"{case_id or label}: source_file must be a relative path inside TEST/TEST")
        elif workspace_path:
            source_path = workspace / source_file
            if not source_path.exists():
                missing_sources.append({"id": case_id or label, "source_file": source_file})

        location = _require_mapping(case.get("expected_location"), f"{case_id or label}.expected_location", failures)
        location_type = str(location.get("type") or "")
        if location_type not in ALLOWED_LOCATION_TYPES:
            failures.append(f"{case_id or label}: invalid expected_location.type {location_type!r}")
        if "strict" not in location:
            warnings.append(f"{case_id or label}: expected_location.strict is not set")
        elif not isinstance(location.get("strict"), bool):
            failures.append(f"{case_id or label}: expected_location.strict must be boolean")

        expected_answer = _require_mapping(case.get("expected_answer"), f"{case_id or label}.expected_answer", failures)
        _require_list(
            expected_answer.get("required_terms_all", []),
            f"{case_id or label}.expected_answer.required_terms_all",
            failures,
        )
        _require_list(
            expected_answer.get("required_terms_any", []),
            f"{case_id or label}.expected_answer.required_terms_any",
            failures,
        )

    for missing in missing_sources:
        failures.append(f"{missing['id']}: source_file does not exist: {missing['source_file']}")

    return {
        "ok": not failures,
        "workspace_path": workspace_path,
        "case_count": len(cases),
        "file_kind_counts": dict(sorted(file_kind_counts.items())),
        "status_counts": dict(sorted(status_counts.items())),
        "missing_sources": missing_sources,
        "warnings": warnings,
        "failures": failures,
    }


# ── SQLite helpers (same as before) ──────────────────────────────────────


def _sqlite_readonly_connection(db_path: Path) -> sqlite3.Connection:
    uri = f"file:{db_path.resolve().as_posix()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def load_workspace_for_fixture(
    data: dict[str, Any],
    *,
    project_root: Path = PROJECT_ROOT,
    db_path: Path = APP_DB_PATH,
) -> dict[str, Any]:
    failures: list[str] = []
    warnings: list[str] = []
    scope = _require_mapping(data.get("fixture_scope"), "fixture_scope", failures)
    workspace_path = str(scope.get("workspace_path") or "")
    expected_path = (project_root / workspace_path).resolve() if workspace_path else None
    if not db_path.exists():
        return {"ok": False, "workspace": None, "failures": [f"app DB does not exist: {db_path}"], "warnings": warnings}
    if expected_path is None:
        return {"ok": False, "workspace": None, "failures": failures or ["fixture workspace_path is required"], "warnings": warnings}

    connection = _sqlite_readonly_connection(db_path)
    try:
        rows = connection.execute(
            """
            SELECT id, name, slug, brand, workspace_kind, storage_path, is_archived
            FROM workspaces
            WHERE workspace_kind = 'project'
              AND (
                storage_path = ?
                OR lower(brand) = 'test'
                OR lower(slug) = 'test'
                OR lower(name) = 'test'
              )
            ORDER BY
              CASE WHEN storage_path = ? THEN 0 ELSE 1 END,
              id
            """,
            (str(expected_path), str(expected_path)),
        ).fetchall()
    finally:
        connection.close()

    exact_matches = []
    candidates = []
    for row in rows:
        payload = dict(row)
        storage_path = Path(str(payload.get("storage_path") or "")).resolve()
        payload["storage_path_resolved"] = str(storage_path)
        candidates.append(payload)
        if storage_path == expected_path:
            exact_matches.append(payload)

    if not exact_matches:
        failures.append(f"no project workspace points to fixture workspace_path: {workspace_path}")
    if len(exact_matches) > 1:
        failures.append(f"multiple project workspaces point to fixture workspace_path: {[row['id'] for row in exact_matches]}")
    workspace = exact_matches[0] if len(exact_matches) == 1 else None
    if workspace and workspace.get("is_archived"):
        warnings.append(f"TEST workspace id={workspace['id']} is archived")

    return {
        "ok": not failures,
        "workspace": workspace,
        "candidates": candidates,
        "failures": failures,
        "warnings": warnings,
    }


# ── Workspace preflight (same as before) ──────────────────────────────


def build_workspace_preflight(
    data: dict[str, Any],
    *,
    project_root: Path = PROJECT_ROOT,
    db_path: Path = APP_DB_PATH,
) -> dict[str, Any]:
    workspace_lookup = load_workspace_for_fixture(data, project_root=project_root, db_path=db_path)
    failures = list(workspace_lookup.get("failures") or [])
    warnings = list(workspace_lookup.get("warnings") or [])
    workspace_row = workspace_lookup.get("workspace")
    if not workspace_row:
        return {
            "ok": False,
            "workspace_lookup": workspace_lookup,
            "source_id": "",
            "registration_plan": None,
            "paths": {},
            "failures": failures,
            "warnings": warnings,
        }

    from core.gbrain import project_source_id_for_workspace, project_source_paths_for_workspace, project_source_registration_plan

    workspace = SimpleNamespace(
        id=int(workspace_row["id"]),
        name=str(workspace_row["name"]),
        slug=str(workspace_row["slug"]),
        brand=str(workspace_row["brand"]),
        workspace_kind=str(workspace_row["workspace_kind"]),
        storage_path=str(workspace_row["storage_path"]),
    )
    source_id = project_source_id_for_workspace(workspace)
    paths = project_source_paths_for_workspace(workspace)
    plan = project_source_registration_plan(workspace)
    normalized_paths = {key: str(path.resolve()) for key, path in paths.items() if isinstance(path, Path)}

    fixture_workspace = Path(project_root / str(data["fixture_scope"]["workspace_path"])).resolve()
    raw_path = paths["raw"].resolve()
    gbrain_ready = paths["gbrain_ready"].resolve()
    preprocessed_root = paths["preprocessed_root"].resolve()
    expected_preprocessed_parent = (project_root / "backend" / "workspace_data" / "_preprocessed" / "project" / "TEST").resolve()

    if raw_path != fixture_workspace:
        failures.append(f"raw path mismatch: {raw_path} != {fixture_workspace}")
    if not source_id.startswith("project-test-"):
        failures.append(f"source_id must start with project-test- for TEST workspace, got {source_id!r}")
    if not str(preprocessed_root).startswith(str(expected_preprocessed_parent)):
        failures.append(f"preprocessed_root must stay under {expected_preprocessed_parent}, got {preprocessed_root}")
    if gbrain_ready.name != "gbrain-ready":
        failures.append(f"gbrain_ready path must end with gbrain-ready, got {gbrain_ready}")
    if Path(plan["path"]).resolve() != gbrain_ready:
        failures.append("registration plan path must point at gbrain_ready")
    legacy_derived = paths.get("legacy_derived")
    if isinstance(legacy_derived, Path) and legacy_derived.exists() and any(legacy_derived.iterdir()):
        warnings.append(f"legacy derived path is non-empty: {legacy_derived}")

    return {
        "ok": not failures,
        "workspace_lookup": workspace_lookup,
        "workspace": workspace_row,
        "source_id": source_id,
        "registration_plan": plan,
        "paths": normalized_paths,
        "failures": failures,
        "warnings": warnings,
    }


# ── Query / Think modes (NEW) ────────────────────────────────────────────


def build_think_query_fn(source_id: str):
    """Build a query function that calls GBrainAdapter.think for the given source.

    Returns a callable suitable for run_regression().
    """
    from core.gbrain import GBrainAdapter

    adapter = GBrainAdapter()

    def query_fn(query_text: str) -> dict[str, Any]:
        return adapter.think(query_text, source_id=source_id)

    return query_fn


def build_offline_query_fn(mock_responses: dict[str, dict[str, Any]]):
    """Build a query function that returns pre-defined responses.

    Args:
        mock_responses: dict mapping query text (or case_id) to a response dict
            with the same shape as GBrainAdapter.think() return value.
    """

    def query_fn(query_text: str) -> dict[str, Any]:
        response = mock_responses.get(query_text)
        if response is not None:
            return response
        # Try matching by normalized text
        normalized = query_text.strip().lower()
        for key, value in mock_responses.items():
            if key.strip().lower() == normalized:
                return value
        return {
            "ok": False,
            "status": "unreachable",
            "reply": "",
            "sources": [],
            "error": f"No mock response for: {query_text}",
        }

    return query_fn


def run_query_regression(
    data: dict[str, Any],
    *,
    mode: str = "query",
    offline: bool = False,
    mock_responses: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run the quality regression in query/think mode.

    Args:
        data: Loaded fixture data.
        mode: 'query' or 'think'.
        offline: If True, use mock responses instead of live GBrain.
        mock_responses: Pre-defined responses for offline mode.

    Returns:
        dict with {ok, report (serialized), storage_path, error}
    """
    from app.features.knowledge.quality.regression import (
        RegressionCase,
        load_fixture as load_cases,
        run_regression,
        regression_report_to_dict,
    )
    from app.features.knowledge.quality.report import store_report

    # Get workspace info
    workspace_lookup = load_workspace_for_fixture(data)
    workspace_row = workspace_lookup.get("workspace")
    if not workspace_row:
        return {"ok": False, "error": "TEST workspace not found in DB", "workspace_lookup_failures": workspace_lookup.get("failures")}

    from core.gbrain import project_source_id_for_workspace, project_source_paths_for_workspace

    workspace = SimpleNamespace(
        id=int(workspace_row["id"]),
        name=str(workspace_row["name"]),
        slug=str(workspace_row["slug"]),
        brand=str(workspace_row["brand"]),
        workspace_kind=str(workspace_row["workspace_kind"]),
        storage_path=str(workspace_row["storage_path"]),
    )
    source_id = project_source_id_for_workspace(workspace)
    paths = project_source_paths_for_workspace(workspace)

    # Load cases
    cases = load_cases(FIXTURE_PATH)

    # Build query function
    if offline and mock_responses is not None:
        query_fn = build_offline_query_fn(mock_responses)
    else:
        query_fn = build_think_query_fn(source_id)

    # Run regression
    report = run_regression(cases, query_fn, mode=mode, source_id=source_id)

    # Store report
    reports_dir = paths.get("manifests") / "quality-reports" if paths.get("manifests") else None
    saved_path = store_report(
        report,
        project_slug=f"{workspace.brand}-{workspace.slug}",
        reports_dir=reports_dir,
    )

    return {
        "ok": True,
        "report": regression_report_to_dict(report),
        "storage_path": str(saved_path) if saved_path else None,
        "workspace_id": workspace.id,
        "source_id": source_id,
    }


# ── Reporting (extended) ────────────────────────────────────────────────


def print_report(report: dict[str, Any], *, workspace_preflight: dict[str, Any] | None = None) -> None:
    print("GBrain project quality regression fixture check")
    print(f"workspace: {report.get('workspace_path')}")
    print(f"cases: {report.get('case_count')}")

    print("by file_kind:")
    for file_kind, count in report.get("file_kind_counts", {}).items():
        print(f"- {file_kind}: {count}")

    print("by expected_status:")
    for status, count in report.get("status_counts", {}).items():
        print(f"- {status}: {count}")

    warnings = report.get("warnings") or []
    if warnings:
        print("warnings:")
        for warning in warnings:
            print(f"- {warning}")

    failures = report.get("failures") or []
    if failures:
        print("failures:")
        for failure in failures:
            print(f"- {failure}")
    else:
        print("Fixture preflight passed. No preprocess, sync, or query was executed.")

    if workspace_preflight is not None:
        print("workspace preflight:")
        workspace = workspace_preflight.get("workspace") or {}
        if workspace:
            print(
                f"- workspace_id={workspace.get('id')} "
                f"brand={workspace.get('brand')} slug={workspace.get('slug')} "
                f"kind={workspace.get('workspace_kind')}"
            )
            print(f"- source_id={workspace_preflight.get('source_id')}")
            paths = workspace_preflight.get("paths") or {}
            for key in ("raw", "preprocessed_root", "gbrain_ready", "runs", "manifests", "legacy_derived"):
                if key in paths:
                    print(f"- {key}: {paths[key]}")
            plan = workspace_preflight.get("registration_plan") or {}
            if plan:
                print(f"- registration_path: {plan.get('path')}")
                print(f"- migration_status: {plan.get('migration_status')}")
        if workspace_preflight.get("warnings"):
            print("workspace warnings:")
            for warning in workspace_preflight["warnings"]:
                print(f"- {warning}")
        if workspace_preflight.get("failures"):
            print("workspace failures:")
            for failure in workspace_preflight["failures"]:
                print(f"- {failure}")
        elif workspace:
            print("Workspace preflight passed. No directories were created and no GBrain source was registered or synced.")


def print_quality_report(result: dict[str, Any]) -> None:
    """Print a formatted quality regression report summary."""
    report = result.get("report")
    if not report:
        print("No report data available.")
        if result.get("error"):
            print(f"Error: {result['error']}")
        if result.get("workspace_lookup_failures"):
            print(f"Workspace lookup failures: {result['workspace_lookup_failures']}")
        return

    summary = report.get("summary", {})
    print(f"\n{'='*60}")
    print(f"Project Quality Regression Report")
    print(f"{'='*60}")
    print(f"Run ID:     {report.get('run_id')}")
    print(f"Mode:       {report.get('mode')}")
    print(f"Source ID:  {report.get('source_id')}")
    print(f"Generated:  {report.get('generated_at')}")
    print(f"{'='*60}")
    print(f"Total:      {summary.get('total', 0)}")
    print(f"Pass:       {summary.get('pass', 0)}")
    print(f"Fail:       {summary.get('fail', 0)}")
    print(f"  wrong_source:         {summary.get('wrong_source', 0)}")
    print(f"  missing_answer_point: {summary.get('missing_answer_point', 0)}")
    print(f"  missing_citation:     {summary.get('missing_citation', 0)}")
    print(f"Known gap:        {summary.get('known_gap', 0)}")
    print(f"Unexpected pass:  {summary.get('unexpected_pass', 0)}")
    print(f"Service unavail:  {summary.get('service_unavailable', 0)}")
    print(f"Meeting FP:       {summary.get('meeting_false_positive', 0)}")
    print(f"Should-pass rate: {summary.get('pass_rate_should_pass', 'N/A')}")
    print(f"{'='*60}")

    if result.get("storage_path"):
        print(f"Report saved: {result['storage_path']}")

    # Print per-case details
    if report.get("results"):
        print(f"\n--- Per-case results ---")
        for r in report["results"]:
            fp_flag = " [MEETING_FP]" if r.get("meeting_false_positive") else ""
            first_hit = r.get("first_hit_source") or "-"
            print(f"  {r['case_id']:50s} {r['status']:25s}{fp_flag}")
            print(f"    first_hit: {first_hit[:80]}")
            if r.get("missing_terms_all"):
                print(f"    missing all: {r['missing_terms_all']}")
            if r.get("error"):
                print(f"    error: {r['error']}")


# ── Offline mock fixtures (for testing) ─────────────────────────────────


def load_offline_mock_responses() -> dict[str, dict[str, Any]]:
    """Return pre-defined mock responses for offline mode testing.

    These simulate what GBrain think would return for each TEST case.
    Used for scoring logic validation without a live GBrain service.
    """
    return {
        "L17 层图纸里有多少个窗？": {
            "ok": True,
            "status": "ok",
            "reply": "图纸 LEVEL 17 共有 12 个窗，详见 Floor Plans (p. 9)。",
            "sources": [
                {"file": "02-图纸与技术资料/240704 Orama [Floor Plans].pdf", "file_kind": "pdf_drawing"}
            ],
            "source_id": "project-test-6-test",
        },
        "L3-15 W19这个窗的宽高尺寸是多少？": {
            "ok": True,
            "status": "ok",
            "reply": "W19 窗宽 1200mm，高 1800mm，位于 L3-15。",
            "sources": [
                {"file": "02-图纸与技术资料/240715 Orama [WS].pdf", "file_kind": "pdf_drawing"}
            ],
            "source_id": "project-test-6-test",
        },
        "项目排期中L6-L39 Shop Drawing图纸需要多少天才能完成？": {
            "ok": True,
            "status": "ok",
            "reply": "L6-L39 Shop Drawing 计划 Duration 为 45 天。",
            "sources": [
                {"file": "02-图纸与技术资料/260205 Madeline [Facade Supply Programme] Rev04.pdf", "file_kind": "pdf_schedule"}
            ],
            "source_id": "project-test-6-test",
        },
        "项目排期中L6-L39 Shop Drawing图纸计划完成日期是什么时候？": {
            "ok": True,
            "status": "ok",
            "reply": "L6-L39 Shop Drawing 计划完成日期为 2026-05-15 (Finish)。",
            "sources": [
                {"file": "02-图纸与技术资料/260205 Madeline [Facade Supply Programme] Rev04.pdf", "file_kind": "pdf_schedule"}
            ],
            "source_id": "project-test-6-test",
        },
        "内部联系单 BG0806-LXD01-补货 为什么要补货？": {
            "ok": True,
            "status": "ok",
            "reply": "BG0806-LXD01 补货原因为现场安装发现铝材数量不足，需增补。",
            "sources": [
                {"file": "04-变更与签证/邱智勇提交的内部联系单.pdf", "file_kind": "pdf_drawing"}
            ],
            "source_id": "project-test-6-test",
        },
        "内部联系单 BG0806-LXD01-补货 补什么？": {
            "ok": True,
            "status": "ok",
            "reply": "需补铝材及相应五金配件。",
            "sources": [
                {"file": "04-变更与签证/邱智勇提交的内部联系单.pdf", "file_kind": "pdf_drawing"}
            ],
            "source_id": "project-test-6-test",
        },
        "会议中Gary提出了一个新的知识库系统叫什么？": {
            "ok": True,
            "status": "ok",
            "reply": "会议中 Gary 讨论了知识库架构，提到了 LMT 和新的框架方案，但未明确命名一个特定的新系统。",
            "sources": [
                {"file": "03-会议纪要/20260529-143933_张学辉Gary_张学辉发起的视频会议_0529_audio.docx", "file_kind": "meeting_transcript_docx"}
            ],
            "source_id": "project-test-6-test",
        },
        "邮件中 daisy推荐客户sky light使用什么玻璃？": {
            "ok": True,
            "status": "ok",
            "reply": "Daisy 推荐客户 Sky light 使用 12mm 钢化玻璃。",
            "sources": [
                {"file": "99-未归档文件/2026-03-13 1551 RE-    BFI _29 Dudley St. _Skylight & Balustrade ShopD.eml", "file_kind": "email"}
            ],
            "source_id": "project-test-6-test",
        },
        "支付截图中，花费了多少钱？": {
            "ok": True,
            "status": "ok",
            "reply": "支付截图显示花费 68.00 元（金额：68.00 CNY，支出，来源：99-未归档文件/支付截图服务器.png）。",
            "sources": [
                {"file": "99-未归档文件/支付截图服务器.png", "file_kind": "image", "source_file_kind": "image"}
            ],
            "source_id": "project-test-6-test",
        },
        "材料清单中，GL01的玻璃规格是什么？": {
            "ok": True,
            "status": "ok",
            "reply": "GL01 玻璃规格为 6+12A+6 中空钢化玻璃。",
            "sources": [
                {"file": "05-生产与发货/260506 ML (材料清单) Rev 01.xlsx", "file_kind": "spreadsheet"}
            ],
            "source_id": "project-test-6-test",
        },
        "注意事项文件中，适配颜色五金件需要注意什么？": {
            "ok": True,
            "status": "ok",
            "reply": "适配颜色五金件需注意与玻璃颜色的协调性，避免色差过大。",
            "sources": [
                {"file": "05-生产与发货/260506 注意事项 [BG0812] Rooster.docx", "file_kind": "office_doc"}
            ],
            "source_id": "project-test-6-test",
        },
    }


# ── Main ──────────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(description="Project_R 8.D project quality regression tool.")
    parser.add_argument("--workspace-preflight", action="store_true", help="Validate fixture + TEST workspace source plan without writes.")
    parser.add_argument("--query", action="store_true", help="Run regression against live GBrain think (project query mode).")
    parser.add_argument("--offline", action="store_true", help="Run regression with mock responses (no live GBrain needed).")
    args = parser.parse_args()

    data = load_fixture()

    # Default: fixture validation only
    if not args.query and not args.offline and not args.workspace_preflight:
        report = validate_fixture(data)
        workspace_preflight = build_workspace_preflight(data)
        print_report(report, workspace_preflight=workspace_preflight)
        ok = report["ok"] and (workspace_preflight is None or workspace_preflight["ok"])
        return 0 if ok else 1

    # Workspace preflight
    if args.workspace_preflight:
        report = validate_fixture(data)
        workspace_preflight = build_workspace_preflight(data)
        print_report(report, workspace_preflight=workspace_preflight)
        ok = report["ok"] and (workspace_preflight is None or workspace_preflight["ok"])
        return 0 if ok else 1

    # Query / offline mode
    if args.offline:
        mock_responses = load_offline_mock_responses()
        result = run_query_regression(data, mode="query", offline=True, mock_responses=mock_responses)
    elif args.query:
        result = run_query_regression(data, mode="query")
    else:
        print("No mode specified. Use --query, --offline, or --workspace-preflight.")
        return 1

    print_quality_report(result)
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
