import json
import os
import unittest
from unittest.mock import patch

from app.shared.web_search import service


class TavilyWebSearchTests(unittest.TestCase):
    def setUp(self):
        service._TAVILY_KEY_CURSOR = 0

    def test_tavily_json_results_are_parsed(self):
        captured = {}

        def fake_request(url, *, method="GET", payload=None, headers=None):
            captured["url"] = url
            captured["method"] = method
            captured["payload"] = payload
            captured["headers"] = headers
            return json.dumps(
                {
                    "results": [
                        {
                            "title": "Result One",
                            "url": "https://example.com/one",
                            "content": "First summary",
                        },
                        {
                            "title": "Duplicate",
                            "url": "https://example.com/one",
                            "content": "Duplicate summary",
                        },
                        {
                            "title": "Result Two",
                            "url": "https://example.com/two",
                            "content": "Second summary",
                        },
                    ]
                }
            ).encode("utf-8")

        with patch.dict(
            os.environ,
            {
                "WEB_SEARCH_PROVIDER": "tavily",
                "TAVILY_API_KEYS": "tvly-key-a,tvly-key-b",
                "TAVILY_MAX_RESULTS": "5",
            },
            clear=True,
        ), patch.object(service, "_request_bytes", side_effect=fake_request):
            response = service.search_web("latest project r", max_results=3)

        self.assertEqual(response.provider, "tavily")
        self.assertEqual(len(response.results), 2)
        self.assertEqual(response.results[0].title, "Result One")
        self.assertEqual(response.results[0].provider, "tavily")
        self.assertEqual(captured["url"], "https://api.tavily.com/search")
        self.assertEqual(captured["method"], "POST")
        self.assertEqual(captured["payload"]["query"], "latest project r")
        self.assertEqual(captured["payload"]["search_depth"], "basic")
        self.assertEqual(captured["payload"]["max_results"], 5)
        self.assertFalse(captured["payload"]["include_answer"])
        self.assertFalse(captured["payload"]["include_raw_content"])
        self.assertEqual(captured["headers"]["authorization"], "Bearer tvly-key-a")

    def test_tavily_missing_key_returns_warning(self):
        with patch.dict(os.environ, {"WEB_SEARCH_PROVIDER": "tavily"}, clear=True):
            response = service.search_web("hello")

        self.assertEqual(response.provider, "tavily")
        self.assertEqual(response.results, [])
        self.assertEqual(response.warnings, ["missing_tavily_api_key"])

    def test_tavily_numbered_keys_rotate(self):
        authorizations = []

        def fake_request(url, *, method="GET", payload=None, headers=None):
            authorizations.append(headers["authorization"])
            return json.dumps(
                {
                    "results": [
                        {
                            "title": "Result",
                            "url": f"https://example.com/{len(authorizations)}",
                            "content": "Summary",
                        }
                    ]
                }
            ).encode("utf-8")

        with patch.dict(
            os.environ,
            {
                "WEB_SEARCH_PROVIDER": "tavily",
                "TAVILY_API_KEY_1": "tvly-key-1",
                "TAVILY_API_KEY_2": "tvly-key-2",
            },
            clear=True,
        ), patch.object(service, "_request_bytes", side_effect=fake_request):
            service.search_web("first")
            service.search_web("second")
            service.search_web("third")

        self.assertEqual(
            authorizations,
            [
                "Bearer tvly-key-1",
                "Bearer tvly-key-2",
                "Bearer tvly-key-1",
            ],
        )

    def test_tavily_retries_next_key_on_quota_or_rate_limit_error(self):
        authorizations = []

        def fake_request(url, *, method="GET", payload=None, headers=None):
            authorizations.append(headers["authorization"])
            if len(authorizations) == 1:
                raise service.WebSearchError("http_429:quota exhausted")
            return json.dumps(
                {
                    "results": [
                        {
                            "title": "Fallback Key Result",
                            "url": "https://example.com/fallback-key",
                            "content": "Summary",
                        }
                    ]
                }
            ).encode("utf-8")

        with patch.dict(
            os.environ,
            {
                "WEB_SEARCH_PROVIDER": "tavily",
                "TAVILY_API_KEY_1": "tvly-key-1",
                "TAVILY_API_KEY_2": "tvly-key-2",
            },
            clear=True,
        ), patch.object(service, "_request_bytes", side_effect=fake_request):
            response = service.search_web("quota test")

        self.assertEqual(
            authorizations,
            [
                "Bearer tvly-key-1",
                "Bearer tvly-key-2",
            ],
        )
        self.assertEqual(len(response.results), 1)
        self.assertEqual(response.results[0].title, "Fallback Key Result")

    def test_web_search_prompt_includes_current_date(self):
        response = service.WebSearchResponse(
            query="最近三天广州天气",
            provider="tavily",
            results=[
                service.WebSearchResult(
                    title="Weather Result",
                    url="https://example.com/weather",
                    snippet="Weather summary",
                    rank=1,
                    provider="tavily",
                )
            ],
        )

        with patch.object(service, "project_r_current_date", return_value="2026-06-18"):
            prompt = service.format_web_search_prompt(response)

        self.assertIn("当前日期：2026-06-18（Asia/Shanghai）", prompt)
        self.assertIn("搜索问题：最近三天广州天气", prompt)


if __name__ == "__main__":
    unittest.main()
