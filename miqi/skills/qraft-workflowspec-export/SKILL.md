---
name: qraft-workflowspec-export
description: >
  Export a WorkflowRun JSON (per workflowspec.schema.json) that organizes the
  scattered outputs of an agent problem-solving session — files, numbers,
  evidence, and conclusions — into a structured, schema-validated run record,
  then confirm the plan with the user and upload it to the Qraft platform via
  the dataUpload API (#674). Use when a session that invoked other skills has
  finished and the user wants its products organized, archived, or unified
  (e.g. "整理这次会话的产物", "把结果归档成 JSON", "export the workflow run",
  "上传方案到 Qraft", "upload the workflow"). Also use when an existing
  WorkflowRun needs to be updated with additional artifacts or conclusions.
  Trigger on post-task archiving regardless of which skills produced the
  outputs.
---

# qraft-workflowspec-export

导出一次 agent 问题解决会话的**运行记录（WorkflowRun）**：把散乱的产物——文件、关键数字、证据、结论——按实际意义归类进 `references/workflowspec.schema.json` 定义的结构，输出一份**通过 schema 校验**的 JSON，落盘到当前工作目录并在对话中给出路径。

产物统一管理 = 让每次会话的产出可追溯（谁调的哪个 skill、产出了什么文件、得出了什么结论、数字是多少）。

## 输入

调用时，从当前会话上下文收集：

- **文件路径列表**：本次会话产出的文件（相对/绝对路径均可，skill 会解析）
- **结论文字**：agent 得出的判断、分析结果（可多条）
- **被调用的 skill 列表**：本次会话实际使用过的其他 skill（每个 = 一个 node_run）
- **用户原始请求**（prompt）与**解析后的意图**（parsed_intent）——从会话开头提取
- **可选**：workflow_ref 覆盖（默认 `qraft.agent-session/1.0.0`）；backend 覆盖

产物收集方式 = **对话中指定**。不做目录扫描，不猜测哪些文件是产物——agent 刚干完活，自己知道产出了什么。

## 产物归类决策表（核心）

把每条产物按实际意义归入四类。**先判文件，再判数字，再判支撑，最后判结论。**

| 产物形态 | 去向 | 关键规则 |
|---|---|---|
| 文件（本地存在的路径） | `artifacts` | `role` 按语义选：output（最终结果）/ report（报告）/ visualization（图）/ model（模型文件）/ log / intermediate / manifest；本地文件必填 size_bytes + checksum(sha256) + exists=true；远端/URI 引用 exists=false、不填 checksum |
| 数字（带单位或明确数值语义，如"分离因子 45"、"能垒 0.8 eV"） | `metrics` | `value` 填数值（数字字符串转 number）、`unit` 填单位；名称用短横线 ID（如 `separation_factor`）；有上下界填 lower/upper_bound；`evidence_level` 按可信度：validated（实验/权威）/ screening（初步计算）/ descriptive（描述性） |
| 支撑材料（"结果来自 X 文件/第 N 行"、"数据见 table.csv"） | `evidence` | `type` 选 artifact（引文件）或 log_excerpt / observation；`artifact_ref`/`metric_ref` 指向对应 id；`quality` 按来源：direct（直接测量）/ derived（推导）/ proxy（间接指标） |
| 判断/结论（"结构是稳定的"、"该方案可行"） | `claims` | `statement` 写完整断言；`status` 按证据强度：supported（有证据支撑）/ provisional（初步判断）/ unsupported（无证据）；`evidence_refs` 挂支撑证据 id；`limitations` 写局限 |
| 会话整体 | `summary` | title（一句话主题）、human_summary（人可读摘要）、key_metric_refs、supported_claim_refs、limitations、next_actions |

**分类优先级**：一个产物只归一类。若既是数字又有结论性质（"能垒 0.8 eV 表明路径可行"）→ 数字进 metrics、判断进 claims，用 evidence_refs 关联。

**无法归类的产物**：放进 `diagnostics`（severity=info，message 说明"未归类产物：<内容>"）——不丢弃，不硬塞。

## 导出流程

### Step 1: 收集并确认输入

从会话上下文提取上述输入。文件路径若相对，先解析为绝对路径。**列出你将要导出的内容清单给用户确认**（文件 N 个、结论 M 条、skill 列表），用户确认后再继续。若关键信息缺失（如不知道调用过哪些 skill），向用户询问，不要猜。

### Step 2: 构建 WorkflowRun

按以下骨架构建 JSON（所有 id 用 `^[A-Za-z][A-Za-z0-9._:-]{0,127}$` 格式）：

```json
{
  "$schema": "https://quantamol.io/schemas/workflowspec.schema.json",
  "spec_version": "1.0.0",
  "document_kind": "workflow_run",
  "run_id": "run.<主题词>-<YYYYMMDD>",
  "workflow_ref": {
    "id": "qraft.agent-session",
    "version": "1.0.0"
  },
  "request": {
    "prompt": "用户原始请求",
    "parsed_intent": "agent 解析后的意图",
    "mode": "full",
    "requested_at": "<ISO 时间，能测就测>"
  },
  "execution": {
    "status": "completed",
    "started_at": "<能测就测，测不到省略>",
    "ended_at": "<当前时间 ISO>",
    "backend": {
      "id": "local-main",
      "kind": "local"
    }
  },
  "node_runs": [],
  "artifacts": [],
  "metrics": [],
  "evidence": [],
  "claims": [],
  "summary": {}
}
```

**字段填充规则：**

- **run_id**：`run.<主题词>-<YYYYMMDD>`，主题词 = 会话主题的英文短词（如 `mof-ion-path`、`gas-separation`），当天多次导出加后缀 `-2`、`-3`…
- **workflow_ref**：默认 `qraft.agent-session/1.0.0`；若用户指定了真实 WorkflowDefinition，则用其 id/version 并填 `definition_uri`
- **backend**：默认 `local`；若对话中明确涉及远端执行（SSH/HPC/Slurm/K8s），填对应 kind（ssh/kubernetes/…）并给 `selection_reason`
- **node_runs**：每个被调用的 skill 一个 node_run：
  ```json
  {
    "node_id": "<skill 名，如 bvse-mof-local-ssh>",
    "status": "completed",
    "output_artifact_refs": ["<该 skill 产出的 artifact id>"]
  }
  ```
  若有开始/结束时间可填，无则省略；未产出文件的 skill 的 output_artifact_refs 留空数组
- **artifacts**：每个文件一个条目：
  ```json
  {
    "id": "art-report-001",
    "title": "人能读懂的标题",
    "role": "report",
    "semantic_type": "如 energy-profile",
    "uri": "<绝对路径或 file:// URI>",
    "media_type": "如 application/pdf / image/png / text/csv",
    "exists": true,
    "size_bytes": 12345,
    "checksum": {"algorithm": "sha256", "value": "<64位hex>"}
  }
  ```
  id 用 `art-<类型>-<序号>` 风格；media_type 按扩展名推断（.pdf→application/pdf, .png→image/png, .csv→text/csv, .cif→chemical/x-cif, .txt/.log→text/plain, .json→application/json, .md→text/markdown, .html→text/html）；无法推断填 application/octet-stream
- **metrics**：`id` 用 `metric-<短名>`，`name` 用可读名，`value` 填数值
- **evidence**：`id` 用 `ev-<短名>`；`description` 写清"什么证据、来自哪"
- **claims**：`id` 用 `claim-<短名>`
- **summary**：必填 title + human_summary；key_metric_refs/supported_claim_refs 填对应 id；无则空数组

### Step 3: 计算文件校验和

对每个本地文件，用脚本计算 sha256 + size_bytes。**必须真实计算**，不得编造或省略。

### Step 4: Schema 校验（必做）

用 `scripts/validate_run.py` 对构建的 JSON 做完整 schema 校验：

```bash
python <skill_dir>/scripts/validate_run.py <output.json>
```

校验失败 → 按报错修正（字段缺失/枚举值错误/id 格式问题）→ 重新校验，直到 `VALID`。**不允许输出未通过校验的 JSON。**

### Step 4.5: 语义合理性校验（必做，A/B 分级）

Schema 校验只保证"结构合法"，不保证"内容有意义"。**每次导出必须额外做语义检查**，按两级处理：

**A 级（必拦——产物无意义，禁止生成正式文件）**：

1. `summary.human_summary` 为空 → 无人类可读摘要，记录失去归档意义
2. `artifacts`、`metrics`、`evidence`、`claims` **同时为空**且无 diagnostics 说明 → 这次导出没收集到任何东西，大概率输入遗漏
3. `metrics[].value` 不是 number（字符串 / NaN / Infinity / null）→ 指标不可比较不可分析
4. `claims[].statement` 为空串 → 结论为空
5. `workflow_ref` 缺 `version` 或 `request.prompt` 为空 → 追溯链断裂

**B 级（警告——可疑但可能真实，允许生成，警告进 diagnostics）**：

6. `metrics[].value` 绝对值超出常见物理量级（如能量 > 1e6 hartree）→ 提示"该值超出常见物理量级，请确认"
7. `request` 为空对象 → 提示"缺少用户请求上下文，追溯性受损"
8. `artifacts[].size_bytes == 0` 但有 checksum → 提示"文件大小为 0，确认是否为空文件"
9. `node_runs` 为空数组 → 提示"未记录任何 skill 调用"
10. `execution.backend.kind` 为 `other`/`manual` → 提示"后端不明确，确认 selection_reason 是否充分"
11. `artifacts[].checksum.value` 长度与 `algorithm` 不匹配（sha256=64 / sha1=40 / md5=32 位 hex）→ 提示"校验和可能错误"

**报告状态（--report-json）**：`status` 取值 `VALID` / `INVALID`（schema 或 strict 失败）/ `SEMANTIC_BLOCKED`（存在 A 级错误）。仅 `VALID` 允许进入上传流程；命令行模式下 schema 层输出 `SCHEMA VALID`，与 `SEMANTIC BLOCKED` 区分，不得用子串匹配判定成功。

**NaN / Infinity 处理**：Python `json.dump` 默认会把 NaN 写成非标准 `NaN` 字样（其他解析器可能拒收）。**任何 metric/字段值出现 NaN/Infinity 一律按 A 级拦截**，必须修正为合法数值或 null。

### Step 5: 落盘 + 最终校验（必做）

- 输出文件名：`workflowspec.run.<YYYYMMDD>.json`（与 schema 同风格；当天多次导出加序号）
- 写到**当前工作目录**
- **落盘后必须对磁盘上的正式文件再跑一次完整校验**（最终交付物校验，不是构建时校验）：

```bash
python <skill_dir>/scripts/validate_run.py <落盘文件> --schema <权威版或副本> --strict --semantic
```

- 必须输出 `VALID` + `Semantic OK (no A/B findings)`（或仅 B 级警告）才算完成
- **最终校验失败** → 回到修正循环（修正 → 重跑 → 重新落盘 → 重新最终校验），不允许交付未通过最终校验的文件
- 对话中给出：输出文件绝对路径、run_id、产物统计（N 个 artifacts、M 条 claims、K 条 metrics）、最终校验结果（VALID + 用时）

## 失败/回退路径

**A 级拦截（必填空/数值不合理/NaN）**：

- **不生成正式文件**。落盘为 `workflowspec.run.<YYYYMMDD>.invalid.json` 草稿（显式标记未通过，正式文件名不占用）
- 返回：完整错误清单（哪个字段、为什么、怎么修）+ 修正指引
- agent 补齐输入 / 修正数值 → 重跑 → 直到 VALID 才落盘正式文件
- 修正完成后提示用户删除 `.invalid.json` 草稿

**B 级警告**：

- 生成正式文件，警告写入 `diagnostics`（severity=warning），对话中明确告知用户哪些值可疑、为什么保留

**其他回退**：

- **文件不存在**（用户给了路径但文件已删除）：artifacts 填 exists=false、uri 保留、不填 size/checksum，加 diagnostics 说明
- **输入信息不足**（不知道调用过哪些 skill / 没有结论文字）：允许最小记录——node_runs 空数组、summary 只填 title+human_summary，但必须告知用户哪些部分因信息不足而留空
- **schema 副本与桌面权威版不同步**：以 skill 内副本为准（自包含原则），如发现桌面版更新，提示用户同步副本

**核心原则：正式文件名只属于通过 schema + 语义校验的产物；`.invalid.json` 只是修正用的工作文件，禁止冒充合格产物。**

## 参考

- `references/workflowspec.schema.json` — 权威 schema（必读字段约束）
- `scripts/validate_run.py` — 校验脚本（Step 4 必用）

## 上传流程（#674 新增：方案确认 → Qraft dataUpload）

导出与校验完成（Step 1–5 全部通过）后，继续以下步骤。

### Step 6: 渲染 Markdown 方案视图（会话内）

读取刚导出的 WorkflowRun JSON，在对话中输出一张 **Markdown 方案视图**，内容必须包含：

- **summary**：title、human_summary；
- **artifacts**：表格（id / title / role / size / checksum 摘要）；
- **metrics**：表格（name / value / unit / evidence_level）；
- **claims**：列表（statement / status / evidence_refs）；
- **证据引用**：每个 claim/metric 关联的 evidence/artifact 引用标注；
- **validation_report 摘要**：VALID 状态 + A 级错误数（0）+ B 级警告清单（如有）。

只读不改：方案视图是上传前的展示，不要在此步骤修改 JSON。

### Step 7: 会话确认（必做，走 #646 确认卡片）

方案视图输出后，**必须调用 `ask_user_confirm_card` 工具**请求确认，不要只在文本里问：

- 卡片标题：`确认上传方案到 Qraft 平台？`
- 卡片正文：方案摘要（title、产物统计 N artifacts / M claims / K metrics）+ 上传目标（测试环境 `test.forge.miqroera.com`）
- choices：`confirm`（确认上传）/ `adjust`（调整方案，返回修改）/ `cancel`（取消）

结果处理：

- `confirmed` → 进入 Step 8；
- `cancelled` 且 choice_id 为 `adjust` → 与用户确认要改什么，修改 JSON 后从 Step 4 重新校验，再走 Step 6–7；
- `cancelled`（超时/取消）→ 停止，不上传，告知用户可随时重来。

### Step 8: 凭据检查 + 上传

```bash
# 1) 检查登录态（只输出 {ok, source, expiresAt}，不含 token —— 防止完整凭据进入
#    工具输出与日志；不要运行不带 --no-token 的 auth.py token）
python <skill_dir>/scripts/auth.py token --json --no-token

# 2) 上传：凭据由 upload_run.py 内部解析（token 文件优先 → env → 自管登录兜底），
#    agent 全程不经手 access_token
python <skill_dir>/scripts/upload_run.py <workflowspec.run.YYYYMMDD.json> --json
```

- `auth.py` 返回 `NOT_LOGGED_IN` → 提示用户：「请到 MiQi 设置 → Qraft 平台 完成登录（浏览器登录或密码登录），登录后我会自动使用你的登录态」，**不要**自行编造凭据；
- `upload_run.py` 返回 `ok:true` → Step 9；
- 返回 `IP_NOT_WHITELISTED` → 提示「出口 IP 未加白，请联系 Qraft 管理员」；
- 返回 `TOKEN_EXPIRED` → 提示用户到 设置 → Qraft 平台 重新登录后重试；
- 返回 `BAD_REQUEST` → 把服务端 message 展示给用户，结合校验报告给修正指引；
- 返回 `SERVER_ERROR` → 平台侧问题（如服务端业务错误/缺表），把响应里的 originalMessage 转给用户并建议联系 Qraft 管理员；
- 网络类错误（`NETWORK_UNREACHABLE`）→ 脚本已自动重试，仍失败则提示稍后重试。

### Step 9: 结果展示与下一步提示

- 成功：展示脱敏后的上传响应原文（实测 body 为纯文本 `ok`），并提示「上传成功，可在 Qraft 平台查看方案」；
- 失败：展示分类后的错误与修复指引（见 Step 8 各分支）；
- 全程脱敏：对话中不得出现完整 access_token / 密码 / 手机号；token 只展示首尾片段。

## 凭据管理约定（#674 功能描述 3）

- **主路径**：读取 MiQi Desktop 登录态生成的 token 文件 `<workspace>/.qraft/token.json`（沙箱内 `/home/miqi/workspace/.qraft/token.json`），存在且未临期（`expiresAt - now > 5min`）直接使用——用户在 设置 → Qraft 平台 登录后无需任何额外配置；
- **兜底**：环境变量 `QRAFT_ACCESS_TOKEN`（直接可用）；`QRAFT_PHONE` + `QRAFT_PASSWORD`（走自管 RSA 登录，测试阶段；client_secret 有硬编码默认值，可用 `QRAFT_CLIENT_SECRET` 覆盖，转正式接入前移除默认值）；
- **安全**：SKILL.md 与脚本不硬编码任何真实凭据；token/密码/手机号在界面与日志中一律脱敏；
- 读取策略与安全权衡详见 `docs/frontend/qraft-oauth2-login.md` 第 6 节。

## 参考

- `references/workflowspec.schema.json` — 权威 schema（必读字段约束）
- `scripts/validate_run.py` — 校验脚本（Step 4 必用；`--report-json` 输出结构化 validation_report）
- `scripts/auth.py` — 凭据解析（token 文件优先 → env → 自管登录兜底）
- `scripts/upload_run.py` — dataUpload 上传封装（前置校验 + 重试 + 错误分类）
