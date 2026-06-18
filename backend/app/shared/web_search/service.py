from __future__ import annotations

from dataclasses import dataclass, field
from html import unescape
from html.parser import HTMLParser
import json
import os
import re
import socket
import threading
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote_plus, unquote, urlencode, urlparse
from urllib.request import Request, urlopen

from app.shared.runtime_context import PROJECT_R_TIMEZONE_NAME, project_r_current_date


DEFAULT_MAX_RESULTS = 5
DEFAULT_TIMEOUT_SECONDS = 8.0
WEB_SEARCH_SKILL_NAME = "web-search-content"
_TAVILY_KEY_LOCK = threading.Lock()
_TAVILY_KEY_CURSOR = 0


class WebSearchError(RuntimeError):
    pass


@dataclass(frozen=True)
class WebSearchResult:
    title: str
    url: str
    snippet: str
    rank: int
    provider: str


@dataclass(frozen=True)
class WebSearchResponse:
    query: str
    provider: str
    results: list[WebSearchResult] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def search_web(
    query: str,
    *,
    max_results: int = DEFAULT_MAX_RESULTS,
    provider: str | None = None,
) -> WebSearchResponse:
    normalized_query = " ".join(query.split()).strip()
    search_provider = _provider_name(provider)
    if not normalized_query:
        return WebSearchResponse(query="", provider=search_provider, warnings=["empty_query"])

    provider = search_provider
    limit = _result_limit(max_results, provider)
    try:
        if provider == "tavily":
            results = _search_tavily(normalized_query, limit)
        elif provider == "bing":
            results = _search_bing(normalized_query, limit)
        elif provider == "serper":
            results = _search_serper(normalized_query, limit)
        elif provider in {"duckduckgo", "duckduckgo_html", "ddg"}:
            provider = "duckduckgo"
            results = _search_duckduckgo_html(normalized_query, limit)
        else:
            raise WebSearchError(f"unsupported_provider:{provider}")
    except WebSearchError as exc:
        return WebSearchResponse(query=normalized_query, provider=provider, warnings=[str(exc)])

    return WebSearchResponse(query=normalized_query, provider=provider, results=results[:limit])


def web_results_to_sources(response: WebSearchResponse) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    for result in response.results:
        sources.append(
            {
                "file": result.url,
                "source_title": result.title,
                "section_path": f"联网搜索 / {response.provider}",
                "content": result.snippet,
                "score": max(0.0, 1.0 - ((result.rank - 1) * 0.08)),
                "source_file": result.url,
                "derived_file": None,
                "source_line": None,
                "source_page": None,
                "source_locator": f"web:{response.provider}:{result.rank}",
            }
        )
    return sources


def format_web_search_prompt(response: WebSearchResponse, *, start_index: int = 1) -> str:
    if response.results:
        snippets = []
        for offset, result in enumerate(response.results):
            source_index = start_index + offset
            snippets.append(
                "\n".join(
                    [
                        f"[来源 {source_index}] {result.title}",
                        f"URL: {result.url}",
                        f"摘要: {result.snippet}",
                    ]
                )
            )
        return (
            "以下是 Project_R 联网搜索 Skill 返回的公开网页摘要。"
            "这些结果可能随时间变化；回答涉及新闻、价格、政策、版本或其他时效信息时，"
            "请优先依据这些网页摘要，并在关键结论后使用对应的 [来源 N] 标注。"
            "如果搜索摘要不足以支撑结论，请明确说明缺口，不要编造网页中没有的信息。\n\n"
            f"当前日期：{project_r_current_date()}（{PROJECT_R_TIMEZONE_NAME}）\n"
            f"搜索问题：{response.query}\n"
            f"搜索 Provider：{response.provider}\n\n"
            + "\n\n".join(snippets)
        )

    warning_text = "；".join(response.warnings) if response.warnings else "未返回可用结果"
    return (
        "本轮用户开启了联网搜索，但 Project_R 联网搜索 Skill 未返回可用网页摘要。"
        f"当前日期：{project_r_current_date()}（{PROJECT_R_TIMEZONE_NAME}）。"
        f"搜索问题：{response.query or '空查询'}。"
        f"搜索 Provider：{response.provider}。"
        f"搜索状态：{warning_text}。"
        "请直接告知用户本轮联网搜索不可用或未命中，再基于已有上下文回答；不要伪造网络来源。"
    )


def _provider_name(provider: str | None = None) -> str:
    return (
        provider
        or os.getenv("WEB_SEARCH_PROVIDER")
        or os.getenv("PROJECT_R_WEB_SEARCH_PROVIDER")
        or "disabled"
    ).strip().lower()


def _result_limit(max_results: int, provider: str) -> int:
    raw_limit: int | str | None = max_results or DEFAULT_MAX_RESULTS
    if provider == "tavily":
        raw_limit = os.getenv("TAVILY_MAX_RESULTS") or raw_limit
    try:
        return max(1, min(int(raw_limit), 10))
    except (TypeError, ValueError):
        return DEFAULT_MAX_RESULTS


def _timeout() -> float:
    raw = os.getenv("WEB_SEARCH_TIMEOUT_SECONDS", "")
    try:
        return max(1.0, min(float(raw), 30.0))
    except (TypeError, ValueError):
        return DEFAULT_TIMEOUT_SECONDS


def _request_bytes(url: str, *, method: str = "GET", payload: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> bytes:
    request_body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request_headers = {
        "user-agent": "Project_R/0.1 web-search-skill",
        "accept": "text/html,application/json",
        **(headers or {}),
    }
    if payload is not None:
        request_headers.setdefault("content-type", "application/json")
    request = Request(url, data=request_body, method=method, headers=request_headers)
    try:
        with urlopen(request, timeout=_timeout()) as response:
            return response.read()
    except HTTPError as exc:
        detail = _read_error_body(exc)
        raise WebSearchError(f"http_{exc.code}:{detail}") from exc
    except (TimeoutError, socket.timeout, URLError) as exc:
        raise WebSearchError(f"network_error:{exc}") from exc


def _search_bing(query: str, limit: int) -> list[WebSearchResult]:
    key = os.getenv("BING_SEARCH_API_KEY") or os.getenv("WEB_SEARCH_API_KEY")
    if not key:
        raise WebSearchError("missing_bing_search_api_key")
    params = urlencode({"q": query, "count": str(limit), "responseFilter": "Webpages"})
    raw = _request_bytes(
        f"https://api.bing.microsoft.com/v7.0/search?{params}",
        headers={"ocp-apim-subscription-key": key, "accept": "application/json"},
    )
    payload = _json_loads(raw)
    items = ((payload.get("webPages") or {}).get("value") or []) if isinstance(payload, dict) else []
    results: list[WebSearchResult] = []
    for index, item in enumerate(items[:limit], start=1):
        if not isinstance(item, dict):
            continue
        title = _clean_text(str(item.get("name") or ""))
        url = str(item.get("url") or "").strip()
        snippet = _clean_text(str(item.get("snippet") or ""))
        if title and url:
            results.append(WebSearchResult(title=title, url=url, snippet=snippet, rank=index, provider="bing"))
    return results


def _search_serper(query: str, limit: int) -> list[WebSearchResult]:
    key = os.getenv("SERPER_API_KEY") or os.getenv("WEB_SEARCH_API_KEY")
    if not key:
        raise WebSearchError("missing_serper_api_key")
    raw = _request_bytes(
        "https://google.serper.dev/search",
        method="POST",
        payload={"q": query, "num": limit},
        headers={"x-api-key": key, "accept": "application/json"},
    )
    payload = _json_loads(raw)
    items = payload.get("organic") or [] if isinstance(payload, dict) else []
    results: list[WebSearchResult] = []
    for index, item in enumerate(items[:limit], start=1):
        if not isinstance(item, dict):
            continue
        title = _clean_text(str(item.get("title") or ""))
        url = str(item.get("link") or "").strip()
        snippet = _clean_text(str(item.get("snippet") or ""))
        if title and url:
            results.append(WebSearchResult(title=title, url=url, snippet=snippet, rank=index, provider="serper"))
    return results


def _search_tavily(query: str, limit: int) -> list[WebSearchResult]:
    keys = _next_tavily_key_rotation()
    if not keys:
        raise WebSearchError("missing_tavily_api_key")
    last_error: WebSearchError | None = None
    for key in keys:
        try:
            return _search_tavily_with_key(query, limit, key)
        except WebSearchError as exc:
            last_error = exc
            if not _is_tavily_key_retryable_error(str(exc)):
                raise
    if last_error:
        raise last_error
    raise WebSearchError("missing_tavily_api_key")


def _search_tavily_with_key(query: str, limit: int, key: str) -> list[WebSearchResult]:
    base_url = (os.getenv("TAVILY_BASE_URL") or "https://api.tavily.com").strip().rstrip("/")
    search_depth = (os.getenv("TAVILY_SEARCH_DEPTH") or "basic").strip().lower()
    if search_depth not in {"basic", "advanced"}:
        search_depth = "basic"
    raw = _request_bytes(
        f"{base_url}/search",
        method="POST",
        payload={
            "query": query,
            "search_depth": search_depth,
            "max_results": limit,
            "include_answer": False,
            "include_raw_content": False,
        },
        headers={
            "authorization": f"Bearer {key}",
            "accept": "application/json",
        },
    )
    payload = _json_loads(raw)
    items = payload.get("results") or [] if isinstance(payload, dict) else []
    results: list[WebSearchResult] = []
    seen_urls: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        title = _clean_text(str(item.get("title") or ""))
        url = str(item.get("url") or "").strip()
        snippet = _clean_text(str(item.get("content") or item.get("snippet") or ""))
        if not title or not url or url in seen_urls:
            continue
        seen_urls.add(url)
        results.append(
            WebSearchResult(
                title=title,
                url=url,
                snippet=snippet,
                rank=len(results) + 1,
                provider="tavily",
            )
        )
        if len(results) >= limit:
            break
    return results


def _next_tavily_key_rotation() -> list[str]:
    keys = _load_tavily_keys()
    if not keys:
        return []
    global _TAVILY_KEY_CURSOR
    with _TAVILY_KEY_LOCK:
        start = _TAVILY_KEY_CURSOR % len(keys)
        _TAVILY_KEY_CURSOR = (_TAVILY_KEY_CURSOR + 1) % len(keys)
    return keys[start:] + keys[:start]


def _load_tavily_keys() -> list[str]:
    raw_keys: list[str] = []
    raw_keys.extend(
        key.strip()
        for key in (os.getenv("TAVILY_API_KEYS") or "").split(",")
        if key.strip()
    )
    single_key = (os.getenv("TAVILY_API_KEY") or os.getenv("WEB_SEARCH_API_KEY") or "").strip()
    if single_key:
        raw_keys.append(single_key)
    numbered_keys: list[tuple[int, str]] = []
    for name, value in os.environ.items():
        match = re.fullmatch(r"TAVILY_API_KEY_(\d+)", name)
        if match and value.strip():
            numbered_keys.append((int(match.group(1)), value.strip()))
    raw_keys.extend(value for _, value in sorted(numbered_keys))
    keys: list[str] = []
    seen: set[str] = set()
    for key in raw_keys:
        if key not in seen:
            keys.append(key)
            seen.add(key)
    return keys


def _is_tavily_key_retryable_error(message: str) -> bool:
    normalized = message.lower()
    if normalized.startswith(("http_401", "http_403", "http_429")):
        return True
    if normalized.startswith(("http_500", "http_502", "http_503", "http_504", "network_error")):
        return True
    quota_markers = ("quota", "credit", "limit", "rate", "exhaust", "insufficient")
    return any(marker in normalized for marker in quota_markers)


def _search_duckduckgo_html(query: str, limit: int) -> list[WebSearchResult]:
    raw = _request_bytes(
        f"https://duckduckgo.com/html/?q={quote_plus(query)}",
        headers={"accept": "text/html"},
    )
    parser = _DuckDuckGoHtmlParser()
    parser.feed(raw.decode("utf-8", errors="ignore"))
    results: list[WebSearchResult] = []
    seen_urls: set[str] = set()
    for item in parser.items:
        url = _normalize_duckduckgo_url(item.get("url", ""))
        title = _clean_text(item.get("title", ""))
        snippet = _clean_text(item.get("snippet", ""))
        if not title or not url or url in seen_urls:
            continue
        seen_urls.add(url)
        results.append(WebSearchResult(title=title, url=url, snippet=snippet, rank=len(results) + 1, provider="duckduckgo"))
        if len(results) >= limit:
            break
    return results


class _DuckDuckGoHtmlParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.items: list[dict[str, str]] = []
        self._current: dict[str, str] | None = None
        self._capture: str | None = None
        self._buffer: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {name: value or "" for name, value in attrs}
        class_name = attrs_dict.get("class", "")
        if tag == "a" and "result__a" in class_name:
            self._current = {"url": attrs_dict.get("href", ""), "title": "", "snippet": ""}
            self._capture = "title"
            self._buffer = []
        elif self._current is not None and tag in {"a", "div"} and "result__snippet" in class_name:
            self._capture = "snippet"
            self._buffer = []

    def handle_data(self, data: str) -> None:
        if self._capture:
            self._buffer.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self._capture == "title" and tag == "a" and self._current is not None:
            self._current["title"] = "".join(self._buffer)
            self._capture = None
            self._buffer = []
            return
        if self._capture == "snippet" and tag in {"a", "div"} and self._current is not None:
            self._current["snippet"] = "".join(self._buffer)
            self._capture = None
            self._buffer = []
            self.items.append(self._current)
            self._current = None


def _normalize_duckduckgo_url(value: str) -> str:
    url = unescape(value).strip()
    if not url:
        return ""
    parsed = urlparse(url)
    if parsed.path == "/l/" or "duckduckgo.com/l/" in url:
        nested = parse_qs(parsed.query).get("uddg", [""])[0]
        return unquote(nested).strip()
    return url


def _json_loads(raw: bytes) -> dict[str, Any]:
    try:
        payload = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise WebSearchError("invalid_json_response") from exc
    if not isinstance(payload, dict):
        raise WebSearchError("unexpected_json_response")
    return payload


def _read_error_body(exc: HTTPError) -> str:
    try:
        raw = exc.read().decode("utf-8", errors="ignore")
    except Exception:
        raw = str(exc.reason)
    return _clean_text(raw)[:240]


def _clean_text(value: str) -> str:
    text = unescape(value)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()
