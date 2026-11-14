import json
import sys
from pathlib import Path

backend_root = Path(__file__).resolve().parents[1]

def main() -> None:
    sys.path.insert(0, str(backend_root))
    from app.core.openapi import normalize_openapi_status_descriptions
    from app.main import app

    schema = app.openapi()
    normalize_openapi_status_descriptions(schema)
    output_path = backend_root / "openapi.json"
    output_path.write_text(
        json.dumps(schema, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
