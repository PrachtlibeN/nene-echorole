import json

import httpx
import pytest

from app.core.config import LLMProfile, LLMProvider, Settings
from app.core.errors import AppError, ErrorCode
from app.llm.client import OpenAICompatibleClient
from app.llm.interfaces import LLMMessage


def make_settings(**overrides: object) -> Settings:
    return Settings(
        _env_file=None,
        LLM_PROVIDER=LLMProvider.OPENAI_COMPATIBLE,
        OPENAI_MODEL="cloud-test-model",
        **overrides,
    )


def chat_response(**overrides: object) -> httpx.Response:
    body: dict[str, object] = {
        "model": "cloud-test-model",
        "choices": [
            {"message": {"role": "assistant", "content": "A useful response."}}
        ],
        "usage": {"prompt_tokens": 15, "completion_tokens": 8},
    }
    body.update(overrides)
    return httpx.Response(200, json=body)


def test_chat_sends_compatible_payload_and_parses_usage() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return chat_response()

    client = httpx.Client(transport=httpx.MockTransport(handler))
    llm = OpenAICompatibleClient(
        make_settings(
            OPENAI_BASE_URL="https://provider.test/v1/",
            OPENAI_API_KEY="unit-test-token",
            roleplay_temperature=0.4,
            roleplay_max_tokens=80,
        ),
        client,
    )
    result = llm.chat(
        LLMProfile.ROLEPLAY,
        [LLMMessage(role="user", content="Hello")],
        json_mode=True,
    )

    request = requests[0]
    payload = json.loads(request.read())
    assert str(request.url) == "https://provider.test/v1/chat/completions"
    assert request.headers["Authorization"] == "Bearer unit-test-token"
    assert payload == {
        "model": "cloud-test-model",
        "messages": [{"role": "user", "content": "Hello"}],
        "temperature": 0.4,
        "max_completion_tokens": 80,
        "response_format": {"type": "json_object"},
    }
    assert result.content == "A useful response."
    assert result.model == "cloud-test-model"
    assert result.profile is LLMProfile.ROLEPLAY
    assert result.prompt_tokens == 15
    assert result.completion_tokens == 8
    client.close()


def test_json_schema_requests_json_object_format() -> None:
    requests: list[httpx.Request] = []
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: (requests.append(request) or chat_response())
        )
    )
    llm = OpenAICompatibleClient(make_settings(), client)
    llm.chat(
        LLMProfile.EVALUATION,
        [LLMMessage(role="user", content="Evaluate.")],
        json_schema={"type": "object", "properties": {"score": {"type": "integer"}}},
    )

    payload = json.loads(requests[0].read())
    assert payload["response_format"] == {"type": "json_object"}
    client.close()


def test_chat_retries_429_with_capped_retry_after(monkeypatch: pytest.MonkeyPatch) -> None:
    requests: list[httpx.Request] = []
    delays: list[float] = []
    monkeypatch.setattr("app.llm.client.time.sleep", delays.append)

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(429, headers={"Retry-After": "100"})
        return chat_response()

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = OpenAICompatibleClient(make_settings(), client).chat(
        LLMProfile.ROLEPLAY,
        [LLMMessage(role="user", content="Hello")],
    )

    assert len(requests) == 2
    assert delays == [OpenAICompatibleClient.MAX_RETRY_AFTER_SECONDS]
    assert result.content == "A useful response."
    client.close()


@pytest.mark.parametrize(
    ("exception", "code", "status"),
    [
        (httpx.ReadTimeout("slow"), ErrorCode.LLM_TIMEOUT, 504),
        (httpx.ConnectError("offline"), ErrorCode.LLM_UNAVAILABLE, 503),
    ],
)
def test_chat_maps_network_errors(
    exception: httpx.TransportError,
    code: ErrorCode,
    status: int,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise exception

    client = httpx.Client(transport=httpx.MockTransport(handler))
    llm = OpenAICompatibleClient(make_settings(), client)

    with pytest.raises(AppError) as error:
        llm.chat(LLMProfile.ROLEPLAY, [])

    assert error.value.code is code
    assert error.value.http_status == status
    client.close()


@pytest.mark.parametrize(
    ("status_code", "payload", "expected_code"),
    [
        (
            400,
            {"error": {"code": "model_not_found", "message": "Model unavailable"}},
            ErrorCode.LLM_MODEL_NOT_FOUND,
        ),
        (
            404,
            {"error": {"message": "The requested model does not exist"}},
            ErrorCode.LLM_MODEL_NOT_FOUND,
        ),
        (404, {"error": {"message": "Not Found"}}, ErrorCode.LLM_UNAVAILABLE),
        (401, {"error": {"message": "Unauthorized"}}, ErrorCode.LLM_UNAVAILABLE),
    ],
)
def test_chat_distinguishes_provider_model_errors_from_endpoint_errors(
    status_code: int,
    payload: dict[str, object],
    expected_code: ErrorCode,
) -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(status_code, json=payload)
        )
    )
    llm = OpenAICompatibleClient(make_settings(), client)

    with pytest.raises(AppError) as error:
        llm.chat(LLMProfile.ROLEPLAY, [])

    assert error.value.code is expected_code
    assert error.value.http_status == 503
    assert "ollama" not in error.value.message.lower()
    client.close()


def test_chat_maps_exhausted_rate_limit_retries() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(429, headers={"Retry-After": "invalid"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    llm = OpenAICompatibleClient(make_settings(), client)

    with pytest.raises(AppError) as error:
        llm.chat(LLMProfile.ROLEPLAY, [])

    assert len(requests) == OpenAICompatibleClient.MAX_RATE_LIMIT_RETRIES + 1
    assert error.value.code is ErrorCode.LLM_UNAVAILABLE
    assert error.value.http_status == 503
    client.close()


def test_health_queries_active_provider_model_endpoint() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={"data": [{"id": "cloud-test-model"}]},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    health = OpenAICompatibleClient(
        make_settings(OPENAI_API_KEY="unit-test-token"),
        client,
    ).health()

    assert requests[0].method == "GET"
    assert requests[0].url.path == "/v1/models"
    assert requests[0].headers["Authorization"] == "Bearer unit-test-token"
    assert health.status == "ok"
    assert health.models == {
        "roleplay": "cloud-test-model",
        "evaluation": "cloud-test-model",
    }
    client.close()
