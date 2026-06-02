import tempfile
import unittest
from pathlib import Path

from scripts import gbrain_agent_citation_fixer_mutation_smoke as script


class GBrainAgentCitationFixerMutationSmokeScriptTest(unittest.TestCase):
    def test_prepare_smoke_page_is_scoped_to_reviews_prefix(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            derived = Path(temp_dir) / "derived"
            target = script.prepare_smoke_page(derived)

            self.assertEqual(target.relative_to(derived), script.SMOKE_RELATIVE_PATH)
            text = target.read_text(encoding="utf-8")

        self.assertIn(script.BROKEN_MARKER, text)
        self.assertIn("content_kind: gbrain_agent_smoke_test", text)
        self.assertEqual(text.count(script.BROKEN_MARKER), 1)
        self.assertTrue(script.text_citation_broken(text))

    def test_build_job_params_requires_put_page_but_limits_slug_prefix(self):
        params = script.build_job_params(
            source_id="company-wiki",
            page_slug=script.SMOKE_SLUG,
            model="deepseek:deepseek-chat",
            max_turns=6,
            tools=script.DEFAULT_TOOLS,
        )

        self.assertEqual(params["source_id"], "company-wiki")
        self.assertEqual(params["allowed_tools"], list(script.DEFAULT_TOOLS))
        self.assertIn("put_page", params["allowed_tools"])
        self.assertEqual(params["allowed_slug_prefixes"], [script.SMOKE_ALLOWED_SLUG_GLOB])
        self.assertIn(script.SMOKE_SLUG, params["prompt"])
        self.assertIn(script.BROKEN_MARKER, params["prompt"])
        self.assertEqual(params["model"], "deepseek:deepseek-chat")

    def test_smoke_page_fixed_requires_marker_replacement(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "page.md"
            path.write_text(f"citation {script.BROKEN_MARKER}\n", encoding="utf-8")
            self.assertFalse(script.smoke_page_fixed(path))

            path.write_text(f"{script.CITATION_PREFIX} {script.FIXED_MARKER}\n", encoding="utf-8")
            self.assertTrue(script.smoke_page_fixed(path))

    def test_gbrain_page_contains_marker_reads_common_payload_shapes(self):
        self.assertTrue(
            script.gbrain_page_contains_marker(
                {"status": "ok", "result": {"page": {"content": f"citation {script.BROKEN_MARKER}"}}}
            )
        )
        self.assertTrue(
            script.gbrain_page_contains_marker(
                {"status": "ok", "result": {"markdown": f"citation {script.FIXED_MARKER}"}}
            )
        )
        self.assertFalse(script.gbrain_page_contains_marker({"status": "not_found", "result": {}}))

    def test_build_page_probe_script_is_source_scoped(self):
        probe = script.build_page_probe_script(source_id="company-wiki", page_slug=script.SMOKE_SLUG)

        self.assertIn("const sourceId = \"company-wiki\";", probe)
        self.assertIn(f"const pageSlug = \"{script.SMOKE_SLUG}\";", probe)
        self.assertIn("WHERE source_id = $1 AND slug = $2", probe)
        self.assertIn("[sourceId, pageSlug]", probe)

    def test_probe_marker_helpers_read_compiled_truth_and_timeline(self):
        broken_probe = {
            "status": "ok",
            "rows": [{"compiled_truth": f"{script.CITATION_PREFIX} {script.BROKEN_MARKER}", "timeline": ""}],
        }
        fixed_probe = {
            "status": "ok",
            "rows": [{"compiled_truth": "body", "timeline": f"{script.CITATION_PREFIX} {script.FIXED_MARKER}"}],
        }

        self.assertTrue(script.probe_contains_marker(broken_probe, script.BROKEN_MARKER))
        self.assertFalse(script.probe_page_fixed(broken_probe))
        self.assertTrue(script.probe_page_fixed(fixed_probe))

    def test_reconcile_agent_write_copies_fixed_sidecar_to_canonical(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            derived = Path(temp_dir) / "derived"
            smoke_path = script.prepare_smoke_page(derived)
            sidecar = script.sidecar_page_path(
                derived,
                source_id="company-wiki",
                page_slug=script.SMOKE_SLUG,
            )
            sidecar.parent.mkdir(parents=True)
            sidecar.write_text(
                script.build_smoke_page().replace(script.BROKEN_MARKER, script.FIXED_MARKER),
                encoding="utf-8",
            )

            result = script.reconcile_agent_write_to_derived(
                derived,
                smoke_path,
                source_id="company-wiki",
                page_slug=script.SMOKE_SLUG,
            )

            self.assertTrue(result["ok"])
            self.assertEqual(result["status"], "copied_sidecar")
            self.assertTrue(script.smoke_page_fixed(smoke_path))

    def test_write_execution_verified_updates_env_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / ".env"
            path.write_text(
                "GBRAIN_AGENT_EXECUTION_VERIFIED=false\n"
                "GBRAIN_AGENT_INLINE_EXECUTION_VERIFIED=false\n"
                "OTHER=value\n",
                encoding="utf-8",
            )

            script.write_execution_verified(path)

            updated = path.read_text(encoding="utf-8")

        self.assertIn("GBRAIN_AGENT_EXECUTION_VERIFIED=true", updated)
        self.assertIn("GBRAIN_AGENT_INLINE_EXECUTION_VERIFIED=true", updated)
        self.assertIn("OTHER=value", updated)

    def test_backup_import_checkpoint_moves_checkpoint(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            home = Path(temp_dir)
            checkpoint = home / ".gbrain" / "import-checkpoint.json"
            checkpoint.parent.mkdir(parents=True)
            checkpoint.write_text('{"completedPaths":[]}', encoding="utf-8")

            backup = script.backup_import_checkpoint(home)

            self.assertIsNotNone(backup)
            self.assertFalse(checkpoint.exists())
            self.assertTrue(backup.exists())
            self.assertIn("smoke-backup", backup.name)

    def test_commit_smoke_page_refuses_non_git_repo(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            derived = Path(temp_dir) / "derived"
            smoke_path = script.prepare_smoke_page(derived)

            result = script.commit_smoke_page(derived, smoke_path)

        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "no_git_repo")

    def test_commit_mutation_refuses_non_git_repo(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            derived = Path(temp_dir) / "derived"
            smoke_path = script.prepare_smoke_page(derived)

            result = script.commit_mutation(derived, smoke_path)

        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "no_git_repo")


if __name__ == "__main__":
    unittest.main()
