"""Source registry validation, loading from YAML, and database synchronization."""

from pathlib import Path

import yaml
from pydantic import ValidationError

from insightbot.models.source import Source
from insightbot.repositories.source_repository import SourceRepository


def load_sources_from_yaml(config_path: Path) -> list[Source]:
    """Parse and validate publisher sources from YAML configuration file."""
    if not config_path.exists():
        raise FileNotFoundError(f"Sources configuration file not found at: '{config_path}'")

    raw_text = config_path.read_text(encoding="utf-8")
    data = yaml.safe_load(raw_text)

    if not isinstance(data, dict) or "sources" not in data:
        raise ValueError("Invalid sources configuration format: expected top-level 'sources' key.")

    sources_list = data["sources"]
    if not isinstance(sources_list, list):
        raise ValueError("Invalid sources configuration: 'sources' must be a list.")

    sources: list[Source] = []
    for item in sources_list:
        sources.append(Source.model_validate(item))

    return sources


def validate_sources_config(config_path: Path) -> tuple[bool, list[str]]:
    """
    Validate sources YAML file without throwing unhandled exceptions.
    Returns (is_valid, list_of_error_or_warning_messages).
    """
    issues: list[str] = []
    if not config_path.exists():
        return False, [f"Configuration file '{config_path}' does not exist."]

    try:
        raw_text = config_path.read_text(encoding="utf-8")
        data = yaml.safe_load(raw_text)
    except Exception as exc:
        return False, [f"Failed to parse YAML file: {exc}"]

    if not isinstance(data, dict) or "sources" not in data:
        return False, ["Missing top-level 'sources' key in YAML configuration."]

    sources_raw = data.get("sources")
    if not isinstance(sources_raw, list):
        return False, ["'sources' field must be a list of source definitions."]

    seen_ids: set[str] = set()
    for idx, item in enumerate(sources_raw):
        if not isinstance(item, dict):
            issues.append(f"Source at index {idx} must be a dictionary.")
            continue

        source_id = item.get("source_id")
        if not source_id:
            issues.append(f"Source at index {idx} missing 'source_id'.")
        elif source_id in seen_ids:
            issues.append(f"Duplicate source_id '{source_id}' at index {idx}.")
        else:
            seen_ids.add(source_id)

        try:
            Source.model_validate(item)
        except ValidationError as val_err:
            issues.append(f"Validation error for source '{source_id or idx}': {val_err}")

    return len(issues) == 0, issues


def sync_sources_to_db(sources: list[Source], source_repo: SourceRepository) -> int:
    """Upsert validated sources into MongoDB sources collection."""
    for source in sources:
        source_repo.upsert_source(source)
    return len(sources)
