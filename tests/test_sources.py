from pathlib import Path

from insightbot.modules.sources.registry import (
    load_sources_from_yaml,
    validate_sources_config,
)

CONFIG_PATH = Path("configs/sources.yaml")


def test_sources_yaml_exists_and_is_valid():
    assert CONFIG_PATH.exists()
    is_valid, issues = validate_sources_config(CONFIG_PATH)
    assert is_valid is True, f"Validation issues: {issues}"
    assert len(issues) == 0


def test_sources_contains_eight_approved_publishers():
    sources = load_sources_from_yaml(CONFIG_PATH)
    assert len(sources) == 8

    # All must be disabled by default
    for s in sources:
        assert s.enabled is False, f"Source '{s.source_id}' must be disabled by default!"
        assert s.policy.retention_days >= 30
        assert len(s.feed_urls) >= 1
        assert s.url.startswith("https://")

    # Verify counts per language: 4 Arabic, 3 English, 1 Russian
    languages = [s.language for s in sources]
    assert languages.count("ar") == 4
    assert languages.count("en") == 3
    assert languages.count("ru") == 1

    source_ids = {s.source_id for s in sources}
    expected_ids = {
        "aljazeera_ar",
        "bbc_ar",
        "alarabiya_ar",
        "skynews_ar",
        "bbc_en",
        "reuters_en",
        "guardian_en",
        "tass_ru",
    }
    assert source_ids == expected_ids
