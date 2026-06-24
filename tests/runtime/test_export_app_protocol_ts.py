from __future__ import annotations

from miqi.runtime.export_app_protocol_ts import render_typescript_contract


def test_render_typescript_contract_is_deterministic():
    first = render_typescript_contract()
    second = render_typescript_contract()

    assert first == second
    assert "APP_PROTOCOL_GENERATED_AT = 'static'" in first


def test_render_typescript_contract_contains_key_method_names():
    output = render_typescript_contract()

    assert "'turn/start'" in output
    assert "'command/exec'" in output
    assert "'process/spawn'" in output
    assert "'fs/writeFile'" in output
    assert "'fuzzyFileSearch/sessionStart'" in output


def test_render_typescript_contract_maps_required_and_optional_fields():
    output = render_typescript_contract()

    assert "export interface FsWriteFileParams" in output
    assert "path: string" in output
    assert "dataBase64: string" in output
    assert "export interface FsRemoveParams" in output
    assert "recursive?: boolean" in output
    assert "force?: boolean" in output


def test_render_typescript_contract_excludes_internal_fields():
    output = render_typescript_contract()

    assert "cwd_raw" not in output
    assert "cwdRaw" not in output


def test_render_typescript_contract_contains_typed_results_and_events():
    output = render_typescript_contract()

    assert "export interface CommandExecResult" in output
    assert "exitCode: number" in output
    assert "export interface ProcessExitedEventPayload" in output
    assert "processHandle: string" in output
    assert "export interface FsChangedEventPayload" in output
    assert "changedPaths: string[]" in output
    assert "export interface AppEventPayloadMap" in output
    assert "'process/exited': ProcessExitedEventPayload" in output
