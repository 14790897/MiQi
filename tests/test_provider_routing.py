from featherflow.providers.openai_provider import OpenAIProvider


def test_ollama_cloud_api_base_normalized_from_api_suffix() -> None:
    provider = OpenAIProvider(
        api_key="ollama_test_key",
        api_base="https://ollama.com/api",
        default_model="gpt-oss:20b-cloud",
        provider_name="ollama_cloud",
    )

    assert provider.api_base == "https://ollama.com/v1"


def test_moonshot_api_base_auto_fills_v1_path() -> None:
    provider = OpenAIProvider(
        api_key="moonshot_test_key",
        api_base="https://api.moonshot.cn",
        default_model="kimi-k2.5",
        provider_name="moonshot",
    )

    assert provider.api_base == "https://api.moonshot.cn/v1"


def test_gateway_api_base_auto_fills_default_path() -> None:
    provider = OpenAIProvider(
        api_key="sk-or-test",
        api_base="https://openrouter.ai",
        default_model="anthropic/claude-opus-4-5",
        provider_name="openrouter",
    )

    assert provider.api_base == "https://openrouter.ai/api/v1"


def test_explicit_api_base_path_is_preserved() -> None:
    provider = OpenAIProvider(
        api_key="moonshot_test_key",
        api_base="https://api.moonshot.cn/proxy/v1",
        default_model="kimi-k2.5",
        provider_name="moonshot",
    )

    assert provider.api_base == "https://api.moonshot.cn/proxy/v1"
