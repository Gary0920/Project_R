import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

from app.features.knowledge.gbrain import GBrainSettings
from app.features.knowledge.gbrain.runtime import GBrainRuntime
from app.features.knowledge.gbrain.transport import GBrainTransport, parse_mcp_tool_payload


def _settings(root: Path) -> GBrainSettings:
    return GBrainSettings(
        enabled=True,
        base_url="http://127.0.0.1:3131",
        service_bearer_token="test-token",
        home_path=root / "home",
        manifests_path=root / "manifests",
        cli_workdir=root,
        local_git_enabled=False,
    )


class GBrainRuntimeTransportTests(unittest.TestCase):
    def test_runtime_writes_and_reads_service_record(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = _settings(Path(temp_dir))
            runtime = GBrainRuntime(
                settings,
                ensure_environment=lambda _: {"ok": True},
                apply_provider_env=lambda env: env,
                default_ollama_base_url="http://127.0.0.1:11434/v1",
            )

            runtime.write_service_record({"pid": 123, "status": "started"})

            self.assertEqual(runtime.read_service_record()["pid"], 123)
            self.assertEqual(runtime.read_service_record()["status"], "started")

    def test_parse_mcp_tool_payload_supports_sse_text_content(self):
        body = {
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps({"answer": "ok", "citations": []}),
                    }
                ]
            },
            "jsonrpc": "2.0",
            "id": 1,
        }
        raw = f"event: message\ndata: {json.dumps(body)}\n\n"

        self.assertEqual(parse_mcp_tool_payload(raw), {"answer": "ok", "citations": []})

    def test_transport_formats_cli_result(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = _settings(Path(temp_dir))
            transport = GBrainTransport(
                settings,
                apply_provider_env=lambda env: env,
                default_ollama_base_url="http://127.0.0.1:11434/v1",
            )

            result = transport.run_gbrain_cli(
                [sys.executable, "-c", "print('gbrain-ok')"],
                os.environ.copy(),
                timeout=10,
            )

            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["result"]["returncode"], 0)
            self.assertIn("gbrain-ok", result["result"]["stdout"])


if __name__ == "__main__":
    unittest.main()
