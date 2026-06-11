import unittest

from app.features.chat.intent import IntentType, classify_intent


class IntentTests(unittest.TestCase):
    def test_knowledge_keywords_stay_chat_in_explicit_routing(self):
        result = classify_intent("请查询公司规定里关于合同评审的流程")

        self.assertEqual(result.intent, IntentType.CHAT)
        self.assertEqual(result.reason, "explicit routing only")

    def test_document_generation_keywords_stay_chat_in_explicit_routing(self):
        result = classify_intent("根据资料生成 Word 报告")

        self.assertEqual(result.intent, IntentType.CHAT)

    def test_natural_document_generation_request_stays_chat_in_explicit_routing(self):
        result = classify_intent("帮我生成一份会议纪要 Word")

        self.assertEqual(result.intent, IntentType.CHAT)

    def test_convert_to_downloadable_word_request_stays_chat_in_explicit_routing(self):
        result = classify_intent("帮我将通知正式转为word文档,供我下载")

        self.assertEqual(result.intent, IntentType.CHAT)

    def test_skill_trigger_text_stays_chat_in_explicit_routing(self):
        result = classify_intent("帮我启动项目沟通风险分析流程")

        self.assertEqual(result.intent, IntentType.CHAT)

    def test_defaults_to_chat(self):
        result = classify_intent("你好，帮我解释一下这句话")

        self.assertEqual(result.intent, IntentType.CHAT)


if __name__ == "__main__":
    unittest.main()
