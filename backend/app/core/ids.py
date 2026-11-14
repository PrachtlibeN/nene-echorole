from uuid import uuid4


def new_id(prefix: str) -> str:
    return f"{prefix}{uuid4().hex}"


def new_request_id() -> str:
    return new_id("req_")
