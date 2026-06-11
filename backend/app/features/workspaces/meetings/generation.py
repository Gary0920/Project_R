from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import HTTPException

from app.features.workspaces.meetings.markdown import (
    MEETING_SYSTEM_PROMPT,
    build_actions_prompt,
    build_fallback_actions,
    build_fallback_minutes,
    build_minutes_prompt,
)
from app.shared.time.utils import serialize_datetime_utc


@dataclass(frozen=True)
class MeetingGenerationResult:
    minutes_md: str
    actions_md: str
    model_used: str
    token_input: int
    token_output: int

    @property
    def token_cost(self) -> int:
        return self.token_input + self.token_output


def generate_meeting_markdowns(
    *,
    transcript_text: str,
    speaker_map_text: str,
    term_corrections_text: str,
    auxiliary_summaries_text: str,
    meeting_type: str,
) -> MeetingGenerationResult:
    try:
        from app.shared.llm.client import get_llm_client

        minutes_prompt = build_minutes_prompt(
            transcript_text,
            speaker_map_text,
            term_corrections_text,
            auxiliary_summaries_text,
            meeting_type=meeting_type,
        )
        actions_prompt = build_actions_prompt(
            transcript_text,
            speaker_map_text,
            term_corrections_text,
            auxiliary_summaries_text,
        )

        client = get_llm_client("deepseek-flash")

        minutes_response = client.complete(
            [{"role": "user", "content": minutes_prompt}],
            system_prompt=MEETING_SYSTEM_PROMPT,
            temperature=0.3,
        )
        actions_response = client.complete(
            [{"role": "user", "content": actions_prompt}],
            system_prompt=MEETING_SYSTEM_PROMPT,
            temperature=0.3,
        )

        minutes_usage = minutes_response.usage or {}
        actions_usage = actions_response.usage or {}
        return MeetingGenerationResult(
            minutes_md=minutes_response.text.strip() if minutes_response.text else "",
            actions_md=actions_response.text.strip() if actions_response.text else "",
            model_used="deepseek-flash",
            token_input=minutes_usage.get("input_tokens", 0) + actions_usage.get("input_tokens", 0),
            token_output=minutes_usage.get("output_tokens", 0) + actions_usage.get("output_tokens", 0),
        )
    except HTTPException:
        raise
    except Exception as exc:
        now_ts = serialize_datetime_utc(datetime.now(timezone.utc))
        return MeetingGenerationResult(
            minutes_md=build_fallback_minutes(transcript_text, now_ts, str(exc)),
            actions_md=build_fallback_actions(now_ts),
            model_used="template-fallback",
            token_input=0,
            token_output=0,
        )
