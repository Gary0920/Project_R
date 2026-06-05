import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from core.gbrain import GBrainAdapter, GBrainSettings, resolve_gbrain_source_paths


class GBrainSourcePathResolverTests(unittest.TestCase):
    def test_resolves_company_preprocessed_paths_with_legacy_derived(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            preprocessed_root = root / "_preprocessed"
            settings = GBrainSettings(
                enabled=True,
                base_url="",
                company_source_id="company-wiki",
                raw_path=root / "global" / "company-wiki" / "raw",
                derived_path=root / "global" / "company-wiki" / "derived",
                manifests_path=root / "global" / "company-wiki" / "manifests",
                local_git_enabled=False,
            )

            with patch.dict(os.environ, {"GBRAIN_PREPROCESSED_ROOT": str(preprocessed_root)}):
                paths = resolve_gbrain_source_paths("company", settings=settings)

        self.assertEqual(paths.source_scope, "company")
        self.assertEqual(paths.source_id, "company-wiki")
        self.assertEqual(paths.gbrain_ready, (preprocessed_root / "company" / "company-wiki" / "gbrain-ready").resolve())
        self.assertEqual(paths.runs, (preprocessed_root / "company" / "company-wiki" / "runs").resolve())
        self.assertEqual(paths.manifests, (preprocessed_root / "company" / "company-wiki" / "manifests").resolve())
        self.assertEqual(paths.legacy_derived, (root / "global" / "company-wiki" / "derived").resolve())

    def test_company_registration_plan_uses_gbrain_ready_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            preprocessed_root = root / "_preprocessed"
            settings = GBrainSettings(
                enabled=True,
                base_url="",
                company_source_id="company-wiki",
                raw_path=root / "global" / "company-wiki" / "raw",
                derived_path=root / "global" / "company-wiki" / "derived",
                manifests_path=root / "global" / "company-wiki" / "manifests",
                local_git_enabled=False,
            )

            with patch.dict(os.environ, {"GBRAIN_PREPROCESSED_ROOT": str(preprocessed_root)}):
                plan = GBrainAdapter(settings).source_registration_plan()

        expected = preprocessed_root / "company" / "company-wiki" / "gbrain-ready"
        self.assertEqual(Path(plan["path"]), expected.resolve())
        self.assertEqual(Path(plan["gbrain_ready_path"]), expected.resolve())
        self.assertEqual(Path(plan["legacy_derived_path"]), (root / "global" / "company-wiki" / "derived").resolve())
        self.assertEqual(plan["migration_status"], "empty")

    def test_resolves_project_preprocessed_paths_outside_user_source_root(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            preprocessed_root = root / "_preprocessed"
            raw_root = root / "workspace_data" / "project" / "BFI" / "BG007"
            workspace = SimpleNamespace(
                id=7,
                brand="BFI",
                slug="BG007",
                name="BG007",
                storage_path=str(raw_root),
            )

            with patch.dict(os.environ, {"GBRAIN_PREPROCESSED_ROOT": str(preprocessed_root)}):
                paths = resolve_gbrain_source_paths("project", workspace=workspace)

        self.assertEqual(paths.source_scope, "project")
        self.assertEqual(paths.source_id, "project-bfi-7")
        self.assertEqual(paths.raw, raw_root.resolve())
        self.assertEqual(paths.gbrain_ready, (preprocessed_root / "project" / "BFI" / "7-BG007" / "gbrain-ready").resolve())
        self.assertEqual(paths.runs, (preprocessed_root / "project" / "BFI" / "7-BG007" / "runs").resolve())
        self.assertEqual(paths.manifests, (preprocessed_root / "project" / "BFI" / "7-BG007" / "manifests").resolve())
        self.assertEqual(paths.legacy_derived, (raw_root / "derived").resolve())

    def test_resolves_customer_preprocessed_paths_outside_user_source_root(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            preprocessed_root = root / "_preprocessed"
            raw_root = root / "workspace_data" / "customer" / "lucerna"
            workspace = SimpleNamespace(
                id=9,
                slug="lucerna",
                name="Lucerna",
                storage_path=str(raw_root),
            )

            with patch.dict(os.environ, {"GBRAIN_PREPROCESSED_ROOT": str(preprocessed_root)}):
                paths = resolve_gbrain_source_paths("customer", workspace=workspace)

        self.assertEqual(paths.source_scope, "customer")
        self.assertEqual(paths.source_id, "customer-lucerna-9")
        self.assertEqual(paths.raw, raw_root.resolve())
        self.assertEqual(paths.gbrain_ready, (preprocessed_root / "customer" / "9-lucerna" / "gbrain-ready").resolve())
        self.assertEqual(paths.runs, (preprocessed_root / "customer" / "9-lucerna" / "runs").resolve())
        self.assertEqual(paths.manifests, (preprocessed_root / "customer" / "9-lucerna" / "manifests").resolve())
        self.assertEqual(paths.legacy_derived, (raw_root / "derived").resolve())


if __name__ == "__main__":
    unittest.main()
