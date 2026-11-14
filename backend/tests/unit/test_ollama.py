import json

import httpx
import pytest

from app.core.config import LLMProfile, Settings
from app.core.errors import AppError, ErrorCode
from app.llm.client import OllamaClient
from app.llm.interfaces import LLMMessage


def make_settings(**overrides: object) -> Settings:
    return Settings(OLLAMA_MODEL="base-test-model", **overrides)


def chat_response(**overrides: object) -> httpx.Response:
    body: dict[str, object] = {
        "model": "roleplay-test-model",
        "message": {"role": "assistant", "content": "Tell me about your project."},
        "prompt_eval_count": 12,
        "eval_count": 7,
    }
    body.update(overrides)
    return httpx.Response(200, json=body)


def test_chat_sends_profile_config_and_json_mode() -> None:
    settings = make_settings(
        OLLAMA_MODEL_ROLEPLAY="roleplay-test-model",
        roleplay_temperature=0.4,
        roleplay_max_tokens=80,
        ollama_num_ctx=1024,
    )
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return chat_response()

    client = httpx.Client(transport=httpx.MockTransport(handler))
    llm = OllamaClient(settings, client)
    result = llm.chat(
        LLMProfile.ROLEPLAY,
        [LLMMessage(role="user", content="Hello")],
        json_mode=True,
    )

    payload = requests[0].read().decode()
    assert requests[0].url.path == "/api/chat"
    assert '"model":"roleplay-test-model"' in payload
    assert '"format":"json"' in payload
    assert '"num_predict":80' in payload
    assert result.content == "Tell me about your project."
    assert result.model == "roleplay-test-model"
    assert result.profile is LLMProfile.ROLEPLAY
    assert result.prompt_tokens == 12
    assert result.completion_tokens == 7
    llm.close()
    client.close()


def test_chat_uses_json_schema_when_provided() -> None:
    requests: list[httpx.Request] = []
    schema: dict[str, object] = {
        "type": "object",
        "properties": {"summary": {"type": "string"}},
        "required": ["summary"],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return chat_response()

    client = httpx.Client(transport=httpx.MockTransport(handler))
    llm = OllamaClient(make_settings(), client)
    llm.chat(
        LLMProfile.EVALUATION,
        [LLMMessage(role="user", content="Evaluate.")],
        json_mode=True,
        json_schema=schema,
    )

    payload = json.loads(requests[0].read().decode())
    assert payload["format"] == schema
    client.close()


def test_chat_retries_connection_errors_once() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise httpx.ConnectError("connection refused", request=request)
        return chat_response()

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = OllamaClient(make_settings(), client).chat(
        LLMProfile.ROLEPLAY,
        [LLMMessage(role="user", content="Hello")],
    )

    assert attempts == 2
    assert result.content == "Tell me about your project."
    client.close()


def test_chat_maps_timeout_to_504() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    llm = OllamaClient(make_settings(), client)

    with pytest.raises(AppError) as error:
        llm.chat(LLMProfile.ROLEPLAY, [])

    assert error.value.code is ErrorCode.LLM_TIMEOUT
    assert error.value.http_status == 504
    client.close()


def test_chat_maps_missing_model_and_includes_pull_hint() -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(404, json={"error": "model not found"})
        )
    )
    llm = OllamaClient(make_settings(), client)

    with pytest.raises(AppError) as error:
        llm.chat(LLMProfile.ROLEPLAY, [])

    assert error.value.code is ErrorCode.LLM_MODEL_NOT_FOUND
    assert error.value.http_status == 503
    assert error.value.details == {
        "model": "base-test-model",
        "hint": "ollama pull base-test-model",
    }
    client.close()


def test_chat_maps_unusable_response_to_502() -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"model": "x"}))
    )
    llm = OllamaClient(make_settings(), client)

    with pytest.raises(AppError) as error:
        llm.chat(LLMProfile.ROLEPLAY, [])

    assert error.value.code is ErrorCode.LLM_BAD_OUTPUT
    assert error.value.http_status == 502
    client.close()


def test_health_reports_missing_configured_models() -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"models": [{"name": "other-model"}]})
        )
    )
    health = OllamaClient(make_settings(), client).health()

    assert health.status == "unavailable"
    assert "ollama pull base-test-model" in (health.detail or "")
    client.close()
