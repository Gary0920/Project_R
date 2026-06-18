from __future__ import annotations

from datetime import datetime, timedelta, timezone


PROJECT_R_TIMEZONE_NAME = "Asia/Shanghai"
PROJECT_R_TIMEZONE = timezone(timedelta(hours=8), PROJECT_R_TIMEZONE_NAME)


def project_r_now(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(PROJECT_R_TIMEZONE)
    if now.tzinfo is None:
        return now.replace(tzinfo=PROJECT_R_TIMEZONE)
    return now.astimezone(PROJECT_R_TIMEZONE)


def project_r_current_date(now: datetime | None = None) -> str:
    return project_r_now(now).strftime("%Y-%m-%d")


def current_time_prompt(now: datetime | None = None) -> str:
    return (
        "当前时间上下文："
        f"今天是 {project_r_current_date(now)}，时区为 {PROJECT_R_TIMEZONE_NAME}。"
        "当用户使用“今天、昨天、明天、最近三天、本周、本月”等相对时间表达时，"
        "必须先按当前日期换算为具体日期范围，再回答。"
    )
