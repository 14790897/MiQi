# 对话轮次刻度条（珠子导航）交接文档

> 交接时间：2026-08-20 ｜ 分支：`feature/573-turn-gutter` ｜ PR：**#734（draft）**
> 前置：issue #573（对话轮次刻度条需求）；曾被 #586 实现后合并又被 revert（#699），#734 为重建版。

## 1. 功能是什么

对话右侧的**轮次刻度条**：每轮用户提问对应一颗珠子（圆点），让用户随时知道"聊到哪了、有哪些话题"，支持：

- **hover 珠子** → 弹出精简预览卡片（Q 编号 + 时间 + 问题 1 行 + 回答 2 行）
- **点击珠子** → 滚动跳转到该轮 + 该轮用户消息气泡闪烁高亮
- **滚动对话** → 当前视口对应珠子点亮（强调色）
- **≥2 轮**才显示刻度条

## 2. 最终设计规格（用户多轮验收后定稿）

| 项 | 规格 |
|---|---|
| 位置 | 对话区右缘（**消息头像右侧、右侧任务资产面板左侧**），从顶部导航栏（TopBar）正下方开始 |
| 布局 | 独立布局列（36px），对话区让出空间，**不覆盖**头像/消息/面板 |
| 珠子 | 9px 圆点、等距 30px、中心 0.5 向上下排布 |
| 珠子状态 | 默认 `--text-faint` 灰、hover 放大 1.35x + `--accent`、选中 `--accent`（无光晕，平淡风格） |
| 中轴线 | 2px 淡线 `rgba(255,255,255,.14)` 贯穿珠子列 |
| 分隔线 | 珠子列右侧 `border-l` 细线（与面板分隔） |
| 滚动 | 轮次多时列内上下滚动（`scrollbarWidth: none` 隐藏滚动条），间距不变 |
| 预览卡片 | hover 弹出，280px 宽，`--surface` 背景 + 细边框 + 圆角，内容精简（Q编号/时间/问题1行/回答2行） |
| 配色 | 平淡低调（参考 Google 风格），无光晕、无独立背景色（透明融入） |

## 3. 设计演进史（用户反馈全记录）

1. **v1（demo 对齐）**：按 `chat-turn-preview-demo.html` 做完整预览弹窗（470px 完整内容、固定居中）→ 用户嫌弹窗遮挡对话
2. **v2（跟随珠子）**：弹窗跟随珠子高度 → 用户对比 demo 说"完全两个物种"
3. **v3（无弹窗）**：删 hover 弹窗（参考 Google 简洁圆点）→ 用户要求珠子**等距** + **主界面右侧**（不是对话区右侧）
4. **v4（fixed 定位）**：fixed 窗口右缘 → E2E 发现 fixed 被降级（祖先 transform），实际偏移 295px
5. **v5（等距+居中）**：等距分布、中心 0.5 向上下排、列内滚动 → 用户认可排布逻辑
6. **v6（导航栏覆盖）**：珠子列从 TopBar 正下方开始（tabs/搜索栏移进对话区）→ 用户认可"导航栏顶到珠子列上方"
7. **v7（位置定稿）**：珠子列在**头像右边、白色面板左边**（对话区和面板之间，293px）→ 用户认可位置
8. **v8（精简预览）**：恢复 hover 预览但**内容精简**（Q 编号 + 时间 + 问题 1 行 + 回答 2 行）→ 当前状态

**教训**：用户对珠子位置极其敏感，反复在"对话区右缘/窗口最右/面板之间"之间反馈；最终定稿 = 对话区和面板之间（布局列不覆盖）。

## 4. 技术实现

### 关键文件
- `apps/desktop/src/renderer/features/chat/ChatConsole.tsx`（全部实现）

### 关键符号
- `turnsData`：useMemo 提取轮次（user 消息 = 一轮，assistant 填充回答）
- `tickPercents`：珠子 top px 数组（等距 30px，`64 + i*30`）
- `updateTurnUI`：滚动联动（activeTurn = 视口顶部轮次）
- `jumpToTurn(i)`：点击跳转 + 气泡 `turn-flash` 闪烁
- `gutterRef`：珠子列 ref（初始滚动定位）
- `hoverTurn`：hover 状态（驱动预览卡片）
- `showGutter`：`turnsData.length >= 2` 才显示

### 布局结构
```
ChatConsole 根 (relative flex-col, TopBar 正下方)
└── main area (flex)
    ├── chat area (flex-1: sub header + scroll + composer)
    ├── Plan Sidebar（条件）
    ├── Right panel（任务资产，panelWidth）
    └── 珠子列（turn-gutter, relative shrink-0 w-[36px], 最后 = 面板右侧）
```

### 样式要点
- 珠子列：`relative shrink-0 w-[36px] overflow-y-auto border-l` + `scrollbarWidth: none`
- 珠子：absolute left-1/2 定位，`top: tickPercents[i]px`，hover `hover:scale-[1.35]` + `hover:!bg-[var(--accent)]`
- 中轴线：`absolute left-1/2 top-0 bottom-0 w-[2px]` + `rgba(255,255,255,.14)`
- 预览卡片：absolute `left:-296px`（珠子列左侧）+ 随珠子 top 定位

## 5. E2E 验证

### 测试脚本
`apps/desktop/tests/e2e/turn-gutter-quick.spec.ts`（未跟踪，本地保留）

- node:http 起 OpenAI 兼容 mock LLM server（custom provider 注入临时 MIQI_HOME）
- 8 轮对话 → 验证珠子出现/数量/位置/交互
- 多状态截图：初始 / hover 第一颗 / hover 中间 / 点击跳转 / 滚到底

### 运行方式
```bash
cd apps/desktop
npx electron-vite build   # 必须先 build（E2E 跑生产构建，不 build 会测旧代码！）
PLAYWRIGHT_SKIP_WEB_SERVER=1 npx playwright test --project=electron tests/e2e/turn-gutter-quick.spec.ts
```

### 关键坑
1. **E2E 跑生产构建**——改了代码必须先 `electron-vite build`，否则测的是旧代码（曾因此误判位置）
2. 临时 `MIQI_HOME` 必须设置（单实例锁冲突）
3. 偶发 1 failed（hover/点击时序）——重跑即过，非代码问题
4. `*.png` 被 .gitignore 忽略——截图入库需 `git add -f`

## 6. 遗留问题 / 待办

- [ ] PR #734 验收后转正式合并（当前 draft）
- [ ] CodeRabbit 评审（#586 时代 APPROVED 过，force push 后需重新触发）
- [ ] 偶发 E2E 时序失败（重跑即过，可加等待优化）
- [ ] Kimi 视觉审查受限：moonshot-v1-8k-vision-preview 有 429 限流；kimi-k2.7-code 对"改代码"任务常返回空输出（不可靠）
- [ ] 珠子位置在不同窗口宽度下的表现（panel 开/关）已用布局列解决（无需 JS 测量）
- [ ] 之前删掉的连接线/完整预览弹窗逻辑（如后续要恢复，参考 git 历史 `8dd4bab8`）

## 7. 相关链接

- Issue #573：对话轮次刻度条需求
- PR #586：首次实现（已合并后被 revert，#699）
- PR #734：**当前重建 PR（draft）**，commit 链 `1c019e93 → 67d51546 → 4216027c → b2a9704f`
- HTML demo：`D:/Desktop/new/chat-turn-preview-demo.html`（本地参考）
- 设计参考：Google 简洁圆点风格（平淡、低调、无光晕）
