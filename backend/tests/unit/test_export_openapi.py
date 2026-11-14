from typing import Any

from app.core.openapi import normalize_openapi_status_descriptions


def test_normalize_openapi_status_descriptions() -> None:
    schema: dict[str, Any] = {
        "paths": {
            "/example": {
                "get": {
                    "responses": {
                        "413": {"description": "Request Entity Too Large"},
                        "422": {"description": "Unprocessable Entity"},
                        "503": {"description": "Service Unavailable"},
                    }
                },
                "parameters": [],
            }
        }
    }

    normalize_openapi_status_descriptions(schema)

    responses = schema["paths"]["/example"]["get"]["responses"]
    assert responses["413"]["description"] == "Content Too Large"
    assert responses["422"]["description"] == "Unprocessable Content"
    assert responses["503"]["description"] == "Service Unavailable"
