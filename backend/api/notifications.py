from datetime import datetime, timezone
import json

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session

from api.auth import get_current_user
from app.shared.time.schemas import UTCDateTimeModel
from app.features.notifications.service import notify_system_risk_alert
from models import get_db
from models.notification import Notification
from models.user import User

router = APIRouter(prefix="/notifications", tags=["notifications"])


class NotificationResponse(UTCDateTimeModel):
    id: int
    type: str
    category: str
    severity: str
    title: str
    content: str
    is_read: bool
    action_status: str
    action_kind: str
    action_payload: dict
    event_key: str
    link: str
    created_at: datetime
    expires_at: datetime | None


class NotificationsListResponse(BaseModel):
    items: list[NotificationResponse]
    unread_count: int
    pending_count: int


class NotificationCountsResponse(BaseModel):
    unread_count: int
    pending_count: int


class UpdateActionStatusRequest(BaseModel):
    status: str


class CreateRiskAlertRequest(BaseModel):
    title: str
    content: str = ""
    event_key: str | None = None


def _payload_to_dict(raw: str) -> dict:
    try:
        parsed = json.loads(raw or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def _to_response(notification: Notification) -> NotificationResponse:
    return NotificationResponse(
        id=notification.id,
        type=notification.type,
        category=notification.category,
        severity=notification.severity,
        title=notification.title,
        content=notification.content,
        is_read=notification.is_read,
        action_status=notification.action_status,
        action_kind=notification.action_kind,
        action_payload=_payload_to_dict(notification.action_payload_json),
        event_key=notification.event_key,
        link=notification.link,
        created_at=notification.created_at,
        expires_at=notification.expires_at,
    )


def _active_user_notifications(db: Session, user_id: int):
    now = datetime.now(timezone.utc)
    return db.query(Notification).filter(
        Notification.user_id == user_id,
        or_(Notification.expires_at.is_(None), Notification.expires_at > now),
    )


def _counts(query) -> NotificationCountsResponse:
    return NotificationCountsResponse(
        unread_count=query.filter(Notification.is_read == False).count(),
        pending_count=query.filter(Notification.action_status == "pending").count(),
    )


@router.get("/counts", response_model=NotificationCountsResponse)
def notification_counts(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return _counts(_active_user_notifications(db, user.id))


@router.get("/unread-count", response_model=NotificationCountsResponse)
def unread_count(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return _counts(_active_user_notifications(db, user.id))


@router.get("", response_model=NotificationsListResponse)
def list_notifications(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    view: str = Query(default="all"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    base_query = _active_user_notifications(db, user.id)
    counts = _counts(base_query)
    query = base_query
    if view == "unread":
        query = query.filter(Notification.is_read == False)
    elif view == "pending":
        query = query.filter(Notification.action_status == "pending")
    elif view != "all":
        raise HTTPException(status_code=400, detail="通知筛选不合法")

    items = (
        query.order_by(Notification.created_at.desc(), Notification.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return NotificationsListResponse(
        items=[_to_response(item) for item in items],
        unread_count=counts.unread_count,
        pending_count=counts.pending_count,
    )


@router.post("/read-all")
def mark_all_read(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _active_user_notifications(db, user.id).filter(Notification.is_read == False).update({"is_read": True})
    db.commit()
    return {"ok": True}


@router.post("/risk-alerts")
def create_risk_alert(
    req: CreateRiskAlertRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="仅管理员可操作")
    title = req.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="告警标题不能为空")
    notifications = notify_system_risk_alert(
        db,
        title=title,
        content=req.content.strip(),
        event_key=req.event_key,
    )
    db.commit()
    return {"ok": True, "created": len(notifications)}


@router.post("/{notification_id}/read")
def mark_read(
    notification_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    notification = (
        db.query(Notification)
        .filter(Notification.id == notification_id, Notification.user_id == user.id)
        .first()
    )
    if not notification:
        raise HTTPException(status_code=404, detail="通知不存在")
    notification.is_read = True
    db.commit()
    return {"ok": True}


@router.post("/{notification_id}/action-status")
def update_action_status(
    notification_id: int,
    req: UpdateActionStatusRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if req.status not in {"done", "dismissed"}:
        raise HTTPException(status_code=400, detail="待办状态不合法")
    notification = (
        db.query(Notification)
        .filter(Notification.id == notification_id, Notification.user_id == user.id)
        .first()
    )
    if not notification:
        raise HTTPException(status_code=404, detail="通知不存在")
    if notification.action_status != "pending":
        raise HTTPException(status_code=400, detail="该通知不是待处理通知")
    if req.status == "dismissed" and notification.severity == "critical":
        raise HTTPException(status_code=400, detail="严重风险通知不能直接忽略")
    notification.action_status = req.status
    notification.is_read = True
    db.commit()
    return {"ok": True}


@router.delete("/cleanup")
def cleanup_expired_notifications(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="仅管理员可操作")
    now = datetime.now(timezone.utc)
    removed = (
        db.query(Notification)
        .filter(
            Notification.expires_at.is_not(None),
            Notification.expires_at <= now,
            Notification.is_read == True,
            Notification.action_status.in_(["none", "done", "dismissed"]),
        )
        .delete(synchronize_session=False)
    )
    db.commit()
    return {"ok": True, "removed": removed}
