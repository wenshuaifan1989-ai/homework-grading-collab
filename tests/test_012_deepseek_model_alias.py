from config import Settings


def test_deepseek_fallback_uses_current_alias_without_network_call():
    settings = Settings(
        MODELS_CONFIG="[]",
        DEEPSEEK_API_KEY="test-only-deepseek-api-key",
    )

    [model] = settings.parsed_models
    assert model.provider == "deepseek"
    assert model.base_url == "https://api.deepseek.com"
    assert model.name == "deepseek-flash"
    assert model.model_id == "deepseek-flash"


def test_deepseek_fallback_can_rollback_to_legacy_alias():
    settings = Settings(
        MODELS_CONFIG="[]",
        DEEPSEEK_API_KEY="test-only-deepseek-api-key",
        DEEPSEEK_MODEL_ALIAS="deepseek-v4-flash-vision-exp",
    )

    [model] = settings.parsed_models
    assert model.name == "deepseek-v4-flash-vision-exp"
    assert model.model_id == "deepseek-v4-flash-vision-exp"

