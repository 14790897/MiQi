/**
 * HermesConfirmBar — 确认条组件（严格对照 Hermes approval.tsx 抄）。
 *
 * Hermes 原版（apps/desktop/src/components/assistant-ui/tool/approval.tsx）：
 *   [Run(带 ⌘⏎/Ctrl⏎ 提示)] | [▾ 下拉: 本会话 / 总是(二次确认 Dialog) / 拒绝] [拒绝(Esc)] [命令展开]
 *   - 快捷键：Ctrl/⌘+Enter → run，Esc → deny（window keydown capture；Dialog 打开时让位）
 *   - submitting 时主/副按钮显示 Loader
 *   - "总是允许" 走二次确认 Dialog（因为要持久化）
 *
 * MiQi 适配：
 *   - 主题色用 --accent（#2a7de1 蓝）替代 Hermes 的 primary
 *   - 档位按用户定稿：一次(confirm)/本会话(session)/拒绝(deny)；"总是" 默认隐藏
 *     （2026-08-25 拍板：always 跨会话被否——allowAlways 默认 false）
 *   - MiQi 特有：修改计划按钮（allowModify —— 引导输入不结束对话）
 *
 * 用于 PlanCard / ActionCard 底部操作条（等待态）。
 */
import { useEffect, useRef, useState } from 'react';
import * as DropdownMenu from '@radix-ui/react-dropdown-menu';
import * as Dialog from '@radix-ui/react-dialog';
import { ChevronDown, Loader2 } from 'lucide-react';

export type HermesConfirmChoice = 'confirm' | 'session' | 'always' | 'deny' | 'modify';

interface HermesConfirmBarProps {
  /** 主按钮文案（开始执行 / 确认上传 / 确认执行…） */
  runLabel: string;
  onResolve: (choice: HermesConfirmChoice, rememberMode?: 'session' | 'always' | null) => void;
  /** 外部 busy（如后端已受理、卡片即将关闭）——禁用所有按钮 */
  busy?: boolean;
  /** 主条色调：accent（计划/普通确认）| danger（危险动作——删除/支付） */
  tone?: 'accent' | 'danger';
  /** 是否显示"本会话"档（默认 true） */
  allowSession?: boolean;
  /** 是否显示"总是"档（默认 false——用户定稿 always 跨会话被否） */
  allowAlways?: boolean;
  /** MiQi 特有：修改计划按钮（默认 false） */
  allowModify?: boolean;
  /** always 二次确认 Dialog 里的描述文本 */
  description?: string;
  /** 可展开的详情文本（命令/计划明细——Hermes 的 showCommand） */
  expandableText?: string;
  /** 展开详情按钮文案（默认"详情"） */
  expandLabel?: string;
  /** 拒绝按钮文案（默认"拒绝"） */
  denyLabel?: string;
  /** 拒绝按钮 title（默认"拒绝（Esc）"） */
  denyTitle?: string;
}

const ACCENT = 'var(--accent, #2a7de1)';
const DANGER = 'var(--danger, #e5484d)';

export function HermesConfirmBar({
  runLabel,
  onResolve,
  busy = false,
  tone = 'accent',
  allowSession = true,
  allowAlways = false,
  allowModify = false,
  description,
  expandableText,
  expandLabel = '详情',
  denyLabel = '拒绝',
  denyTitle = '拒绝（Esc）',
}: HermesConfirmBarProps) {
  const [submitting, setSubmitting] = useState<HermesConfirmChoice | null>(null);
  const [confirmAlways, setConfirmAlways] = useState(false);
  const [showDetails, setShowDetails] = useState(false);
  const busyNow = busy || submitting !== null;
  const hasDetails = !!expandableText && expandableText.trim().length > 0;
  const barColor = tone === 'danger' ? DANGER : ACCENT;

  const respond = (choice: HermesConfirmChoice) => {
    if (busyNow) return;
    if (choice === 'always') {
      // Hermes 同款：always 持久化前先二次确认（Radix focus-return 竞态——
      // 延一 tick 等菜单卸载再挂 Dialog）
      setConfirmAlways(true);
      return;
    }
    setSubmitting(choice);
    onResolve(choice);
  };

  // Ctrl/⌘+Enter → run；Esc → deny。always Dialog 打开时键盘让位（Esc 关 Dialog）。
  useEffect(() => {
    if (confirmAlways) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
        event.preventDefault();
        if (!busyNow) {
          setSubmitting('confirm');
          onResolve('confirm');
        }
      } else if (event.key === 'Escape') {
        event.preventDefault();
        if (!busyNow) {
          setSubmitting('deny');
          onResolve('deny');
        }
      }
    };
    window.addEventListener('keydown', onKeyDown, true);
    return () => window.removeEventListener('keydown', onKeyDown, true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [confirmAlways, busy]);

  const isMac = typeof navigator !== 'undefined' && /Mac|iP(hone|ad|od)/.test(navigator.platform);

  return (
    <div className="flex items-center gap-2">
      {/* Hermes 原样条：Run + 竖分隔 + Dropdown(本会话/总是/拒绝) */}
      <div
        className="inline-flex h-6 items-stretch overflow-hidden rounded-md border"
        style={{ borderColor: 'color-mix(in srgb, ${barColor} 25%, transparent)', background: 'color-mix(in srgb, ${barColor} 10%, transparent)' }}
      >
        <button
          onClick={() => respond('confirm')}
          disabled={busyNow}
          className="h-full gap-1 rounded-none px-3 text-xs font-medium cursor-pointer hover:opacity-85 disabled:opacity-50"
          style={{ background: 'none', border: 'none', color: barColor, fontFamily: 'inherit' }}
        >
          {submitting === 'confirm' ? (
            <Loader2 className="inline size-3 animate-spin" />
          ) : (
            <>
              {runLabel}
              <span className="ml-1 text-[0.625rem]" style={{ color: 'color-mix(in srgb, ${barColor} 60%, transparent)' }}>
                {isMac ? '⌘⏎' : 'Ctrl⏎'}
              </span>
            </>
          )}
        </button>
        <span aria-hidden className="w-px self-stretch" style={{ background: 'color-mix(in srgb, ${barColor} 20%, transparent)' }} />
        <DropdownMenu.Root>
          <DropdownMenu.Trigger asChild>
            <button
              aria-label="更多选项"
              className="h-full w-5 cursor-pointer rounded-none px-0 hover:opacity-85 disabled:opacity-50"
              style={{ background: 'none', border: 'none', color: barColor }}
              disabled={busyNow}
            >
              {submitting === 'session' || submitting === 'always' ? (
                <Loader2 className="mx-auto size-3 animate-spin" />
              ) : (
                <ChevronDown className="mx-auto size-3" />
              )}
            </button>
          </DropdownMenu.Trigger>
          <DropdownMenu.Portal>
            <DropdownMenu.Content
              align="start"
              sideOffset={4}
              className="z-50 min-w-40 rounded-lg border bg-white p-1 shadow-lg"
              style={{ borderColor: 'rgba(0,0,0,.08)', fontFamily: 'inherit' }}
            >
              {allowSession && (
                <DropdownMenu.Item
                  onSelect={() => {
                    setSubmitting('session');
                    onResolve('session');
                  }}
                  className="cursor-pointer rounded-md px-2.5 py-1.5 text-xs outline-none hover:bg-[#f0f2f5]"
                >
                  本会话允许
                </DropdownMenu.Item>
              )}
              {allowAlways && (
                <DropdownMenu.Item
                  onSelect={() => respond('always')}
                  className="cursor-pointer rounded-md px-2.5 py-1.5 text-xs outline-none hover:bg-[#f0f2f5]"
                >
                  总是允许
                </DropdownMenu.Item>
              )}
              <DropdownMenu.Item
                onSelect={() => {
                  setSubmitting('deny');
                  onResolve('deny');
                }}
                className="cursor-pointer rounded-md px-2.5 py-1.5 text-xs outline-none hover:bg-[#fdf0ef]"
                style={{ color: '#d64545' }}
              >
                拒绝
              </DropdownMenu.Item>
            </DropdownMenu.Content>
          </DropdownMenu.Portal>
        </DropdownMenu.Root>
      </div>

      {/* MiQi 特有：修改计划（引导输入——不结束对话） */}
      {allowModify && (
        <button
          onClick={() => respond('modify')}
          disabled={busyNow}
          className="px-3 py-[6px] rounded-[6px] text-[12px] font-medium cursor-pointer hover:opacity-80 disabled:opacity-50"
          style={{
            background: 'none',
            color: 'var(--text-muted, #6b7280)',
            border: '1px solid var(--border, #e0e3e8)',
            fontFamily: 'inherit',
          }}
        >
          修改计划
        </button>
      )}

      {/* 拒绝（Hermes 原样：独立按钮 + Esc 提示） */}
      <button
        onClick={() => respond('deny')}
        disabled={busyNow}
        title={denyTitle}
        className="h-6 rounded-md px-1.5 text-xs cursor-pointer hover:opacity-80 disabled:opacity-50"
        style={{
          background: 'none',
          border: 'none',
          color: 'var(--text-faint, #a0a6b0)',
          fontFamily: 'inherit',
        }}
      >
        {submitting === 'deny' ? (
          <Loader2 className="inline size-3 animate-spin" />
        ) : (
          <>
            {denyLabel}
            <span className="ml-1 text-[0.625rem] opacity-60">Esc</span>
          </>
        )}
      </button>

      {/* 详情展开（Hermes 的 command 展开——pre 限高滚动） */}
      {hasDetails && (
        <button
          aria-expanded={showDetails}
          onClick={() => setShowDetails((v) => !v)}
          className="h-6 rounded-md px-1.5 text-xs cursor-pointer hover:opacity-80"
          style={{
            background: 'none',
            border: 'none',
            color: 'var(--text-faint, #a0a6b0)',
            fontFamily: 'inherit',
          }}
        >
          {expandLabel}
          <ChevronDown
            className="ml-0.5 inline size-3 transition-transform"
            style={{ transform: showDetails ? 'rotate(180deg)' : 'none' }}
          />
        </button>
      )}

      {showDetails && hasDetails && (
        <pre
          className="mt-1.5 max-h-40 w-full overflow-auto whitespace-pre-wrap break-words rounded-md border px-2.5 py-1.5 font-mono text-xs leading-snug"
          style={{
            borderColor: 'var(--border-subtle, #eceef1)',
            background: 'var(--surface-2, #f7f7f8)',
            color: 'var(--text, #1d2129)',
            fontFamily: 'inherit',
          }}
        >
          {expandableText.trim()}
        </pre>
      )}

      {/* always 二次确认 Dialog（Hermes 原样——持久化前确认） */}
      <Dialog.Root open={confirmAlways} onOpenChange={setConfirmAlways}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-50 bg-black/30" />
          <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-[calc(100%-2rem)] max-w-md -translate-x-1/2 -translate-y-1/2 rounded-xl border bg-white p-4 shadow-xl"
            style={{ borderColor: 'rgba(0,0,0,.08)', fontFamily: 'inherit' }}>
            <Dialog.Title className="text-sm font-semibold" style={{ color: 'var(--text, #1d2129)' }}>
              总是允许？
            </Dialog.Title>
            <Dialog.Description className="mt-1.5 text-xs leading-relaxed" style={{ color: 'var(--text-muted, #6b7280)' }}>
              {description || '将此操作加入永久允许列表，下次不再询问。'}
            </Dialog.Description>
            <div className="mt-4 flex justify-end gap-2">
              <button
                onClick={() => setConfirmAlways(false)}
                className="rounded-md px-3 py-1.5 text-xs cursor-pointer hover:bg-[#f2f2f2]"
                style={{ background: 'none', border: 'none', color: 'var(--text-muted, #6b7280)', fontFamily: 'inherit' }}
              >
                取消
              </button>
              <button
                onClick={() => {
                  setConfirmAlways(false);
                  setSubmitting('always');
                  onResolve('always');
                }}
                className="rounded-md px-3 py-1.5 text-xs font-medium cursor-pointer"
                style={{
                  background: '#d64545',
                  border: 'none',
                  color: '#fff',
                  fontFamily: 'inherit',
                }}
              >
                总是允许
              </button>
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </div>
  );
}
