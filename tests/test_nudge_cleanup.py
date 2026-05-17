"""Phase 7: trace nudge variables must not exist in AgentLoop.__init__."""
import ast, pathlib

LOOP = pathlib.Path("miqi/agent/loop.py")


def _assignments_in_init():
    src = LOOP.read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "AgentLoop":
            for item in ast.walk(node):
                if isinstance(item, ast.FunctionDef) and item.name == "__init__":
                    for stmt in ast.walk(item):
                        if isinstance(stmt, (ast.Assign, ast.AnnAssign)):
                            targets: list = []
                            if isinstance(stmt, ast.Assign):
                                targets = stmt.targets
                            elif isinstance(stmt, ast.AnnAssign) and stmt.target:
                                targets = [stmt.target]
                            for t in targets:
                                if isinstance(t, ast.Attribute):
                                    yield t.attr


assigned = set(_assignments_in_init())


def test_trace_nudge_counter_removed():
    assert "_trace_nudge_counter" not in assigned, \
        "_trace_nudge_counter should be removed from AgentLoop.__init__"


def test_trace_nudge_pending_removed():
    assert "_trace_nudge_pending" not in assigned, \
        "_trace_nudge_pending should be removed from AgentLoop.__init__"


def test_trace_nudge_interval_removed():
    assert "_trace_nudge_interval" not in assigned, \
        "_trace_nudge_interval should be removed from AgentLoop.__init__"


def test_memory_nudge_counter_still_present():
    """memory nudge is still useful — must NOT be removed."""
    assert "_memory_nudge_counter" in assigned
