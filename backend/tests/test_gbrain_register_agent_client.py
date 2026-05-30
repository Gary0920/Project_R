import unittest
from pathlib import Path

from scripts import gbrain_register_agent_client as script


class GBrainRegisterAgentClientScriptTest(unittest.TestCase):
    def test_parse_registration_output_extracts_confidential_client(self):
        output = """
OAuth client registered: "project-r-citation-fixer"

  Client ID:           gbrain_cl_abc123
  Client Secret:       gbrain_cs_secret456
  Scopes:              agent
"""

        result = script._parse_registration_output(output)

        self.assertEqual(result.client_id, "gbrain_cl_abc123")
        self.assertEqual(result.client_secret, "gbrain_cs_secret456")

    def test_parse_registration_output_rejects_public_client(self):
        output = "  Client ID: gbrain_cl_abc123\n  Client Secret: <public client - none issued>\n"

        with self.assertRaises(ValueError):
            script._parse_registration_output(output)

    def test_redact_registration_output_hides_secret(self):
        output = "Client ID: gbrain_cl_abc123\nClient Secret: gbrain_cs_secret456\n"

        redacted = script._redact_registration_output(output)

        self.assertIn("Client Secret: <redacted>", redacted)
        self.assertNotIn("gbrain_cs_secret456", redacted)

    def test_updated_env_text_replaces_existing_and_appends_missing(self):
        original = "GBRAIN_AGENT_ENABLED=false\nOTHER=value\n"
        updated = script._updated_env_text(
            original,
            {
                "GBRAIN_AGENT_ENABLED": "true",
                "GBRAIN_AGENT_OAUTH_CLIENT_ID": "gbrain_cl_abc123",
            },
        )

        self.assertIn("GBRAIN_AGENT_ENABLED=true", updated)
        self.assertIn("OTHER=value", updated)
        self.assertIn("GBRAIN_AGENT_OAUTH_CLIENT_ID=gbrain_cl_abc123", updated)
        self.assertTrue(updated.endswith("\n"))

    def test_build_command_uses_agent_bindings(self):
        command = script._build_command(
            bun_bin="bun",
            name="project-r-citation-fixer",
            source_id="company-wiki",
            tools=("search", "get_page", "put_page", "list_pages"),
            slug_prefixes=("rules/", "reviews/"),
            max_concurrent=1,
            budget_usd_per_day=1.0,
        )

        self.assertEqual(command[:5], ["bun", "run", "src/commands/auth.ts", "register-client", "project-r-citation-fixer"])
        self.assertIn("--scopes", command)
        self.assertIn("agent", command)
        self.assertIn("--bound-tools", command)
        self.assertIn("search,get_page,put_page,list_pages", command)
        self.assertIn("--bound-slug-prefixes", command)
        self.assertIn("rules/,reviews/", command)

    def test_gbrain_subprocess_env_removes_project_database_url(self):
        env = script._gbrain_subprocess_env(
            {
                "DATABASE_URL": "sqlite:///./app.db",
                "GBRAIN_DATABASE_URL": "postgres://wrong",
                "KEEP": "value",
            },
            Path("brain-home"),
        )

        self.assertNotIn("DATABASE_URL", env)
        self.assertNotIn("GBRAIN_DATABASE_URL", env)
        self.assertEqual(env["KEEP"], "value")
        self.assertTrue(env["GBRAIN_HOME"].endswith("brain-home"))


if __name__ == "__main__":
    unittest.main()
