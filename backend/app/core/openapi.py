from typing import Any

STABLE_STATUS_DESCRIPTIONS = {
    "413": "Content Too Large",
    "422": "Unprocessable Content",
}


def normalize_openapi_status_descriptions(schema: dict[str, Any]) -> None:
    for path_item in schema["paths"].values():
        for operation in path_item.values():
            if not isinstance(operation, dict):
                continue
            responses = operation.get("responses")
            if not isinstance(responses, dict):
                continue
            for status_code, description in STABLE_STATUS_DESCRIPTIONS.items():
                response = responses.get(status_code)
                if isinstance(response, dict):
                    response["description"] = description
