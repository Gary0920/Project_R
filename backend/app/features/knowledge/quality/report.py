from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.features.knowledge.quality.regression import RegressionReport, regression_report_to_dict


# Aggregated report directory (admin-visible, across projects)
AGGREGATED_REPORTS_DIR = (
    Path(__file__).resolve().parents[4]
    / "workspace_data"
    / "_preprocessed"
    / "_quality-reports"
)


def store_report(
    report: RegressionReport,
    *,
    project_slug: str = "",
    reports_dir: Path | None = None,
) -> Path:
    """Store a regression report to disk.

    Writes to two locations:
        1. Project-scoped: `_preprocessed/project/{brand}/{slug}/manifests/quality-reports/{run_id}.json`
        2. Aggregated:      `_preprocessed/_quality-reports/{project_slug}/{run_id}.json`

    Returns the project-scoped path.
    """
    report_dict = regression_report_to_dict(report)

    # 1. Project-scoped
    if reports_dir is None and project_slug:
        # Try to derive from workspace paths
        from app.features.knowledge.gbrain import resolve_gbrain_source_paths

        try:
            paths = resolve_gbrain_source_paths(project_slug, workspace_kind="project")
            reports_dir = paths.get("manifests") / "quality-reports"
        except Exception:
            reports_dir = None

    if reports_dir is not None:
        reports_dir.mkdir(parents=True, exist_ok=True)
        project_path = reports_dir / f"{report.run_id}.json"
        project_path.write_text(
            json.dumps(report_dict, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    else:
        project_path = Path()

    # 2. Aggregated
    slug = project_slug or report.source_id or "unknown"
    agg_dir = AGGREGATED_REPORTS_DIR / slug
    agg_dir.mkdir(parents=True, exist_ok=True)
    agg_path = agg_dir / f"{report.run_id}.json"
    agg_path.write_text(
        json.dumps(report_dict, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return project_path if project_path else agg_path


def load_report(path: Path) -> dict[str, Any]:
    """Load a stored regression report from disk."""
    return json.loads(path.read_text(encoding="utf-8"))


def list_reports(
    *,
    project_slug: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """List available regression reports, most recent first.

    If project_slug is set, scope to that project only.
    """
    if project_slug:
        base = AGGREGATED_REPORTS_DIR / project_slug
    else:
        base = AGGREGATED_REPORTS_DIR

    if not base.exists():
        return []

    reports: list[dict[str, Any]] = []
    for path in sorted(base.glob("*.json"), reverse=True)[:limit]:
        try:
            data = load_report(path)
            reports.append(
                {
                    "run_id": data.get("run_id", path.stem),
                    "generated_at": data.get("generated_at", ""),
                    "mode": data.get("mode", ""),
                    "source_id": data.get("source_id", ""),
                    "summary": data.get("summary", {}),
                }
            )
        except Exception:
            continue

    return reports


def report_summary_to_text(summary: dict) -> str:
    """Format a report summary as human-readable text."""
    lines = [
        f"Total: {summary.get('total', 0)}",
        f"Pass: {summary.get('pass', 0)}",
        f"Fail: {summary.get('fail', 0)}",
        f"  - wrong_source: {summary.get('wrong_source', 0)}",
        f"  - missing_answer_point: {summary.get('missing_answer_point', 0)}",
        f"  - missing_citation: {summary.get('missing_citation', 0)}",
        f"Known gap: {summary.get('known_gap', 0)}",
        f"Unexpected pass: {summary.get('unexpected_pass', 0)}",
        f"Service unavailable: {summary.get('service_unavailable', 0)}",
        f"Meeting false positive: {summary.get('meeting_false_positive', 0)}",
        f"Should-pass rate: {summary.get('pass_rate_should_pass', 'N/A')}",
    ]
    return "\n".join(lines)
