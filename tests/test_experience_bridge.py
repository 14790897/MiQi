"""Phase 5: bridge handlers for experience store exist and are registered."""
import ast, pathlib

SERVER = pathlib.Path("miqi/bridge/server.py")


def _all_function_names():
    src = SERVER.read_text(encoding="utf-8")
    tree = ast.parse(src)
    return {
        n.name for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def test_handle_experience_list_defined():
    assert "handle_experience_list" in _all_function_names()

def test_handle_experience_delete_defined():
    assert "handle_experience_delete" in _all_function_names()

def test_handle_experience_toggle_defined():
    assert "handle_experience_toggle" in _all_function_names()

def test_handle_experience_search_defined():
    assert "handle_experience_search" in _all_function_names()

def test_experience_ipc_constants_defined():
    ipc_src = pathlib.Path("apps/desktop/src/shared/ipc.ts").read_text(encoding="utf-8")
    for key in ("experience:list", "experience:delete", "experience:toggle", "experience:search"):
        assert key in ipc_src, f"IPC constant missing: {key}"
