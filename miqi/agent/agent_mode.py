"""Agent Reasoning Modes (issue #680): Fast / Think.

Two orthogonal dimensions of the agent runtime:

- Reasoning Mode (this module): HOW the agent thinks.
    - fast  — Answer-oriented: shortest path to a good-enough answer.
    - think — Task-oriented: maximize task quality, no limits (current behavior).
- Permission Mode (ExecutionPolicy, untouched): whether to modify files,
  auto-execute, or confirm. ``plan`` / ``manual`` / ``edit`` / ``auto``.

Keeping the two axes separate avoids an NxM switch explosion
(Fast-Edit-Auto / Think-Plan …). Future modes (Deep Research, Coding,
Analysis) attach to Reasoning Mode; permission semantics stay in
ExecutionPolicy.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


# ── Generation profile: the model-side budget ────────────────────────────────
# Without this, a "fast" mode that optimizes search still stalls on a model
# that reasons for 40s (DeepSeek TTFT is the dominant latency variable).
@dataclass(frozen=True)
class GenerationProfile:
    max_tokens: int
    temperature: float | None = None


# ── Tool policy: execution-side guardrails ───────────────────────────────────
@dataclass(frozen=True)
class ToolPolicy:
    # Fuse on the agent DECISION LOOP, not a tool-count budget: caps how many
    # model→tool→model rounds a turn may take, so the model cannot spiral into
    # search→search→search. This is deliberately NOT "web_search max N calls"
    # (a count budget would just cut information quality).
    max_tool_rounds: int | None
    parallel_limit: int
    # "info_only": informational tools (search/read/fetch) run automatically;
    # permission-typed actions (write/delete/shell) still go through
    # ExecutionPolicy confirmation. "full": current confirmation behavior.
    confirm_policy: Literal["info_only", "full"]


# ── Search strategy: consumed by SearchOrchestrator ──────────────────────────
@dataclass(frozen=True)
class SearchStrategy:
    name: Literal["breadth", "depth"]
    fanout_queries: int = 1   # parallel search queries per web_search call
    fanout_fetches: int = 0   # parallel page fetches after dedup
    verify: bool = False      # reserved (Phase 2): second-pass verification


@dataclass(frozen=True)
class AgentModeConfig:
    mode: Literal["fast", "think"]
    generation: GenerationProfile
    tool: ToolPolicy
    search: SearchStrategy
    # Fast-mode system-prompt snippet appended to the base prompt (think: none).
    prompt_snippet: str = ""


FAST_PROMPT = (
    "你是「极速回答」模式：目标是在 30 秒内给出足够好的答案。"
    "直接回答，不要展示思考过程，不要多轮搜索；"
    "确需信息时使用 web_search（内部会并行抓取），一轮搜索后立即作答。"
)

THINK_PROMPT = (
    "你是「深度研究」模式：目标最大化任务质量。"
    "请全面分析问题，多角度思考（背景、机制、对比、数据、局限性），"
    "给出结构化、详尽、有依据的回答（分点、对比、引用来源）；"
    "确需信息时使用 web_search/web_fetch 深入调研，允许多轮工具调用。"
)

FAST = AgentModeConfig(
    mode="fast",
    generation=GenerationProfile(max_tokens=2048),
    tool=ToolPolicy(max_tool_rounds=3, parallel_limit=5, confirm_policy="info_only"),
    search=SearchStrategy(name="breadth", fanout_queries=2, fanout_fetches=3),
    prompt_snippet=FAST_PROMPT,
)

THINK = AgentModeConfig(
    mode="think",
    generation=GenerationProfile(max_tokens=8192),
    # None = unlimited rounds; current loop behavior unchanged.
    tool=ToolPolicy(max_tool_rounds=None, parallel_limit=3, confirm_policy="full"),
    # depth reserved for Phase 2 (exploratory parallel research).
    search=SearchStrategy(name="depth", fanout_queries=1, fanout_fetches=0),
    prompt_snippet=THINK_PROMPT,
)

_MODES: dict[str, AgentModeConfig] = {m.mode: m for m in (FAST, THINK)}


def get_mode_config(mode: str | None) -> AgentModeConfig:
    """Resolve a mode name to its config; unknown/None → fast (默认极速版)."""
    return _MODES.get(mode or "", FAST)


def mode_names() -> tuple[str, ...]:
    return tuple(_MODES.keys())
