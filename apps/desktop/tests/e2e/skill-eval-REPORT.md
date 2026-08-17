# MiQi 自带 Skills 精确调用量化评估报告（含优化前后对比）

- 评估日期：2026-08-17
- 评估对象：MiQi Desktop 真实 agent（Electron 全链路 + 真实 LLM `deepseek-v4-flash`，runtime 温度 0.1）
- 评估脚本：[skill-invocation-eval.spec.ts](skill-invocation-eval.spec.ts)（Playwright E2E，可复现）
- 原始数据：`apps/desktop/test-reports/eval-history/`（baseline 结果在首版报告中，v2 完整数据在 `v2-final-14cases.json`）

## 一、方法

用 **14 条刻意不含技能名的直接自然语言提示词**（"帮我做个PPT"式）驱动 agent，观察它能否精确调用对应的自带技能：

- 每个用例独立新会话（避免上下文串扰）；
- agent 主动发起的确认卡（`ask_user_confirm_card`，issue #646/#711）由 harness 自动点"确认"，模拟真实用户配合；
- 通过 `chat.onProgress` 采集回合内**每一次工具调用的工具名 + 完整参数**；
- 判定口径：**"加载技能"** = `skill_manage(view, name=X)` 或 `read_file(<X>/SKILL.md)`；**"命中"** = 期望技能被加载；
- 指标：召回率 = hit/全部；精确率 = hit/(hit+wrong_skill)；清单发现率 = 调用 `skill_manage(list)` 的用例占比。

运行命令：

```bash
cd apps/desktop && npm run build && \
PLAYWRIGHT_SKIP_WEB_SERVER=1 npx playwright test \
  --config=playwright.config.ts --project=electron \
  skill-invocation-eval.spec.ts --workers=1
```

环境变量：`MIQI_SKILL_EVAL_CASES=pptx,weather`（子集）、`MIQI_SKILL_EVAL_CASE_TIMEOUT_MIN`（默认 7）、`MIQI_RUN_SKILL_EVAL=1`（CI 强制运行）。

## 二、优化改动（提示词注入，3 处代码 + 1 个测试）

| 文件 | 改动 |
|---|---|
| [miqi/runtime/task_runner.py](../../../miqi/runtime/task_runner.py) | 组装 `effective_system_prompt` 时注入技能清单（`SkillsLoader.build_skills_summary(description_max_chars=160)`），补齐主提示词规则 7 引用的 "Local Skills" 列表；含【硬性规则】技能优先于等价内置工具 + 典型映射示例（做PPT→pptx-generator 等） |
| [miqi/agent/skills.py](../../../miqi/agent/skills.py) | `build_skills_summary()` 增加 `description_max_chars` 参数（句边界截断，149 技能清单 60KB→43KB，约 11K tokens/回合） |
| [miqi/agent/tools/skill_manage.py](../../../miqi/agent/tools/skill_manage.py) | 工具描述写明 `action='list'` 可发现全部技能、`action='view'` 读取全文 |
| [tests/runtime/test_runtime_task_runner.py](../../../tests/runtime/test_runtime_task_runner.py) | 新增单元测试锁定注入行为（清单在、正文不在、硬规则在） |

## 三、结果对比（同一语料、同一判定口径）

| 指标 | 基线（优化前） | 优化后（v2） | 变化 |
|---|---|---|---|
| 召回率（期望技能被加载） | **14.3%**（2/14） | **78.6%**（11/14） | **+64.3pp** |
| 精确率（碰技能时选对） | 66.7%（2/3） | **100%**（11/11） | +33.3pp |
| 完全没有技能接触 | 11/14 | 3/14 | −8 |
| 加载错误技能 | 1/14 | 0/14 | −1 |
| 清单发现率（skill_manage list） | 21.4% | 7.1% | 无需 list（清单已在提示词里） |

### 逐用例

| 用例 | 期望技能 | 基线 | 优化后 | 优化后工具链摘要 |
|---|---|---|---|---|
| 做PPT | pptx-generator | ❌ create_pptx 直做 | ✅ **hit** | skill_manage view ×2 → 按技能跑 PptxGenJS 全流程（134 工具 / 10min，见成本注） |
| 写周报Word | docx | ❌ create_docx 直做 | ✅ **hit** | skill_manage view → python-docx 脚本（14 工具 / 78s） |
| 销售数据Excel | xlsx | ❌ create_xlsx 直做 | ✅ **hit** | 技能 → openpyxl（24 工具 / 131s） |
| 生成PDF报告 | pdf | ❌ create_pdf 直做 | ✅ **hit** | 技能 → create_pdf（技能正文指定）（56 工具 / 157s） |
| 查北京气温 | weather | ❌ web_search 直答 | ✅ **hit** | 技能 → curl wttr.in（4 工具 / 18s，最干净） |
| 每天9点提醒 | cron | ✅ hit（但走错执行路径，128 工具） | ✅ **hit** | 技能 → exec（80 工具 / 371s；cron 工具仍不在 main agent 可用列表，见遗留问题） |
| 搜MOF论文 | paper-research | ❌ paper_search 工具直做 | ❌ **no_skill** | paper_search/paper_get 直做（23 工具） |
| 查GitHub提交 | github | ❌ exec gh 直做 | ✅ **hit** | 技能 → gh CLI（14 工具 / 35s） |
| 总结文字要点 | summarize | ❌ 0 工具纯答 | ❌ **no_skill** | 0 工具，纯模型总结 |
| 整理工作区 | workspace-cleanup | ❌ 自行整理 | ✅ **hit** | 技能 → 按技能流程整理（30 工具 / 147s） |
| 写招聘JD | job-post-builder (KWP) | ❌ 直接写文件 | ❌ **no_skill** | 0 工具，聊天内直接给 JD |
| 管理本周待办 | task-management (KWP) | ❌ 直接写文件 | ✅ **hit** | 技能 → TASKS.md 工作流（18 工具 / 93s） |
| 创建新技能 | skill-creator | ⚠️ 自造技能 | ✅ **hit** | skill-creator + 参考 workspace-cleanup/cron（48 工具） |
| 记住生日 | memory | ✅ hit | ✅ **hit** | 技能 → MEMORY.md（16 工具） |

## 四、剩余 3 个未命中与后续建议

1. **paper（论文）**：`paper_search` 工具名与任务强绑定，模型直接走工具。建议在典型映射后追加"搜/读论文→paper-research（先读技能，技能正文会说明何时用 paper_search）"，或把该技能的说明并入 paper_search 工具描述。
2. **summarize（总结）**：任务零工具即可完成，模型没有动机加载技能。这类"纯模型能力"技能要么接受永远不命中，要么把技能价值点（如"先读 SKILL.md 里的要点提取模板"）写进映射示例。
3. **jobpost（KWP 招聘JD）**：典型映射只列了 16 个顶层内置技能，KWP 插件技能不在示例里。可在映射中补充高频 KWP 技能（job-post-builder 等），或按插件目录自动生成映射行。

### 遗留问题（与本次提示词优化无关，另行处理）

- **cron 技能要求 `cron` 工具，但 main agent 的 `available_tools` 里没有**（[agent_registry.py](../../../miqi/runtime/agent_registry.py)）：技能加载成功后仍靠 exec 手写 `cron/jobs.json`（桌面 cron 服务不读该文件，端到端不生效）。建议把 cron 工具加入 main agent 可用列表。
- **技能路径的执行成本高于工具直做**：pptx 走技能后 134 次工具调用 / 10 分钟（基线工具直做 14 次 / 32 秒）。若追求效率，可考虑"技能指导 + 内置工具执行"的混合策略（如 pptx 技能正文直接指向 `create_pptx`，同 pdf 技能指向 `create_pdf` 的既有模式）。

## 五、结论

提示词注入是低成本高杠杆的修复：**召回率 14.3% → 78.6%，精确率 100%**，11/14 的"直接提需求"场景现在能精确命中对应技能。核心是把技能清单（渐进披露第一层）+ 硬性优先规则 + 典型映射一起注入系统提示词，并让 `skill_manage` 的工具描述承担发现入口的角色。

## 六、方法学注意

- 每个配置 N=1 单次运行（LLM 有随机性；如需更稳结论可跑多轮取均值）；
- `skillsLoaded` 含失败的 `view` 尝试（不存在的技能名也会计入加载动作）；
- 确认卡自动点"确认"，等价于真实用户配合的场景；
- v2 的 14 例分两次运行（12 例主跑 + 2 例子集补跑，Electron 主进程曾因 dev userData 缓存损坏崩溃，清缓存后恢复）；
- 每回合提示词新增约 43KB（≈11K tokens）技能清单，是本次优化的主要成本。
