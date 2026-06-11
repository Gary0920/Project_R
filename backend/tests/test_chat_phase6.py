import unittest
import json
import os
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.NamedTemporaryFile(delete=False).name}"

import api.chat as chat_api
import app.features.skills.execution as skill_execution
from app.shared.llm.client import LLMProviderError, LLMResponse
from app.shared.web_search.service import WebSearchResponse, WebSearchResult
from fastapi import HTTPException
from models import Base, SessionLocal, engine
from models.attachment import SessionAttachment
from models.audit_log import AuditLog
from models.knowledge_review import KnowledgeReview
from models.message import ChatMessage
from models.notification import Notification
from models.session import ChatSession
from models.skill_run import SkillRun
from models.user import User
from models.workspace import Workspace, WorkspaceMember
from app.features.skills.runner import SkillRunner


class FakeLLMClient:
    def __init__(self, should_fail=False):
        self.should_fail = should_fail
        self.last_system_prompt = None
        self.last_thinking = None
        self.last_temperature = None

    def complete(self, messages, *, system_prompt=None, thinking=False, reasoning_effort=None, temperature=None):
        self.last_system_prompt = system_prompt
        self.last_thinking = thinking
        self.last_temperature = temperature
        if self.should_fail:
            raise LLMProviderError("mock provider unavailable", retryable=True, key_index=1)
        return LLMResponse(
            text=f"mock reply: {messages[-1]['content']}",
            model="mock-model",
            provider="mock",
            key_index=1,
            usage={"input_tokens": 2, "output_tokens": 3},
        )


def fake_gbrain_company_sources():
    return [
        {
            "file": "gbrain:company-wiki/rules/用车申请",
            "source_title": "用车申请",
            "section_path": "用车申请 > 目的",
            "content": "当员工因公需借用公司车辆时，必须走此【用车申请】流程。",
            "score": 0.92,
        }
    ]


def fake_gbrain_think_result():
    return {
        "ok": True,
        "status": "ok",
        "source_id": "company-wiki",
        "reply": "用车申请需要先获得审批。\n\n引用与缺口： 来源 1 来源 2",
        "model": "gbrain-think-test",
        "metadata": {
            "gaps": ["缺少审批时限。"],
            "conflicts": ["车辆申请权限在两条规则中不一致。"],
            "warnings": ["source_scope_limited"],
            "diagnostics": {"trace_id": "think-trace-1", "pipeline": "think"},
        },
        "sources": [
            {
                "file": "gbrain:company-wiki/rules/用车申请",
                "source_title": "用车申请",
                "section_path": "rules/用车申请",
                "content": "审批要求",
                "score": 1.0,
            },
            {
                "file": "gbrain:company-wiki/__think_gaps__",
                "source_title": "GBrain 缺口分析 / Gap Analysis",
                "section_path": "GBrain 缺口分析 / Gap Analysis",
                "content": "- 缺少审批时限。",
                "score": 0.0,
            },
        ],
    }


class FakeKnowledgeSources:
    def __init__(self, sources=None, think_result=None):
        self.sources = sources or []
        self.think_result = think_result or {
            "ok": False,
            "status": "disabled",
            "source_id": "company-wiki",
            "reply": "GBrain think disabled",
            "sources": [],
        }
        self.search_calls = []
        self.think_calls = []

    def search(
        self,
        db,
        content,
        *,
        workspace_id,
        forced_company_query,
        reduce_knowledge_context,
    ):
        self.search_calls.append(
            {
                "content": content,
                "workspace_id": workspace_id,
                "forced_company_query": forced_company_query,
                "reduce_knowledge_context": reduce_knowledge_context,
            }
        )
        if reduce_knowledge_context or not forced_company_query:
            return []
        return self.sources

    def search_workspace_sources(self, db, workspace_id, content):
        return []

    def think(self, db, content, *, workspace_id=None):
        self.think_calls.append({"content": content, "workspace_id": workspace_id})
        return self.think_result


class ChatPhase6Tests(unittest.TestCase):
    def setUp(self):
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        self.db = SessionLocal()
        self.user = User(
            username="phase6",
            password_hash="hash",
            role="admin",
            nickname="Phase 6",
        )
        self.db.add(self.user)
        self.db.commit()
        self.db.refresh(self.user)
        self.session = ChatSession(user_id=self.user.id, title="Phase 6")
        self.db.add(self.session)
        self.db.commit()
        self.db.refresh(self.session)
        self.original_get_llm_client = chat_api.get_llm_client
        self.original_knowledge_sources = chat_api.KNOWLEDGE_SOURCES
        self.original_generated_root = chat_api.GENERATED_FILES_ROOT
        self.original_skill_generated_root = skill_execution.GENERATED_FILES_ROOT
        self.original_global_base_prompt_path = chat_api.GLOBAL_BASE_PROMPT_PATH
        self.original_feedback_root = chat_api.MESSAGE_FEEDBACK_ROOT
        self.original_run_web_search_skill = chat_api._run_web_search_skill
        self.generated_root = tempfile.TemporaryDirectory()
        self.prompt_root = tempfile.TemporaryDirectory()
        self.feedback_root = tempfile.TemporaryDirectory()
        chat_api.GENERATED_FILES_ROOT = Path(self.generated_root.name)
        skill_execution.GENERATED_FILES_ROOT = Path(self.generated_root.name)
        chat_api.GLOBAL_BASE_PROMPT_PATH = Path(self.prompt_root.name) / "global-base-prompt.md"
        chat_api.GLOBAL_BASE_PROMPT_PATH.write_text("", encoding="utf-8")
        chat_api.MESSAGE_FEEDBACK_ROOT = Path(self.feedback_root.name)
        chat_api.get_llm_client = lambda provider=None: FakeLLMClient()
        chat_api.KNOWLEDGE_SOURCES = FakeKnowledgeSources()
        SkillRunner._instance = None

    def tearDown(self):
        chat_api.get_llm_client = self.original_get_llm_client
        chat_api.KNOWLEDGE_SOURCES = self.original_knowledge_sources
        chat_api.GENERATED_FILES_ROOT = self.original_generated_root
        skill_execution.GENERATED_FILES_ROOT = self.original_skill_generated_root
        chat_api.GLOBAL_BASE_PROMPT_PATH = self.original_global_base_prompt_path
        chat_api.MESSAGE_FEEDBACK_ROOT = self.original_feedback_root
        chat_api._run_web_search_skill = self.original_run_web_search_skill
        self.generated_root.cleanup()
        self.prompt_root.cleanup()
        self.feedback_root.cleanup()
        self.db.close()
        SkillRunner._instance = None

    def test_build_llm_messages_uses_recent_successful_history(self):
        self.db.add_all(
            [
                ChatMessage(
                    session_id=self.session.id,
                    user_id=self.user.id,
                    role="user",
                    content="hello",
                    status="success",
                ),
                ChatMessage(
                    session_id=self.session.id,
                    user_id=self.user.id,
                    role="assistant",
                    content="hi",
                    status="success",
                ),
                ChatMessage(
                    session_id=self.session.id,
                    user_id=self.user.id,
                    role="assistant",
                    content="failed",
                    status="failed",
                ),
            ]
        )
        self.db.commit()

        messages = chat_api._build_llm_messages(self.db, self.user.id, self.session.id)

        self.assertEqual(
            messages,
            [
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "hi"},
            ],
        )

    def test_exclude_message_context_hides_message_and_filters_llm_history(self):
        self.db.add_all(
            [
                ChatMessage(
                    session_id=self.session.id,
                    user_id=self.user.id,
                    role="user",
                    content="test",
                    status="success",
                ),
                ChatMessage(
                    session_id=self.session.id,
                    user_id=self.user.id,
                    role="assistant",
                    content="test answer",
                    status="success",
                ),
                ChatMessage(
                    session_id=self.session.id,
                    user_id=self.user.id,
                    role="user",
                    content="keep instruction",
                    status="success",
                ),
                ChatMessage(
                    session_id=self.session.id,
                    user_id=self.user.id,
                    role="assistant",
                    content="keep answer",
                    status="success",
                ),
            ]
        )
        self.db.commit()
        target = (
            self.db.query(ChatMessage)
            .filter(ChatMessage.content == "test")
            .one()
        )

        response = chat_api.exclude_message_context(self.session.id, target.id, self.user, self.db)

        self.assertEqual(response["ok"], True)
        self.assertEqual(
            self.db.query(ChatMessage).filter(ChatMessage.session_id == self.session.id).count(),
            4,
        )
        visible = chat_api.list_messages(self.session.id, 50, 0, self.user, self.db)
        self.assertEqual([message.content for message in visible.items], ["keep instruction", "keep answer"])
        messages = chat_api._build_llm_messages(self.db, self.user.id, self.session.id)
        self.assertEqual(
            messages,
            [
                {"role": "user", "content": "keep instruction"},
                {"role": "assistant", "content": "keep answer"},
            ],
        )
        excluded = (
            self.db.query(ChatMessage)
            .filter(ChatMessage.session_id == self.session.id, ChatMessage.is_excluded == True)
            .order_by(ChatMessage.id.asc())
            .all()
        )
        self.assertEqual([message.content for message in excluded], ["test", "test answer"])

    def test_restore_excluded_messages_undoes_pair_delete(self):
        self.db.add_all(
            [
                ChatMessage(
                    session_id=self.session.id,
                    user_id=self.user.id,
                    role="user",
                    content="test",
                    status="success",
                ),
                ChatMessage(
                    session_id=self.session.id,
                    user_id=self.user.id,
                    role="assistant",
                    content="test answer",
                    status="success",
                ),
                ChatMessage(
                    session_id=self.session.id,
                    user_id=self.user.id,
                    role="user",
                    content="keep instruction",
                    status="success",
                ),
            ]
        )
        self.db.commit()
        target = self.db.query(ChatMessage).filter(ChatMessage.content == "test").one()
        deleted = chat_api.exclude_message_context(self.session.id, target.id, self.user, self.db)

        restored = chat_api.restore_excluded_messages(
            self.session.id,
            chat_api.RestoreMessagesRequest(message_ids=deleted["excluded_message_ids"]),
            self.user,
            self.db,
        )

        self.assertTrue(restored["ok"])
        self.assertEqual([message["content"] for message in restored["messages"]], ["test", "test answer"])
        visible = chat_api.list_messages(self.session.id, 50, 0, self.user, self.db)
        self.assertEqual(
            [message.content for message in visible.items],
            ["test", "test answer", "keep instruction"],
        )

    def test_regenerate_message_creates_new_active_version_and_excludes_later_context(self):
        self.db.add_all(
            [
                ChatMessage(
                    session_id=self.session.id,
                    user_id=self.user.id,
                    role="user",
                    content="original question",
                    status="success",
                    version_group_id="user-group",
                ),
                ChatMessage(
                    session_id=self.session.id,
                    user_id=self.user.id,
                    role="assistant",
                    content="old answer",
                    status="success",
                    version_group_id="answer-group",
                ),
                ChatMessage(
                    session_id=self.session.id,
                    user_id=self.user.id,
                    role="user",
                    content="later context",
                    status="success",
                    version_group_id="later-group",
                ),
            ]
        )
        self.db.commit()
        target = self.db.query(ChatMessage).filter(ChatMessage.content == "old answer").one()

        response = chat_api.regenerate_message(
            self.session.id,
            target.id,
            chat_api.RegenerateMessageRequest(temperature=0.9),
            self.user,
            self.db,
        )

        self.assertTrue(response["ok"])
        self.assertEqual(response["assistant_message"]["content"], "mock reply: original question")
        self.assertEqual(response["assistant_message"]["version_count"], 2)
        self.assertEqual(response["excluded_message_ids"], [target.id + 1])
        self.db.refresh(target)
        self.assertFalse(target.active_version)
        visible = chat_api.list_messages(self.session.id, 50, 0, self.user, self.db)
        self.assertEqual(
            [message.content for message in visible.items],
            ["original question", "mock reply: original question"],
        )

    def test_edit_message_creates_question_version_and_new_branch_reply(self):
        self.db.add_all(
            [
                ChatMessage(
                    session_id=self.session.id,
                    user_id=self.user.id,
                    role="user",
                    content="old question",
                    status="success",
                    version_group_id="question-group",
                ),
                ChatMessage(
                    session_id=self.session.id,
                    user_id=self.user.id,
                    role="assistant",
                    content="old answer",
                    status="success",
                    version_group_id="answer-group",
                ),
            ]
        )
        self.db.commit()
        target = self.db.query(ChatMessage).filter(ChatMessage.content == "old question").one()

        response = chat_api.edit_message(
            self.session.id,
            target.id,
            chat_api.EditMessageRequest(content="new question"),
            self.user,
            self.db,
        )

        self.assertTrue(response["ok"])
        self.assertEqual(response["user_message"]["content"], "new question")
        self.assertEqual(response["user_message"]["version_count"], 2)
        self.assertEqual(response["assistant_message"]["content"], "mock reply: new question")
        self.assertEqual(response["excluded_message_ids"], [target.id + 1])
        self.db.refresh(target)
        self.assertFalse(target.active_version)
        visible = chat_api.list_messages(self.session.id, 50, 0, self.user, self.db)
        self.assertEqual(
            [message.content for message in visible.items],
            ["new question", "mock reply: new question"],
        )

    def test_activate_message_version_switches_visible_content(self):
        self.db.add_all(
            [
                ChatMessage(
                    session_id=self.session.id,
                    user_id=self.user.id,
                    role="assistant",
                    content="first answer",
                    status="success",
                    version_group_id="answer-group",
                    version_index=1,
                    active_version=False,
                ),
                ChatMessage(
                    session_id=self.session.id,
                    user_id=self.user.id,
                    role="assistant",
                    content="second answer",
                    status="success",
                    version_group_id="answer-group",
                    version_index=2,
                    active_version=True,
                ),
            ]
        )
        self.db.commit()
        first = self.db.query(ChatMessage).filter(ChatMessage.content == "first answer").one()
        second = self.db.query(ChatMessage).filter(ChatMessage.content == "second answer").one()

        response = chat_api.activate_message_version(self.session.id, second.id, first.id, self.user, self.db)

        self.assertTrue(response["ok"])
        self.assertEqual(response["message"]["content"], "first answer")
        self.db.refresh(first)
        self.db.refresh(second)
        self.assertTrue(first.active_version)
        self.assertFalse(second.active_version)
        visible = chat_api.list_messages(self.session.id, 50, 0, self.user, self.db)
        self.assertEqual([message.content for message in visible.items], ["first answer"])

    def test_submit_message_feedback_writes_structured_json(self):
        message = ChatMessage(
            session_id=self.session.id,
            user_id=self.user.id,
            role="assistant",
            content="answer to rate",
            status="success",
            provider="mock",
            model="mock-model",
            version_group_id="answer-group",
        )
        self.db.add(message)
        self.db.commit()
        self.db.refresh(message)

        response = chat_api.submit_message_feedback(
            self.session.id,
            message.id,
            chat_api.MessageFeedbackRequest(rating=4, comment="Need more AS2047 detail"),
            self.user,
            self.db,
        )

        self.assertTrue(response["ok"])
        files = list(Path(self.feedback_root.name).rglob("*.json"))
        self.assertEqual(len(files), 1)
        payload = json.loads(files[0].read_text(encoding="utf-8"))
        self.assertEqual(payload["rating"], 4)
        self.assertEqual(payload["comment"], "Need more AS2047 detail")
        self.assertEqual(payload["message"]["id"], message.id)
        visible = chat_api.list_messages(self.session.id, 50, 0, self.user, self.db)
        self.assertEqual(visible.items[0].feedback_rating, 4)
        self.assertIsNone(response["knowledge_review_id"])
        self.assertEqual(self.db.query(KnowledgeReview).count(), 0)

    def test_low_rating_gbrain_feedback_creates_knowledge_correction_review(self):
        user_message = ChatMessage(
            session_id=self.session.id,
            user_id=self.user.id,
            role="user",
            content="/query 书面化原则是什么",
            status="success",
        )
        assistant_message = ChatMessage(
            session_id=self.session.id,
            user_id=self.user.id,
            role="assistant",
            content="书面化原则要求重要事项用文字确认。[1]",
            status="success",
            provider="mock",
            model="mock-model",
            rag_used=True,
            sources_json=json.dumps(
                [
                    {
                        "file": "gbrain:company-wiki/rules/书面化原则",
                        "source_title": "书面化原则",
                        "section_path": "rules/书面化原则",
                        "content": "客户确认、内部决策、变更事项都需要书面留痕。",
                        "score": 0.91,
                    }
                ],
                ensure_ascii=False,
            ),
        )
        self.db.add_all([user_message, assistant_message])
        self.db.commit()
        self.db.refresh(assistant_message)

        response = chat_api.submit_message_feedback(
            self.session.id,
            assistant_message.id,
            chat_api.MessageFeedbackRequest(rating=1, comment="回答把范围说窄了，需要纠正引用。"),
            self.user,
            self.db,
        )

        self.assertTrue(response["ok"])
        self.assertIsNotNone(response["knowledge_review_id"])
        review = self.db.get(KnowledgeReview, response["knowledge_review_id"])
        self.assertIsNotNone(review)
        assert review is not None
        self.assertEqual(review.status, "pending")
        self.assertEqual(review.source, f"gbrain_answer_correction:message:{assistant_message.id}")
        self.assertIn("知识纠错候选", review.content)
        self.assertIn("/query 书面化原则是什么", review.content)
        self.assertIn("gbrain:company-wiki/rules/书面化原则", review.content)
        self.assertIn("citation-fixer", review.content)
        notification = (
            self.db.query(Notification)
            .filter(Notification.event_key == f"knowledge_review:{review.id}:pending")
            .first()
        )
        self.assertIsNotNone(notification)

    def test_low_rating_without_gbrain_sources_does_not_create_knowledge_review(self):
        message = ChatMessage(
            session_id=self.session.id,
            user_id=self.user.id,
            role="assistant",
            content="普通聊天回答",
            status="success",
            provider="mock",
            model="mock-model",
        )
        self.db.add(message)
        self.db.commit()
        self.db.refresh(message)

        response = chat_api.submit_message_feedback(
            self.session.id,
            message.id,
            chat_api.MessageFeedbackRequest(rating=1, comment="不准确"),
            self.user,
            self.db,
        )

        self.assertTrue(response["ok"])
        self.assertIsNone(response["knowledge_review_id"])
        self.assertEqual(self.db.query(KnowledgeReview).count(), 0)

    def test_submit_gbrain_think_review_creates_pending_knowledge_review(self):
        user_message = ChatMessage(
            session_id=self.session.id,
            user_id=self.user.id,
            role="user",
            content="/query 用车申请怎么做",
            status="success",
        )
        assistant_message = ChatMessage(
            session_id=self.session.id,
            user_id=self.user.id,
            role="assistant",
            content="用车申请需要先获得审批。",
            status="success",
            provider="gbrain",
            model="gbrain-think-test",
            rag_used=True,
            sources_json=json.dumps(fake_gbrain_think_result()["sources"], ensure_ascii=False),
            context_json=json.dumps(
                {
                    "gbrain_think": {
                        "source_id": "company-wiki",
                        "status": "ok",
                        "model": "gbrain-think-test",
                        "gap_count": 1,
                        "conflict_count": 1,
                        "warning_count": 1,
                        "gaps": ["缺少审批时限。"],
                        "conflicts": ["车辆申请权限在两条规则中不一致。"],
                        "warnings": ["source_scope_limited"],
                        "diagnostics": {"trace_id": "think-trace-1", "pipeline": "think"},
                    }
                },
                ensure_ascii=False,
            ),
        )
        self.db.add_all([user_message, assistant_message])
        self.db.commit()
        self.db.refresh(assistant_message)

        response = chat_api.submit_gbrain_think_review(
            self.session.id,
            assistant_message.id,
            chat_api.GBrainThinkReviewRequest(note="请管理员确认审批时限。"),
            self.user,
            self.db,
        )

        self.assertTrue(response["ok"])
        self.assertTrue(response["created"])
        review = self.db.get(KnowledgeReview, response["knowledge_review_id"])
        self.assertIsNotNone(review)
        assert review is not None
        self.assertEqual(review.status, "pending")
        self.assertEqual(review.source, f"gbrain_think_review:message:{assistant_message.id}")
        self.assertIn("GBrain Think 缺口", review.content)
        self.assertIn("缺少审批时限", review.content)
        self.assertIn("车辆申请权限", review.content)
        self.assertIn("source_scope_limited", review.content)
        self.assertIn("gbrain:company-wiki/rules/用车申请", review.content)
        self.assertIn("请管理员确认审批时限", review.content)
        notification = (
            self.db.query(Notification)
            .filter(Notification.event_key == f"knowledge_review:{review.id}:pending")
            .one()
        )
        self.assertEqual(notification.category, "approval")
        audit = self.db.query(AuditLog).filter(AuditLog.action == "gbrain_think_review_submit").one()
        self.assertIn(f"审核 {review.id}", audit.detail)

        second = chat_api.submit_gbrain_think_review(
            self.session.id,
            assistant_message.id,
            chat_api.GBrainThinkReviewRequest(note="第二次补充"),
            self.user,
            self.db,
        )
        self.assertFalse(second["created"])
        self.assertEqual(second["knowledge_review_id"], review.id)
        self.db.refresh(review)
        self.assertIn("第二次补充", review.content)
        self.assertEqual(
            self.db.query(KnowledgeReview)
            .filter(KnowledgeReview.source == f"gbrain_think_review:message:{assistant_message.id}")
            .count(),
            1,
        )

    def test_submit_gbrain_think_review_rejects_message_without_gap_conflict_warning(self):
        assistant_message = ChatMessage(
            session_id=self.session.id,
            user_id=self.user.id,
            role="assistant",
            content="普通回答",
            status="success",
            provider="gbrain",
            model="gbrain-think-test",
            context_json=json.dumps({"gbrain_think": {"source_id": "company-wiki"}}, ensure_ascii=False),
        )
        self.db.add(assistant_message)
        self.db.commit()
        self.db.refresh(assistant_message)

        with self.assertRaises(HTTPException) as ctx:
            chat_api.submit_gbrain_think_review(
                self.session.id,
                assistant_message.id,
                chat_api.GBrainThinkReviewRequest(),
                self.user,
                self.db,
            )

        self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(self.db.query(KnowledgeReview).count(), 0)

    def test_llm_response_token_cost_maps_to_message_fields(self):
        response = FakeLLMClient().complete([{"role": "user", "content": "hello"}])
        message = ChatMessage(
            session_id=self.session.id,
            user_id=self.user.id,
            role="assistant",
            content=response.text,
            provider=response.provider,
            model=response.model,
            token_input=response.usage["input_tokens"],
            token_output=response.usage["output_tokens"],
            token_total=response.token_cost,
        )

        self.assertEqual(message.content, "mock reply: hello")
        self.assertEqual(message.provider, "mock")
        self.assertEqual(message.model, "mock-model")
        self.assertEqual(message.token_total, 5)

    def test_send_message_persists_user_and_assistant_messages(self):
        response = chat_api.send_message(
            self.session.id,
            chat_api.SendMessageRequest(content="hello"),
            self.user,
            self.db,
        )

        self.assertEqual(response["reply"], "mock reply: hello")
        self.assertEqual(response["provider"], "mock")
        self.assertEqual(response["usage"], {"input_tokens": 2, "output_tokens": 3})

        messages = (
            self.db.query(ChatMessage)
            .filter(ChatMessage.session_id == self.session.id)
            .order_by(ChatMessage.id.asc())
            .all()
        )
        self.assertEqual([message.role for message in messages], ["user", "assistant"])
        self.assertEqual(messages[1].token_total, 5)

        audit = self.db.query(AuditLog).filter(AuditLog.action == "chat").one()
        self.assertTrue(audit.success)
        self.assertEqual(audit.token_cost, 5)

    def test_send_message_does_not_auto_start_skill_from_trigger_text_in_explicit_routing(self):
        client = FakeLLMClient()
        chat_api.get_llm_client = lambda provider=None: client

        response = chat_api.send_message(
            self.session.id,
            chat_api.SendMessageRequest(content="帮我分析客户邮件有没有 VO 风险：Builder 要求无费用变更。"),
            self.user,
            self.db,
        )

        self.assertEqual(response["intent"], "chat")
        self.assertEqual(response["provider"], "mock")
        self.assertIsNone(response["skill_run"])
        self.assertEqual(self.db.query(SkillRun).filter(SkillRun.skill_name == "project-communication-analysis").count(), 0)

    def test_send_message_starts_selected_skill_without_trigger_text(self):
        client = FakeLLMClient()
        chat_api.get_llm_client = lambda provider=None: client

        response = chat_api.send_message(
            self.session.id,
            chat_api.SendMessageRequest(content="先按我下面的资料处理", selected_skill="project-communication-analysis"),
            self.user,
            self.db,
        )

        self.assertEqual(response["intent"], "skill_trigger")
        self.assertEqual(response["provider"], "mock")
        self.assertEqual(response["skill_run"]["skill_name"], "project-communication-analysis")
        self.assertEqual(response["skill_run"]["status"], "completed")
        self.assertEqual(response["agent_run"]["source_type"], "skill")
        self.assertEqual(response["agent_run"]["status"], "completed")
        self.assertEqual(response["context_trace"]["skill"]["skill_name"], "project-communication-analysis")
        history = chat_api.list_messages(self.session.id, limit=50, offset=0, user=self.user, db=self.db)
        assistant = next(item for item in history.items if item.role == "assistant")
        self.assertEqual(assistant.skill_run["skill_name"], "project-communication-analysis")
        self.assertEqual(assistant.skill_run["dispatch"]["mode"], "llm_chat_text")
        message = self.db.query(ChatMessage).filter(ChatMessage.role == "user").one()
        self.assertEqual(message.content, "先按我下面的资料处理")

    def test_send_message_runs_selected_chat_text_skill_with_prompt(self):
        client = FakeLLMClient()
        chat_api.get_llm_client = lambda provider=None: client

        response = chat_api.send_message(
            self.session.id,
            chat_api.SendMessageRequest(
                content="请根据这段背景起草英文回复：客户要求我们承担 delay cost，但我方不接受。",
                selected_skill="client-reply-drafting",
            ),
            self.user,
            self.db,
        )

        self.assertEqual(response["intent"], "skill_trigger")
        self.assertEqual(response["provider"], "mock")
        self.assertEqual(response["skill_run"]["skill_name"], "client-reply-drafting")
        self.assertEqual(response["skill_run"]["status"], "completed")
        self.assertEqual(response["agent_run"]["source_type"], "skill")
        self.assertEqual(response["agent_run"]["status"], "completed")
        self.assertEqual(response["skill_run"]["dispatch"]["mode"], "llm_chat_text")
        self.assertTrue(any(event["event_type"] == "execution_plan" for event in response["agent_run"]["events"]))
        self.assertTrue(
            any(
                event["event_type"] == "tool_call"
                and event["payload"].get("tool") == "llm.complete"
                for event in response["agent_run"]["events"]
            )
        )
        self.assertIn("客户英文回复起草", client.last_system_prompt)
        self.assertIn("Client Reply Drafting Skill", client.last_system_prompt)
        self.assertIn("mock reply", response["reply"])

    def test_send_message_does_not_auto_run_chat_text_skill_from_trigger_text_in_explicit_routing(self):
        client = FakeLLMClient()
        chat_api.get_llm_client = lambda provider=None: client

        response = chat_api.send_message(
            self.session.id,
            chat_api.SendMessageRequest(content="帮我分析客户邮件有没有 VO 风险：Builder 要求无费用变更。"),
            self.user,
            self.db,
        )

        self.assertEqual(response["intent"], "chat")
        self.assertIsNone(response["skill_run"])
        self.assertNotIn("项目沟通风险分析", client.last_system_prompt)
        self.assertNotIn("Project Communication Analysis Skill", client.last_system_prompt)

    def test_send_message_passes_thinking_toggle_to_llm(self):
        client = FakeLLMClient()
        chat_api.get_llm_client = lambda provider=None: client

        chat_api.send_message(
            self.session.id,
            chat_api.SendMessageRequest(content="需要深度分析", thinking=True),
            self.user,
            self.db,
        )

        self.assertTrue(client.last_thinking)

    def test_send_message_runs_web_search_skill_when_enabled(self):
        client = FakeLLMClient()
        chat_api.get_llm_client = lambda provider=None: client
        calls = []

        def fake_web_search(query: str) -> WebSearchResponse:
            calls.append(query)
            return WebSearchResponse(
                query=query,
                provider="test",
                results=[
                    WebSearchResult(
                        title="Project R Search Result",
                        url="https://example.com/project-r",
                        snippet="联网搜索返回的摘要内容。",
                        rank=1,
                        provider="test",
                    )
                ],
            )

        chat_api._run_web_search_skill = fake_web_search

        response = chat_api.send_message(
            self.session.id,
            chat_api.SendMessageRequest(content="查一下 Project_R 当前联网搜索能力", web_search=True),
            self.user,
            self.db,
        )

        self.assertEqual(calls, ["查一下 Project_R 当前联网搜索能力"])
        self.assertEqual(response["sources"][0]["source_title"], "Project R Search Result")
        self.assertEqual(response["sources"][0]["source_file"], "https://example.com/project-r")
        self.assertIn("联网搜索 Skill", client.last_system_prompt)
        self.assertIn("Project R Search Result", client.last_system_prompt)
        self.assertTrue(response["context_trace"]["model"]["web_search"])
        self.assertEqual(response["context_trace"]["web_search"]["skill_name"], "web-search-content")
        self.assertEqual(response["context_trace"]["web_search"]["result_count"], 1)

        assistant = (
            self.db.query(ChatMessage)
            .filter(ChatMessage.session_id == self.session.id, ChatMessage.role == "assistant")
            .order_by(ChatMessage.id.desc())
            .first()
        )
        self.assertTrue(assistant.rag_used)
        self.assertEqual(assistant.sources[0]["source_locator"], "web:test:1")

    def test_send_message_does_not_run_web_search_skill_when_disabled(self):
        client = FakeLLMClient()
        chat_api.get_llm_client = lambda provider=None: client

        def fail_if_called(query: str):
            raise AssertionError("web search should not run when disabled")

        chat_api._run_web_search_skill = fail_if_called

        response = chat_api.send_message(
            self.session.id,
            chat_api.SendMessageRequest(content="普通聊天"),
            self.user,
            self.db,
        )

        self.assertEqual(response["sources"], [])
        self.assertNotIn("联网搜索 Skill", client.last_system_prompt)

    def test_explicit_routing_does_not_auto_generate_document_during_active_skill_collection(self):
        SkillRunner.get().start_run(
            self.db,
            "client-reply-drafting",
            user_id=self.user.id,
            session_id=self.session.id,
        )

        response = chat_api.send_message(
            self.session.id,
            chat_api.SendMessageRequest(content="帮我生成一份会议纪要Word文档"),
            self.user,
            self.db,
        )

        self.assertEqual(response["intent"], "skill_trigger")
        self.assertIsNone(response["generated_file"])
        self.assertIsNotNone(response["skill_run"])
        self.assertEqual(
            self.db.query(SkillRun).filter(SkillRun.status == "collecting_inputs").count(),
            1,
        )

    def test_update_session_persists_pin_state(self):
        updated = chat_api.update_session(
            self.session.id,
            chat_api.UpdateSessionRequest(is_pinned=True),
            self.user,
            self.db,
        )

        self.assertTrue(updated.is_pinned)
        self.assertTrue(self.db.get(ChatSession, self.session.id).is_pinned)

    def test_send_message_passes_session_system_prompt(self):
        client = FakeLLMClient()
        chat_api.get_llm_client = lambda provider=None: client

        chat_api.send_message(
            self.session.id,
            chat_api.SendMessageRequest(content="hello", system_prompt="Use Project_R prompt"),
            self.user,
            self.db,
        )

        self.assertIn("Use Project_R prompt", client.last_system_prompt)
        self.assertIn("输出格式要求", client.last_system_prompt)

    def test_empty_global_base_prompt_does_not_change_system_prompt(self):
        prompt = chat_api._compose_system_prompt("Session prompt", [], None, "")

        self.assertTrue(prompt.startswith("Session prompt"))
        self.assertIn("输出格式要求", prompt)

    def test_global_base_prompt_is_injected_before_session_prompt(self):
        chat_api.GLOBAL_BASE_PROMPT_PATH.write_text("公司全局底层规则：必须服从公司业务逻辑。", encoding="utf-8")
        client = FakeLLMClient()
        chat_api.get_llm_client = lambda provider=None: client

        chat_api.send_message(
            self.session.id,
            chat_api.SendMessageRequest(content="hello", system_prompt="Use Project_R prompt"),
            self.user,
            self.db,
        )

        self.assertTrue(client.last_system_prompt.startswith("公司全局底层规则"))
        self.assertLess(
            client.last_system_prompt.index("公司全局底层规则"),
            client.last_system_prompt.index("Use Project_R prompt"),
        )
        self.assertIn("输出格式要求", client.last_system_prompt)

    def test_send_message_does_not_inject_rag_sources_without_query_command(self):
        client = FakeLLMClient()
        chat_api.get_llm_client = lambda provider=None: client

        response = chat_api.send_message(
            self.session.id,
            chat_api.SendMessageRequest(content="请查询公司规定里的 UI 原则", system_prompt="Base prompt"),
            self.user,
            self.db,
        )

        self.assertEqual(response["intent"], "chat")
        self.assertEqual(response["sources"], [])
        self.assertIn("Base prompt", client.last_system_prompt)
        self.assertNotIn("检索片段：界面必须保持清晰。", client.last_system_prompt)

        assistant = (
            self.db.query(ChatMessage)
            .filter(ChatMessage.session_id == self.session.id, ChatMessage.role == "assistant")
            .order_by(ChatMessage.id.desc())
            .first()
        )
        self.assertFalse(assistant.rag_used)
        self.assertEqual(assistant.sources, [])

    def test_query_command_uses_gbrain_native_think_without_llm(self):
        def fail_if_called(provider=None):
            raise AssertionError("LLM should not be called for /query")

        chat_api.get_llm_client = fail_if_called
        knowledge_sources = FakeKnowledgeSources(
            fake_gbrain_company_sources(),
            think_result=fake_gbrain_think_result(),
        )
        chat_api.KNOWLEDGE_SOURCES = knowledge_sources

        response = chat_api.send_message(
            self.session.id,
            chat_api.SendMessageRequest(content="/query 用车申请怎么做"),
            self.user,
            self.db,
        )

        self.assertEqual(response["intent"], "rag_query")
        self.assertEqual(response["provider"], "gbrain")
        self.assertEqual(response["model"], "gbrain-think-test")
        self.assertIn("用车申请需要先获得审批", response["reply"])
        self.assertEqual(response["sources"][0]["file"], "gbrain:company-wiki/rules/用车申请")
        self.assertEqual(response["agent_run"]["source_type"], "gbrain_think")
        self.assertEqual(response["context_trace"]["gbrain_think"]["gap_count"], 1)
        self.assertEqual(response["context_trace"]["gbrain_think"]["conflict_count"], 1)
        self.assertEqual(response["context_trace"]["gbrain_think"]["warning_count"], 1)
        self.assertIn("缺少审批时限", response["context_trace"]["gbrain_think"]["gaps"][0])
        self.assertIn("车辆申请权限", response["context_trace"]["gbrain_think"]["conflicts"][0])
        self.assertEqual(response["context_trace"]["gbrain_think"]["warnings"], ["source_scope_limited"])
        self.assertEqual(response["context_trace"]["gbrain_think"]["diagnostics"]["trace_id"], "think-trace-1")
        self.assertEqual(response["agent_run"]["result"]["gbrain_think"]["gap_count"], 1)
        self.assertEqual(knowledge_sources.think_calls[0]["content"], "用车申请怎么做")
        self.assertEqual(knowledge_sources.search_calls, [])

    def test_query_command_returns_gbrain_status_when_think_unavailable(self):
        def fail_if_called(provider=None):
            raise AssertionError("LLM should not be called when GBrain think is unavailable")

        chat_api.get_llm_client = fail_if_called
        knowledge_sources = FakeKnowledgeSources(fake_gbrain_company_sources())
        chat_api.KNOWLEDGE_SOURCES = knowledge_sources

        response = chat_api.send_message(
            self.session.id,
            chat_api.SendMessageRequest(content="/query 用车申请怎么做"),
            self.user,
            self.db,
        )

        self.assertEqual(response["intent"], "rag_query")
        self.assertEqual(response["provider"], "gbrain")
        self.assertEqual(response["model"], "think-unavailable")
        self.assertIn("GBrain think disabled", response["reply"])
        self.assertEqual(response["agent_run"]["source_type"], "gbrain_think")
        self.assertEqual(response["agent_run"]["status"], "failed")
        self.assertEqual(response["sources"], [])
        self.assertEqual(knowledge_sources.think_calls[0]["content"], "用车申请怎么做")
        self.assertEqual(knowledge_sources.search_calls, [])
        self.assertEqual(response["context_trace"]["gbrain_source_id"], "company-wiki")

    def test_plain_chat_does_not_inject_empty_knowledge_constraint(self):
        client = FakeLLMClient()
        chat_api.get_llm_client = lambda provider=None: client

        chat_api.send_message(
            self.session.id,
            chat_api.SendMessageRequest(content="你好，帮我解释一下这句话"),
            self.user,
            self.db,
        )

        self.assertIn("输出格式要求", client.last_system_prompt)
        self.assertNotIn("知识库中未检索到", client.last_system_prompt)

    def test_text_transformation_prompt_skips_knowledge_context(self):
        client = FakeLLMClient()
        chat_api.get_llm_client = lambda provider=None: client

        response = chat_api.send_message(
            self.session.id,
            chat_api.SendMessageRequest(
                content=(
                    "这些文件是门窗幕墙强相关的规范，还是澳洲建筑规范中和门窗幕墙沾了一点点？\n"
                    "我想我们需要再甄别一下收集回来的文件。"
                ),
                system_prompt="纯文本改写提示词",
                selected_prompt_id="company:company-work-message-polish",
            ),
            self.user,
            self.db,
        )

        self.assertEqual(response["intent"], "chat")
        self.assertEqual(response["sources"], [])
        self.assertIn("纯文本改写提示词", client.last_system_prompt)
        self.assertIn("文本变换类提示词", client.last_system_prompt)
        self.assertNotIn("当员工因公需借用公司车辆", client.last_system_prompt)
        self.assertNotIn("知识库中未检索到", client.last_system_prompt)

    def test_query_command_overrides_text_transformation_prompt_rag_reduction(self):
        def fail_if_called(provider=None):
            raise AssertionError("LLM should not be called for /query even when a text prompt is selected")

        chat_api.get_llm_client = fail_if_called
        chat_api.KNOWLEDGE_SOURCES = FakeKnowledgeSources(think_result=fake_gbrain_think_result())

        response = chat_api.send_message(
            self.session.id,
            chat_api.SendMessageRequest(
                content="/query 如何借用公司车辆",
                selected_prompt_id="company:company-work-message-polish",
            ),
            self.user,
            self.db,
        )

        self.assertEqual(response["intent"], "rag_query")
        self.assertEqual(response["provider"], "gbrain")
        self.assertIn("用车申请需要先获得审批", response["reply"])

    def test_query_command_forces_knowledge_mode(self):
        def fail_if_called(provider=None):
            raise AssertionError("LLM should not be called for /query")

        chat_api.get_llm_client = fail_if_called

        response = chat_api.send_message(
            self.session.id,
            chat_api.SendMessageRequest(content="/query 一个完全没有命中的问题"),
            self.user,
            self.db,
        )

        self.assertEqual(response["intent"], "rag_query")
        self.assertEqual(response["provider"], "gbrain")
        self.assertEqual(response["model"], "think-unavailable")

    def test_document_generation_text_stays_chat_without_explicit_route(self):
        response = chat_api.send_message(
            self.session.id,
            chat_api.SendMessageRequest(content="帮我生成一份会议纪要 Word"),
            self.user,
            self.db,
        )

        generated = response["generated_file"]
        self.assertEqual(response["intent"], "chat")
        self.assertIsNone(generated)

    def test_convert_previous_notice_to_word_stays_chat_without_explicit_route(self):
        self.db.add(
            ChatMessage(
                session_id=self.session.id,
                user_id=self.user.id,
                role="assistant",
                content="```text\n【病假通知】\n请假人：[你的名字]\n```",
                status="success",
            )
        )
        self.db.commit()

        response = chat_api.send_message(
            self.session.id,
            chat_api.SendMessageRequest(content="帮我将通知正式转为word文档,供我下载"),
            self.user,
            self.db,
        )

        self.assertEqual(response["intent"], "chat")
        self.assertIsNone(response["generated_file"])

    def test_user_isolation_blocks_other_users(self):
        other = User(username="other", password_hash="hash", role="employee", nickname="Other")
        self.db.add(other)
        self.db.commit()
        self.db.refresh(other)

        with self.assertRaises(HTTPException) as exc:
            chat_api.get_session(self.session.id, other, self.db)

        self.assertEqual(exc.exception.status_code, 404)

    def test_create_session_assigns_workspace_when_user_is_member(self):
        workspace = Workspace(name="Design", slug="design", created_by=self.user.id)
        self.db.add(workspace)
        self.db.commit()
        self.db.refresh(workspace)
        self.db.add(WorkspaceMember(workspace_id=workspace.id, user_id=self.user.id, role="admin"))
        self.db.commit()

        session = chat_api.create_session(
            chat_api.CreateSessionRequest(title="Workspace chat", workspace_id=workspace.id),
            self.user,
            self.db,
        )

        self.assertEqual(session.workspace_id, workspace.id)

    def test_create_session_allows_open_project_for_non_member_employee(self):
        employee = User(username="employee-open-project", password_hash="hash", role="employee", nickname="Employee")
        workspace = Workspace(name="Open", slug="open", created_by=self.user.id, workspace_kind="project", is_hidden=False)
        self.db.add_all([employee, workspace])
        self.db.commit()
        self.db.refresh(employee)
        self.db.refresh(workspace)

        session = chat_api.create_session(
            chat_api.CreateSessionRequest(title="Open project chat", workspace_id=workspace.id),
            employee,
            self.db,
        )

        self.assertEqual(session.workspace_id, workspace.id)

    def test_audio_transcription_skill_processes_audio_attachment(self):
        audio_path = Path(self.generated_root.name) / "sample.mp3"
        audio_path.write_bytes(b"fake mp3 bytes")
        attachment = SessionAttachment(
            session_id=self.session.id,
            user_id=self.user.id,
            original_name="sample.mp3",
            stored_path=str(audio_path),
            content_type="audio/mpeg",
            size=audio_path.stat().st_size,
            source_scope="project",
            source_label="项目资料引用",
            authorization_status="uploaded",
        )
        self.db.add(attachment)
        self.db.commit()
        self.db.refresh(attachment)
        transcription_result = SimpleNamespace(text="这是模拟转录文本。")

        with patch("core.tools.media_transcription_tool.run_media_transcription_tool", return_value=transcription_result):
            response = chat_api.send_message(
                self.session.id,
                chat_api.SendMessageRequest(
                    content="将这段录音转录成文字",
                    files=[str(attachment.id)],
                    selected_skill="audio-transcription",
                ),
                self.user,
                self.db,
            )

        self.assertEqual(response["intent"], "skill_trigger")
        self.assertIn("已完成录音转文字", response["reply"])
        self.assertIn("```text", response["reply"])
        self.assertIn("这是模拟转录文本。", response["reply"])
        self.assertEqual(response["skill_run"]["skill_name"], "audio-transcription")

    def test_audio_transcription_skill_without_audio_gives_actionable_instruction(self):
        response = chat_api.send_message(
            self.session.id,
            chat_api.SendMessageRequest(
                content="将这段录音转录成文字",
                selected_skill="audio-transcription",
            ),
            self.user,
            self.db,
        )

        self.assertEqual(response["intent"], "skill_trigger")
        self.assertIn("请先在当前会话上传或从项目文件中引用一个音频/视频文件", response["reply"])
        self.assertIn("```text", response["reply"])
        self.assertEqual(response["skill_run"]["skill_name"], "audio-transcription")

    def test_update_session_blocks_hidden_workspace_for_non_member(self):
        employee = User(username="employee-hidden-project", password_hash="hash", role="employee", nickname="Employee")
        workspace = Workspace(name="Locked", slug="locked", created_by=self.user.id, workspace_kind="project", is_hidden=True)
        self.db.add(employee)
        self.db.add(workspace)
        self.db.commit()
        self.db.refresh(employee)
        self.db.refresh(workspace)
        session = ChatSession(user_id=employee.id, title="Employee session")
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)

        with self.assertRaises(HTTPException) as exc:
            chat_api.update_session(
                session.id,
                chat_api.UpdateSessionRequest(workspace_id=workspace.id),
                employee,
                self.db,
            )

        self.assertEqual(exc.exception.status_code, 403)

    def test_delete_session_deletes_messages_and_blocks_future_access(self):
        chat_api.send_message(
            self.session.id,
            chat_api.SendMessageRequest(content="hello"),
            self.user,
            self.db,
        )

        response = chat_api.delete_session(self.session.id, self.user, self.db)

        self.assertEqual(response, {"ok": True})
        self.assertEqual(
            self.db.query(ChatMessage).filter(ChatMessage.session_id == self.session.id).count(),
            0,
        )
        with self.assertRaises(HTTPException) as exc:
            chat_api.get_session(self.session.id, self.user, self.db)
        self.assertEqual(exc.exception.status_code, 404)

    def test_llm_failure_keeps_user_message_and_writes_failed_audit(self):
        chat_api.get_llm_client = lambda provider=None: FakeLLMClient(should_fail=True)

        with self.assertRaises(HTTPException) as exc:
            chat_api.send_message(
                self.session.id,
                chat_api.SendMessageRequest(content="please fail"),
                self.user,
                self.db,
            )

        self.assertEqual(exc.exception.status_code, 503)
        self.assertEqual(exc.exception.detail, "AI 服务暂时不可用，请稍后重试")
        messages = (
            self.db.query(ChatMessage)
            .filter(ChatMessage.session_id == self.session.id)
            .order_by(ChatMessage.id.asc())
            .all()
        )
        self.assertEqual([message.role for message in messages], ["user", "assistant"])
        self.assertEqual(messages[0].content, "please fail")
        self.assertEqual(messages[1].status, "failed")
        self.assertNotIn("sk-", messages[1].error_message or "")

        audit = self.db.query(AuditLog).filter(AuditLog.action == "chat").one()
        self.assertFalse(audit.success)


if __name__ == "__main__":
    unittest.main()
