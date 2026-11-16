from insightbot.config import Settings


def test_settings_default_values():
    settings = Settings(
        env="development",
        secret_key="dev-secret-key-at-least-32-chars-long",
    )
    assert settings.env == "development"
    assert settings.mongo_db == "insightbot"
    assert settings.timezone == "UTC"
    assert settings.search_backend == "basic"
    assert settings.enable_llm is False


def test_settings_validation_production_requires_secret():
    settings = Settings(
        env="production",
        secret_key="",
    )
    issues = settings.validate_runtime()
    assert any("INSIGHTBOT_SECRET_KEY" in issue for issue in issues)


def test_settings_validation_dev_allows_empty_secret():
    settings = Settings(
        env="development",
        secret_key="",
    )
    issues = settings.validate_runtime()
    # In dev mode, missing secret_key should not be a critical issue
    assert not any("INSIGHTBOT_SECRET_KEY" in issue for issue in issues)
