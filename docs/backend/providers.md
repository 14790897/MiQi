# Provider 系统

Provider 系统负责与各类 LLM 服务通信，通过 `ProviderRegistry`（`miqi/providers/registry.py`）统一管理。

## 支持的提供商

### OpenAI 兼容协议

| 提供商 | 默认 Base URL | 说明 |
|--------|--------------|------|
| OpenAI | `https://api.openai.com/v1` | GPT-4o / GPT-4 / o1 系列 |
| DeepSeek | `https://api.deepseek.com` | DeepSeek-V3 / R1 |
| Moonshot | `https://api.moonshot.cn/v1` | Kimi 系列 |
| DashScope | `https://dashscope.aliyuncs.com/compatible-mode/v1` | Qwen 系列 |
| Zhipu | `https://open.bigmodel.cn/api/paas/v4` | GLM-4 系列 |
| MiniMax | `https://api.minimax.chat/v1` | abab 系列 |
| SiliconFlow | `https://api.siliconflow.cn/v1` | 开源模型托管 |
| vLLM | `http://localhost:8000/v1` | 本地自建服务 |
| Ollama | `http://localhost:11434/v1` | 本地模型 |

### 原生协议

| 提供商 | SDK | 说明 |
|--------|-----|------|
| Anthropic | `anthropic` | Claude 3.5 / 4 系列 |
| Google Gemini | `google-genai` | Gemini 1.5 / 2.0 系列 |

### 网关型

| 提供商 | 说明 |
|--------|------|
| OpenRouter | 统一 API 访问 200+ 模型 |
| AiHubMix | 国内模型聚合网关 |

## Provider 配置

```json
{
  "providers": {
    "openai": {
      "apiKey": "sk-...",
      "apiBase": "https://api.openai.com/v1",
      "defaultModel": "gpt-4o"
    },
    "deepseek": {
      "apiKey": "sk-...",
      "apiBase": "https://api.deepseek.com",
      "defaultModel": "deepseek-chat"
    }
  }
}
```

## 高级功能

### 回退链

主提供商不可用时自动切换到备用提供商：

```json
{
  "agents": {
    "fallback_chain": ["openai", "deepseek", "siliconflow"]
  }
}
```

### 智能路由

`SmartModelRouter` 根据任务复杂度自动选择模型：

- 简单任务（文件读写、信息查询）→ 低成本模型
- 复杂任务（代码生成、多步推理）→ 高性能模型
- 根据历史成功率动态调整路由策略

### 连接测试

每个提供商配置后可通过 `providers:test` IPC 测试连通性和模型可用性。
