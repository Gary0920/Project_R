import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError

from core.gbrain import GBrainAdapter, ensure_gbrain_environment, load_gbrain_settings
from core.knowledge_sources import KnowledgeSources


class FakeHttpResponse:
    def __init__(self, body: str, status: int = 200):
        self._body = body.encode("utf-8")
        self.status = status

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


class FakeGBrainQueryAdapter:
    def __init__(self, hit_when: str):
        self.hit_when = hit_when
        self.queries: list[str] = []

    def query(self, query: str, *, limit: int = 5, expand: bool = False, detail: str = "medium"):
        self.queries.append(query)
        if self.hit_when in query:
            return {
                "status": "ok",
                "result": [
                    {
                        "slug": "standards/as-1288",
                        "source_id": "company-wiki",
                        "title": "AS 1288",
                        "chunk_text": "中文：安全玻璃要求。\nEnglish: Safety glass requirements.",
                        "score": 0.9,
                    }
                ],
            }
        return {"status": "ok", "result": []}


class FakeGBrainThinkAdapter:
    def think(self, query: str, *, source_id: str | None = None):
        return {
            "status": "ok",
            "result": {
                "answer": "需要先提交用车申请，并保留书面记录。",
                "citations": [{"page_slug": "rules/用车申请", "row_num": None}],
                "gaps": ["缺少审批时限。"],
                "warnings": [],
                "modelUsed": "gbrain-think-test",
                "diagnostics": {"pagesFromHybrid": 1},
            },
        }


class GBrainConfigTests(unittest.TestCase):
    def _env_for_root(self, root: Path, **extra):
        env = {
            "GBRAIN_ENABLED": "false",
            "GBRAIN_BASE_URL": "",
            "GBRAIN_HOME": str(root),
            "GBRAIN_COMPANY_SOURCE_ID": "company-wiki",
            "GBRAIN_COMPANY_RAW_PATH": str(root / "raw"),
            "GBRAIN_COMPANY_DERIVED_PATH": str(root / "derived"),
            "GBRAIN_COMPANY_MANIFESTS_PATH": str(root / "manifests"),
            "GBRAIN_PREPROCESSED_ROOT": str(root / "_preprocessed"),
            "GBRAIN_LOCAL_GIT_ENABLED": "false",
        }
        for key in ("PATH", "Path", "SystemRoot", "WINDIR"):
            if key in os.environ:
                env[key] = os.environ[key]
        env.update(extra)
        return env

    def test_load_settings_uses_company_wiki_defaults(self):
        with patch.dict(os.environ, {}, clear=True):
            settings = load_gbrain_settings()

        self.assertTrue(settings.enabled)
        self.assertEqual(settings.base_url, "http://127.0.0.1:3131")
        self.assertEqual(settings.company_source_id, "company-wiki")
        self.assertTrue(settings.home_path.as_posix().endswith("workspace_data/_gbrain"))
        self.assertTrue(settings.raw_path.as_posix().endswith("workspace_data/global/company-wiki/raw"))
        self.assertTrue(
            settings.derived_path.as_posix().endswith(
                "workspace_data/_preprocessed/company/company-wiki/gbrain-ready"
            )
        )
        self.assertTrue(settings.manifests_path.as_posix().endswith("workspace_data/_gbrain/manifests"))

    def test_ensure_environment_creates_company_wiki_directories(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with patch.dict(os.environ, self._env_for_root(root), clear=True):
                status = ensure_gbrain_environment()

            self.assertTrue(status["ok"])
            self.assertTrue((root / "raw").is_dir())
            self.assertTrue((root / "_preprocessed" / "company" / "company-wiki" / "gbrain-ready").is_dir())
            self.assertTrue((root / "_preprocessed" / "company" / "company-wiki" / "manifests").is_dir())
            self.assertTrue((root / "_preprocessed" / "company" / "company-wiki" / "runs").is_dir())
            self.assertFalse((root / "derived").exists())
            self.assertFalse(status["local_git"]["enabled"])

    def test_ensure_environment_initializes_local_git_when_enabled(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            env = self._env_for_root(root, GBRAIN_LOCAL_GIT_ENABLED="true")
            with patch.dict(os.environ, env, clear=True):
                status = ensure_gbrain_environment()

            self.assertTrue(status["ok"])
            self.assertTrue(status["local_git"]["enabled"])
            self.assertTrue(status["local_git"]["initialized"])
            self.assertTrue((root / "_preprocessed" / "company" / "company-wiki" / "gbrain-ready" / ".git").is_dir())

    def test_health_does_not_expose_service_token(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            env = self._env_for_root(
                root,
                GBRAIN_SERVICE_BEARER_TOKEN="secret-token",
            )
            with patch.dict(os.environ, env, clear=True):
                health = GBrainAdapter().health()

        self.assertFalse(health["enabled"])
        self.assertEqual(health["service"], {"status": "disabled"})
        self.assertNotIn("secret-token", repr(health))

    def test_health_reports_unreachable_service(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            env = self._env_for_root(
                root,
                GBRAIN_ENABLED="true",
                GBRAIN_BASE_URL="http://127.0.0.1:3131",
            )
            with patch.dict(os.environ, env, clear=True), patch(
                "core.gbrain._adapter.urllib.request.urlopen",
                side_effect=URLError("connection refused"),
            ):
                health = GBrainAdapter().health()

        self.assertEqual(health["service"]["status"], "unreachable")
        self.assertEqual(health["company_source"]["status"], "auth_required")

    def test_health_reports_reachable_service_mock(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            env = self._env_for_root(
                root,
                GBRAIN_ENABLED="true",
                GBRAIN_BASE_URL="http://127.0.0.1:3131",
            )
            with patch.dict(os.environ, env, clear=True), patch(
                "core.gbrain._adapter.urllib.request.urlopen",
                return_value=FakeHttpResponse('{"status":"ok","engine":"pglite"}'),
            ):
                health = GBrainAdapter().health()

        self.assertEqual(health["service"]["status"], "ok")
        self.assertEqual(health["service"]["body"]["engine"], "pglite")
        self.assertEqual(health["company_source"]["status"], "auth_required")

    def test_health_reports_embedding_disabled_from_local_config(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_dir = root / ".gbrain"
            config_dir.mkdir()
            (config_dir / "config.json").write_text(
                json.dumps(
                    {
                        "engine": "pglite",
                        "schema_pack": "gbrain-base-v2",
                        "embedding_disabled": True,
                    }
                ),
                encoding="utf-8",
            )
            with patch.dict(os.environ, self._env_for_root(root), clear=True):
                health = GBrainAdapter().health()

        embedding = health["local_config"]["embedding"]
        self.assertFalse(embedding["semantic_search_ready"])
        self.assertTrue(embedding["disabled"])
        self.assertEqual(embedding["reason"], "embedding disabled in GBrain config")

    def test_health_reports_missing_embedding_provider_key(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_dir = root / ".gbrain"
            config_dir.mkdir()
            (config_dir / "config.json").write_text(
                json.dumps(
                    {
                        "engine": "pglite",
                        "schema_pack": "gbrain-base-v2",
                        "embedding_model": "zeroentropyai:zembed-1",
                        "embedding_dimensions": 1280,
                    }
                ),
                encoding="utf-8",
            )
            with patch.dict(os.environ, self._env_for_root(root), clear=True):
                health = GBrainAdapter().health()

        embedding = health["local_config"]["embedding"]
        self.assertFalse(embedding["semantic_search_ready"])
        self.assertEqual(embedding["model"], "zeroentropyai:zembed-1")
        self.assertEqual(embedding["dimensions"], 1280)
        self.assertEqual(embedding["provider_env"], "ZEROENTROPY_API_KEY")
        self.assertEqual(embedding["provider_config_key"], "zeroentropy_api_key")
        self.assertFalse(embedding["provider_configured"])
        self.assertEqual(embedding["reason"], "missing ZEROENTROPY_API_KEY")

    def test_health_accepts_embedding_provider_key_from_gbrain_config(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_dir = root / ".gbrain"
            config_dir.mkdir()
            (config_dir / "config.json").write_text(
                json.dumps(
                    {
                        "engine": "pglite",
                        "schema_pack": "gbrain-base-v2",
                        "embedding_model": "zeroentropyai:zembed-1",
                        "embedding_dimensions": 1280,
                        "zeroentropy_api_key": "secret",
                    }
                ),
                encoding="utf-8",
            )
            with patch.dict(os.environ, self._env_for_root(root), clear=True):
                health = GBrainAdapter().health()

        embedding = health["local_config"]["embedding"]
        self.assertTrue(embedding["semantic_search_ready"])
        self.assertTrue(embedding["provider_configured"])
        self.assertNotIn("secret", repr(health))

    def test_health_accepts_local_ollama_embedding_model(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_dir = root / ".gbrain"
            config_dir.mkdir()
            (config_dir / "config.json").write_text(
                json.dumps(
                    {
                        "engine": "pglite",
                        "schema_pack": "gbrain-base-v2",
                        "embedding_model": "ollama:mxbai-embed-large",
                        "embedding_dimensions": 1024,
                    }
                ),
                encoding="utf-8",
            )
            env = self._env_for_root(root, OLLAMA_BASE_URL="http://127.0.0.1:11434/v1")
            with patch.dict(os.environ, env, clear=True), patch(
                "core.gbrain._adapter.urllib.request.urlopen",
                return_value=FakeHttpResponse('{"models":[{"name":"mxbai-embed-large:latest"}]}'),
            ):
                health = GBrainAdapter().health()

        embedding = health["local_config"]["embedding"]
        self.assertTrue(embedding["semantic_search_ready"])
        self.assertEqual(embedding["model"], "ollama:mxbai-embed-large")
        self.assertEqual(embedding["dimensions"], 1024)
        self.assertEqual(embedding["provider"], "ollama")
        self.assertTrue(embedding["provider_configured"])
        self.assertIsNone(embedding["reason"])

    def test_health_reports_missing_local_ollama_embedding_model(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_dir = root / ".gbrain"
            config_dir.mkdir()
            (config_dir / "config.json").write_text(
                json.dumps(
                    {
                        "engine": "pglite",
                        "schema_pack": "gbrain-base-v2",
                        "embedding_model": "ollama:mxbai-embed-large",
                        "embedding_dimensions": 1024,
                    }
                ),
                encoding="utf-8",
            )
            with patch.dict(os.environ, self._env_for_root(root), clear=True), patch(
                "core.gbrain._adapter.urllib.request.urlopen",
                return_value=FakeHttpResponse('{"models":[]}'),
            ):
                health = GBrainAdapter().health()

        embedding = health["local_config"]["embedding"]
        self.assertFalse(embedding["semantic_search_ready"])
        self.assertFalse(embedding["provider_configured"])
        self.assertEqual(embedding["reason"], "ollama service or embedding model is not available")

    def test_list_sources_reads_mcp_sse_payload(self):
        payload = {
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": '{"sources":[{"id":"company-wiki","page_count":0}]}',
                    }
                ]
            },
            "jsonrpc": "2.0",
            "id": 1,
        }
        sse = f"event: message\ndata: {json.dumps(payload)}\n\n"
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            env = self._env_for_root(
                root,
                GBRAIN_ENABLED="true",
                GBRAIN_BASE_URL="http://127.0.0.1:3131",
                GBRAIN_SERVICE_BEARER_TOKEN="service-token",
            )
            with patch.dict(os.environ, env, clear=True), patch(
                "core.gbrain._adapter.urllib.request.urlopen",
                return_value=FakeHttpResponse(sse),
            ):
                sources = GBrainAdapter().list_sources()

        self.assertEqual(sources["status"], "ok")
        self.assertEqual(sources["sources"][0]["id"], "company-wiki")

    def test_company_source_status_reads_mcp_sse_payload(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            derived_path = root / "_preprocessed" / "company" / "company-wiki" / "gbrain-ready"
            source_payload = {
                "id": "company-wiki",
                "name": "Project_R Company Wiki",
                "local_path": str(derived_path.resolve()),
                "federated": True,
                "page_count": 0,
                "clone_state": "corrupted",
            }
            payload = {
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(source_payload),
                        }
                    ]
                },
                "jsonrpc": "2.0",
                "id": 1,
            }
            sse = f"event: message\ndata: {json.dumps(payload)}\n\n"
            env = self._env_for_root(
                root,
                GBRAIN_ENABLED="true",
                GBRAIN_BASE_URL="http://127.0.0.1:3131",
                GBRAIN_SERVICE_BEARER_TOKEN="service-token",
            )
            with patch.dict(os.environ, env, clear=True), patch(
                "core.gbrain._adapter.urllib.request.urlopen",
                return_value=FakeHttpResponse(sse),
            ):
                status = GBrainAdapter().company_source_status()

        self.assertEqual(status["status"], "registered")
        self.assertTrue(status["registered"])
        self.assertTrue(status["path_matches"])
        self.assertEqual(status["source"]["clone_state"], "corrupted")

    def test_query_scopes_to_company_source(self):
        payload = {
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": '[{"slug":"rules/vmu流程","source_id":"company-wiki"}]',
                    }
                ]
            },
            "jsonrpc": "2.0",
            "id": 1,
        }
        sse = f"event: message\ndata: {json.dumps(payload)}\n\n"
        captured = {}

        def fake_urlopen(request, timeout):
            captured["body"] = json.loads(request.data.decode("utf-8"))
            return FakeHttpResponse(sse)

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            env = self._env_for_root(
                root,
                GBRAIN_ENABLED="true",
                GBRAIN_BASE_URL="http://127.0.0.1:3131",
                GBRAIN_SERVICE_BEARER_TOKEN="service-token",
            )
            with patch.dict(os.environ, env, clear=True), patch(
                "core.gbrain._adapter.urllib.request.urlopen",
                side_effect=fake_urlopen,
            ):
                result = GBrainAdapter().query("VMU")

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["result"][0]["source_id"], "company-wiki")
        arguments = captured["body"]["params"]["arguments"]
        self.assertEqual(arguments["query"], "VMU")
        self.assertEqual(arguments["source_id"], "company-wiki")
        self.assertFalse(arguments["expand"])

    def test_company_query_expands_chinese_terms_when_keyword_only_search_misses(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            adapter = FakeGBrainQueryAdapter("safety glass")
            env = self._env_for_root(Path(temp_dir))
            with patch.dict(os.environ, env, clear=True):
                sources = KnowledgeSources(gbrain_factory=lambda: adapter).search_company_sources("安全玻璃有哪些要求")

        self.assertEqual(len(adapter.queries), 2)
        self.assertEqual(adapter.queries[0], "安全玻璃有哪些要求")
        self.assertEqual(adapter.queries[1], "safety glass human impact AS 1288")
        self.assertEqual(sources[0]["file"], "gbrain:company-wiki/standards/as-1288")

    def test_company_query_expansion_can_be_disabled(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            adapter = FakeGBrainQueryAdapter("safety glass")
            env = self._env_for_root(Path(temp_dir), GBRAIN_COMPANY_QUERY_EXPANSION_ENABLED="false")
            with patch.dict(os.environ, env, clear=True):
                sources = KnowledgeSources(gbrain_factory=lambda: adapter).search_company_sources("安全玻璃有哪些要求")

        self.assertEqual(adapter.queries, ["安全玻璃有哪些要求"])
        self.assertEqual(sources, [])

    def test_think_refuses_when_source_scope_is_not_verified(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            env = self._env_for_root(
                root,
                GBRAIN_ENABLED="true",
                GBRAIN_BASE_URL="http://127.0.0.1:3131",
                GBRAIN_THINK_ENABLED="true",
                GBRAIN_THINK_OAUTH_CLIENT_ID="project-r-company-think",
                GBRAIN_THINK_OAUTH_CLIENT_SECRET="secret",
            )
            with patch.dict(os.environ, env, clear=True):
                adapter = GBrainAdapter()

        result = adapter.think("hello")

        self.assertEqual(result["status"], "source_scope_unverified")
        self.assertEqual(result["source_id"], "company-wiki")

    def test_think_uses_oauth_client_credentials_and_mcp_think(self):
        think_payload = {
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(
                            {
                                "answer": "Use written approval.",
                                "citations": [{"page_slug": "rules/written-rule", "row_num": None}],
                                "gaps": ["No owner found."],
                                "warnings": [],
                                "modelUsed": "claude-sonnet",
                            }
                        ),
                    }
                ]
            },
            "jsonrpc": "2.0",
            "id": 1,
        }
        sse = f"event: message\ndata: {json.dumps(think_payload)}\n\n"
        captured = {}

        def fake_urlopen(request, timeout):
            if request.full_url.endswith("/token"):
                captured["token_body"] = request.data.decode("utf-8")
                return FakeHttpResponse('{"access_token":"oauth-token","expires_in":3600,"token_type":"Bearer"}')
            captured["mcp_authorization"] = request.get_header("Authorization")
            captured["mcp_body"] = json.loads(request.data.decode("utf-8"))
            return FakeHttpResponse(sse)

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            env = self._env_for_root(
                root,
                GBRAIN_ENABLED="true",
                GBRAIN_BASE_URL="http://127.0.0.1:3131",
                GBRAIN_THINK_ENABLED="true",
                GBRAIN_THINK_SOURCE_SCOPE_VERIFIED="true",
                GBRAIN_THINK_ALLOWED_SOURCES="company-wiki",
                GBRAIN_THINK_OAUTH_CLIENT_ID="project-r-company-think",
                GBRAIN_THINK_OAUTH_CLIENT_SECRET="secret",
                GBRAIN_THINK_ROUNDS="2",
            )
            with patch.dict(os.environ, env, clear=True), patch(
                "core.gbrain._adapter.urllib.request.urlopen",
                side_effect=fake_urlopen,
            ):
                result = GBrainAdapter().think("书面化原则是什么")

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["source_id"], "company-wiki")
        self.assertIn("grant_type=client_credentials", captured["token_body"])
        self.assertIn("client_id=project-r-company-think", captured["token_body"])
        self.assertIn("client_secret=secret", captured["token_body"])
        self.assertEqual(captured["mcp_authorization"], "Bearer oauth-token")
        self.assertEqual(captured["mcp_body"]["params"]["name"], "think")
        arguments = captured["mcp_body"]["params"]["arguments"]
        self.assertEqual(arguments["question"], "书面化原则是什么")
        self.assertEqual(arguments["rounds"], 2)
        self.assertNotIn("source_id", arguments)
        self.assertEqual(result["result"]["answer"], "Use written approval.")

    def test_think_uses_project_source_client_manifest_without_env_allowlist(self):
        think_payload = {
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(
                            {
                                "answer": "Use this project's approved record.",
                                "citations": [{"page_slug": "meetings/kickoff", "row_num": None}],
                                "gaps": [],
                                "warnings": [],
                                "modelUsed": "deepseek",
                            }
                        ),
                    }
                ]
            },
            "jsonrpc": "2.0",
            "id": 1,
        }
        sse = f"event: message\ndata: {json.dumps(think_payload)}\n\n"
        captured = {}

        def fake_urlopen(request, timeout):
            if request.full_url.endswith("/token"):
                captured["token_body"] = request.data.decode("utf-8")
                return FakeHttpResponse('{"access_token":"project-token","expires_in":3600,"token_type":"Bearer"}')
            captured["mcp_authorization"] = request.get_header("Authorization")
            captured["mcp_body"] = json.loads(request.data.decode("utf-8"))
            return FakeHttpResponse(sse)

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project_source_id = "project-bfi-7"
            manifests = root / "manifests"
            manifests.mkdir(parents=True)
            (manifests / "gbrain-think-source-clients.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "clients": {
                            project_source_id: {
                                "source_id": project_source_id,
                                "name": "project-r-think-project-bfi-7",
                                "client_id": "project-think-client",
                                "client_secret": "project-secret",
                                "scope": "read write",
                                "token_auth_method": "client_secret_post",
                                "allowed_sources": [project_source_id],
                                "created_at": "2026-06-01T00:00:00+00:00",
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            env = self._env_for_root(
                root,
                GBRAIN_ENABLED="true",
                GBRAIN_BASE_URL="http://127.0.0.1:3131",
                GBRAIN_THINK_ENABLED="true",
                GBRAIN_THINK_SOURCE_SCOPE_VERIFIED="true",
                GBRAIN_THINK_ALLOWED_SOURCES="company-wiki",
            )
            with patch.dict(os.environ, env, clear=True), patch(
                "core.gbrain._adapter.urllib.request.urlopen",
                side_effect=fake_urlopen,
            ):
                result = GBrainAdapter().think("项目启动会结论是什么", source_id=project_source_id)

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["source_id"], project_source_id)
        self.assertIn("client_id=project-think-client", captured["token_body"])
        self.assertIn("client_secret=project-secret", captured["token_body"])
        self.assertEqual(captured["mcp_authorization"], "Bearer project-token")
        self.assertEqual(captured["mcp_body"]["params"]["name"], "think")
        self.assertNotIn("source_id", captured["mcp_body"]["params"]["arguments"])
        self.assertEqual(result["source_scope"]["allowed_sources"], [project_source_id])
        self.assertEqual(result["source_scope"]["credential_source"], "manifest")

    def test_schema_context_uses_token_bound_source_client(self):
        captured_tools: list[dict] = []

        def fake_urlopen(request, timeout):
            if request.full_url.endswith("/token"):
                return FakeHttpResponse('{"access_token":"customer-token","expires_in":3600,"token_type":"Bearer"}')
            captured_tools.append(
                {
                    "authorization": request.get_header("Authorization"),
                    "body": json.loads(request.data.decode("utf-8")),
                }
            )
            tool_name = captured_tools[-1]["body"]["params"]["name"]
            result_by_tool = {
                "get_active_schema_pack": {"pack_name": "gbrain-base-v2"},
                "schema_stats": {"per_source": [{"source_id": "customer-crm", "total_pages": 3}]},
                "schema_graph": {"nodes": [], "edges": []},
                "schema_review_orphans": {"orphan_count": 0, "orphans": []},
            }
            payload = {
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(result_by_tool[tool_name]),
                        }
                    ]
                },
                "jsonrpc": "2.0",
                "id": 1,
            }
            return FakeHttpResponse(f"event: message\ndata: {json.dumps(payload)}\n\n")

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_id = "customer-crm"
            manifests = root / "manifests"
            manifests.mkdir(parents=True)
            (manifests / "gbrain-think-source-clients.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "clients": {
                            source_id: {
                                "source_id": source_id,
                                "name": "project-r-think-customer-crm",
                                "client_id": "customer-client",
                                "client_secret": "customer-secret",
                                "scope": "read write",
                                "token_auth_method": "client_secret_post",
                                "allowed_sources": [source_id],
                                "created_at": "2026-06-08T00:00:00+00:00",
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            env = self._env_for_root(
                root,
                GBRAIN_ENABLED="true",
                GBRAIN_BASE_URL="http://127.0.0.1:3131",
                GBRAIN_THINK_ENABLED="true",
                GBRAIN_THINK_SOURCE_SCOPE_VERIFIED="true",
                GBRAIN_THINK_ALLOWED_SOURCES="company-wiki",
            )
            with patch.dict(os.environ, env, clear=True), patch(
                "core.gbrain._adapter.urllib.request.urlopen",
                side_effect=fake_urlopen,
            ):
                result = GBrainAdapter().schema_context(source_id=source_id, orphan_limit=5)

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["source_id"], source_id)
        self.assertEqual(result["source_scope"]["allowed_sources"], [source_id])
        self.assertEqual([item["body"]["params"]["name"] for item in captured_tools], [
            "get_active_schema_pack",
            "schema_stats",
            "schema_graph",
            "schema_review_orphans",
        ])
        for item in captured_tools:
            self.assertEqual(item["authorization"], "Bearer customer-token")
            self.assertNotIn("source_id", item["body"]["params"]["arguments"])

    def test_ensure_project_think_client_registers_and_persists_manifest(self):
        stdout = (
            'OAuth client registered: "project-r-think-project-bfi-7"\n'
            "  Client ID:           generated-client\n"
            "  Client Secret:       generated-secret\n"
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            cli_root = root / "gbrain"
            (cli_root / "src" / "commands").mkdir(parents=True)
            (cli_root / "src" / "commands" / "auth.ts").write_text("// fake", encoding="utf-8")
            env = self._env_for_root(
                root,
                GBRAIN_ENABLED="true",
                GBRAIN_CLI_WORKDIR=str(cli_root),
                GBRAIN_THINK_ENABLED="true",
                GBRAIN_THINK_SOURCE_SCOPE_VERIFIED="true",
            )
            with patch.dict(os.environ, env, clear=True):
                adapter = GBrainAdapter()
                with patch.object(
                    adapter,
                    "_run_cli_exclusive",
                    return_value={
                        "status": "ok",
                        "result": {"stdout": stdout, "stderr": ""},
                        "service_restart": {"reason": "register_think_source_client"},
                    },
                ) as run_cli:
                    result = adapter.ensure_think_source_client("project-bfi-7")

            manifest = json.loads((root / "manifests" / "gbrain-think-source-clients.json").read_text(encoding="utf-8"))

        self.assertTrue(result["ok"])
        self.assertEqual(result["client_id"], "generated-client")
        self.assertEqual(result["client_secret"], "generated-secret")
        self.assertEqual(manifest["clients"]["project-bfi-7"]["client_id"], "generated-client")
        self.assertEqual(manifest["clients"]["project-bfi-7"]["client_secret"], "generated-secret")
        args = run_cli.call_args.args[0]
        self.assertIn("register-client", args)
        self.assertIn("--federated-read", args)
        self.assertIn("project-bfi-7", args)

    def test_ensure_project_think_client_replaces_stale_manifest_client(self):
        stdout = (
            'OAuth client registered: "project-r-think-project-test-6"\n'
            "  Client ID:           refreshed-client\n"
            "  Client Secret:       refreshed-secret\n"
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "manifests").mkdir(parents=True)
            (root / "manifests" / "gbrain-think-source-clients.json").write_text(
                json.dumps(
                    {
                        "clients": {
                            "project-test-6": {
                                "source_id": "project-test-6",
                                "name": "old-client",
                                "client_id": "stale-client",
                                "client_secret": "stale-secret",
                                "scope": "read write",
                                "token_auth_method": "client_secret_post",
                                "allowed_sources": ["project-test-6"],
                                "created_at": "2026-06-01T00:00:00+00:00",
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            cli_root = root / "gbrain"
            (cli_root / "src" / "commands").mkdir(parents=True)
            (cli_root / "src" / "commands" / "auth.ts").write_text("// fake", encoding="utf-8")
            env = self._env_for_root(
                root,
                GBRAIN_ENABLED="true",
                GBRAIN_CLI_WORKDIR=str(cli_root),
                GBRAIN_THINK_ENABLED="true",
                GBRAIN_THINK_SOURCE_SCOPE_VERIFIED="true",
            )
            with patch.dict(os.environ, env, clear=True):
                adapter = GBrainAdapter()
                with patch.object(
                    adapter,
                    "_fetch_oauth_token",
                    return_value={
                        "status": "token_request_failed",
                        "http_status": 400,
                        "error": '{"error":"invalid_grant","error_description":"Client not found"}',
                    },
                ), patch.object(
                    adapter,
                    "_run_cli_exclusive",
                    return_value={"status": "ok", "result": {"stdout": stdout, "stderr": ""}},
                ) as run_cli:
                    result = adapter.ensure_think_source_client("project-test-6")

            manifest = json.loads((root / "manifests" / "gbrain-think-source-clients.json").read_text(encoding="utf-8"))

        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "registered")
        self.assertEqual(result["client_id"], "refreshed-client")
        self.assertEqual(result["client_secret"], "refreshed-secret")
        self.assertEqual(manifest["clients"]["project-test-6"]["client_id"], "refreshed-client")
        self.assertEqual(manifest["clients"]["project-test-6"]["client_secret"], "refreshed-secret")
        args = run_cli.call_args.args[0]
        self.assertIn("register-client", args)

    def test_citation_fixer_uses_agent_oauth_and_submit_agent(self):
        agent_payload = {
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps({"id": 88, "name": "subagent", "client_id": "project-r-agent"}),
                    }
                ]
            },
            "jsonrpc": "2.0",
            "id": 1,
        }
        sse = f"event: message\ndata: {json.dumps(agent_payload)}\n\n"
        captured = {}

        def fake_urlopen(request, timeout):
            if request.full_url.endswith("/token"):
                captured["token_body"] = request.data.decode("utf-8")
                return FakeHttpResponse('{"access_token":"agent-token","expires_in":3600,"token_type":"Bearer"}')
            captured["mcp_authorization"] = request.get_header("Authorization")
            captured["mcp_body"] = json.loads(request.data.decode("utf-8"))
            return FakeHttpResponse(sse)

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            env = self._env_for_root(
                root,
                GBRAIN_ENABLED="true",
                GBRAIN_BASE_URL="http://127.0.0.1:3131",
                GBRAIN_AGENT_ENABLED="true",
                GBRAIN_AGENT_OAUTH_CLIENT_ID="project-r-agent",
                GBRAIN_AGENT_OAUTH_CLIENT_SECRET="secret",
                GBRAIN_AGENT_MODEL="deepseek:deepseek-chat",
            )
            with patch.dict(os.environ, env, clear=True), patch(
                "core.gbrain._adapter.urllib.request.urlopen",
                side_effect=fake_urlopen,
            ):
                result = GBrainAdapter().submit_citation_fixer(
                    page_slug="rules/written-principle",
                    review_id=7,
                    allowed_slug_prefixes=["rules/"],
                )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["result"]["id"], 88)
        self.assertIn("scope=agent", captured["token_body"])
        self.assertIn("client_id=project-r-agent", captured["token_body"])
        self.assertEqual(captured["mcp_authorization"], "Bearer agent-token")
        self.assertEqual(captured["mcp_body"]["params"]["name"], "submit_agent")
        arguments = captured["mcp_body"]["params"]["arguments"]
        self.assertEqual(arguments["model"], "deepseek:deepseek-chat")
        self.assertEqual(arguments["allowed_tools"], ["search", "get_page", "put_page", "list_pages"])
        self.assertEqual(arguments["allowed_slug_prefixes"], ["rules/"])
        self.assertIn("citation-fixer", arguments["prompt"])
        self.assertIn("rules/written-principle", arguments["prompt"])
        self.assertIn("KnowledgeReview id: 7", arguments["prompt"])

    def test_get_page_calls_gbrain_mcp_get_page(self):
        captured = {}

        def fake_urlopen(request, timeout=0):
            del timeout
            captured["body"] = json.loads(request.data.decode("utf-8"))
            return FakeHttpResponse(json.dumps({"result": {"content": "ok"}}))

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            env = self._env_for_root(
                root,
                GBRAIN_ENABLED="true",
                GBRAIN_BASE_URL="http://127.0.0.1:3131",
                GBRAIN_SERVICE_BEARER_TOKEN="service-token",
            )
            with patch.dict(os.environ, env, clear=True), patch(
                "core.gbrain._adapter.urllib.request.urlopen",
                side_effect=fake_urlopen,
            ):
                result = GBrainAdapter().get_page("reviews/citation-fixer-smoke/project-r-citation-fixer-smoke")

        self.assertEqual(result["status"], "ok")
        self.assertEqual(captured["body"]["params"]["name"], "get_page")
        self.assertEqual(
            captured["body"]["params"]["arguments"]["slug"],
            "reviews/citation-fixer-smoke/project-r-citation-fixer-smoke",
        )

    def test_citation_fixer_refuses_until_agent_oauth_is_enabled(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            env = self._env_for_root(
                root,
                GBRAIN_ENABLED="true",
                GBRAIN_BASE_URL="http://127.0.0.1:3131",
            )
            with patch.dict(os.environ, env, clear=True):
                result = GBrainAdapter().submit_citation_fixer(page_slug="rules/written-principle")

        self.assertEqual(result["status"], "disabled")
        self.assertEqual(result["error"], "GBRAIN_AGENT_ENABLED is not true")

    def test_agent_status_reports_non_sensitive_readiness(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            env = self._env_for_root(
                root,
                GBRAIN_AGENT_ENABLED="true",
                GBRAIN_AGENT_OAUTH_CLIENT_ID="project-r-agent",
                GBRAIN_AGENT_OAUTH_CLIENT_SECRET="secret",
                GBRAIN_AGENT_MODEL="deepseek:deepseek-chat",
                GBRAIN_CITATION_FIXER_TOOLS="search,get_page,put_page,list_pages",
            )
            with patch.dict(os.environ, env, clear=True):
                status = GBrainAdapter().agent_status()

        self.assertEqual(status["status"], "configured_unverified")
        self.assertTrue(status["enabled"])
        self.assertTrue(status["oauth_configured"])
        self.assertTrue(status["client_configured"])
        self.assertFalse(status["binding_submit_verified"])
        self.assertFalse(status["inline_execution_verified"])
        self.assertFalse(status["execution_verified"])
        self.assertFalse(status["execution_ready"])
        self.assertEqual(status["binding_status"], "not_verified")
        self.assertEqual(status["citation_fixer_tools"], ["search", "get_page", "put_page", "list_pages"])
        self.assertNotIn("secret", repr(status))

    def test_agent_status_requires_explicit_execution_verification_before_ready(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            env = self._env_for_root(
                root,
                GBRAIN_AGENT_ENABLED="true",
                GBRAIN_AGENT_OAUTH_CLIENT_ID="project-r-agent",
                GBRAIN_AGENT_OAUTH_CLIENT_SECRET="secret",
                GBRAIN_AGENT_EXECUTION_VERIFIED="true",
            )
            config_dir = root / ".gbrain"
            config_dir.mkdir(parents=True)
            (config_dir / "config.json").write_text('{"engine":"pglite"}', encoding="utf-8")
            with patch.dict(os.environ, env, clear=True):
                status = GBrainAdapter().agent_status()

        self.assertEqual(status["status"], "ready")
        self.assertTrue(status["execution_ready"])
        self.assertEqual(status["binding_status"], "execution_verified")
        self.assertEqual(status["worker"]["engine"], "pglite")
        self.assertFalse(status["worker"]["persistent_worker_supported"])

    def test_agent_status_reports_submit_verified_before_execution_ready(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            env = self._env_for_root(
                root,
                GBRAIN_AGENT_ENABLED="true",
                GBRAIN_AGENT_OAUTH_CLIENT_ID="project-r-agent",
                GBRAIN_AGENT_OAUTH_CLIENT_SECRET="secret",
                GBRAIN_AGENT_BINDING_SUBMIT_VERIFIED="true",
            )
            with patch.dict(os.environ, env, clear=True):
                status = GBrainAdapter().agent_status()

        self.assertEqual(status["status"], "configured_unverified")
        self.assertTrue(status["binding_submit_verified"])
        self.assertFalse(status["inline_execution_verified"])
        self.assertFalse(status["execution_verified"])
        self.assertEqual(status["binding_status"], "submit_verified")

    def test_agent_status_reports_inline_execution_verified_before_full_ready(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            env = self._env_for_root(
                root,
                GBRAIN_AGENT_ENABLED="true",
                GBRAIN_AGENT_OAUTH_CLIENT_ID="project-r-agent",
                GBRAIN_AGENT_OAUTH_CLIENT_SECRET="secret",
                GBRAIN_AGENT_BINDING_SUBMIT_VERIFIED="true",
                GBRAIN_AGENT_INLINE_EXECUTION_VERIFIED="true",
            )
            with patch.dict(os.environ, env, clear=True):
                status = GBrainAdapter().agent_status()

        self.assertEqual(status["status"], "configured_unverified")
        self.assertTrue(status["binding_submit_verified"])
        self.assertTrue(status["inline_execution_verified"])
        self.assertFalse(status["execution_verified"])
        self.assertEqual(status["binding_status"], "inline_execution_verified")

    def test_knowledge_sources_normalizes_think_citations_and_gaps(self):
        result = KnowledgeSources(gbrain_factory=FakeGBrainThinkAdapter).think(None, "用车申请怎么做")

        self.assertTrue(result["ok"])
        self.assertEqual(result["model"], "gbrain-think-test")
        self.assertIn("来源 1", result["reply"])
        self.assertEqual(result["sources"][0]["file"], "gbrain:company-wiki/rules/用车申请")
        self.assertEqual(result["sources"][1]["source_title"], "GBrain 缺口分析 / Gap Analysis")

    def test_sync_source_calls_gbrain_mcp_sync_brain_for_derived_repo(self):
        payload = {
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": '{"status":"synced","chunksCreated":3}',
                    }
                ]
            },
            "jsonrpc": "2.0",
            "id": 1,
        }
        sse = f"event: message\ndata: {json.dumps(payload)}\n\n"
        captured = {}

        def fake_urlopen(request, timeout):
            captured["body"] = json.loads(request.data.decode("utf-8"))
            return FakeHttpResponse(sse)

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            env = self._env_for_root(
                root,
                GBRAIN_ENABLED="true",
                GBRAIN_BASE_URL="http://127.0.0.1:3131",
                GBRAIN_SERVICE_BEARER_TOKEN="service-token",
            )
            with patch.dict(os.environ, env, clear=True), patch(
                "core.gbrain._adapter.urllib.request.urlopen",
                side_effect=fake_urlopen,
            ):
                result = GBrainAdapter().sync_source()

        self.assertEqual(result["status"], "ok")
        body = captured["body"]
        self.assertEqual(body["params"]["name"], "sync_brain")
        arguments = body["params"]["arguments"]
        self.assertEqual(
            arguments["repo"],
            str((root / "_preprocessed" / "company" / "company-wiki" / "gbrain-ready").resolve()),
        )
        self.assertTrue(arguments["no_pull"])
        self.assertFalse(arguments["no_embed"])

    def test_sync_source_falls_back_to_local_cli_when_http_hides_local_only_tool(self):
        payload = {
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": '{"error":"unknown_operation","message":"Unknown: sync_brain"}',
                    }
                ]
            },
            "jsonrpc": "2.0",
            "id": 1,
        }
        sse = f"event: message\ndata: {json.dumps(payload)}\n\n"
        captured = {}

        def fake_run(args, **kwargs):
            captured["args"] = args
            captured["cwd"] = kwargs.get("cwd")
            captured["env"] = kwargs.get("env")
            return subprocess.CompletedProcess(args, 0, stdout="Already up to date.", stderr="")

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            cli = root / "gbrain-cli"
            (cli / "src").mkdir(parents=True)
            (cli / "src" / "cli.ts").write_text("cli", encoding="utf-8")
            env = self._env_for_root(
                root,
                GBRAIN_ENABLED="true",
                GBRAIN_BASE_URL="http://127.0.0.1:3131",
                GBRAIN_SERVICE_BEARER_TOKEN="service-token",
                GBRAIN_CLI_WORKDIR=str(cli),
            )
            with (
                patch.dict(os.environ, env, clear=True),
                patch("core.gbrain._adapter.urllib.request.urlopen", return_value=FakeHttpResponse(sse)),
                patch("core.gbrain._adapter.subprocess.run", side_effect=fake_run),
            ):
                result = GBrainAdapter().sync_source()

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["method"], "cli")
        self.assertEqual(captured["args"][:5], ["bun", "src/cli.ts", "sync", "--source", "company-wiki"])
        self.assertIn("--no-pull", captured["args"])
        self.assertEqual(captured["cwd"], cli)
        self.assertEqual(captured["env"]["GBRAIN_HOME"], str(root.resolve()))


if __name__ == "__main__":
    unittest.main()
