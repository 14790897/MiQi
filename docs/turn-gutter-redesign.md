# 对话轮次导航珠子重构说明

## 背景
桌面端右侧“对话轮次导航珠子”此前存在间距、滚动条贴近、预览卡无锚点、视觉过硬等问题。本次按 HTML demo 的交互方向重构。

## 改动文件
- apps/desktop/src/renderer/features/chat/ChatConsole.tsx
- apps/desktop/src/renderer/styles/globals.css
- apps/desktop/src/renderer/components/Sidebar.tsx

## 1. 布局与定位
- 珠子轨道从 right-4 调整到 right-7，与右侧滚动条保持约 13-16px 安全距离。
- 滚动容器增加 scrollbar-gutter: stable，避免内容随滚动条出现抖动。
- 预览卡片仍垂直跟随 hover 珠子，卡片右侧新增三角箭头指向珠子。
- 消息容器宽度改为 calc(100% - 96px)，输入框容器改为 calc(100% - 56px)，均保持居中，视觉上与主界面宽度基本一致。

## 2. 珠子与时间轴
- 轨道线改为 1px 半透明细线，贯穿所有珠子中心。
- 默认态：6px 半透明灰点。
- 悬停态：0.2s 平滑放大（scale 属性，不与 Tailwind translate 叠加），背景加亮并带软阴影；激活珠子悬停时保持主题色。
- 激活态：10px 主题色圆点，外圈 4px 半透明主题色光环。
- 珠子以轨道中线为轴等距分布，轮次多时压缩在中间区域，不出现内部滚动条。

## 3. 预览卡片
- 阴影改为 0 8px 24px rgba(0,0,0,0.15)。
- 增加毛玻璃 backdrop-filter: blur(8px)，背景为 88% 透明度的 surface。
- 悬停打开增加 150ms 防抖，避免快速划过时频繁闪烁。
- 关闭保留 200ms 延迟，便于指针从珠子移动到卡片。

## 4. 其他
- Sidebar.tsx 修复 ContextMenu clone 的类型问题。
- 跳转闪烁改为低调中性色。

## 验证
- npm run typecheck:web 通过
- npm run build 通过
- 截图：C:/tmp/miqi-turn-gutter-v2.png、C:/tmp/miqi-turn-preview-v2.png
- Playwright 坐标验证：预览卡中心与珠子中心 alignDelta = 0；卡片与输入框间距 102px；珠子以轨道中线 494 对称分布，轨道无内部滚动条。
- PR：https://github.com/14790897/MiQi/pull/586