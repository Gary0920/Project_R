import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import gbrain_agent_inline_execution_smoke as script


class GBrainAgentInlineExecutionSmokeScriptTest(unittest.TestCase):
    def test_build_job_params_is_read_only_and_source_scoped(self):
        params = script._build_job_params(
            source_id="company-wiki",
            page_slug="rules/written-principle",
            model="deepseek:deepseek-chat",
            max_turns=3,
            tools=("search", "get_page"),
        )

        self.assertEqual(params["source_id"], "company-wiki")
        self.assertEqual(params["allowed_tools"], ["search", "get_page"])
        self.assertNotIn("put_page", params["allowed_tools"])
        self.assertIn("rules/written-principle", params["prompt"])
        self.assertEqual(params["model"], "deepseek:deepseek-chat")

    def test_build_command_submits_subagent_with_follow(self):
        command = script._build_command(
            bun_bin="bun",
            params={"prompt": "x", "source_id": "company-wiki"},
            timeout_ms=120_000,
        )

        self.assertEqual(command[:5], ["bun", "src/cli.ts", "jobs", "submit", "subagent"])
        self.assertIn("--follow", command)
        self.assertIn("--max-attempts", command)
        self.assertIn('"source_id":"company-wiki"', " ".join(command))

    def test_extract_completed_job_id(self):
        self.assertEqual(script._extract_completed_job_id("Job #12 completed in 1.0s"), 12)
        self.assertIsNone(script._extract_completed_job_id("Job #12 failed"))

    def test_promote_deepseek_key_uses_first_csv_key(self):
        env = {"DEEPSEEK_API_KEYS": " first-key , second-key "}
        with patch.dict(os.environ, {}, clear=True):
            script._promote_deepseek_key(env)

        self.assertEqual(env["DEEPSEEK_API_KEY"], "first-key")

    def test_write_inline_execution_verified_updates_env_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / ".env"
            path.write_text("GBRAIN_AGENT_INLINE_EXECUTION_VERIFIED=false\nOTHER=value\n", encoding="utf-8")

            script._write_inline_execution_verified(path)

            updated = path.read_text(encoding="utf-8")
        self.assertIn("GBRAIN_AGENT_INLINE_EXECUTION_VERIFIED=true", updated)
        self.assertIn("OTHER=value", updated)


if __name__ == "__main__":
    unittest.main()
