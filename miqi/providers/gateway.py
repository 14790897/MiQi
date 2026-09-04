"""Platform AI gateway — creds + endpoint constants for issue #922.

Qraft OAuth 登录后,Electron 主进程把 /oauth2/userinfo 下发的 AI 网关信息
(encryptedApiKey / aiGatewayStatus / configVersion)随 token 文件
`<workspace>/.qraft/token.json` 的 `aiGateway` 块同步到 Python。本模块负责
读取该块并判定是否应把 deepseek 模型调用路由到平台 AI 网关。

网关契约定稿于 apps/desktop/src/main/qraft/live.ai-gateway.test.ts:
  POST {GATEWAY_ORIGIN}{GATEWAY_PREFIX}/v1/messages
  header X-Api-Key: <encryptedApiKey>
  Anthropic Messages 兼容(复用 AnthropicProvider)。

放 providers 下而非 kun_runtime:providers/factory 构造 provider 时读取,
避免 providers → kun_runtime 反向依赖。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

# 网关地址走环境变量注入,默认沿用实测值(test env)。生产域名确认后经
# QRAFT_GATEWAY_BASE 下发,勿在此处硬编码密钥。
GATEWAY_ORIGIN = os.environ.get("QRAFT_GATEWAY_BASE", "http://118.25.115.164").rstrip("/")
GATEWAY_PREFIX = os.environ.get("QRAFT_GATEWAY_PREFIX", "/miqroera-deepseek")
# 唯一经过实测的网关模型(issue #922;平台模型清单随 #893 后续下发)。
GATEWAY_MODEL = "deepseek-v4-flash"
GATEWAY_ENDPOINT = f"{GATEWAY_ORIGIN}{GATEWAY_PREFIX}/v1/messages"


def gateway_token_file(config: Any) -> Path:
    """Python 侧 token 文件路径(与 services._build_billing 同源)。"""
    return Path(config.workspace_path) / ".qraft" / "token.json"


def read_gateway_creds(token_file: Path) -> dict[str, Any] | None:
    """读取可用网关凭据:aiGateway 块存在、encryptedApiKey 非空、status=='active'。

    任一前提不满足(未登录/文件缺失损坏/网关未 active/无密钥)返回 None → 保持
    直连路径。损坏/缺失按"无凭据"静默处理,不抛给 provider 构造链。
    """
    try:
        if not token_file.is_file():
            return None
        data = json.loads(token_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    gateway = data.get("aiGateway")
    if not isinstance(gateway, dict):
        return None
    key = gateway.get("encryptedApiKey")
    if not (isinstance(key, str) and key) or gateway.get("status") != "active":
        return None
    return dict(gateway)
