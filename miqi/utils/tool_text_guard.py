"""Guard against tool-call text leaking into assistant output.

Models occasionally write a tool call as plain text instead of emitting it
through the tool-calling interface, e.g. ``functions.paper_download(
paperId="An Image is Worth 16x16 Words")``. Such text is never executed and
confuses the user. We detect the leak and replace it with a notice — we never
parse or execute it (issue #532).
"""
from __future__ import annotations

import re

LEAK_NOTICE = "〔检测到未被执行的工具调用文本，已忽略〕"


def tool_names_from_definitions(tools: list[dict] | None) -> set[str]:
    """Extract tool names from tool definitions.

    Accepts both OpenAI function schema (``{"function": {"name": ...}}``) and
    flat ``{"name": ...}`` forms.
    """
    names: set[str] = set()
    for t in tools or []:
        if not t:
            continue
        n = t.get("name")
        if not n:
            fn = t.get("function") or {}
            n = fn.get("name")
        if n:
            names.add(n)
    return names


def sanitize_tool_call_text(
    text: str,
    tool_names: list[str] | set[str] | None,
    notice: str = LEAK_NOTICE,
) -> tuple[str, bool]:
    """Replace tool calls written as plain text with a notice.

    Only names in ``tool_names`` are matched (guarded by identifier
    boundaries), so ordinary prose like "use paper_download to fetch the
    paper" is left untouched. Returns (cleaned_text, was_modified).
    """
    if not text or not tool_names:
        return text or "", False
    names = "|".join(re.escape(n) for n in sorted(set(tool_names), key=len, reverse=True))
    pattern = re.compile(r"(?<![\w.])(?:functions\.)?(" + names + r")\s*\([^)\n]{0,500}\)")
    cleaned = pattern.sub(notice, text)
    return cleaned, cleaned != text
