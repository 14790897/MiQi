from miqi.sandbox import sandbox_manager

def read_file(path: str):
    resolved_path = sandbox_manager.resolve_path(path)
    with open(resolved_path, 'r', encoding='utf-8', errors='ignore') as f:
        return f.read()

def open_external(path: str):
    resolved_path = sandbox_manager.resolve_path(path)
    import os
    os.startfile(resolved_path) if hasattr(os, 'startfile') else os.system(f'open "{resolved_path}"')
