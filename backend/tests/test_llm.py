import unittest
import os
from unittest.mock import patch

from app.shared.llm.client import (
    BaseProviderClient,
    LLMResponse,
    LLMProviderError,
    OpenAICompatibleChatClient,
    ProviderSettings,
    load_provider_settings,
    list_provider_statuses,
)


class FakeProviderClient(BaseProviderClient):
    def __init__(self):
        super().__init__(
            ProviderSettings(
                provider="test",
                api_keys=("key-1", "key-2"),
                model="test-model",
                max_tokens=128,
                base_url="https://example.test",
                timeout_seconds=1,
                system_prompt=None,
            )
        )
        self.calls = []
        self.fail_first_key = False

    def _post_messages(self, key, payload):
        raise NotImplementedError

    def _build_payload(self, messages, system_prompt, thinking, reasoning_effort, temperature=None):
        return {"model": self.settings.model, "messages": messages}

    def _post(self, key, payload):
        self.calls.append(key.value)
        if self.fail_first_key and key.value == "key-1":
            raise LLMProviderError("rate limited", status_code=429, retryable=True)
        return {
            "id": "msg_test",
            "model": payload["model"],
            "content": [{"type": "text", "text": f"ok:{key.value}"}],
            "usage": {"input_tokens": 3, "output_tokens": 5},
        }

    def _parse_response(self, raw, key_index):
        usage = raw["usage"]
        return LLMResponse(
            text=raw["content"][0]["text"],
            model=raw["model"],
            provider=self.settings.provider,
            key_index=key_index,
            usage={
                "input_tokens": usage["input_tokens"],
                "output_tokens": usage["output_tokens"],
            },
            raw_id=raw["id"],
        )


class ProviderClientTests(unittest.TestCase):
    def test_round_robin_keys_between_successful_calls(self):
        client = FakeProviderClient()

        first = client.complete([{"role": "user", "content": "hello"}])
        second = client.complete([{"role": "user", "content": "hello again"}])

        self.assertEqual(first.text, "ok:key-1")
        self.assertEqual(second.text, "ok:key-2")
        self.assertEqual(client.calls, ["key-1", "key-2"])

    def test_retries_next_key_on_retryable_error(self):
        client = FakeProviderClient()
        client.fail_first_key = True

        response = client.complete([{"role": "user", "content": "hello"}])

        self.assertEqual(response.text, "ok:key-2")
        self.assertEqual(response.key_index, 2)
        self.assertEqual(client.calls, ["key-1", "key-2"])
        self.assertEqual(response.token_cost, 8)

    def test_provider_statuses_do_not_expose_keys(self):
        with patch.dict(os.environ, {}, clear=True):
            statuses = list_provider_statuses()

        self.assertEqual({item["provider"] for item in statuses}, {"claude", "openai", "deepseek", "mimo"})
        self.assertTrue(all("api_keys" not in item for item in statuses))

    def test_model_profiles_can_share_provider_key_group(self):
        env = {
            "LLM_MODEL_PROFILES": "deepseek-flash,deepseek-pro",
            "LLM_DEFAULT_PROFILE": "deepseek-flash",
            "DEEPSEEK_API_KEYS": "key-a,key-b",
            "LLM_REASONING_EFFORT": "max",
            "LLM_PROFILE_DEEPSEEK_FLASH_LABEL": "DeepSeek Flash",
            "LLM_PROFILE_DEEPSEEK_FLASH_PROVIDER": "deepseek",
            "LLM_PROFILE_DEEPSEEK_FLASH_MODEL": "deepseek-v4-flash",
            "LLM_PROFILE_DEEPSEEK_PRO_LABEL": "DeepSeek Pro",
            "LLM_PROFILE_DEEPSEEK_PRO_PROVIDER": "deepseek",
            "LLM_PROFILE_DEEPSEEK_PRO_MODEL": "deepseek-v4-pro",
            "LLM_PROFILE_DEEPSEEK_PRO_REASONING_EFFORT": "high",
        }
        with patch.dict(os.environ, env, clear=True):
            flash = load_provider_settings("deepseek-flash")
            pro = load_provider_settings("deepseek-pro")
            statuses = list_provider_statuses()

        self.assertEqual(flash.provider, "deepseek")
        self.assertEqual(pro.provider, "deepseek")
        self.assertEqual(flash.api_keys, ("key-a", "key-b"))
        self.assertEqual(pro.api_keys, ("key-a", "key-b"))
        self.assertEqual(flash.model, "deepseek-v4-flash")
        self.assertEqual(pro.model, "deepseek-v4-pro")
        self.assertEqual(flash.reasoning_effort, "max")
        self.assertEqual(pro.reasoning_effort, "high")
        self.assertEqual({item["profile"] for item in statuses}, {"deepseek-flash", "deepseek-pro"})
        self.assertTrue(all("api_keys" not in item for item in statuses))

    def test_deepseek_payload_uses_thinking_and_reasoning_effort(self):
        client = OpenAICompatibleChatClient(
            ProviderSettings(
                provider="deepseek",
                api_keys=("key",),
                model="deepseek-v4-pro",
                max_tokens=128,
                base_url="https://api.deepseek.com",
                timeout_seconds=1,
                system_prompt=None,
                reasoning_effort="max",
            )
        )

        payload = client._build_payload(
            [{"role": "user", "content": "hello"}],
            None,
            True,
            client.settings.reasoning_effort,
        )

        self.assertEqual(payload["thinking"], {"type": "enabled"})
        self.assertEqual(payload["reasoning_effort"], "max")

    def test_deepseek_payload_can_disable_thinking_explicitly(self):
        client = OpenAICompatibleChatClient(
            ProviderSettings(
                provider="deepseek",
                api_keys=("key",),
                model="deepseek-v4-flash",
                max_tokens=128,
                base_url="https://api.deepseek.com",
                timeout_seconds=1,
                system_prompt=None,
                reasoning_effort="high",
            )
        )

        payload = client._build_payload(
            [{"role": "user", "content": "hello"}],
            None,
            False,
            client.settings.reasoning_effort,
        )

        self.assertEqual(payload["thinking"], {"type": "disabled"})
        self.assertNotIn("reasoning_effort", payload)

    def test_mimo_payload_uses_thinking_without_unverified_effort_param(self):
        client = OpenAICompatibleChatClient(
            ProviderSettings(
                provider="mimo",
                api_keys=("key",),
                model="mimo-v2.5-pro",
                max_tokens=128,
                base_url="https://api.xiaomimimo.com/v1",
                timeout_seconds=1,
                system_prompt=None,
                reasoning_effort="max",
            )
        )

        payload = client._build_payload(
            [{"role": "user", "content": "hello"}],
            None,
            True,
            client.settings.reasoning_effort,
        )

        self.assertEqual(payload["thinking"], {"type": "enabled"})
        self.assertEqual(payload["max_completion_tokens"], 128)
        self.assertNotIn("reasoning_effort", payload)

    def test_mimo_profiles_advertise_vision_support_for_vision_capable_models(self):
        env = {
            "LLM_MODEL_PROFILES": "deepseek-pro,mimo-v2-5,mimo-v2-5-pro",
            "LLM_DEFAULT_PROFILE": "mimo-v2-5",
            "DEEPSEEK_API_KEYS": "deepseek-key",
            "MIMO_API_KEYS": "mimo-key",
            "LLM_PROFILE_DEEPSEEK_PRO_PROVIDER": "deepseek",
            "LLM_PROFILE_DEEPSEEK_PRO_MODEL": "deepseek-v4-pro",
            "LLM_PROFILE_MIMO_V2_5_PROVIDER": "mimo",
            "LLM_PROFILE_MIMO_V2_5_MODEL": "mimo-v2.5",
            "LLM_PROFILE_MIMO_V2_5_PRO_PROVIDER": "mimo",
            "LLM_PROFILE_MIMO_V2_5_PRO_MODEL": "mimo-v2.5-pro",
        }
        with patch.dict(os.environ, env, clear=True):
            statuses = {item["profile"]: item for item in list_provider_statuses()}

        self.assertFalse(statuses["deepseek-pro"]["supports_vision"])
        self.assertTrue(statuses["mimo-v2-5"]["supports_vision"])
        self.assertFalse(statuses["mimo-v2-5-pro"]["supports_vision"])

    def test_openai_compatible_payload_accepts_multimodal_user_content(self):
        client = OpenAICompatibleChatClient(
            ProviderSettings(
                provider="mimo",
                api_keys=("key",),
                model="mimo-v2.5",
                max_tokens=128,
                base_url="https://api.xiaomimimo.com/v1",
                timeout_seconds=1,
                system_prompt=None,
                supports_vision=True,
            )
        )
        content = [
            {"type": "text", "text": "Describe this image"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}},
        ]

        payload = client._build_payload(
            [{"role": "user", "content": content}],
            None,
            False,
            None,
        )

        client._validate_messages(payload["messages"])
        self.assertEqual(payload["messages"][0]["content"], content)


if __name__ == "__main__":
    unittest.main()
