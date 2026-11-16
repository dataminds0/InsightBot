"""Export OpenAPI specification schema to JSON for frontend code generation."""

import argparse
import json
from pathlib import Path

from insightbot.api.main import app


def export_openapi(output_path: Path) -> None:
    """Generate and write OpenAPI JSON schema."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    schema = app.openapi()
    output_path.write_text(json.dumps(schema, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"OpenAPI schema successfully exported to: {output_path.resolve()}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Export InsightBot OpenAPI schema.")
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=Path("apps/web/openapi.json"),
        help="Path to output OpenAPI JSON file (default: apps/web/openapi.json)",
    )
    args = parser.parse_args()
    export_openapi(args.output)


if __name__ == "__main__":
    main()
