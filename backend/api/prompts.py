from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
import yaml

from api.auth import get_current_user
from app.shared.time.schemas import UTCDateTimeModel
from models.user import User

router = APIRouter(prefix="/prompts", tags=["prompts"])

BASE_DIR = Path(__file__).resolve().parent.parent
PROMPT_PRESET_DIR = BASE_DIR / "prompt_presets"
COMPANY_PROMPT_DIR = PROMPT_PRESET_DIR / "company"


class CompanyPromptResponse(UTCDateTimeModel):
    id: str
    name: str
    description: str
    content: str
    updated_at: datetime


def _parse_markdown_prompt(path: Path) -> CompanyPromptResponse | None:
    raw = path.read_text(encoding="utf-8")
    metadata: dict[str, Any] = {}
    body = raw

    if raw.startswith("---"):
        parts = raw.split("---", 2)
        if len(parts) == 3:
            parsed = yaml.safe_load(parts[1]) or {}
            if isinstance(parsed, dict):
                metadata = parsed
            body = parts[2]

    content = _extract_prompt_content(body)
    prompt_id = str(metadata.get("id") or path.stem).strip()
    name = str(metadata.get("title") or "").strip()
    description = str(metadata.get("description") or "").strip()

    if not prompt_id or not name or not content:
        return None

    return CompanyPromptResponse(
        id=prompt_id,
        name=name,
        description=description,
        content=content,
        updated_at=datetime.fromtimestamp(path.stat().st_mtime, timezone.utc),
    )


def _extract_prompt_content(markdown: str) -> str:
    lines = markdown.splitlines()
    start_index: int | None = None
    end_index = len(lines)

    for index, line in enumerate(lines):
        if line.strip() == "## 提示词内容":
            start_index = index + 1
            break

    if start_index is None:
        return markdown.strip()

    for index in range(start_index, len(lines)):
        line = lines[index].strip()
        if line.startswith("## ") and line != "## 提示词内容":
            end_index = index
            break

    return "\n".join(lines[start_index:end_index]).strip()


def _load_company_prompts() -> list[CompanyPromptResponse]:
    if not COMPANY_PROMPT_DIR.exists():
        return []

    prompts: list[CompanyPromptResponse] = []
    seen_ids: set[str] = set()
    for path in sorted(COMPANY_PROMPT_DIR.glob("*.md")):
        prompt = _parse_markdown_prompt(path)
        if prompt is None or prompt.id in seen_ids:
            continue
        prompts.append(prompt)
        seen_ids.add(prompt.id)
    return prompts


@router.get("/company", response_model=list[CompanyPromptResponse])
def list_company_prompts(_user: User = Depends(get_current_user)):
    return _load_company_prompts()
