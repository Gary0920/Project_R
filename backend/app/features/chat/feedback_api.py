from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import uuid

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.features.chat.access import get_user_session
from app.features.chat.schemas import (
    GBrainThinkReviewRequest,
    MessageFeedbackRequest,
)
from app.features.notifications.service import notify_knowledge_review_pending
from app.shared.time.utils import serialize_datetime_utc
from models.audit_log import AuditLog
from models.knowledge_review import KnowledgeReview
from models.message import ChatMessage
from models.session import ChatSession
from models.user import User


def submit_message_feedback(
    db: Session,
    session_id: int,
    message_id: int,
    req: MessageFeedbackRequest,
    user: User,
    *,
    feedback_root: Path,
    answer_correction_rating_threshold: int,
    answer_correction_review_prefix: str,
) -> dict:
    session = get_user_session(db, user.id, session_id)
    message = _assistant_message(db, user.id, session_id, message_id)
    comment = req.comment.strip()[:2000]
    feedback = write_message_feedback(feedback_root, user, message, req.rating, comment)
    correction_review = maybe_create_answer_correction_review(
        db,
        user=user,
        session=session,
        message=message,
        rating=req.rating,
        comment=comment,
        feedback_id=feedback["feedback_id"],
        answer_correction_rating_threshold=answer_correction_rating_threshold,
        answer_correction_review_prefix=answer_correction_review_prefix,
    )
    db.add(
        AuditLog(
            user_id=user.id,
            action="message_feedback",
            detail=(
                f"会话 {session_id} 回答 {message_id} 评分 {req.rating}/5"
                + (f"，生成知识纠错审核 {correction_review.id}" if correction_review else "")
            ),
            success=True,
        )
    )
    db.commit()
    return {
        "ok": True,
        "feedback_id": feedback["feedback_id"],
        "rating": req.rating,
        "comment": comment,
        "created_at": feedback["created_at"],
        "knowledge_review_id": correction_review.id if correction_review else None,
        "knowledge_review_status": correction_review.status if correction_review else None,
    }


def submit_gbrain_think_review(
    db: Session,
    session_id: int,
    message_id: int,
    req: GBrainThinkReviewRequest,
    user: User,
    *,
    gbrain_think_review_prefix: str,
) -> dict:
    session = get_user_session(db, user.id, session_id)
    message = _assistant_message(db, user.id, session_id, message_id, not_found_detail="可提交审核的 GBrain 回答不存在")
    review, created = create_gbrain_think_review(
        db,
        user=user,
        session=session,
        message=message,
        note=req.note.strip()[:2000],
        gbrain_think_review_prefix=gbrain_think_review_prefix,
    )
    if not review:
        raise HTTPException(status_code=400, detail="该回答没有可提交审核的 GBrain 缺口、冲突或警告")
    db.add(
        AuditLog(
            user_id=user.id,
            action="gbrain_think_review_submit",
            detail=f"会话 {session_id} 回答 {message_id} 提交 GBrain gap/conflict 审核 {review.id}",
            success=True,
        )
    )
    db.commit()
    return {
        "ok": True,
        "knowledge_review_id": review.id,
        "knowledge_review_status": review.status,
        "created": created,
    }


def _assistant_message(
    db: Session,
    user_id: int,
    session_id: int,
    message_id: int,
    *,
    not_found_detail: str = "可评分的回答不存在",
) -> ChatMessage:
    message = (
        db.query(ChatMessage)
        .filter(
            ChatMessage.session_id == session_id,
            ChatMessage.user_id == user_id,
            ChatMessage.id == message_id,
            ChatMessage.role == "assistant",
        )
        .first()
    )
    if not message:
        raise HTTPException(status_code=404, detail=not_found_detail)
    return message


def feedback_message_dir(feedback_root: Path, message: ChatMessage) -> Path:
    return feedback_root / f"user_{message.user_id}" / f"session_{message.session_id}" / f"message_{message.id}"


def write_message_feedback(feedback_root: Path, user: User, message: ChatMessage, rating: int, comment: str) -> dict:
    created_at = datetime.now(timezone.utc)
    feedback_id = f"{created_at.strftime('%Y%m%dT%H%M%S%fZ')}-{uuid.uuid4().hex[:8]}"
    payload = {
        "schema_version": 1,
        "feedback_id": feedback_id,
        "created_at": serialize_datetime_utc(created_at),
        "rating": rating,
        "comment": comment,
        "user": {
            "id": user.id,
            "username": user.username,
            "nickname": user.nickname,
        },
        "message": {
            "id": message.id,
            "session_id": message.session_id,
            "role": message.role,
            "provider": message.provider,
            "model": message.model,
            "version_group_id": message.version_group_id,
            "version_index": message.version_index,
            "content_excerpt": message.content[:1200],
        },
        "sources": message.sources,
        "intended_use": "ai_prompt_and_skill_iteration",
    }
    target_dir = feedback_message_dir(feedback_root, message)
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / f"{feedback_id}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return payload


def maybe_create_answer_correction_review(
    db: Session,
    *,
    user: User,
    session: ChatSession,
    message: ChatMessage,
    rating: int,
    comment: str,
    feedback_id: str,
    answer_correction_rating_threshold: int,
    answer_correction_review_prefix: str,
) -> KnowledgeReview | None:
    if rating > answer_correction_rating_threshold:
        return None
    gbrain_sources = gbrain_sources_for_message(message)
    if not gbrain_sources:
        return None

    source = f"{answer_correction_review_prefix}{message.id}"
    question = previous_user_message_content(db, message)
    content = build_answer_correction_review_content(
        user=user,
        session=session,
        message=message,
        rating=rating,
        comment=comment,
        feedback_id=feedback_id,
        question=question,
        sources=gbrain_sources,
    )
    review = (
        db.query(KnowledgeReview)
        .filter(KnowledgeReview.source == source, KnowledgeReview.status == "pending")
        .order_by(KnowledgeReview.created_at.desc(), KnowledgeReview.id.desc())
        .first()
    )
    if review:
        review.content = content
    else:
        review = KnowledgeReview(submitter_id=user.id, content=content, source=source)
        db.add(review)
    db.flush()
    notify_knowledge_review_pending(db, review_id=review.id, source=source)
    return review


def create_gbrain_think_review(
    db: Session,
    *,
    user: User,
    session: ChatSession,
    message: ChatMessage,
    note: str,
    gbrain_think_review_prefix: str,
) -> tuple[KnowledgeReview | None, bool]:
    trace = message.context_trace
    gbrain_think = trace.get("gbrain_think") if isinstance(trace.get("gbrain_think"), dict) else {}
    gaps = safe_trace_list(gbrain_think.get("gaps"))
    conflicts = safe_trace_list(gbrain_think.get("conflicts"))
    warnings = safe_trace_list(gbrain_think.get("warnings"))
    if not (gaps or conflicts or warnings):
        return None, False

    source = f"{gbrain_think_review_prefix}{message.id}"
    content = build_gbrain_think_review_content(
        user=user,
        session=session,
        message=message,
        note=note,
        question=previous_user_message_content(db, message),
        sources=gbrain_sources_for_message(message),
        gbrain_think=gbrain_think,
        gaps=gaps,
        conflicts=conflicts,
        warnings=warnings,
    )
    review = (
        db.query(KnowledgeReview)
        .filter(KnowledgeReview.source == source, KnowledgeReview.status == "pending")
        .order_by(KnowledgeReview.created_at.desc(), KnowledgeReview.id.desc())
        .first()
    )
    created = review is None
    if review:
        review.content = content
    else:
        review = KnowledgeReview(submitter_id=user.id, content=content, source=source)
        db.add(review)
    db.flush()
    notify_knowledge_review_pending(db, review_id=review.id, source=source)
    return review, created


def gbrain_sources_for_message(message: ChatMessage) -> list[dict]:
    sources = []
    for source in message.sources:
        if not isinstance(source, dict):
            continue
        file_ref = str(source.get("file") or "")
        source_type = str(source.get("type") or "")
        tags = str(source.get("tags") or "")
        if file_ref.startswith("gbrain:") or source_type.startswith("gbrain") or "gbrain" in tags.lower():
            sources.append(source)
    return sources


def previous_user_message_content(db: Session, message: ChatMessage) -> str:
    previous = (
        db.query(ChatMessage)
        .filter(
            ChatMessage.session_id == message.session_id,
            ChatMessage.user_id == message.user_id,
            ChatMessage.role == "user",
            ChatMessage.id < message.id,
        )
        .order_by(ChatMessage.id.desc())
        .first()
    )
    return previous.content if previous else ""


def build_answer_correction_review_content(
    *,
    user: User,
    session: ChatSession,
    message: ChatMessage,
    rating: int,
    comment: str,
    feedback_id: str,
    question: str,
    sources: list[dict],
) -> str:
    source_lines = []
    for index, source in enumerate(sources, start=1):
        source_lines.append(
            "\n".join(
                [
                    f"{index}. `{safe_review_text(str(source.get('file') or 'gbrain'))}`",
                    f"   - 标题 / Title: {safe_review_text(str(source.get('source_title') or ''))}",
                    f"   - 位置 / Path: {safe_review_text(str(source.get('section_path') or ''))}",
                    f"   - 摘录 / Excerpt: {safe_review_text(str(source.get('content') or ''), 500)}",
                ]
            )
        )
    source_block = "\n".join(source_lines)
    comment_text = comment or "用户未填写补充意见。 / No additional user comment."
    question_text = question or "未找到上一条用户问题。 / Previous user question was not found."
    return (
        "# 知识纠错候选 / Knowledge Correction Candidate\n\n"
        "> 本候选来自用户对带 GBrain 引用回答的低分反馈。管理员需要判断问题属于事实错误、来源过期、引用缺失、资料冲突，还是回答组织问题；"
        "审核通过前应改写为可沉淀的中英文对齐知识，不应把未核实反馈直接作为事实。\n\n"
        "> This candidate comes from low-rated feedback on an answer with GBrain citations. Before approval, an administrator must decide whether the issue is a factual error, stale source, missing citation, source conflict, or answer-composition problem, then rewrite it as verified bilingual knowledge.\n\n"
        "## 反馈元数据 / Feedback Metadata\n\n"
        f"- feedback_id: `{feedback_id}`\n"
        f"- rating: {rating}/5\n"
        f"- user: `{user.username}` / `{user.nickname}`\n"
        f"- session_id: {session.id}\n"
        f"- workspace_id: {session.workspace_id if session.workspace_id is not None else 'company-wiki'}\n"
        f"- assistant_message_id: {message.id}\n"
        f"- model: `{message.provider or ''}:{message.model or ''}`\n\n"
        "## 用户反馈 / User Feedback\n\n"
        f"- 中文：{safe_review_text(comment_text)}\n"
        f"- English: Same user feedback text for review: {safe_review_text(comment_text)}\n\n"
        "## 原问题 / Original Question\n\n"
        f"{safe_review_text(question_text, 1200)}\n\n"
        "## 原回答摘录 / Answer Excerpt\n\n"
        f"{safe_review_text(message.content, 1600)}\n\n"
        "## GBrain 引用来源 / GBrain Citations\n\n"
        f"{source_block}\n\n"
        "## 管理员处理建议 / Admin Triage Guidance\n\n"
        "- 中文：如果只是引用格式或缺少引用，优先后续调用 GBrain citation-fixer；如果是资料冲突，进入 contradiction review；如果是原始知识错误或过期，审核后沉淀修正知识。\n"
        "- English: If the issue is only citation formatting or missing citation, prefer a later GBrain citation-fixer task. If sources conflict, route it to contradiction review. If the underlying knowledge is wrong or stale, approve a verified correction into the knowledge base.\n"
    )


def build_gbrain_think_review_content(
    *,
    user: User,
    session: ChatSession,
    message: ChatMessage,
    note: str,
    question: str,
    sources: list[dict],
    gbrain_think: dict,
    gaps: list[str],
    conflicts: list[str],
    warnings: list[str],
) -> str:
    source_lines = []
    for index, source in enumerate(sources, start=1):
        source_lines.append(
            "\n".join(
                [
                    f"{index}. `{safe_review_text(str(source.get('file') or 'gbrain'))}`",
                    f"   - 标题 / Title: {safe_review_text(str(source.get('source_title') or ''))}",
                    f"   - 位置 / Path: {safe_review_text(str(source.get('section_path') or ''))}",
                    f"   - 摘录 / Excerpt: {safe_review_text(str(source.get('content') or ''), 500)}",
                ]
            )
        )
    source_block = "\n".join(source_lines) or "- 无引用来源 / No citation source."
    question_text = question or "未找到上一条用户问题。 / Previous user question was not found."
    note_text = note or "用户未补充说明。 / No additional user note."
    gap_block = "\n".join(f"- {item}" for item in gaps) or "- 无 / None"
    conflict_block = "\n".join(f"- {item}" for item in conflicts) or "- 无 / None"
    warning_block = "\n".join(f"- {item}" for item in warnings) or "- 无 / None"
    diagnostics = gbrain_think.get("diagnostics") if isinstance(gbrain_think.get("diagnostics"), dict) else {}
    return (
        "# GBrain Think 缺口 / 冲突审核候选\n\n"
        "> 本候选来自 GBrain Think 在回答时返回的 gap/conflict/warning。管理员需要判断它是资料缺失、资料冲突、检索范围问题，还是回答组织问题；"
        "审核通过前不得把未核实的 gap/conflict 直接写成事实。\n\n"
        "> This candidate comes from GBrain Think gaps/conflicts/warnings. Before approval, an administrator must decide whether it indicates missing knowledge, conflicting sources, retrieval scope issues, or answer-composition issues. Do not turn unverified gaps/conflicts into facts.\n\n"
        "## 元数据 / Metadata\n\n"
        f"- user: `{user.username}` / `{user.nickname}`\n"
        f"- session_id: {session.id}\n"
        f"- workspace_id: {session.workspace_id if session.workspace_id is not None else 'company-wiki'}\n"
        f"- assistant_message_id: {message.id}\n"
        f"- source_id: `{safe_review_text(str(gbrain_think.get('source_id') or ''))}`\n"
        f"- status: `{safe_review_text(str(gbrain_think.get('status') or ''))}`\n"
        f"- model: `{safe_review_text(str(gbrain_think.get('model') or message.model or ''))}`\n"
        f"- trace_id: `{safe_review_text(str(diagnostics.get('trace_id') or ''))}`\n\n"
        "## 用户补充 / User Note\n\n"
        f"- 中文：{safe_review_text(note_text)}\n"
        f"- English: Same user note for review: {safe_review_text(note_text)}\n\n"
        "## 原问题 / Original Question\n\n"
        f"{safe_review_text(question_text, 1200)}\n\n"
        "## 原回答摘录 / Answer Excerpt\n\n"
        f"{safe_review_text(message.content, 1600)}\n\n"
        "## GBrain 缺口 / Gaps\n\n"
        f"{safe_review_text(gap_block, 1600)}\n\n"
        "## GBrain 冲突 / Conflicts\n\n"
        f"{safe_review_text(conflict_block, 1600)}\n\n"
        "## GBrain 警告 / Warnings\n\n"
        f"{safe_review_text(warning_block, 1600)}\n\n"
        "## GBrain 引用来源 / GBrain Citations\n\n"
        f"{source_block}\n\n"
        "## 管理员处理建议 / Admin Triage Guidance\n\n"
        "- 中文：资料缺失时补充经验证知识；资料冲突时进入 contradiction review；引用格式问题可调用 citation-fixer；检索范围问题应先检查 source scope 和权限。\n"
        "- English: Add verified knowledge for real gaps; route source conflicts to contradiction review; use citation-fixer for citation-format issues; check source scope and permissions for retrieval-scope issues.\n"
    )


def safe_review_text(value: str, limit: int = 2000) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) > limit:
        return text[:limit].rstrip() + "..."
    return text


def safe_trace_list(value: object, *, limit: int = 6, item_limit: int = 220) -> list[str]:
    if not isinstance(value, list):
        return []
    items: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text:
            items.append(text[:item_limit])
        if len(items) >= limit:
            break
    return items


def load_latest_message_feedback(feedback_root: Path, message: ChatMessage) -> dict | None:
    target_dir = feedback_message_dir(feedback_root, message)
    if not target_dir.exists():
        return None
    files = sorted(target_dir.glob("*.json"), key=lambda path: path.name, reverse=True)
    if not files:
        return None
    try:
        payload = json.loads(files[0].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None
