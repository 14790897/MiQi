from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class PolicyVerdict(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    PROMPT = "prompt"


@dataclass
class PolicyDecision:
    verdict: PolicyVerdict
    source: str = ""
    reason: str = ""


@dataclass
class CommandRule:
    prefix: list[str]
    decision: str
    source: str


@dataclass
class NetworkRule:
    protocol: str
    host: str
    decision: str
    source: str
    port: int | None = None


@dataclass
class FilesystemRule:
    path_prefix: str
    access: str
    decision: str
    source: str


@dataclass
class ExecPolicy:
    command_rules: list[CommandRule] = field(default_factory=list)
    network_rules: list[NetworkRule] = field(default_factory=list)
    filesystem_rules: list[FilesystemRule] = field(default_factory=list)

    @classmethod
    def from_config(cls, cfg: dict) -> ExecPolicy:
        command_rules = [
            CommandRule(
                prefix=item["prefix"].split(),
                decision=item["decision"],
                source=item.get("source", "config"),
            )
            for item in cfg.get("command", [])
        ]
        network_rules = [
            NetworkRule(
                protocol=item["protocol"],
                host=item["host"],
                port=item.get("port"),
                decision=item["decision"],
                source=item.get("source", "config"),
            )
            for item in cfg.get("network", [])
        ]
        filesystem_rules = [
            FilesystemRule(
                path_prefix=item["path_prefix"],
                access=item["access"],
                decision=item["decision"],
                source=item.get("source", "config"),
            )
            for item in cfg.get("filesystem", [])
        ]
        return cls(
            command_rules=command_rules,
            network_rules=network_rules,
            filesystem_rules=filesystem_rules,
        )

    def evaluate_command(self, cmd: str) -> PolicyDecision:
        tokens = cmd.split()
        matches: list[CommandRule] = []
        for rule in self.command_rules:
            prefix_len = len(rule.prefix)
            if len(tokens) >= prefix_len and tokens[:prefix_len] == rule.prefix:
                matches.append(rule)
        return self._apply_matches(matches)

    def evaluate_network(self, proto: str, host: str, port: int) -> PolicyDecision:
        matches: list[NetworkRule] = []
        for rule in self.network_rules:
            protocol_ok = rule.protocol == "*" or rule.protocol == proto
            host_ok = rule.host == "*" or rule.host == host
            port_ok = rule.port is None or rule.port == port
            if protocol_ok and host_ok and port_ok:
                matches.append(rule)
        return self._apply_matches(matches)

    def evaluate_filesystem(self, path: str, access: str) -> PolicyDecision:
        matches: list[FilesystemRule] = []
        for rule in self.filesystem_rules:
            path_ok = path.startswith(rule.path_prefix)
            access_ok = rule.access == "*" or rule.access == access
            if path_ok and access_ok:
                matches.append(rule)
        return self._apply_matches(matches)

    def amend_command(self, rule: CommandRule) -> None:
        self.command_rules.append(rule)

    def amend_network(self, rule: NetworkRule) -> None:
        self.network_rules.append(rule)

    def amend_filesystem(self, rule: FilesystemRule) -> None:
        self.filesystem_rules.append(rule)

    @staticmethod
    def _apply_matches(rules: list) -> PolicyDecision:
        allow_rule = None
        for rule in rules:
            decision = rule.decision
            if isinstance(decision, str):
                decision = decision.lower()
            if decision == PolicyVerdict.DENY:
                return PolicyDecision(PolicyVerdict.DENY, source=rule.source)
            if decision == PolicyVerdict.ALLOW and allow_rule is None:
                allow_rule = rule
        if allow_rule is not None:
            return PolicyDecision(PolicyVerdict.ALLOW, source=allow_rule.source)
        return PolicyDecision(PolicyVerdict.PROMPT)
