from __future__ import annotations

import math
import time
from dataclasses import asdict
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from app.core.config import LLMProfile, ProfileConfig, Settings
from app.core.errors import AppError, ErrorCode
from app.llm.interfaces import LLMHealth, LLMMessage, LLMResult


class OpenAICompatibleClient:
    MAX_RATE_LIMIT_RETRIES = 2
    MAX_RETRY_AFTER_SECONDS = 5.0

    def __init__(
        self,
        settings: Settings,
        client: httpx.Client | None = None,
    ) -> None:
        self._settings = settings
        self._base_url = settings.openai_base_url.rstrip("/")
        self._client = client or httpx.Client()
        self._owns_client = client is None

    def model_for(self, profile: LLMProfile) -> str:
        return self._settings.model_for(profile)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def chat(
        self,
        profile: LLMProfile,
        messages: list[LLMMessage],
        *,
        json_mode: bool = False,
        json_schema: dict[str, object] | None = None,
    ) -> LLMResult:
        profile_config = self._settings.profile_config(profile)
        payload: dict[str, object] = {
            "model": profile_config.model,
            "messages": [asdict(message) for message in messages],
            "temperature": profile_config.temperature,
            "max_completion_tokens": profile_config.max_tokens,
        }
        if json_mode or json_schema is not None:
            payload["response_format"] = {"type": "json_object"}

        started = time.perf_counter()
        response = self._request(
            "POST",
            "/chat/completions",
            timeout=profile_config.timeout_s,
            json=payload,
        )
        data = self._response_json(response)
        choices = data.get("choices")
        choice = choices[0] if isinstance(choices, list) and choices else None
        message = choice.get("message") if isinstance(choice, dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        response_model = data.get("model")
        usage = data.get("usage")
        usage = usage if isinstance(usage, dict) else {}
        if (
            not isinstance(content, str)
            or not content.strip()
            or not isinstance(response_model, str)
            or not response_model.strip()
        ):
            raise AppError(
                ErrorCode.LLM_BAD_OUTPUT,
                "OpenAI-compatible provider returned no usable message content or model metadata.",
                502,
            )

        return LLMResult(
            content=content,
            model=response_model,
            profile=profile,
            prompt_tokens=self._optional_count(usage.get("prompt_tokens")),
            completion_tokens=self._optional_count(usage.get("completion_tokens")),
            latency_ms=int((time.perf_counter() - started) * 1000),
        )

    def health(self) -> LLMHealth:
        models = {
            "roleplay": self.model_for(LLMProfile.ROLEPLAY),
            "evaluation": self.model_for(LLMProfile.EVALUATION),
        }
        try:
            response = self._request(
                "GET",
                "/models",
                timeout=self._settings.llm_timeout_s,
            )
            data = self._response_json(response)
        except AppError as exc:
            return LLMHealth(status="unavailable", models=models, detail=exc.message)

        raw_models = data.get("data")
        if not isinstance(raw_models, list):
            return LLMHealth(
                status="unavailable",
                models=models,
                detail="OpenAI-compatible provider returned an invalid model list.",
            )
        available = {
            model["id"]
            for model in raw_models
            if isinstance(model, dict) and isinstance(model.get("id"), str)
        }
        missing = sorted(set(models.values()) - available)
        if missing:
            return LLMHealth(
                status="unavailable",
                models=models,
                detail="Configured model(s) are not available from the provider.",
            )
        return LLMHealth(status="ok", models=models)

    def _request(
        self,
        method: str,
        path: str,
        *,
        timeout: float,
        json: dict[str, object] | None = None,
    ) -> httpx.Response:
        api_key = self._settings.openai_api_key.get_secret_value()
        headers = (
            {"Authorization": f"Bearer {api_key}"}
            if api_key
            else {}
        )
        for attempt in range(self.MAX_RATE_LIMIT_RETRIES + 1):
            try:
                response = self._client.request(
                    method,
                    f"{self._base_url}{path}",
                    timeout=timeout,
                    json=json,
                    headers=headers,
                )
            except httpx.TimeoutException:
                raise AppError(
                    ErrorCode.LLM_TIMEOUT,
                    "OpenAI-compatible provider request exceeded the configured timeout.",
                    504,
                ) from None
            except httpx.TransportError:
                raise AppError(
                    ErrorCode.LLM_UNAVAILABLE,
                    "OpenAI-compatible provider is unavailable.",
                    503,
                ) from None

            if response.status_code == 429:
                if attempt < self.MAX_RATE_LIMIT_RETRIES:
                    time.sleep(
                        self._retry_after_seconds(
                            response.headers.get("Retry-After")
                        )
                    )
                    continue
                raise AppError(
                    ErrorCode.LLM_UNAVAILABLE,
                    "OpenAI-compatible provider is rate limited.",
                    503,
                )
            if self._is_model_not_found(response):
                raise AppError(
                    ErrorCode.LLM_MODEL_NOT_FOUND,
                    "The configured OpenAI-compatible model was not found or is not "
                    "accessible. Verify OPENAI_MODEL and provider access.",
                    503,
                )
            if response.is_error:
                if response.status_code == 404:
                    raise AppError(
                        ErrorCode.LLM_UNAVAILABLE,
                        "The OpenAI-compatible endpoint returned HTTP 404. Verify "
                        "OPENAI_BASE_URL and endpoint compatibility.",
                        503,
                    )
                if response.status_code in (401, 403):
                    raise AppError(
                        ErrorCode.LLM_UNAVAILABLE,
                        "OpenAI-compatible provider authentication failed. Verify "
                        "OPENAI_API_KEY and model access.",
                        503,
                    )
                if response.status_code >= 500:
                    raise AppError(
                        ErrorCode.LLM_UNAVAILABLE,
                        "OpenAI-compatible provider is unavailable.",
                        503,
                    )
                raise AppError(
                    ErrorCode.LLM_BAD_OUTPUT,
                    "OpenAI-compatible provider rejected the request.",
                    502,
                )
            return response

        raise AppError(
            ErrorCode.LLM_UNAVAILABLE,
            "OpenAI-compatible provider is unavailable.",
            503,
        )

    @staticmethod
    def _is_model_not_found(response: httpx.Response) -> bool:
        try:
            data = response.json()
        except ValueError:
            return False
        if not isinstance(data, dict):
            return False
        error = data.get("error")
        if not isinstance(error, dict):
            return False

        code = error.get("code")
        if isinstance(code, str) and code.lower() in {
            "model_not_found",
            "model_not_found_error",
            "model_decommissioned",
        }:
            return True

        message = error.get("message")
        if not isinstance(message, str):
            return False
        normalized_message = message.lower()
        return "model" in normalized_message and any(
            phrase in normalized_message
            for phrase in ("not found", "does not exist", "decommissioned")
        )

    @classmethod
    def _retry_after_seconds(cls, value: str | None) -> float:
        delay = 0.0
        if value is not None:
            try:
                delay = float(value)
                if not math.isfinite(delay):
                    delay = 0.0
            except ValueError:
                try:
                    retry_at = parsedate_to_datetime(value)
                    if retry_at.tzinfo is None:
                        retry_at = retry_at.replace(tzinfo=UTC)
                    delay = (retry_at - datetime.now(UTC)).total_seconds()
                except (TypeError, ValueError, OverflowError):
                    delay = 0.0
        return min(max(delay, 0.0), cls.MAX_RETRY_AFTER_SECONDS)

    @staticmethod
    def _response_json(response: httpx.Response) -> dict[str, Any]:
        try:
            data = response.json()
        except ValueError:
            raise AppError(
                ErrorCode.LLM_BAD_OUTPUT,
                "OpenAI-compatible provider returned invalid JSON.",
                502,
            ) from None
        if not isinstance(data, dict):
            raise AppError(
                ErrorCode.LLM_BAD_OUTPUT,
                "OpenAI-compatible provider returned an invalid response.",
                502,
            )
        return data

    @staticmethod
    def _optional_count(value: object) -> int | None:
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            return value
        return None


class OllamaClient:
    def __init__(
        self,
        settings: Settings,
        client: httpx.Client | None = None,
    ) -> None:
        self._settings = settings
        self._base_url = settings.ollama_base_url.rstrip("/")
        self._client = client or httpx.Client()
        self._owns_client = client is None

    def model_for(self, profile: LLMProfile) -> str:
        return self._settings.model_for(profile)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def chat(
        self,
        profile: LLMProfile,
        messages: list[LLMMessage],
        *,
        json_mode: bool = False,
        json_schema: dict[str, object] | None = None,
    ) -> LLMResult:
        profile_config = self._settings.profile_config(profile)
        payload: dict[str, object] = {
            "model": profile_config.model,
            "messages": [asdict(message) for message in messages],
            "stream": False,
            "options": {
                "temperature": profile_config.temperature,
                "num_predict": profile_config.max_tokens,
                "num_ctx": profile_config.num_ctx,
            },
        }
        if json_schema is not None:
            payload["format"] = json_schema
        elif json_mode:
            payload["format"] = "json"

        started = time.perf_counter()
        response = self._request(
            "POST",
            "/api/chat",
            timeout=profile_config.timeout_s,
            json=payload,
            model_config=profile_config,
        )
        data = self._response_json(response)
        message = data.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        response_model = data.get("model")
        if (
            not isinstance(content, str)
            or not content.strip()
            or not isinstance(response_model, str)
            or not response_model.strip()
        ):
            raise AppError(
                ErrorCode.LLM_BAD_OUTPUT,
                "Ollama returned a response without usable message content or model metadata.",
                502,
            )

        return LLMResult(
            content=content,
            model=response_model,
            profile=profile,
            prompt_tokens=self._optional_count(data.get("prompt_eval_count")),
            completion_tokens=self._optional_count(data.get("eval_count")),
            latency_ms=int((time.perf_counter() - started) * 1000),
        )

    def health(self) -> LLMHealth:
        models = {
            "roleplay": self.model_for(LLMProfile.ROLEPLAY),
            "evaluation": self.model_for(LLMProfile.EVALUATION),
        }
        try:
            response = self._request(
                "GET",
                "/api/tags",
                timeout=self._settings.llm_timeout_s,
            )
            data = self._response_json(response)
        except AppError as exc:
            return LLMHealth(status="unavailable", models=models, detail=exc.message)

        raw_models = data.get("models")
        if not isinstance(raw_models, list):
            return LLMHealth(
                status="unavailable",
                models=models,
                detail="Ollama returned an invalid model list.",
            )
        installed = {
            model["name"]
            for model in raw_models
            if isinstance(model, dict) and isinstance(model.get("name"), str)
        }
        missing = sorted(set(models.values()) - installed)
        if missing:
            commands = ", ".join(f"ollama pull {model}" for model in missing)
            return LLMHealth(
                status="unavailable",
                models=models,
                detail=f"Configured model(s) are not installed; run: {commands}",
            )
        return LLMHealth(status="ok", models=models)

    def _request(
        self,
        method: str,
        path: str,
        *,
        timeout: float,
        json: dict[str, object] | None = None,
        model_config: ProfileConfig | None = None,
    ) -> httpx.Response:
        for attempt in range(2):
            try:
                response = self._client.request(
                    method,
                    f"{self._base_url}{path}",
                    timeout=timeout,
                    json=json,
                )
            except httpx.TimeoutException as exc:
                raise AppError(
                    ErrorCode.LLM_TIMEOUT,
                    "Ollama request exceeded the configured timeout.",
                    504,
                ) from exc
            except httpx.TransportError as exc:
                if attempt == 0:
                    continue
                raise AppError(
                    ErrorCode.LLM_UNAVAILABLE,
                    "Ollama is unavailable.",
                    503,
                ) from exc

            if response.is_error:
                self._raise_response_error(response, model_config)
            return response

        raise AppError(ErrorCode.LLM_UNAVAILABLE, "Ollama is unavailable.", 503)

    @staticmethod
    def _raise_response_error(
        response: httpx.Response,
        model_config: ProfileConfig | None,
    ) -> None:
        body = response.text
        model = model_config.model if model_config else None
        if response.status_code == 404 or (
            "model" in body.lower() and "not found" in body.lower()
        ):
            details: dict[str, object] = {}
            if model is not None:
                details = {"model": model, "hint": f"ollama pull {model}"}
            raise AppError(
                ErrorCode.LLM_MODEL_NOT_FOUND,
                "The configured Ollama model is not installed.",
                503,
                details=details,
            )
        if response.status_code >= 500:
            raise AppError(
                ErrorCode.LLM_UNAVAILABLE,
                "Ollama is unavailable.",
                503,
            )
        raise AppError(
            ErrorCode.LLM_BAD_OUTPUT,
            "Ollama rejected the request.",
            502,
        )

    @staticmethod
    def _response_json(response: httpx.Response) -> dict[str, Any]:
        try:
            data = response.json()
        except ValueError as exc:
            raise AppError(
                ErrorCode.LLM_BAD_OUTPUT,
                "Ollama returned invalid JSON.",
                502,
            ) from exc
        if not isinstance(data, dict):
            raise AppError(
                ErrorCode.LLM_BAD_OUTPUT,
                "Ollama returned an invalid response.",
                502,
            )
        return data

    @staticmethod
    def _optional_count(value: object) -> int | None:
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            return value
        return None
