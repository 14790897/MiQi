import os

from featherflow.providers.litellm_provider import LiteLLMProvider


def test_ollama_cloud_provider_name_takes_priority_for_glm_model() -> None:
    old_ollama = os.environ.get("OLLAMA_API_KEY")
    old_zai = os.environ.get("ZAI_API_KEY")
    try:
        provider = LiteLLMProvider(
            api_key="ollama_test_key",
            api_base="https://ollama.com/api",
            default_model="glm-5",
            provider_name="ollama_cloud",
        )

        resolved = provider._resolve_model("glm-5")

        assert resolved == "ollama/glm-5"
        assert os.environ.get("OLLAMA_API_KEY") == "ollama_test_key"
        assert os.environ.get("ZAI_API_KEY") != "ollama_test_key"
    finally:
        if old_ollama is None:
            os.environ.pop("OLLAMA_API_KEY", None)
        else:
            os.environ["OLLAMA_API_KEY"] = old_ollama

        if old_zai is None:
            os.environ.pop("ZAI_API_KEY", None)
        else:
            os.environ["ZAI_API_KEY"] = old_zai


def test_ollama_cloud_api_base_normalized_from_api_suffix() -> None:
    provider = LiteLLMProvider(
        api_key="ollama_test_key",
        api_base="https://ollama.com/api",
        default_model="gpt-oss:20b-cloud",
        provider_name="ollama_cloud",
    )

    assert provider.api_base == "https://ollama.com"


def test_moonshot_api_base_auto_fills_v1_path() -> None:
    provider = LiteLLMProvider(
        api_key="moonshot_test_key",
        api_base="https://api.moonshot.cn",
        default_model="kimi-k2.5",
        provider_name="moonshot",
    )

    assert provider.api_base == "https://api.moonshot.cn/v1"


def test_gateway_api_base_auto_fills_default_path() -> None:
    provider = LiteLLMProvider(
        api_key="sk-or-test",
        api_base="https://openrouter.ai",
        default_model="anthropic/claude-opus-4-5",
        provider_name="openrouter",
    )

    assert provider.api_base == "https://openrouter.ai/api/v1"


def test_explicit_api_base_path_is_preserved() -> None:
    provider = LiteLLMProvider(
        api_key="moonshot_test_key",
        api_base="https://api.moonshot.cn/proxy/v1",
        default_model="kimi-k2.5",
        provider_name="moonshot",
    )

    assert provider.api_base == "https://api.moonshot.cn/proxy/v1"
