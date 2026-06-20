from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ApprovalMode(str, Enum):
    UNLESS_TRUSTED = "unless_trusted"
    ON_FAILURE = "on_failure"
    ON_REQUEST = "on_request"
    GRANULAR = "granular"
    NEVER = "never"


@dataclass
class ApprovalPolicy:
    mode: ApprovalMode = ApprovalMode.ON_REQUEST
    trusted: set[str] = field(default_factory=set)
    granular: dict[str, str] = field(default_factory=dict)

    def requires_prompt(self, category: str, failed: bool) -> bool:
        match self.mode:
            case ApprovalMode.NEVER:
                return False
            case ApprovalMode.ON_REQUEST:
                return True
            case ApprovalMode.ON_FAILURE:
                return failed
            case ApprovalMode.UNLESS_TRUSTED:
                return category not in self.trusted
            case ApprovalMode.GRANULAR:
                result = self.granular.get(category)
                match result:
                    case "never":
                        return False
                    case "on_failure":
                        return failed
                    case "on_request" | None:
                        return True
                    case _:
                        return True
            case _:
                return True

    @classmethod
    def from_config(cls, cfg: dict) -> ApprovalPolicy:
        mode = ApprovalMode(cfg.get("mode", "on_request"))
        trusted = set(cfg.get("trusted", []))
        granular = dict(cfg.get("granular", {}))
        return cls(mode=mode, trusted=trusted, granular=granular)
