export interface ActionCardEntry {
  action: 'upload' | 'payment' | 'delete' | 'external' | string;
  target: string;
  fileName?: string;
  sizeBytes?: number;
  sha256?: string;
  description?: string;
}

const ACTION_META: Record<string, { icon: string; title: string; verb: string }> = {
  upload: { icon: '☁', title: '即将上传数据', verb: '上传' },
  payment: { icon: '💳', title: '即将产生费用', verb: '支付' },
  delete: { icon: '🗑', title: '即将删除数据', verb: '删除' },
  external: { icon: '📤', title: '即将外发数据', verb: '外发' },
};

function formatSize(bytes?: number): string {
  if (!bytes || bytes <= 0) return '';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

export function ActionCard({
  entry,
  onResolve,
}: {
  entry: ActionCardEntry;
  onResolve: (choiceId: string) => void;
}) {
  const meta = ACTION_META[entry.action] ?? { icon: '⚠️', title: '危险操作确认', verb: '执行' };
  const danger = 'var(--danger, #e5484d)';
  const accent = 'var(--accent, #2a7de1)';
  const highRisk = entry.action === 'delete' || entry.action === 'payment';
  const statusColor = highRisk ? danger : accent;

  return (
    <div
      className="rounded-[18px] my-2 max-w-[520px] overflow-hidden"
      data-testid="action-card"
      style={{
        background: '#ffffff',
        border: '1px solid #eceef1',
        boxShadow: '0 8px 28px rgba(30, 41, 59, .06), 0 2px 8px rgba(30, 41, 59, .03)',
      }}
    >
      {/* 头部：图标 + 标题 + 状态小圆点 */}
      <div className="px-5 pt-4 pb-3">
        <div className="flex items-start gap-3">
          <span
            className="mt-0.5 w-8 h-8 rounded-[10px] flex items-center justify-center text-[14px] shrink-0"
            style={{
              background: highRisk
                ? 'color-mix(in srgb, var(--danger, #e5484d) 10%, transparent)'
                : 'color-mix(in srgb, var(--accent, #2a7de1) 10%, transparent)',
              color: statusColor,
            }}
          >
            {meta.icon}
          </span>

          <div className="min-w-0 flex-1">
            <div className="text-[14px] font-semibold leading-snug" style={{ color: '#1d2129' }}>
              {meta.title}
            </div>

            {entry.description && (
              <div className="mt-1 text-[12px] leading-relaxed" style={{ color: '#6b7280' }}>
                {entry.description}
              </div>
            )}

            <div className="mt-2 inline-flex items-center gap-1.5">
              <span
                className="w-1.5 h-1.5 rounded-full"
                style={{ background: statusColor }}
              />
              <span className="text-[11px]" style={{ color: '#9aa0a8' }}>
                {highRisk ? '高风险操作' : '待确认'}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* 详情 */}
      <div className="px-5 pb-4">
        <div
          className="rounded-[12px] px-4 py-3 flex flex-col gap-2"
          style={{ background: '#f8f9fa' }}
        >
          <div className="flex items-start justify-between gap-4">
            <span className="text-[12px] shrink-0 pt-0.5" style={{ color: '#9aa0a8' }}>
              目标
            </span>
            <span
              className="text-[13px] text-right break-all leading-snug"
              style={{ color: '#1d2129' }}
            >
              {entry.target}
            </span>
          </div>

          {entry.fileName && (
            <div className="flex items-start justify-between gap-4">
              <span className="text-[12px] shrink-0 pt-0.5" style={{ color: '#9aa0a8' }}>
                文件
              </span>
              <span
                className="text-[13px] text-right truncate max-w-[260px] leading-snug"
                style={{ color: '#1d2129' }}
              >
                {entry.fileName}
                {entry.sizeBytes && entry.sizeBytes > 0 && ` · ${formatSize(entry.sizeBytes)}`}
              </span>
            </div>
          )}

          {entry.sha256 && (
            <div className="flex items-start justify-between gap-4">
              <span className="text-[12px] shrink-0 pt-0.5" style={{ color: '#9aa0a8' }}>
                指纹
              </span>
              <span
                className="