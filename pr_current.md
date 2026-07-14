## 类型

- [x] Bug 修复
- [x] UI 改进

## 变更概述

修复 #242 中侧边栏缩窄后任务筛选标签溢出的问题，并全面优化侧边栏 UI。

## 变更内容

### Bug 修复
- 筛选标签去框 → 下划线风格 + 数量光晕，缩窄时不溢出
- IN-PROGRESS 选中卡片深青绿边框（修复白框消失问题）
- 悬停阴影 + 微上浮，选中卡片加深阴影

### UI 优化
- 筛选标签：下划线指示 + Count 数字光晕（去掉了丑框）
- 卡片状态图标：进行中/待审阅/已完成/待处理 各有色块图标
- 时间中文化：刚刚 → N分钟前 → N小时前 → 昨天
- 标题中文化：任务、系统设置（+设置图标）
- 右键菜单：加 Play/Clock/Eye/CheckCircle2/RotateCcw/Archive 图标
- 进行中配色：深蓝 → 青绿 (teal #0F766E)，与其他状态彻底区分
- 卡片底色：增强 tint 从 88% → 75~90%

### 技术改动
- ContextMenu.tsx：新增可选 icon 字段
- useSessionStatus.ts：cardBg tint 调整
- globals.css：IN-PROGRESS 标签色改为 teal

### 冲突解决
- 与 #256 合并，对齐措辞：审阅 → 待审阅

## 日志/验证证据

```
npm run typecheck    → 通过
npm run build        → 通过 (4.2s)
pytest 82 tests      → 82 passed in 0.55s
vitest 6 tests       → 6 passed
```

## 截图

<img width="1264" height="821" alt="image" src="https://github.com/user-attachments/assets/db0a2ed5-2129-4630-a852-0fd798cc89a0" />

## 测试情况

- [x] typecheck 通过
- [x] build 通过
- [x] pytest 82 passed
- [x] 本地 UI 验证通过

Closes #242

