"""Unit tests for miqi.utils.tool_text_guard."""
import pytest

from miqi.utils.tool_text_guard import (
    LEAK_NOTICE,
    sanitize_tool_call_text,
    tool_names_from_definitions,
)

TOOL_NAMES = {"paper_download", "paper_search", "web_search", "web_fetch", "write_file"}


def test_normal_prose_not_flagged():
    text = "请用 paper_download 下载论文"
    cleaned, flagged = sanitize_tool_call_text(text, TOOL_NAMES)
    assert cleaned == text
    assert flagged is False


def test_non_tool_function_not_flagged():
    text = "调用 `foo()` 完成"
    cleaned, flagged = sanitize_tool_call_text(text, TOOL_NAMES)
    assert cleaned == text
    assert flagged is False


def test_functions_prefix_leak_replaced():
    text = 'functions.paper_download(paperId="An Image is Worth 16x16 Words")'
    cleaned, flagged = sanitize_tool_call_text(text, TOOL_NAMES)
    assert flagged is True
    assert cleaned == LEAK_NOTICE
    assert "An Image is Worth 16x16 Words" not in cleaned


def test_bare_name_leak_replaced():
    text = 'paper_download("abc123")'
    cleaned, flagged = sanitize_tool_call_text(text, TOOL_NAMES)
    assert flagged is True
    assert cleaned == LEAK_NOTICE


def test_multiple_leaks_all_replaced():
    text = (
        "functions.paper_search(query=\"a\") done\n"
        'then paper_download("b") end'
    )
    cleaned, flagged = sanitize_tool_call_text(text, TOOL_NAMES)
    assert flagged is True
    assert cleaned.count(LEAK_NOTICE) == 2
    assert "paper_search" not in cleaned
    assert "paper_download" not in cleaned


def test_unknown_tool_name_not_flagged():
    text = 'unknown_tool("x")'
    cleaned, flagged = sanitize_tool_call_text(text, TOOL_NAMES)
    assert cleaned == text
    assert flagged is False


def test_identifier_boundaries_not_flagged():
    assert sanitize_tool_call_text("my_paper_download(1)", TOOL_NAMES)[1] is False
    assert sanitize_tool_call_text("paper_downloadx()", TOOL_NAMES)[1] is False
    assert sanitize_tool_call_text("_paper_download(1)", TOOL_NAMES)[1] is False


def test_leak_embedded_in_prose_keeps_context():
    text = '结果如下：functions.web_search(query="hi") 已完成'
    cleaned, flagged = sanitize_tool_call_text(text, TOOL_NAMES)
    assert flagged is True
    assert cleaned == f"结果如下：{LEAK_NOTICE} 已完成"


def test_tool_names_from_definitions_both_schemas():
    tools = [
        {"type": "function", "function": {"name": "paper_search"}},
        {"name": "write_file"},
        {},
        None,
    ]
    assert tool_names_from_definitions(tools) == {"paper_search", "write_file"}
    assert tool_names_from_definitions(None) == set()
    assert tool_names_from_definitions([]) == set()


@pytest.mark.parametrize("text", ["", None, "   "])
def test_empty_text_untouched(text):
    cleaned, flagged = sanitize_tool_call_text(text, TOOL_NAMES)
    assert flagged is False
    assert cleaned == (text or "")


def test_empty_tool_set_untouched():
    text = 'paper_download("abc")'
    cleaned, flagged = sanitize_tool_call_text(text, [])
    assert cleaned == text
    assert flagged is False
