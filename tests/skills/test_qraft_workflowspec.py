"""qraft-workflowspec-export Skill 脚本测试（#674）。

覆盖 auth.py（token 文件解析/过期/兜底/自管登录/脱敏）与
upload_run.py（前置校验/重试/错误分类）。HTTP 全部走 httpx.MockTransport，
无真实网络依赖。
"""

from __future__ import annotations

import importlib.util
import json
import time
from pathlib import Path

import httpx
import pytest

SKILL_DIR = (
    Path(__file__).resolve().parents[2]
    / "miqi"
    / "skills"
    / "qraft-workflowspec-export"
    / "scripts"
)


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


auth = _load_module("qraft_auth", SKILL_DIR / "auth.py")
upload = _load_module("qraft_upload", SKILL_DIR / "upload_run.py")


def make_token_file(tmp_path: Path, expires_in_ms: int) -> Path:
    path = tmp_path / "token.json"
    path.write_text(
        json.dumps(
            {"accessToken": "TOKEN-ABC", "expiresAt": int(time.time() * 1000) + expires_in_ms}
        ),
        encoding="utf-8",
    )
    return path


# ── auth.py：token 解析 ──────────────────────────────────────────────────


class TestResolveToken:
    def test_token_file_valid(self, tmp_path, monkeypatch):
        path = make_token_file(tmp_path, 7_199_000)
        monkeypatch.delenv("QRAFT_ACCESS_TOKEN", raising=False)
        monkeypatch.delenv("QRAFT_PHONE", raising=False)
        data = auth.resolve_token("https://test.forge.miqroera.com/api", str(path))
        assert data["accessToken"] == "TOKEN-ABC"
        assert data["source"] == f"token_file:{path}"

    def test_token_file_expired_falls_through(self, tmp_path, monkeypatch):
        path = make_token_file(tmp_path, -1_000)  # 已过期
        monkeypatch.setenv("QRAFT_ACCESS_TOKEN", "ENV-TOKEN")
        data = auth.resolve_token("https://test.forge.miqroera.com/api", str(path))
        assert data["accessToken"] == "ENV-TOKEN"
        assert data["source"] == "env:QRAFT_ACCESS_TOKEN"

    def test_not_logged_in_gives_settings_guidance(self, tmp_path, monkeypatch):
        monkeypatch.delenv("QRAFT_ACCESS_TOKEN", raising=False)
        monkeypatch.delenv("QRAFT_PHONE", raising=False)
        monkeypatch.delenv("QRAFT_PASSWORD", raising=False)
        monkeypatch.delenv("QRAFT_TOKEN_FILE", raising=False)
        monkeypatch.setenv("MIQI_HOME", str(tmp_path))  # 无 token 文件的临时 home
        monkeypatch.chdir(tmp_path)  # 隔离 cwd，避免读到自己机器上的 workspace token 文件
        with pytest.raises(auth.AuthError) as exc_info:
            auth.resolve_token("https://test.forge.miqroera.com/api", None)
        assert exc_info.value.code == "NOT_LOGGED_IN"
        assert "设置" in exc_info.value.message and "Qraft" in exc_info.value.message


class TestMaskSecret:
    def test_short_value_fully_masked(self):
        assert auth.mask_secret("abc") == "***"

    def test_tail_zero_does_not_leak(self):
        code = "VWEM98W74FDoNGXvBazCF2xuPv15s4LMeINsXtqg2d9u8yi415yKd3IpExDu"
        masked = auth.mask_secret(code, 6, 0)
        assert masked == "VWEM98…"
        assert "VWEM98W74FDo" not in masked


class TestSelfManagedLogin:
    """自管凭据兜底：mock 全链路 HTTP（公钥提取 → 登录 → 授权 → 换 token）。"""

    def test_full_flow(self, monkeypatch):
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import rsa

        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        pem = key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode("utf-8")
        escaped = pem.replace("\n", "\\n")

        code = "BROWSER-CODE-123"
        authorize_count = {"n": 0}
        login_requests: list[dict] = []

        def handler2(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/oauth2/authorize" and request.method == "GET":
                authorize_count["n"] += 1
                if authorize_count["n"] >= 2:
                    return httpx.Response(
                        302,
                        headers={
                            "Location": f"http://localhost:38000/callback?code={code}"
                        },
                    )
                return httpx.Response(200, text="<html>授权确认页</html>")
            if request.url.path == "/api/oauth2/token" and request.method == "POST":
                return httpx.Response(
                    200,
                    json={
                        "code": 200,
                        "msg": "ok",
                        "access_token": "REAL-ACCESS",
                        "refresh_token": "REAL-REFRESH",
                        "expires_in": "7199",
                        "openid": "openid-1",
                    },
                )
            if request.url.path == "/api/portal/auth/login" and request.method == "POST":
                body = json.loads(request.content)
                login_requests.append(body)
                return httpx.Response(
                    200,
                    json={"code": 200, "data": {"userId": "19"}},
                    headers={"Set-Cookie": "Authorization=cookie-1; Path=/"},
                )
            if request.url.path == "/api/oauth2/doConfirm" and request.method == "POST":
                return httpx.Response(200, json={"code": 200, "msg": "ok"})
            if request.url.path == "/login" and request.method == "GET":
                return httpx.Response(
                    200,
                    text='<html><script src="/static/js/era-index-abc.js"></script></html>',
                )
            if "/era-index-abc.js" in str(request.url):
                return httpx.Response(200, text=f'var pub="{escaped}";')
            return httpx.Response(404)

        orig_client = httpx.Client
        def fake_client(**kwargs):
            return orig_client(transport=httpx.MockTransport(handler2))

        monkeypatch.setattr(auth.httpx, "Client", fake_client)
        monkeypatch.setenv("QRAFT_CLIENT_SECRET", "test-secret")
        data = auth.self_managed_login(
            "https://test.forge.miqroera.com/api", "18500000000", "test-password"
        )
        assert data["accessToken"] == "REAL-ACCESS"
        assert data["expiresAt"] > time.time() * 1000
        # 授权流程：首次 200 确认页 → doConfirm → 二次 302 取 code
        assert authorize_count["n"] >= 2
        # 密码经 RSA PKCS#1 v1.5 加密后传输，私钥可还原
        import base64 as b64

        from cryptography.hazmat.primitives.asymmetric import padding

        plain = key.decrypt(
            b64.b64decode(login_requests[0]["password"]), padding.PKCS1v15()
        ).decode("utf-8")
        assert plain == "test-password"


# ── upload_run.py：前置校验 / 分类 / 重试 ───────────────────────────────


class TestPreCheck:
    def test_missing_file(self, tmp_path):
        with pytest.raises(upload.UploadError, match="文件不存在"):
            upload.pre_check(tmp_path / "nope.json")

    def test_wrong_suffix(self, tmp_path):
        f = tmp_path / "run.txt"
        f.write_text("{}", encoding="utf-8")
        with pytest.raises(upload.UploadError, match="仅支持 .json"):
            upload.pre_check(f)

    def test_oversize(self, tmp_path, monkeypatch):
        monkeypatch.setattr(upload, "MAX_FILE_BYTES", 10)
        f = tmp_path / "run.json"
        f.write_text("x" * 20, encoding="utf-8")
        with pytest.raises(upload.UploadError, match="上限"):
            upload.pre_check(f)

    def test_invalid_json(self, tmp_path):
        f = tmp_path / "run.json"
        f.write_text("{not json", encoding="utf-8")
        with pytest.raises(upload.UploadError, match="不是合法 JSON"):
            upload.pre_check(f)

    def test_missing_document_kind(self, tmp_path):
        f = tmp_path / "run.json"
        f.write_text('{"a": 1}', encoding="utf-8")
        with pytest.raises(upload.UploadError, match="document_kind"):
            upload.pre_check(f)

    def test_ok(self, tmp_path):
        f = tmp_path / "run.json"
        f.write_text('{"document_kind": "workflow_run"}', encoding="utf-8")
        doc = upload.pre_check(f)
        assert doc["document_kind"] == "workflow_run"


class TestClassifyResponse:
    def _resp(self, status: int, body: str, headers=None):
        return httpx.Response(status, text=body, headers=headers or {})

    def test_403_ip_whitelist(self):
        code, msg = upload.classify_response(self._resp(403, "<html>nginx</html>"), "")
        assert code == "IP_NOT_WHITELISTED"
        assert "加白" in msg

    def test_401_token_expired(self):
        code, msg = upload.classify_response(self._resp(401, "unauthorized"), "")
        assert code == "TOKEN_EXPIRED"
        assert "重新登录" in msg

    def test_400_business_message(self):
        code, msg = upload.classify_response(
            self._resp(400, '{"message":"参数错误"}',
                       headers={"content-type": "application/json"}), ""
        )
        assert code == "BAD_REQUEST"
        assert "参数错误" in msg

    def test_200_ok(self):
        code, msg = upload.classify_response(self._resp(200, "ok"), "ok")
        assert code == "OK"
        assert msg == "ok"

    def test_200_with_business_error_envelope_not_treated_as_ok(self):
        # 实测：Qraft 服务端缺表时 HTTP 200 + 业务错误信封，必须分类为失败
        body = json.dumps(
            {
                "code": 500,
                "msg": "未知错误",
                "data": {"originalMessage": "SQLSyntaxErrorException: Table 'x' doesn't exist"},
            }
        )
        code, msg = upload.classify_response(
            self._resp(200, body, headers={"content-type": "application/json"}), body
        )
        assert code == "SERVER_ERROR"
        assert "doesn't exist" in msg or "业务错误" in msg


class TestUploadFile:
    def test_success(self, tmp_path, monkeypatch):
        f = tmp_path / "run.json"
        f.write_text('{"document_kind": "workflow_run"}', encoding="utf-8")
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(200, text="ok")

        orig_client = httpx.Client

        def fake_client(**kwargs):
            return orig_client(transport=httpx.MockTransport(handler))

        monkeypatch.setattr(upload.httpx, "Client", fake_client)
        code, message, status = upload.upload_file(
            "https://test.forge.miqroera.com/api", f, "TOKEN", retries=2
        )
        assert code == "OK"
        assert status == 200
        assert seen[0].headers["Authorization"] == "Bearer TOKEN"
        assert seen[0].url.path == "/api/oauth2/dataUpload"

    def test_network_error_then_success_retries(self, tmp_path, monkeypatch):
        f = tmp_path / "run.json"
        f.write_text('{"document_kind": "workflow_run"}', encoding="utf-8")
        calls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            if calls["n"] == 1:
                raise httpx.TransportError("connection reset")
            return httpx.Response(200, text="ok")

        orig_client = httpx.Client

        def fake_client(**kwargs):
            return orig_client(transport=httpx.MockTransport(handler))

        monkeypatch.setattr(upload.httpx, "Client", fake_client)
        monkeypatch.setattr(upload.time, "sleep", lambda s: None)  # 跳过退避
        code, _, _ = upload.upload_file(
            "https://test.forge.miqroera.com/api", f, "TOKEN", retries=2
        )
        assert code == "OK"
        assert calls["n"] == 2

    def test_403_no_retry(self, tmp_path, monkeypatch):
        f = tmp_path / "run.json"
        f.write_text('{"document_kind": "workflow_run"}', encoding="utf-8")
        calls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            return httpx.Response(403, text="<html>nginx</html>")

        orig_client = httpx.Client

        def fake_client(**kwargs):
            return orig_client(transport=httpx.MockTransport(handler))

        monkeypatch.setattr(upload.httpx, "Client", fake_client)
        code, message, _ = upload.upload_file(
            "https://test.forge.miqroera.com/api", f, "TOKEN", retries=2
        )
        assert code == "IP_NOT_WHITELISTED"
        assert calls["n"] == 1  # 业务错误不重试


class TestClientSecretAndRetryExhaustion:
    def test_exchange_token_requires_env_secret(self, monkeypatch):
        monkeypatch.delenv("QRAFT_CLIENT_SECRET", raising=False)
        client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500)))
        with pytest.raises(auth.AuthError) as exc_info:
            auth.exchange_token(client, "https://test.forge.miqroera.com/api", "code-1", "http://localhost:1/cb")
        assert exc_info.value.code == "CLIENT_SECRET_MISSING"
        assert "QRAFT_CLIENT_SECRET" in exc_info.value.message

    def test_auth_retry_exhausted_raises_classified_error(self, monkeypatch):
        def boom():
            raise httpx.TransportError("connection reset")

        monkeypatch.setattr(auth.time, "sleep", lambda s: None)
        monkeypatch.setattr(auth, "RETRIES", 1)
        with pytest.raises(auth.AuthError) as exc_info:
            auth.retry_http(boom)
        assert exc_info.value.code == "NETWORK_UNREACHABLE"

    def test_upload_retry_exhausted_raises_upload_error(self, tmp_path, monkeypatch):
        f = tmp_path / "run.json"
        f.write_text('{"document_kind": "workflow_run"}', encoding="utf-8")

        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.TransportError("connection reset")

        orig_client = httpx.Client

        def fake_client(**kwargs):
            return orig_client(transport=httpx.MockTransport(handler))

        monkeypatch.setattr(upload.httpx, "Client", fake_client)
        monkeypatch.setattr(upload.time, "sleep", lambda s: None)
        with pytest.raises(upload.UploadError) as exc_info:
            upload.upload_file("https://test.forge.miqroera.com/api", f, "bearer-x", retries=1)
        assert exc_info.value.code == "NETWORK_UNREACHABLE"


class TestAuthCliNoToken:
    def test_no_token_mode_omits_access_token(self, tmp_path, monkeypatch, capsys):
        path = make_token_file(tmp_path, 7_199_000)
        monkeypatch.setattr(
            "sys.argv", ["auth.py", "token", "--json", "--no-token", "--token-file", str(path)]
        )
        rc = auth.main()
        assert rc == 0
        out = capsys.readouterr().out.strip()
        payload = json.loads(out)
        assert payload["ok"] is True
        assert "accessToken" not in payload
        assert payload["source"].startswith("token_file:")

    def test_json_mode_still_includes_token_for_script_consumption(
        self, tmp_path, monkeypatch, capsys
    ):
        path = make_token_file(tmp_path, 7_199_000)
        monkeypatch.setattr(
            "sys.argv", ["auth.py", "token", "--json", "--token-file", str(path)]
        )
        rc = auth.main()
        assert rc == 0
        payload = json.loads(capsys.readouterr().out.strip())
        assert payload["accessToken"] == "TOKEN-ABC"
