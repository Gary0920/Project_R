import unittest

from fastapi import HTTPException

from app.features.chat.schemas import TransformTextRequest
from app.features.chat.transform_service import transform_chat_text
from app.shared.llm.client import LLMResponse


class FakeTransformClient:
    def __init__(self):
        self.messages = []
        self.system_prompt = None
        self.thinking = None
        self.temperature = None

    def complete(self, messages, *, system_prompt=None, thinking=False, reasoning_effort=None, temperature=None):
        self.messages = messages
        self.system_prompt = system_prompt
        self.thinking = thinking
        self.temperature = temperature
        return LLMResponse(
            text=f"transformed: {messages[-1]['content']}",
            model="mock-model",
            provider="mock",
            key_index=1,
            usage={"input_tokens": 1, "output_tokens": 2},
        )


class ChatTransformTests(unittest.TestCase):
    def test_transform_supports_all_actions(self):
        for action in ("rewrite", "translate", "summarize", "expand"):
            client = FakeTransformClient()
            response = transform_chat_text(
                TransformTextRequest(
                    action=action,
                    text="Please review this email.",
                    target_language="English",
                    tone="professional",
                ),
                get_llm_client=lambda provider=None: client,
            )

            self.assertEqual(response.provider, "mock")
            self.assertIn("Please review this email.", client.messages[-1]["content"])
            self.assertIs(client.thinking, False)
            self.assertIsNone(client.temperature)
            self.assertTrue(client.system_prompt)

    def test_transform_rejects_unknown_action(self):
        with self.assertRaises(HTTPException) as exc:
            transform_chat_text(
                TransformTextRequest(action="polish-hard", text="hello"),
                get_llm_client=lambda provider=None: FakeTransformClient(),
            )

        self.assertEqual(exc.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
