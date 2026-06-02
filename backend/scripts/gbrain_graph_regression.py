from __future__ import annotations

import json
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
FIXTURE_PATH = BACKEND_DIR / "tests" / "fixtures" / "gbrain_graph_regression_cases.json"


def _node_titles(graph: dict) -> set[str]:
    return {str(node.get("title") or "") for node in graph.get("nodes", []) if isinstance(node, dict)}


def _edge_matches(graph: dict, expected: dict) -> bool:
    nodes = {str(node.get("id") or ""): str(node.get("title") or "") for node in graph.get("nodes", []) if isinstance(node, dict)}
    for edge in graph.get("edges", []):
        if not isinstance(edge, dict):
            continue
        from_title = nodes.get(str(edge.get("from") or ""))
        to_title = nodes.get(str(edge.get("to") or ""))
        if (
            from_title == expected.get("from_title")
            and to_title == expected.get("to_title")
            and str(edge.get("relation_type") or "") == expected.get("relation_type")
        ):
            return True
    return False


def main() -> int:
    sys.path.insert(0, str(BACKEND_DIR))

    from core.gbrain_graph import build_entity_merge_candidates, build_source_graph

    cases = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    failures: list[str] = []
    for case in cases:
        graph = build_source_graph(
            str(case["source_id"]),
            focus=str(case.get("focus") or ""),
            limit=int(case.get("limit") or 120),
        )
        if not graph.get("ok"):
            failures.append(f"{case['id']}: graph build failed: {graph.get('warnings') or graph.get('error')}")
            continue
        titles = _node_titles(graph)
        for title in case.get("expected_node_titles", []):
            if title not in titles:
                failures.append(f"{case['id']}: missing node title {title!r}")
        for expected_edge in case.get("expected_edges", []):
            if not _edge_matches(graph, expected_edge):
                failures.append(f"{case['id']}: missing edge {expected_edge!r}")
        min_events = int(case.get("min_events") or 0)
        if len(graph.get("events", [])) < min_events:
            failures.append(f"{case['id']}: events={len(graph.get('events', []))}, expected at least {min_events}")
        expected_candidate_titles = set(case.get("expected_entity_merge_candidate_titles", []))
        if expected_candidate_titles:
            merge_result = build_entity_merge_candidates(
                str(case["source_id"]),
                focus=str(case.get("focus") or ""),
                limit=int(case.get("merge_limit") or 80),
            )
            candidate_titles = {
                str(candidate.get("title") or "")
                for candidate in merge_result.get("candidates", [])
                if isinstance(candidate, dict)
            }
            for title in expected_candidate_titles:
                if title not in candidate_titles:
                    failures.append(f"{case['id']}: missing entity merge candidate {title!r}")
        if not any(failure.startswith(f"{case['id']}:") for failure in failures):
            stats = graph.get("stats") or {}
            print(
                f"PASS {case['id']}: nodes={stats.get('nodes')} "
                f"edges={stats.get('edges')} events={stats.get('events')}"
            )

    if failures:
        print("GBrain graph regression failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print(f"GBrain graph regression passed ({len(cases)} cases).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
