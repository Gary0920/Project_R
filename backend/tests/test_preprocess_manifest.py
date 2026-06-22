from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
import tempfile
import unittest
from typing import Any

from app.features.knowledge.gbrain.preprocess_manifest import (
    manifest_item_from_result,
    status_summary_from_results,
    summary_from_results,
    write_manifest_with_git_status,
)


@dataclass(frozen=True)
class _Result:
    source_path: Path
    status: str
    target_path: Path | None = None
    error: str | None = None
    source_sha256: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class PreprocessManifestTests(unittest.TestCase):
    def test_summary_from_results_keeps_declared_status_keys(self):
        results = [
            _Result(Path("a.md"), "compiled"),
            _Result(Path("b.md"), "failed"),
            _Result(Path("c.png"), "pending_extractor_capability"),
        ]

        summary = summary_from_results(
            results,
            status_keys=("compiled", "pending_extractor_capability", "pending_transcription", "skipped", "failed"),
        )

        self.assertEqual(
            summary,
            {
                "total": 3,
                "compiled": 1,
                "pending_extractor_capability": 1,
                "pending_transcription": 0,
                "skipped": 0,
                "failed": 1,
            },
        )

    def test_status_summary_from_results_keeps_dynamic_statuses_and_defaults(self):
        results = [
            _Result(Path("a.md"), "compiled"),
            _Result(Path("b.png"), "pending_extractor_capability"),
        ]

        summary = status_summary_from_results(results, defaults={"compiled": 0, "skipped": 0, "failed": 0})

        self.assertEqual(summary["total"], 2)
        self.assertEqual(summary["compiled"], 1)
        self.assertEqual(summary["pending_extractor_capability"], 1)
        self.assertEqual(summary["skipped"], 0)
        self.assertEqual(summary["failed"], 0)

    def test_manifest_item_filters_empty_metadata_and_uses_relative_paths(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_root = root / "raw"
            target_root = root / "gbrain-ready"
            source = source_root / "notes" / "a.md"
            target = target_root / "rules" / "a.md"
            source.parent.mkdir(parents=True)
            target.parent.mkdir(parents=True)
            source.write_text("source", encoding="utf-8")
            target.write_text("target", encoding="utf-8")

            item = manifest_item_from_result(
                _Result(
                    source,
                    "compiled",
                    target,
                    source_sha256="abc",
                    metadata={"keep": "yes", "drop_none": None, "drop_empty": [], "drop_dict": {}},
                ),
                source_root=source_root,
                target_root=target_root,
            )

        self.assertEqual(item["source_file"], "notes/a.md")
        self.assertEqual(item["target_file"], "rules/a.md")
        self.assertEqual(item["source_sha256"], "abc")
        self.assertEqual(item["keep"], "yes")
        self.assertNotIn("drop_none", item)
        self.assertNotIn("drop_empty", item)
        self.assertNotIn("drop_dict", item)

    def test_write_manifest_with_git_status_persists_local_git_result(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manifest_path = root / "manifests" / "manifest.json"
            repo_path = root / "gbrain-ready"
            repo_path.mkdir()

            def fake_commit(path: Path, summary: dict[str, Any], enabled: bool) -> dict[str, Any]:
                self.assertEqual(path, repo_path)
                self.assertEqual(summary["compiled"], 1)
                self.assertTrue(enabled)
                return {"enabled": True, "committed": False, "reason": "no changes"}

            manifest = write_manifest_with_git_status(
                {"summary": {"compiled": 1}},
                manifest_path=manifest_path,
                repo_path=repo_path,
                local_git_enabled=True,
                commit_changes=fake_commit,
            )
            saved = json.loads(manifest_path.read_text(encoding="utf-8"))

        self.assertEqual(manifest["local_git"]["reason"], "no changes")
        self.assertEqual(saved["local_git"]["reason"], "no changes")


if __name__ == "__main__":
    unittest.main()
