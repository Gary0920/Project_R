from fastapi import APIRouter

from core.gbrain import get_gbrain_health
from core.llm import list_provider_statuses, load_provider_settings

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
def health_check():
    return {"status": "ok"}


@router.get("/llm")
def llm_health_check():
    settings = load_provider_settings()
    return {
        "profile": settings.profile,
        "label": settings.label,
        "description": settings.description,
        "provider": settings.provider,
        "configured": settings.configured,
        "key_count": len(settings.api_keys),
        "model": settings.model,
        "base_url": settings.base_url,
        "api_version": settings.api_version,
        "reasoning_effort": settings.reasoning_effort,
        "supports_vision": settings.supports_vision,
        "providers": list_provider_statuses(),
    }


@router.get("/gbrain")
def gbrain_health_check():
    return get_gbrain_health()
