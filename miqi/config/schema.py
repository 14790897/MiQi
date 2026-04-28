"""Configuration schema using Pydantic."""

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel
from pydantic_settings import BaseSettings


class Base(BaseModel):
    """Base model that accepts both camelCase and snake_case keys."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class TelegramConfig(Base):
    """Telegram channel configuration."""

    enabled: bool = False
    token: str = ""  # Bot token from @BotFather
    allow_from: list[str] = Field(default_factory=list)  # Allowed user IDs or usernames
    proxy: str | None = None  # HTTP/SOCKS5 proxy URL, e.g. "http://127.0.0.1:7890" or "socks5://127.0.0.1:1080"
    reply_to_message: bool = False  # If true, bot replies quote the original message


class DingTalkConfig(Base):
    """DingTalk channel configuration using Stream mode."""

    enabled: bool = False
    client_id: str = ""  # AppKey
    client_secret: str = ""  # AppSecret
    allow_from: list[str] = Field(default_factory=list)  # Allowed staff_ids


class DiscordConfig(Base):
    """Discord channel configuration."""

    enabled: bool = False
    token: str = ""  # Bot token from Discord Developer Portal
    allow_from: list[str] = Field(default_factory=list)  # Allowed user IDs
    gateway_url: str = "wss://gateway.discord.gg/?v=10&encoding=json"
    intents: int = 37377  # GUILDS + GUILD_MESSAGES + DIRECT_MESSAGES + MESSAGE_CONTENT


class EmailConfig(Base):
    """Email channel configuration (IMAP inbound + SMTP outbound)."""

    enabled: bool = False
    consent_granted: bool = False  # Explicit owner permission to access mailbox data

    # IMAP (receive)
    imap_host: str = ""
    imap_port: int = 993
    imap_username: str = ""
    imap_password: str = ""
    imap_mailbox: str = "INBOX"
    imap_use_ssl: bool = True

    # SMTP (send)
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = True
    smtp_use_ssl: bool = False
    from_address: str = ""

    # Behavior
    auto_reply_enabled: bool = True  # If false, inbound email is read but no automatic reply is sent
    poll_interval_seconds: int = 30
    mark_seen: bool = True
    max_body_chars: int = 12000
    subject_prefix: str = "Re: "
    allow_from: list[str] = Field(default_factory=list)  # Allowed sender email addresses


class MochatMentionConfig(Base):
    """Mochat mention behavior configuration."""

    require_in_groups: bool = False


class MochatGroupRule(Base):
    """Mochat per-group mention requirement."""

    require_mention: bool = False


class MochatConfig(Base):
    """Mochat channel configuration."""

    enabled: bool = False
    base_url: str = "https://mochat.io"
    socket_url: str = ""
    socket_path: str = "/socket.io"
    socket_disable_msgpack: bool = False
    socket_reconnect_delay_ms: int = 1000
    socket_max_reconnect_delay_ms: int = 10000
    socket_connect_timeout_ms: int = 10000
    refresh_interval_ms: int = 30000
    watch_timeout_ms: int = 25000
    watch_limit: int = 100
    retry_delay_ms: int = 500
    max_retry_attempts: int = 0  # 0 means unlimited retries
    claw_token: str = ""
    agent_user_id: str = ""
    sessions: list[str] = Field(default_factory=list)
    panels: list[str] = Field(default_factory=list)
    allow_from: list[str] = Field(default_factory=list)
    mention: MochatMentionConfig = Field(default_factory=MochatMentionConfig)
    groups: dict[str, MochatGroupRule] = Field(default_factory=dict)
    reply_delay_mode: str = "non-mention"  # off | non-mention
    reply_delay_ms: int = 120000


class SlackDMConfig(Base):
    """Slack DM policy configuration."""

    enabled: bool = True
    policy: str = "open"  # "open" or "allowlist"
    allow_from: list[str] = Field(default_factory=list)  # Allowed Slack user IDs


class SlackConfig(Base):
    """Slack channel configuration."""

    enabled: bool = False
    mode: str = "socket"  # "socket" supported
    webhook_path: str = "/slack/events"
    bot_token: str = ""  # xoxb-...
    app_token: str = ""  # xapp-...
    user_token_read_only: bool = True
    reply_in_thread: bool = True
    react_emoji: str = "eyes"
    group_policy: str = "mention"  # "mention", "open", "allowlist"
    group_allow_from: list[str] = Field(default_factory=list)  # Allowed channel IDs if allowlist
    dm: SlackDMConfig = Field(default_factory=SlackDMConfig)


class QQConfig(Base):
    """QQ channel configuration using botpy SDK."""

    enabled: bool = False
    app_id: str = ""  # 机器人 ID (AppID) from q.qq.com
    secret: str = ""  # 机器人密钥 (AppSecret) from q.qq.com
    allow_from: list[str] = Field(default_factory=list)  # Allowed user openids (empty = public access)


class FeishuChannelConfig(Base):
    """Feishu (Lark) channel configuration using WebSocket long connection."""

    enabled: bool = False
    app_id: str = ""      # Developer Console App ID (cli_xxx)
    app_secret: str = ""  # Developer Console App Secret
    allow_from: list[str] = Field(default_factory=list)  # Allowed open_ids (empty = anyone)
    reply_delay_ms: int = 3000  # Debounce window in ms: coalesce rapid messages before sending to agent (0 = off)
    require_mention_in_groups: bool = True  # If true, only respond when @mentioned in group chats


class ChannelsConfig(Base):
    """Configuration for chat channels."""

    send_progress: bool = True    # stream agent's text progress to the channel
    send_tool_hints: bool = False  # stream tool-call hints (e.g. read_file("…"))
    send_queue_notifications: bool = True  # Notify users about their position in the task queue
    feishu: FeishuChannelConfig = Field(default_factory=FeishuChannelConfig)


class FallbackChainEntry(Base):
    """One entry in the provider fallback chain."""

    model: str = ""    # full model string, e.g. "openai/gpt-4o"


class AgentDefaults(Base):
    """Default agent configuration."""

    name: str = "miqi"
    workspace: str = "~/.miqi/workspace"
    model: str = "anthropic/claude-opus-4-5"
    max_tokens: int = 8192
    temperature: float = 0.1
    max_tool_iterations: int = 100
    memory_window: int = 100
    reflect_after_tool_calls: bool = True
    # Maximum characters kept per tool result in the live prompt.
    max_tool_result_chars: int = 16000
    # Soft cap on total estimated context chars before LLM call.
    context_limit_chars: int = 600000
    # Provider fallback chain — tried in order when primary fails
    fallback_chain: list[FallbackChainEntry] = Field(default_factory=list)


class AgentMemoryConfig(Base):
    """Agent memory runtime configuration."""

    flush_every_updates: int = 8
    flush_interval_seconds: int = 120
    short_term_turns: int = 12
    pending_limit: int = 20


class AgentSessionConfig(Base):
    """Session storage runtime configuration."""

    compact_threshold_messages: int = 400
    compact_threshold_bytes: int = 2_000_000
    compact_keep_messages: int = 300
    session_tool_result_max_chars: int = 500
    # SQLite backend (new): when True use miqi/session/sqlite_store.py instead of JSONL
    use_sqlite: bool = False


class SmartRoutingCheapModel(Base):
    """Cheap model config for smart routing."""

    provider: str = ""   # e.g. "openai"
    model: str = ""      # e.g. "gpt-4o-mini"


class SmartRoutingConfig(Base):
    """Smart model routing configuration (routes simple turns to a cheaper model)."""

    enabled: bool = False
    cheap_model: SmartRoutingCheapModel = Field(default_factory=SmartRoutingCheapModel)
    max_chars: int = 160    # turns exceeding this go to primary
    max_words: int = 28     # turns exceeding this go to primary


class CommandApprovalConfig(Base):
    """Dangerous command approval configuration."""

    enabled: bool = True         # when False, all commands approved silently
    mode: str = "manual"         # manual | off
    timeout: int = 60            # CLI approval prompt timeout (seconds)
    allowlist: list[str] = Field(default_factory=list)  # pattern descriptions permanently approved


class AgentSelfImprovementConfig(Base):
    """Self-improvement lesson configuration."""

    enabled: bool = True
    max_lessons_in_prompt: int = 5
    min_lesson_confidence: int = 1
    max_lessons: int = 200
    lesson_confidence_decay_hours: int = 168
    feedback_max_message_chars: int = 220
    feedback_require_prefix: bool = True
    promotion_enabled: bool = True
    promotion_min_users: int = 3
    promotion_triggers: list[str] = Field(
        default_factory=lambda: ["response:length", "response:language"]
    )


class AgentsConfig(Base):
    """Agent configuration."""

    defaults: AgentDefaults = Field(default_factory=AgentDefaults)
    memory: AgentMemoryConfig = Field(default_factory=AgentMemoryConfig)
    sessions: AgentSessionConfig = Field(default_factory=AgentSessionConfig)
    self_improvement: AgentSelfImprovementConfig = Field(default_factory=AgentSelfImprovementConfig)
    smart_routing: SmartRoutingConfig = Field(default_factory=SmartRoutingConfig)
    command_approval: CommandApprovalConfig = Field(default_factory=CommandApprovalConfig)


class ProviderConfig(Base):
    """LLM provider configuration."""

    api_key: str = ""
    api_base: str | None = None
    extra_headers: dict[str, str] | None = None  # Custom headers (e.g. APP-Code for AiHubMix)


class ProvidersConfig(Base):
    """Configuration for LLM providers."""

    custom: ProviderConfig = Field(default_factory=ProviderConfig)  # Any OpenAI-compatible endpoint
    anthropic: ProviderConfig = Field(default_factory=ProviderConfig)
    openai: ProviderConfig = Field(default_factory=ProviderConfig)
    openrouter: ProviderConfig = Field(default_factory=ProviderConfig)
    deepseek: ProviderConfig = Field(default_factory=ProviderConfig)
    groq: ProviderConfig = Field(default_factory=ProviderConfig)
    zhipu: ProviderConfig = Field(default_factory=ProviderConfig)
    dashscope: ProviderConfig = Field(default_factory=ProviderConfig)  # 阿里云通义千问
    vllm: ProviderConfig = Field(default_factory=ProviderConfig)
    gemini: ProviderConfig = Field(default_factory=ProviderConfig)
    moonshot: ProviderConfig = Field(default_factory=ProviderConfig)
    minimax: ProviderConfig = Field(default_factory=ProviderConfig)
    aihubmix: ProviderConfig = Field(default_factory=ProviderConfig)  # AiHubMix API gateway
    ollama_local: ProviderConfig = Field(default_factory=ProviderConfig)
    ollama_cloud: ProviderConfig = Field(default_factory=ProviderConfig)
    siliconflow: ProviderConfig = Field(default_factory=ProviderConfig)  # SiliconFlow (硅基流动) API gateway
    volcengine: ProviderConfig = Field(default_factory=ProviderConfig)  # VolcEngine (火山引擎) API gateway


class GatewayConfig(Base):
    """Gateway/server configuration."""

    host: str = "0.0.0.0"
    port: int = 18790


class HeartbeatConfig(Base):
    """Background heartbeat configuration."""

    enabled: bool = True
    interval_seconds: int = 30 * 60


class CronConfig(Base):
    """Cron scheduler configuration."""

    job_timeout_seconds: int = 86400  # Max time a single cron job may run (default 24 h)


class WebSearchConfig(Base):
    """Web search tool configuration."""

    provider: str = "brave"  # brave | ollama | hybrid
    api_key: str = ""  # Brave Search API key
    ollama_api_key: str = ""  # Ollama web search API key
    ollama_api_base: str = "https://ollama.com"
    max_results: int = 5


class WebFetchConfig(Base):
    """Web fetch tool configuration."""

    provider: str = "builtin"  # builtin | ollama | hybrid
    ollama_api_key: str = ""  # Ollama web fetch API key
    ollama_api_base: str = "https://ollama.com"


class WebToolsConfig(Base):
    """Web tools configuration."""

    search: WebSearchConfig = Field(default_factory=WebSearchConfig)
    fetch: WebFetchConfig = Field(default_factory=WebFetchConfig)


class ExecToolConfig(Base):
    """Shell exec tool configuration."""

    timeout: int = 60
    env_passthrough: list[str] = Field(
        default_factory=list,
        description=(
            "Explicit list of environment variable names that are permitted to pass through "
            "to shell subprocesses spawned by the exec tool.  By default ALL credential "
            "variables (API keys, tokens, secrets, passwords) are stripped before the "
            "subprocess starts (SEC-09).  Use this list to selectively restore access to "
            "specific variables needed by your scripts, e.g. ['OPENAI_API_KEY'].  "
            "Note: MCP server processes are NOT affected — they always inherit the full "
            "parent environment via StdioServerParameters."
        ),
    )


class PapersToolConfig(Base):
    """Paper research tools configuration."""

    provider: str = "hybrid"  # hybrid | semantic_scholar | arxiv
    semantic_scholar_api_key: str = ""
    timeout_seconds: int = 20
    default_limit: int = 8
    max_limit: int = 20


class MCPServerConfig(Base):
    """MCP server connection configuration (stdio or HTTP)."""

    command: str = ""  # Stdio: command to run (e.g. "npx")
    args: list[str] = Field(default_factory=list)  # Stdio: command arguments
    env: dict[str, str] = Field(default_factory=dict)  # Stdio: extra env vars
    url: str = ""  # HTTP: streamable HTTP endpoint URL
    headers: dict[str, str] = Field(default_factory=dict)  # HTTP: Custom HTTP Headers
    tool_timeout: int = 30  # Seconds before a tool call is cancelled
    progress_interval_seconds: int = 15  # Interval for heartbeat progress messages during long-running tool calls (0 = off)
    description: str = ""  # Description shown to LLM in the gateway entry-point tool (lazy mode)
    lazy: bool = False  # If true, register a single gateway tool instead of all tools upfront; activate on demand


class ToolsConfig(Base):
    """Tools configuration."""

    web: WebToolsConfig = Field(default_factory=WebToolsConfig)
    exec: ExecToolConfig = Field(default_factory=ExecToolConfig)
    papers: PapersToolConfig = Field(default_factory=PapersToolConfig)
    restrict_to_workspace: bool = False  # If true, restrict all tool access to workspace directory
    mcp_servers: dict[str, MCPServerConfig] = Field(default_factory=dict)


class Config(BaseSettings):
    """Root configuration for MiQi runtime."""

    agents: AgentsConfig = Field(default_factory=AgentsConfig)
    channels: ChannelsConfig = Field(default_factory=ChannelsConfig)
    providers: ProvidersConfig = Field(default_factory=ProvidersConfig)
    gateway: GatewayConfig = Field(default_factory=GatewayConfig)
    heartbeat: HeartbeatConfig = Field(default_factory=HeartbeatConfig)
    cron: CronConfig = Field(default_factory=CronConfig)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)

    @property
    def workspace_path(self) -> Path:
        """Get expanded workspace path."""
        return Path(self.agents.defaults.workspace).expanduser()

    def _match_provider(self, model: str | None = None) -> tuple["ProviderConfig | None", str | None]:
        """Match provider config and its registry name. Returns (config, spec_name)."""
        from miqi.providers.registry import PROVIDERS

        model_lower = (model or self.agents.defaults.model).lower()
        model_normalized = model_lower.replace("-", "_")
        model_prefix = model_lower.split("/", 1)[0] if "/" in model_lower else ""
        normalized_prefix = model_prefix.replace("-", "_")

        def _kw_matches(kw: str) -> bool:
            kw = kw.lower()
            return kw in model_lower or kw.replace("-", "_") in model_normalized

        def _is_configured(spec, provider) -> bool:
            if spec.is_local:
                return bool(provider.api_base)
            return bool(provider.api_key)

        # Explicit provider prefix wins.
        for spec in PROVIDERS:
            p = getattr(self.providers, spec.name, None)
            if p and model_prefix and normalized_prefix == spec.name:
                if _is_configured(spec, p):
                    return p, spec.name

        # Match by keyword (order follows PROVIDERS registry)
        for spec in PROVIDERS:
            p = getattr(self.providers, spec.name, None)
            if p and any(_kw_matches(kw) for kw in spec.keywords):
                if _is_configured(spec, p):
                    return p, spec.name

        # Fallback: gateways first, then others (follows registry order)
        for spec in PROVIDERS:
            p = getattr(self.providers, spec.name, None)
            if p and _is_configured(spec, p):
                return p, spec.name
        return None, None

    def get_provider(self, model: str | None = None) -> ProviderConfig | None:
        """Get matched provider config (api_key, api_base, extra_headers). Falls back to first available."""
        p, _ = self._match_provider(model)
        return p

    def get_provider_name(self, model: str | None = None) -> str | None:
        """Get the registry name of the matched provider (e.g. "deepseek", "openrouter")."""
        _, name = self._match_provider(model)
        return name

    def get_api_key(self, model: str | None = None) -> str | None:
        """Get API key for the given model. Falls back to first available key."""
        p = self.get_provider(model)
        return p.api_key if p else None

    def get_api_base(self, model: str | None = None) -> str | None:
        """Get API base URL for the given model. Applies default URLs for known gateways."""
        from miqi.providers.registry import find_by_name

        p, name = self._match_provider(model)
        if p and p.api_base:
            return p.api_base
        # Only gateways get a default api_base here. Standard providers
        # set their base URL directly in OpenAIProvider._normalize_api_base.
        if name:
            spec = find_by_name(name)
            if spec and spec.is_gateway and spec.default_api_base:
                return spec.default_api_base
        return None

    def build_provider(self, model: str) -> "LLMProvider | None":
        """Build an LLMProvider instance for the given model string.

        Used by ProviderFallbackChain to construct fallback provider instances.
        Returns None if the model/provider cannot be resolved.
        """
        from miqi.providers.base import LLMProvider  # noqa: F401 (type hint only)

        api_key = self.get_api_key(model)
        api_base = self.get_api_base(model)
        provider_name = self.get_provider_name(model)

        if not provider_name:
            return None

        from miqi.providers.registry import find_by_name
        spec = find_by_name(provider_name)
        if spec is None:
            return None

        try:
            if spec.provider_type == "anthropic":
                from miqi.providers.anthropic_provider import AnthropicProvider
                return AnthropicProvider(api_key=api_key, api_base=api_base, provider_name=provider_name, default_model=model)
            elif spec.provider_type == "gemini":
                from miqi.providers.gemini_provider import GeminiProvider
                return GeminiProvider(api_key=api_key, api_base=api_base, provider_name=provider_name, default_model=model)
            else:
                from miqi.providers.openai_provider import OpenAIProvider
                extra_headers = getattr(self.providers, provider_name, None)
                headers = extra_headers.extra_headers if extra_headers else None
                return OpenAIProvider(api_key=api_key, api_base=api_base, extra_headers=headers, provider_name=provider_name, default_model=model)
        except Exception:
            return None

    model_config = ConfigDict(env_prefix="MIQI_", env_nested_delimiter="__")
