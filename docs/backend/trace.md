# 任务追踪 (Git 风格)

`miqi/agent/trace/` 实现了类似 Git 的轻量级任务追踪系统（2026-05-15 上线），替代了旧的 Lessons 经验系统。

## 核心组件

| 组件 | 文件 | 功能 |
|------|------|------|
| `TraceStore` | `store.py` | SQLite WAL 存储 + FTS5 全文索引 |
| `TaskTrace` | `model.py` | 任务追踪数据模型 |
| `Embedder` | `embedder.py` | fastembed 向量嵌入 + 余弦相似度搜索 |
| `migrate` | `migrate.py` | LESSONS.jsonl → TaskTrace 迁移工具 |

## 数据模型

```python
@dataclass
class TaskStep:
    """工具调用步骤"""
    tool_name: str           # 工具名称
    args_summary: str        # 参数摘要 (≤200 字符)
    result_summary: str      # 结果摘要 (≤200 字符)
    timestamp: float         # Unix 时间戳

@dataclass
class TaskTrace:
    """完整任务追踪"""
    trace_hash: str          # SHA256 唯一标识
    parent_hash: str | None  # 父任务 hash (支持 DAG)
    session_id: str          # 所属会话 ID
    task_name: str           # 任务名称
    goal: str                # 任务目标描述
    tool_calls: List[TaskStep]  # 工具调用链
    outcome: Literal["success", "partial", "failure"]
    outcome_notes: str       # 结果说明
    embedding: List[float] | None  # 向量嵌入
    metadata: Dict[str, Any] # 扩展元数据
```

## 追踪流程

```
任务开始
  │ task_begin(name, goal)
  ▼
工具调用链
  │ tool_A → tool_B → tool_C → ...
  ▼
任务结束
  │ task_end(outcome, notes)
  ▼
自动处理
  │ 1. 生成 embedding (fastembed)
  │ 2. 写入 TraceStore (SQLite)
  │ 3. FTS5 索引更新
```

## 相似任务检索

通过语义嵌入实现相似任务搜索：

```python
# Agent 开始新任务时自动注入相似历史任务
similar = store.search_similar(
    goal="download papers about MOF simulation",
    top_k=3,
    threshold=0.65
)
# → 注入到系统提示词，帮助 Agent 参考历史经验
```

## 嵌入模型

默认使用 `intfloat/multilingual-e5-small`：

- 支持中英文混合查询
- 本地运行，无需外部 API
- 模型大小约 92MB
- 首次使用时自动下载

## CLI 命令

```bash
miqi trace log              # 查看追踪列表
miqi trace show <hash>      # 查看追踪详情
miqi trace search <query>   # 语义搜索
miqi trace export           # 导出 JSON
miqi trace import <file>    # 导入数据
miqi trace migrate          # 从 LESSONS 迁移
```

## 与旧 Lessons 的对比

| 特性 | Legacy Lessons | Task Trace |
|------|---------------|------------|
| 数据结构 | 自然语言文本 | 结构化 Step 链 |
| 检索方式 | 关键词匹配 | 语义向量搜索 |
| 上下文注入 | 默认注入所有 | Top-K 相似注入 |
| 关系建模 | 无 | parent_hash DAG |
| 持久化 | JSONL 文件 | SQLite WAL |
