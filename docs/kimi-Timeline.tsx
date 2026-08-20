We need respond with code only. User wants transform single component (Timeline) to match reference UI from screenshot: large rounded white card 16-20px, dark near-black primary button #1f1f1f, gray status small text, colored small dots, lots of whitespace, restrained. But keep props/data-testid unchanged — wait they say "plan-card" but component is Timeline with data-testid="timeline". They mention only transform this component (keep props/data-testid unchanged——plan-card). Maybe they refer to PlanCard. But they gave Timeline component. We should keep Timeline props and data-testid timeline, maybe because it's also called plan-card? They say "plan-card" maybe indicate class or data-testid? The component currently has data-testid="timeline". It says keep props/data-testid unchanged. So we shouldn't change data-testid. Maybe plan-card implies maintain same as PlanCard? We should output full tsx code no explanations.

We need infer the reference UI. The screenshot shows a timeline/task list card inside WorkBuddy chat. It is a white rounded card with a header "任务列表" maybe "在任务列表" with dropdown, contains list of todo items, some completed (check), some pending (circle), some active (filled dot). There's no button. The card appears as a clean white rounded panel with subtle border/shadow, gray text, colored dots (blue maybe active, green completed, gray pending), minimal. Need transform the Timeline component to look more like that.

Need ensure Tailwind classes. Use rounded-[18px] maybe 16-20px. White background. Dark primary button #1f1f1f if needed? But Timeline has no button. Maybe header badges. The reference has dark badge maybe "任务列表"? It includes a dark near-black primary button #1f1f1f. But timeline component no button. Could apply same dark style to the status badge? Or maybe header row has a dark pill "任务列表" or expand button. We should integrate #1f1f1f. "深色近黑主按钮 #1f1f1f" suggests a primary action button dark. But Timeline by design has no buttons. Perhaps use it for the toggle "收起/展开"? The current toggle is small gray text. We could make it a dark pill button? That would be a button. But user said "无按钮、不等待用户——只展示任务计划与执行进度". However design reference includes dark primary button? Wait reference images are拼图从左到右5张. The referenced UI includes some card with dark button at bottom? In the screenshot there are many parts. Hard to see small details.

We need obey user: "对照抄" the reference UI. But maintain Timeline semantics: no user-blocking buttons. Could use the dark near-black style for header icon/label badge? A button element is interactive. The collapse button could be styled dark #1f1f1f to match reference primary button. But if the reference has a primary button perhaps it's not needed. We could make collapse a minimal text, not dark. However user explicitly lists "深色近黑主按钮 #1f1f1f" as characteristics of reference. Maybe in timeline card, top left title pill "任务列表" is dark? In screenshot third image from left, there's a red box around a card. Header: a row with a small triangle dropdown and "任务列表" maybe dark? Hard to see. The list items have status dots: completed is green check, active blue filled, pending gray empty. Gray status small text. We can apply.

Let's parse reference images more. The red box in third image outlines a card with header: "在 任务列表" with a chevron, then list:
- 调研全球AI应用市场现状与宏观趋势 (check? or active? maybe completed, green)
- 分析竞争格局与主要玩家 (check)
- 用户行为洞察与需求痛点调研 (circle)
- 投融资动态与产业生态梳理 (circle)
- 综合分析与趋势预测报告撰写 (circle)
- 调研全球AI Agent与数字人市场宏观趋势 (sub-item maybe with chevron)
- 分析全球竞争格局与主要玩家 (sub circle)
- 调研市场规模与机会及技术趋势
- 综合分析与趋势预测报告撰写

Looks like nested subitems with right chevrons. It may be grouped. Our component only flat list. But we can style similarly with chevron for items with tools? The steps/todo items can include tools. Maybe right chevron for items with nested tools? Not necessary.

Need produce full tsx file with imports, interface, PERM_META, Timeline, isTimelineRequest. Keep props exactly same: entry: TimelineEntry. Keep data-testid="timeline".

Let's design improved component:

- Container: rounded-[18px] bg-white border border-gray-100 shadow-[0_6px_20px_rgba(0,0,0,0.05)] overflow-hidden my-2 max-w-[520px]. This matches large rounded white card.
- Header: px-5 pt-4 pb-3. Left: maybe a dark icon circle or small colored dot? The reference header likely has a label pill. But to include dark near-black #1f1f1f, we can make a small status badge or label pill with dark background and white text? The screenshot's top left of card maybe "任务列表" text inside a dark rounded tag? Could mimic: a dark pill containing icon or title. But header already has title. Alternatively we can create a header left area: icon box rounded-lg bg-neutral-100, then title, then a status pill that is dark near-black (#1f1f1f) with white text and dot. That would be a status pill not button. User says "主按钮" dark. But this pill is primary visual element. Or we could keep current gray status pill. The reference includes "灰色状态小字、彩色小圆点". So maybe the header title or goal should be gray small text? We can make goal gray small text.

The list should be on light gray surface (currently var(--surface-3) f6f7f8). That is fine. But maybe cleaner white background with no inner gray. The reference card list items appear on white card background, no inner gray, with thin connecting line? Actually red box shows card with items on white? Maybe slight gray background. Let's examine: red box around a card in a chat; inside it appears white/light with text. It may have no inner gray container. The status dots and chevrons on right. The left has numbers? Maybe no numbers, just bullets/dots. The top has an indented dropdown "任务列表". The items have maybe expand arrows on right for nested groups. We can create a clean white list with subtle separator lines.

Reference list items:
- A small colored dot or check icon at left.
- Title in normal dark text.
- Right side: check/chevron? Actually screenshot: first items have check marks on left? Let’s inspect: The first two items have a check icon maybe in green circle on left, and title. Others have an empty circle. Some have chevron right. Bottom group has a right chevron maybe because it is collapsible group. It looks like vertical timeline with check/circle. Our component already uses numbered circles with connecting line. That is fine and elegant.

But reference maybe doesn't show numbers; only dots. The prompt mentions "彩色小圆点" colored small dots, not numbered. So maybe we should replace numbers with simple colored dots or check/circle. The current design uses numbered circle. The reference shows small colored dots (green filled for done, blue filled for active, gray outline for pending). Use smaller dot rather than numbers. Also "灰色状态小字" suggests item status labels maybe small gray.

Let's produce a version with:
- Header: title + dark status pill (#1f1f1f). The dark pill shows colored dot + "执行中"/"已完成". This incorporates dark primary button style, though not a button.
- Goal: gray small text below title or subtitle. 
- List items: 
  - no inner gray background? Maybe keep very subtle surface but rounded-xl px-3 py-2. Or no background. Use soft white and separators. I think reference has white card and list on white. But for readability, use transparent background and add py-2 and border-b last:border-b-0. However current timeline has connecting line through dots; could keep.
  - Each item: colored dot (6px) or check icon. For done: a green check inside small circle. For active: blue dot with pulse. For pending: gray empty circle. For blocked/orange, cancelled maybe. 
  - Keep vertical connecting line between dots, color changes based on previous done? Simpler always gray.
  - Text: if done, gray muted; active dark semibold; pending dark.
  - Maybe right chevron for items with tools or sub-steps? Add if tools?.length. Use `>` icon in gray. But could omit.

- Footer: permissions as small gray pills. Collapse toggle as small dark button? Since prompt mentions dark primary button, perhaps toggle can be dark rounded-md px-3 py-1 text-xs text-white bg-[#1f1f1f]. That would make it a button. The component currently uses a button for collapse; even though timeline has no blocking actions, collapse is optional. Could style as dark near-black text button. But user says "无按钮" meaning no main action buttons. The collapse is a button. But if reference has dark primary button, maybe they want this collapse button dark. However the collapse is a small utility button, not primary. I can style it as dark pill? Might look too heavy. But user says "对照抄" reference which includes dark primary button. Maybe they want the status badge to be dark. Better to reserve #1f1f1f for the top-right status badge, and keep the collapse as subtle gray text link.

However, "主按钮" means primary button, likely a call-to-action. In PlanCard there are confirm buttons dark. Timeline shouldn't have confirm, but could have a "查看详情" or "停止" action? The reference images maybe include a dark "确认执行" button? Hard to tell. But original Timeline intentionally no buttons. We shouldn't add an action that does nothing.

Need keep data-testid unchanged. Also keep import of UserInputCardRequest. Maybe remove unused `useState`? We need keep collapsed behavior. Yes.

Use CSS variables? The reference uses white etc. We can hardcode values. Keep some var fallbacks maybe. But cleaner to use Tailwind arbitrary values.

Need ensure animation pulse uses `animate-pulse` Tailwind. Add keyframes maybe not needed. Could use CSS animation within style for blue dot. But Tailwind's animate-pulse. Use style for radial shadow. For active dot we can use a ring with boxShadow.

We need output code only, no explanations.

Let's build final code:

```
import { useState } from 'react';
import type { UserInputCardRequest } from '../../../../shared/ipc';

export interface TimelineEntry {
  title: string;
  goal: string;
  steps: { name: string; tools?: string[] }[];
  permissions: string[];
  phase?: string;
  stepStatus?: Record<string, string>;
  todoItems?: { id: string; title: string; status: string }[];
  todoRevision?: number;
}

const PERM_META: Record<string, { icon: string; label: string }> = {
  network_read: { icon: '🌐', label: '网络访问' },
  workspace_write: { icon: '📄', label: '创建/修改文件' },
  exec: { icon: '⚙️', label: '执行命令' },
  external_upload: { icon: '⬆️', label: '外部上传' },
};

export function Timeline({ entry }: { entry: TimelineEntry }) {
  const [collapsed, setCollapsed] = useState(false);
  const running = entry.phase !== 'completed' && entry.phase !== 'cancelled';

  const items = entry.todoItems
    ? entry.todoItems.map((t) => ({ key: t.id, title: t.title, status: t.status, tools: [] as string[] }))
    : entry.steps.map((s) => ({ key: s.name, title: s.name, status: entry.stepStatus?.[s.name] ?? 'pending', tools: s.tools ?? [] }));

  const statusOf = (status: string) => {
    const s = status.toLowerCase();
    if (s === 'completed' || s === 'done') return 'done';
    if (s === 'in_progress' || s === 'running') return 'active';
    if (s === 'blocked') return 'blocked';
    if (s === 'cancelled') return 'cancelled';
    return 'pending';
  };

  return (
    <div
      data-testid="timeline"
      className="my-2 max-w-[520px] overflow-hidden rounded-[18px] border border-[#eceef1] bg-white shadow-[0_8px_24px_rgba(30,41,59,0.06)]"
    >
      {/* Header */}
      <div className="flex items-start gap-3 px-5 pt-4 pb-3">
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-[10px] bg-[#f4f5f6] text-[14px]">
          📋
        </div>
        <div className="min-w-0 flex-1">
          <div className="truncate text-[14px] font-semibold leading-tight text-[#1f1f1f]">
            {entry.title}
          </div>
          {entry.goal && (
            <div className="mt-1 truncate text-[12px] text-[#8e95a0]">
              {entry.goal}
            </div>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-1.5 rounded-full bg-[#1f1f1f] px-2.5 py-1 text-[11px] font-medium text-white">
          <span
            className="h-1.5 w-1.5 rounded-full bg-white"
            style={{ opacity: running ? 1 : 0.7 }}
          />
          {running ? '执行中' : '已完成'}
        </div>
      </div>

      {/* Task list */}
      {!collapsed && (
        <div className="px-5 pb-3">
          <div className="flex flex-col">
            {items.map((item, i) => {
              const st = statusOf(item.status);
              const isDone = st === 'done';
              const isActive = st === 'active';
              const isBlocked = st === 'blocked';
              const isCancelled = st === 'cancelled';

              const dotColor = isDone
                ? '#34c77b'
                : isActive
                ? '#2a7de1'
                : isBlocked
                ? '#f59e0b'
                : isCancelled
                ? '#ef4444'
                : '#d0d5dd';

              const textColor = isDone || isCancelled ? '#9aa0a8' : '#1f1f1f';
              const fontWeight = isActive ? 600 : 400;

              return (
                <div key={item.key || i} className="relative flex items-start gap-3 py-2">
                  {i < items.length - 1 && (
                    <span
                      className="absolute top-[22px] left-[5px] h-[calc(100%-12px)] w-[1.5px] bg-[#eceef1]"
                    />
                  )}
                  <span className="relative z-[1] mt-[5px] flex h-[12px] w-[12px] shrink-0 items-center justify-center rounded-full border"
                    style={{
                      borderColor: isDone ? 'transparent' : isActive ? '#2a7de1' : dotColor,
                      backgroundColor: isDone ? '#34c77b' : isActive ? '#2a7de1' : 'transparent',
                      boxShadow: isActive ? '0 0 0 3px rgba(42,125,225,0.12)' : 'none',
                    }}
                  >
                    {isDone && (
                      <svg width="7" height="7" viewBox="0 0 10 8" fill="none">
                        <path d="M1 4L3.5 6.5L9 1" stroke="white" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
                      </svg>
                    )}
                    {isActive && (
                      <span className="h-2 w-2 animate-pulse rounded-full bg-white" />
                    )}
                  </span>
                  <div className="min-w-0 flex-1">
                    <div
                      className="text-[13px] leading-snug"
                      style={{ color: textColor, fontWeight }}
                    >
                      {item.title}
                    </div>
                    {item.tools && item.tools.length > 0 && (
                      <div className="mt-1 flex flex-wrap gap-1">
                        {item.tools.map((tool) => (
                          <span
                            key={tool}
                            className="text-[10px] text-[#9aa0a8] rounded bg-[#f4f5f6] px-1.5 py-[2px]"
                          >
                            {tool}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                  {item.tools && item.tools.length > 0 && (
                    <span className="mt-1 text-[11px] text-[#c4c9d0]">›</span>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Footer */}
      <div className="flex items-center justify-between gap-3 border-t border-[#f2f3f5] px-5 py-3">
        <div className="flex flex-wrap items-center gap-1.5">
          {entry.permissions.map((p) => {
            const meta = PERM_META[p];
            if (!meta) return null;
            return (
              <span
                key={p}
                className="inline-flex items-center gap-1 rounded-md bg-[#f4f5f6] px-2 py-1 text-[11px] text-[#6b7280]"
              >
                {meta.icon}
                <span>{meta.label}</span>
              </span>
            );
          })}
        </div>
        <button
          type="button"
          onClick={() => setCollapsed((v)