/**
 * ActionCard — 危险动作最后确认（#646-v2，GPT 第五轮拍板）。
 *
 * 与 PlanCard 完全分离（GPT：不要复用一个 UI）：
 * - PlanCard：任务开始前「你准备干什么」
 * - ActionCard：危险动作执行前「你现在要做危险动作」（上传/支付/删除/外发）
 *
 * 展示：动作类型 + 目标 + 文件 + 大小 + sha256 指纹（防确认 A 上传 B）。
 */
export interface ActionCardEntry {
  action: 'upload' | 'payment' | 'delete' | 'external' | string;
  target: string;
  fileName?: string;
  sizeBytes?: number;
  sha256?: string;
  description?: string;
}

const ACTION_META: Record<string, { icon: string; title: string }> = {
  upload: { icon: '☁', title: '即将上传数据' },
  payment: { icon: '💳', title: '即将产生费用' },
  delete: { icon: '🗑', title: '即将删除数据' },
  external: { icon: '📤', title: '即将外发数据' },
};

function formatSize(bytes?: number): string {
  if (!bytes || bytes <= 0) return '';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

export function ActionCard({
  entry,
  onResolve,
}: {
  entry: ActionCardEntry;
  onResolve: (choiceId: string) => void;
}) {
  const meta = ACTION_META[entry.action] ?? { icon: '⚠️', title: '危险操作确认' };
  const danger = 'var(--danger, #e5484d)';
  // Kimi 评审（2026-08-18）：去掉全卡红边框（错误告警感）——中性边框 +
  // 左侧 4px 危险色条区分场景；危险色仅保留在按钮
  const highRisk = entry.action === 'delete' || entry.action === 'payment';

  return (
    <div
      className="rounded-[16px] my-2 w-full max-w-full overflow-hidden"
      data-testid="action-card"
      style={{
        background: '#ffffff',
        border: '1px solid rgba(0,0,0,.06)',
        boxShadow: '0 1px 4px rgba(0,0,0,.04), 0 4px 16px rgba(0,0,0,.04)',
        borderLeft: highRisk ? `4px solid ${danger}` : '4px solid var(--accent, #2a7de1)',
      }}
    >
      {/* 标题行 */}
      <div className="flex items-center gap-2.5 px-4 pt-3.5 pb-2.5">
        <span
          className="w-7 h-7 rounded-[8px] flex items-center justify-center text-[13px] shrink-0"
          style={{ background: 'color-mix(in srgb, var(--danger, #e5484d) 10%, transparent)', color: danger }}
        >
          {meta.icon}
        </span>
        <div className="min-w-0 flex-1">
          <div className="text-[13px] font-semibold leading-snug" style={{ color: 'var(--text, #1d2129)' }}>
            {meta.title}
          </div>
          {entry.description && (
            <div className="text-[11.5px] mt-1" style={{ color: danger }}>
              {entry.description}
            </div>
          )}
        </div>
      </div>

      {/* 详情 */}
      <div className="px-4 pb-2.5">
        <div className="flex flex-col gap-1 rounded-[10px] px-3 py-2.5" style={{ background: 'var(--surface-3, #f6f7f8)' }}>
          <div className="flex justify-between text-[12px]">
            <span style={{ color: 'var(--text-faint, #9aa0a8)' }}>目标</span>
            <span style={{ color: 'var(--text, #1d2129)' }}>{entry.target}</span>
          </div>
          {entry.fileName && (
            <div className="flex justify-between text-[12px]">
              <span style={{ color: 'var(--text-faint, #9aa0a8)' }}>文件</span>
              <span className="truncate max-w-[240px]" style={{ color: 'var(--text, #1d2129)' }}>
                {entry.fileName}
                {formatSize(entry.sizeBytes) ? ` · ${formatSize(entry.sizeBytes)}` : ''}
              </span>
            </div>
          )}
          {entry.sha256 && (
            <div className="flex justify-between text-[12px]">
              <span style={{ color: 'var(--text-faint, #9aa0a8)' }}>指纹</span>
              <span className="font-mono text-[10.5px]" style={{ color: 'var(--text-muted, #6b7280)' }}>
                {entry.sha256.slice(0, 12)}…
              </span>
            </div>
          )}
        </div>
      </div>

      {/* 操作 */}
      <div
        className="flex items-center justify-end gap-2 px-4 py-2.5"
        style={{ borderTop: '1px solid var(--border-subtle, #eceef1)' }}
      >
        <button
          onClick={() => onResolve('cancel')}
          className="px-3.5 py-[6px] rounded-full text-[12px] font-medium cursor-pointer hover:bg-[#f2f2f2] transition-colors"
          style={{ background: 'none', color: '#8a8a8a', border: 'none' }}
        >
          跳过
        </button>
        <button
          onClick={() => onResolve('confirm')}
          className="px-4 py-[6px] rounded-[8px] text-[12px] font-semibold cursor-pointer hover:opacity-90"
          style={{ background: '#1f1f1f', color: '#fff', border: 'none' }}
        >
          确认{entry.action === 'upload' ? '上传' : entry.action === 'payment' ? '支付' : '执行'}
        </button>
      </div>
    </div>
  );
}