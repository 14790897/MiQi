"""Model catalog and provider-capability projection dataclasses.

Codex-style shapes exposed via model/list and modelProvider/capabilities/read.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ModelView:
    """A single model row returned by model/list."""

    id: str
    name: str
    provider: str
    provider_display_name: str
    hidden: bool = False
    default: bool = False
    supported_reasoning_efforts: list[str] = field(default_factory=list)
    additional_speed_tiers: list[str] = field(default_factory=list)
    service_tiers: list[str] = field(default_factory=list)
    default_service_tier: str | None = None
    upgrade: list[str] = field(default_factory=list)
    upgrade_info: dict[str, Any] | None = None
    availability_nux: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "provider": self.provider,
            "providerDisplayName": self.provider_display_name,
            "hidden": self.hidden,
            "default": self.default,
            "supportedReasoningEfforts": list(self.supported_reasoning_efforts),
            "additionalSpeedTiers": list(self.additional_speed_tiers),
            "serviceTiers": list(self.service_tiers),
            "defaultServiceTier": self.default_service_tier,
            "upgrade": list(self.upgrade),
            "upgradeInfo": self.upgrade_info,
            "availabilityNux": self.availability_nux,
        }


@dataclass(frozen=True)
class ProviderCapabilitiesView:
    """Capabilities snapshot for a single provider."""

    provider: str
    display_name: str
    provider_type: str
    is_gateway: bool
    is_local: bool
    supports_prompt_caching: bool
    supports_reasoning_history: bool
    supports_streaming: bool
    supports_tools: bool
    default_api_base: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "displayName": self.display_name,
            "providerType": self.provider_type,
            "isGateway": self.is_gateway,
            "isLocal": self.is_local,
            "supportsPromptCaching": self.supports_prompt_caching,
            "supportsReasoningHistory": self.supports_reasoning_history,
            "supportsStreaming": self.supports_streaming,
            "supportsTools": self.supports_tools,
            "defaultApiBase": self.default_api_base,
        }
