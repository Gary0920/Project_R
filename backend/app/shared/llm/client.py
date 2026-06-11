from __future__ import annotations

import json
import os
import re
import socket
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[3]
load_dotenv(BASE_DIR / ".env")

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
KEY_SPECIFIC_STATUS_CODES = {401, 403}
SUPPORTED_PROVIDERS = {"claude", "openai", "deepseek", "mimo"}

LLMContentBlock = dict[str, Any]
LLMMessage = dict[str, Any]


class LLMConfigurationError(RuntimeError):
    pass


class LLMProviderError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        retryable: bool = False,
        key_index: int | None = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable
        self.key_index = key_index


@dataclass(frozen=True)
class ProviderSettings:
    provider: str
    api_keys: tuple[str, ...]
    model: str
    max_tokens: int
    base_url: str
    timeout_seconds: float
    system_prompt: str | None
    api_version: str | None = None
    profile: str | None = None
    label: str | None = None
    description: str | None = None
    key_prefix: str | None = None
    reasoning_effort: str | None = None
    supports_vision: bool = False

    @property
    def configured(self) -> bool:
        return bool(self.api_keys)


@dataclass(frozen=True)
class ProviderKey:
    index: int
    value: str


@dataclass(frozen=True)
class LLMResponse:
    text: str
    model: str
    provider: str
    key_index: int
    usage: dict[str, int]
    raw_id: str | None = None

    @property
    def token_cost(self) -> int:
        return int(self.usage.get("input_tokens", 0)) + int(
            self.usage.get("output_tokens", 0)
        )


class LLMClient(Protocol):
    settings: ProviderSettings

    def complete(
        self,
        messages: list[LLMMessage],
        *,
        system_prompt: str | None = None,
        thinking: bool = False,
        reasoning_effort: str | None = None,
        temperature: float | None = None,
    ) -> LLMResponse:
        ...


class ProviderKeyPool:
    def __init__(self, keys: tuple[str, ...]):
        self._keys = tuple(ProviderKey(index=i + 1, value=key) for i, key in enumerate(keys))
        self._cursor = 0
        self._lock = threading.Lock()

    def next_rotation(self) -> list[ProviderKey]:
        if not self._keys:
            raise LLMConfigurationError("未配置当前 Provider 的 API Key")

        with self._lock:
            start = self._cursor
            self._cursor = (self._cursor + 1) % len(self._keys)

        return list(self._keys[start:]) + list(self._keys[:start])


class BaseProviderClient:
    def __init__(self, settings: ProviderSettings):
        self.settings = settings
        self._pool = ProviderKeyPool(settings.api_keys)

    def complete(
        self,
        messages: list[LLMMessage],
        *,
        system_prompt: str | None = None,
        thinking: bool = False,
        reasoning_effort: str | None = None,
        temperature: float | None = None,
    ) -> LLMResponse:
        self._validate_messages(messages)
        payload = self._build_payload(
            messages,
            system_prompt or self.settings.system_prompt,
            thinking,
            reasoning_effort or self.settings.reasoning_effort,
            temperature,
        )

        last_error: LLMProviderError | None = None
        for key in self._pool.next_rotation():
            try:
                raw = self._post(key, payload)
                return self._parse_response(raw, key.index)
            except LLMProviderError as exc:
                exc.key_index = key.index
                last_error = exc
                if not exc.retryable and exc.status_code not in KEY_SPECIFIC_STATUS_CODES:
                    raise exc

        if last_error:
            raise last_error
        raise LLMConfigurationError("未配置当前 Provider 的 API Key")

    def _build_payload(
        self,
        messages: list[LLMMessage],
        system_prompt: str | None,
        thinking: bool,
        reasoning_effort: str | None,
        temperature: float | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError

    def _post(self, key: ProviderKey, payload: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    def _parse_response(self, raw: dict[str, Any], key_index: int) -> LLMResponse:
        raise NotImplementedError

    def _request_json(
        self,
        url: str,
        key: ProviderKey,
        payload: dict[str, Any],
        headers: dict[str, str],
    ) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        request = Request(url, data=body, method="POST", headers=headers)

        try:
            with urlopen(request, timeout=self.settings.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            message = self._read_error_message(exc)
            raise LLMProviderError(
                message,
                status_code=exc.code,
                retryable=exc.code in RETRYABLE_STATUS_CODES,
            ) from exc
        except (TimeoutError, socket.timeout, URLError) as exc:
            raise LLMProviderError(
                f"{self.settings.provider} API 网络请求失败: {exc}",
                retryable=True,
            ) from exc
        except json.JSONDecodeError as exc:
            raise LLMProviderError(
                f"{self.settings.provider} API 返回了无法解析的 JSON",
                retryable=True,
            ) from exc

    @staticmethod
    def _validate_messages(messages: list[LLMMessage]) -> None:
        if not messages:
            raise ValueError("messages 不能为空")
        for message in messages:
            role = message.get("role")
            content = message.get("content")
            if role not in {"user", "assistant"}:
                raise ValueError("messages 必须包含 role=user/assistant")
            if isinstance(content, str):
                continue
            if role == "user" and isinstance(content, list) and all(isinstance(block, dict) for block in content):
                continue
            raise ValueError("messages content 必须是字符串，或用户消息的多模态 content blocks")

    @staticmethod
    def _read_error_message(exc: HTTPError) -> str:
        try:
            raw = exc.read().decode("utf-8")
            payload = json.loads(raw)
            detail = payload.get("error", {}).get("message") or raw
        except Exception:
            detail = exc.reason
        return f"LLM Provider 请求失败 ({exc.code}): {detail}"


class AnthropicMessagesClient(BaseProviderClient):
    def _build_payload(
        self,
        messages: list[LLMMessage],
        system_prompt: str | None,
        thinking: bool,
        reasoning_effort: str | None,
        temperature: float | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.settings.model,
            "max_tokens": self.settings.max_tokens,
            "messages": messages,
        }
        if system_prompt:
            payload["system"] = system_prompt
        if temperature is not None:
            payload["temperature"] = temperature
        return payload

    def _post(self, key: ProviderKey, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request_json(
            f"{self.settings.base_url.rstrip('/')}/v1/messages",
            key,
            payload,
            {
                "x-api-key": key.value,
                "anthropic-version": self.settings.api_version or "2023-06-01",
                "content-type": "application/json",
            },
        )

    def _parse_response(self, raw: dict[str, Any], key_index: int) -> LLMResponse:
        content = raw.get("content", [])
        text_parts = [
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        text = "\n".join(part for part in text_parts if part).strip()
        if not text:
            raise LLMProviderError("Claude API 返回为空", retryable=True, key_index=key_index)

        usage = raw.get("usage") or {}
        return LLMResponse(
            text=text,
            model=str(raw.get("model") or self.settings.model),
            provider=self.settings.provider,
            key_index=key_index,
            usage={
                "input_tokens": int(usage.get("input_tokens", 0)),
                "output_tokens": int(usage.get("output_tokens", 0)),
            },
            raw_id=raw.get("id"),
        )


class OpenAICompatibleChatClient(BaseProviderClient):
    def _build_payload(
        self,
        messages: list[LLMMessage],
        system_prompt: str | None,
        thinking: bool,
        reasoning_effort: str | None,
        temperature: float | None = None,
    ) -> dict[str, Any]:
        outgoing = list(messages)
        if system_prompt:
            outgoing = [{"role": "system", "content": system_prompt}] + outgoing
        payload: dict[str, Any] = {
            "model": self.settings.model,
            "messages": outgoing,
        }
        if temperature is not None:
            payload["temperature"] = temperature
        if self.settings.provider == "mimo":
            payload["max_completion_tokens"] = self.settings.max_tokens
        else:
            payload["max_tokens"] = self.settings.max_tokens

        if self.settings.provider in {"deepseek", "mimo"}:
            payload["thinking"] = {"type": "enabled" if thinking else "disabled"}
        if self.settings.provider == "deepseek" and thinking:
            effort = _normalize_reasoning_effort(reasoning_effort or "high")
            if effort:
                payload["reasoning_effort"] = effort
        return payload

    def _post(self, key: ProviderKey, payload: dict[str, Any]) -> dict[str, Any]:
        base_url = self.settings.base_url.rstrip("/")
        if base_url.endswith("/v1"):
            url = f"{base_url}/chat/completions"
        else:
            url = f"{base_url}/v1/chat/completions"
        return self._request_json(
            url,
            key,
            payload,
            {
                "authorization": f"Bearer {key.value}",
                "content-type": "application/json",
            },
        )

    def _parse_response(self, raw: dict[str, Any], key_index: int) -> LLMResponse:
        choices = raw.get("choices") or []
        first = choices[0] if choices else {}
        message = first.get("message") if isinstance(first, dict) else {}
        text = (message or {}).get("content", "")
        if isinstance(text, list):
            text = "\n".join(
                block.get("text", "")
                for block in text
                if isinstance(block, dict) and block.get("type") == "text"
            )
        text = str(text).strip()
        if not text:
            raise LLMProviderError(
                f"{self.settings.provider} API 返回为空",
                retryable=True,
                key_index=key_index,
            )

        usage = raw.get("usage") or {}
        return LLMResponse(
            text=text,
            model=str(raw.get("model") or self.settings.model),
            provider=self.settings.provider,
            key_index=key_index,
            usage={
                "input_tokens": int(usage.get("prompt_tokens", 0)),
                "output_tokens": int(usage.get("completion_tokens", 0)),
            },
            raw_id=raw.get("id"),
        )


def load_provider_settings(provider: str | None = None) -> ProviderSettings:
    profile_ids = _load_model_profile_ids()
    default_profile = _default_model_profile(profile_ids)

    if provider:
        normalized_candidate = _normalize_profile_id(provider)
        if normalized_candidate in profile_ids:
            return _load_model_profile_settings(normalized_candidate)

    if provider is None and default_profile:
        return _load_model_profile_settings(default_profile)

    provider_name = _normalize_provider(provider or os.getenv("LLM_PROVIDER", "claude"))
    defaults = _provider_defaults(provider_name)
    prefix = _provider_env_prefix(provider_name)
    global_system_prompt = os.getenv(
        "LLM_SYSTEM_PROMPT",
        "你是 Project_R 的企业知识与业务流程助手。回答要准确、简洁，并优先说明可执行下一步。",
    )

    return ProviderSettings(
        provider=provider_name,
        api_keys=tuple(_load_api_keys(prefix)),
        model=os.getenv(f"{prefix}_MODEL", defaults["model"]),
        max_tokens=int(os.getenv(f"{prefix}_MAX_TOKENS", os.getenv("LLM_MAX_TOKENS", "2048"))),
        base_url=os.getenv(f"{prefix}_BASE_URL", defaults["base_url"]),
        timeout_seconds=float(
            os.getenv(f"{prefix}_TIMEOUT_SECONDS", os.getenv("LLM_TIMEOUT_SECONDS", "60"))
        ),
        system_prompt=os.getenv(f"{prefix}_SYSTEM_PROMPT", global_system_prompt),
        api_version=os.getenv(f"{prefix}_API_VERSION", defaults.get("api_version")),
        key_prefix=prefix,
        reasoning_effort=_load_reasoning_effort(prefix),
        supports_vision=_load_supports_vision(provider_name, os.getenv(f"{prefix}_MODEL", defaults["model"]), prefix),
    )


def get_llm_client(provider: str | None = None) -> LLMClient:
    settings = load_provider_settings(provider)
    with _client_lock:
        cache_key = settings.profile or settings.provider
        client = _clients.get(cache_key)
        if client is None or client.settings != settings:
            client = _build_client(settings)
            _clients[cache_key] = client
        return client


def get_claude_client() -> LLMClient:
    return get_llm_client("claude")


def list_provider_statuses() -> list[dict[str, Any]]:
    profile_ids = _load_model_profile_ids()
    if profile_ids:
        default_profile = _default_model_profile(profile_ids)
        statuses = []
        for profile_id in profile_ids:
            settings = _load_model_profile_settings(profile_id)
            statuses.append(
                {
                    "profile": profile_id,
                    "provider": settings.provider,
                    "label": settings.label or _profile_label(profile_id),
                    "description": settings.description or "",
                    "default": profile_id == default_profile,
                    "configured": settings.configured,
                    "key_count": len(settings.api_keys),
                    "model": settings.model,
                    "base_url": settings.base_url,
                    "api_version": settings.api_version,
                    "reasoning_effort": settings.reasoning_effort,
                    "supports_vision": settings.supports_vision,
                }
            )
        return statuses

    statuses = []
    default_provider = _normalize_provider(os.getenv("LLM_PROVIDER", "claude"))
    for provider in sorted(SUPPORTED_PROVIDERS):
        settings = load_provider_settings(provider)
        statuses.append(
            {
                "provider": provider,
                "profile": None,
                "label": provider.upper(),
                "description": "",
                "default": provider == default_provider,
                "configured": settings.configured,
                "key_count": len(settings.api_keys),
                "model": settings.model,
                "base_url": settings.base_url,
                "api_version": settings.api_version,
                "reasoning_effort": settings.reasoning_effort,
                "supports_vision": settings.supports_vision,
            }
        )
    return statuses


def _build_client(settings: ProviderSettings) -> LLMClient:
    if settings.provider == "claude":
        return AnthropicMessagesClient(settings)
    if settings.provider in {"openai", "deepseek", "mimo"}:
        return OpenAICompatibleChatClient(settings)
    raise LLMConfigurationError(f"不支持的 LLM Provider: {settings.provider}")


def _normalize_provider(provider: str) -> str:
    normalized = provider.strip().lower()
    if normalized == "anthropic":
        normalized = "claude"
    if normalized not in SUPPORTED_PROVIDERS:
        raise LLMConfigurationError(f"不支持的 LLM Provider: {provider}")
    return normalized


def _provider_env_prefix(provider: str) -> str:
    if provider == "claude":
        return "CLAUDE"
    return provider.upper()


def _provider_defaults(provider: str) -> dict[str, str]:
    if provider == "claude":
        return {
            "model": "claude-sonnet-4-20250514",
            "base_url": "https://api.anthropic.com",
            "api_version": "2023-06-01",
        }
    if provider == "openai":
        return {
            "model": "gpt-4o-mini",
            "base_url": "https://api.openai.com",
        }
    if provider == "deepseek":
        return {
            "model": "deepseek-v4-flash",
            "base_url": "https://api.deepseek.com",
        }
    if provider == "mimo":
        return {
            "model": "mimo-v2.5",
            "base_url": "https://api.xiaomimimo.com/v1",
        }
    raise LLMConfigurationError(f"不支持的 LLM Provider: {provider}")


def _load_model_profile_ids() -> list[str]:
    raw = os.getenv("LLM_MODEL_PROFILES", "")
    ids: list[str] = []
    for item in raw.split(","):
        profile_id = _normalize_profile_id(item)
        if profile_id and profile_id not in ids:
            ids.append(profile_id)
    return ids


def _default_model_profile(profile_ids: list[str]) -> str | None:
    if not profile_ids:
        return None
    raw = os.getenv("LLM_DEFAULT_PROFILE") or os.getenv("LLM_MODEL_PROFILE") or ""
    profile_id = _normalize_profile_id(raw)
    if profile_id in profile_ids:
        return profile_id
    return profile_ids[0]


def _load_model_profile_settings(profile_id: str) -> ProviderSettings:
    normalized_profile = _normalize_profile_id(profile_id)
    prefix = _profile_env_prefix(normalized_profile)
    provider_name = _normalize_provider(
        os.getenv(f"{prefix}_PROVIDER", normalized_profile.split("-")[0])
    )
    provider_prefix = _provider_env_prefix(provider_name)
    key_prefix = os.getenv(f"{prefix}_KEY_PREFIX", provider_prefix).strip().upper()
    defaults = _provider_defaults(provider_name)
    global_system_prompt = os.getenv(
        "LLM_SYSTEM_PROMPT",
        "你是 Project_R 的企业知识与业务流程助手。回答要准确、简洁，并优先说明可执行下一步。",
    )

    return ProviderSettings(
        provider=provider_name,
        api_keys=tuple(_load_api_keys(key_prefix)),
        model=os.getenv(f"{prefix}_MODEL", os.getenv(f"{provider_prefix}_MODEL", defaults["model"])),
        max_tokens=int(
            os.getenv(
                f"{prefix}_MAX_TOKENS",
                os.getenv(f"{provider_prefix}_MAX_TOKENS", os.getenv("LLM_MAX_TOKENS", "2048")),
            )
        ),
        base_url=os.getenv(
            f"{prefix}_BASE_URL",
            os.getenv(f"{provider_prefix}_BASE_URL", defaults["base_url"]),
        ),
        timeout_seconds=float(
            os.getenv(
                f"{prefix}_TIMEOUT_SECONDS",
                os.getenv(f"{provider_prefix}_TIMEOUT_SECONDS", os.getenv("LLM_TIMEOUT_SECONDS", "60")),
            )
        ),
        system_prompt=os.getenv(
            f"{prefix}_SYSTEM_PROMPT",
            os.getenv(f"{provider_prefix}_SYSTEM_PROMPT", global_system_prompt),
        ),
        api_version=os.getenv(
            f"{prefix}_API_VERSION",
            os.getenv(f"{provider_prefix}_API_VERSION", defaults.get("api_version")),
        ),
        profile=normalized_profile,
        label=os.getenv(f"{prefix}_LABEL", _profile_label(normalized_profile)),
        description=os.getenv(f"{prefix}_DESCRIPTION", ""),
        key_prefix=key_prefix,
        reasoning_effort=_load_reasoning_effort(prefix, provider_prefix),
        supports_vision=_load_supports_vision(
            provider_name,
            os.getenv(f"{prefix}_MODEL", os.getenv(f"{provider_prefix}_MODEL", defaults["model"])),
            prefix,
            provider_prefix,
        ),
    )


def _normalize_profile_id(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_.-]+", "-", value.strip().lower())
    return normalized.strip("-")


def _profile_env_prefix(profile_id: str) -> str:
    suffix = re.sub(r"[^A-Za-z0-9]+", "_", profile_id).strip("_").upper()
    return f"LLM_PROFILE_{suffix}"


def _profile_label(profile_id: str) -> str:
    return " ".join(part.upper() if part in {"v2", "v3", "v4"} else part.capitalize() for part in profile_id.split("-"))


def _load_supports_vision(provider: str, model: str, *prefixes: str) -> bool:
    for prefix in prefixes:
        raw = os.getenv(f"{prefix}_SUPPORTS_VISION")
        if raw is not None:
            return raw.strip().lower() in {"1", "true", "yes", "y", "on"}
    return _default_supports_vision(provider, model)


def _default_supports_vision(provider: str, model: str) -> bool:
    normalized_model = model.strip().lower().replace("_", "-")
    if provider == "mimo":
        return normalized_model in {"mimo-v2.5", "mimo-v2-omni"}
    return False


def _load_reasoning_effort(*prefixes: str) -> str | None:
    for prefix in prefixes:
        value = os.getenv(f"{prefix}_REASONING_EFFORT")
        if value:
            return _normalize_reasoning_effort(value)
    return _normalize_reasoning_effort(os.getenv("LLM_REASONING_EFFORT"))


def _normalize_reasoning_effort(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip().lower().replace("-", "_")
    if normalized in {"low", "medium", "standard", "default"}:
        return "high"
    if normalized in {"high", "max"}:
        return normalized
    if normalized in {"xhigh", "x_high", "extra_high", "maximum"}:
        return "max"
    return None


def _load_api_keys(prefix: str) -> list[str]:
    keys: list[str] = []

    csv_keys = os.getenv(f"{prefix}_API_KEYS", "")
    keys.extend(key.strip() for key in csv_keys.split(",") if key.strip())

    numbered_keys: list[tuple[int, str]] = []
    for name, value in os.environ.items():
        match = re.fullmatch(rf"{re.escape(prefix)}_API_KEY_(\d+)", name)
        if match and value.strip():
            numbered_keys.append((int(match.group(1)), value.strip()))
    keys.extend(value for _, value in sorted(numbered_keys))

    deduped: list[str] = []
    seen: set[str] = set()
    for key in keys:
        if key not in seen:
            deduped.append(key)
            seen.add(key)
    return deduped


_clients: dict[str, LLMClient] = {}
_client_lock = threading.Lock()
