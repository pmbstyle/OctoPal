from __future__ import annotations

import argparse
import json
from pathlib import Path

from broodmind.config.settings import Settings
from broodmind.gateway.app import build_app


def build_openapi_document() -> dict:
    project_root = Path(__file__).resolve().parents[1]
    settings = Settings(
        TELEGRAM_BOT_TOKEN="dummy:token",
        BROODMIND_STATE_DIR=project_root / "tmp" / "openapi_state",
        BROODMIND_WORKSPACE_DIR=project_root / "workspace",
    )
    app = build_app(settings)
    return app.openapi()


def main() -> None:
    parser = argparse.ArgumentParser(description="Export FastAPI OpenAPI spec for frontend type generation.")
    parser.add_argument(
        "--out",
        default="webapp/openapi.json",
        help="Path to write the generated OpenAPI JSON file.",
    )
    args = parser.parse_args()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    document = build_openapi_document()
    out_path.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote OpenAPI schema to {out_path}")


if __name__ == "__main__":
    main()
