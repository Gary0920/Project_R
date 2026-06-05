from __future__ import annotations

from dataclasses import dataclass

from core.llm import ProviderSettings


TEXT_MODEL_PROFILE = "deepseek-flash"
VISION_MODEL_PROFILE = "mimo-v2-5"
MIMO_V2_5_MODEL = "mimo-v2.5"
PROHIBITED_MIMO_MODELS = {"mimo-v2.5-pro", "mimo-v2-5-pro"}


class PreprocessModelPolicyError(ValueError):
    """Raised when a preprocessing route violates Project_R model policy."""


@dataclass(frozen=True)
class PreprocessModelRoute:
    route_name: str
    provider: str
    model: str
    model_profile: str | None


def ensure_profile_allowed(model_profile: str | None, *, route_name: str) -> None:
    normalized = _normalize_model_name(model_profile or "")
    if normalized in PROHIBITED_MIMO_MODELS:
        raise PreprocessModelPolicyError(
            f"{route_name} cannot use MiMo V2.5 Pro; use {VISION_MODEL_PROFILE} / {MIMO_V2_5_MODEL}"
        )


def ensure_text_preprocess_model(settings: ProviderSettings, *, route_name: str) -> PreprocessModelRoute:
    route = _route(settings, route_name)
    _reject_prohibited_mimo(route)
    if route.provider != "deepseek":
        raise PreprocessModelPolicyError(
            f"{route_name} must use DeepSeek for text preprocessing, got provider={route.provider}"
        )
    return route


def ensure_mimo_v2_5_model(settings: ProviderSettings, *, route_name: str) -> PreprocessModelRoute:
    route = _route(settings, route_name)
    _reject_prohibited_mimo(route)
    if route.provider != "mimo" or _normalize_model_name(route.model) != MIMO_V2_5_MODEL:
        raise PreprocessModelPolicyError(
            f"{route_name} must use MiMo V2.5, got provider={route.provider} model={route.model}"
        )
    return route


def _route(settings: ProviderSettings, route_name: str) -> PreprocessModelRoute:
    return PreprocessModelRoute(
        route_name=route_name,
        provider=(settings.provider or "").strip().lower(),
        model=(settings.model or "").strip(),
        model_profile=settings.profile,
    )


def _reject_prohibited_mimo(route: PreprocessModelRoute) -> None:
    normalized_profile = _normalize_model_name(route.model_profile or "")
    normalized_model = _normalize_model_name(route.model)
    if normalized_profile in PROHIBITED_MIMO_MODELS or normalized_model in PROHIBITED_MIMO_MODELS:
        raise PreprocessModelPolicyError(
            f"{route.route_name} cannot use MiMo V2.5 Pro; use {VISION_MODEL_PROFILE} / {MIMO_V2_5_MODEL}"
        )


def _normalize_model_name(value: str) -> str:
    return value.strip().lower().replace("_", "-")
