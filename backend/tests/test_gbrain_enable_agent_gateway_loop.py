import unittest

from scripts import gbrain_enable_agent_gateway_loop as script


class GBrainEnableAgentGatewayLoopScriptTest(unittest.TestCase):
    def test_build_command_sets_agent_gateway_loop(self):
        command = script._build_command("bun")

        self.assertEqual(
            command,
            [
                "bun",
                "run",
                "src/cli.ts",
                "config",
                "set",
                "agent.use_gateway_loop",
                "true",
                "--force",
            ],
        )


if __name__ == "__main__":
    unittest.main()
