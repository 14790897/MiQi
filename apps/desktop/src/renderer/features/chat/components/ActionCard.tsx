import { useState } from 'react';
import { HermesConfirmBar, type HermesConfirmChoice } from './HermesConfirmBar';
import { HermesToolRow, TOOL_PRE_CLASS } from './HermesToolRow';

/**
 * ActionCard — 危险动作确认（Hermes 工具行结构，2026-08-26 用户"抄 Hermes"）。
 * 工具行：标题 + spinner + 行下审批条（Hermes 无独立危险卡——审批是工具行的
 * chrome）。确认/拒绝后审批条消失（工具行接管状态）。
 */
interface ActionCardProps {
  entry: {
    action: string;
    target: string;
    fileName?: string;
    sizeBytes?: number;
    sha256?: string;
    description?: string;
  };
  onResolve: (choiceId: string, rememberMode?: 'session' | 'always' | null) => void;
}

function formatSize(bytes?: number): string {
  if (!bytes || bytes <= 0) return '';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

const ACTION_META: Record<string, { icon: string; title: string }> = {
  upload: { icon: '☁', title: '上传' },
  payment: { icon: '💳', title: '支付' },
  external_send: { icon: '💬', title: '对外发送' },
};

export function ActionCard({ entry, onResolve }: ActionCardProps) {
  const [submitting, setSubmitting] = useState<string | null>(null);
  const highRisk = entry.action === 'payment';
  const meta = ACTION_META[entry.action] ?? { icon: '⚠', title: '执行' };

  const handleResolve = (choice: HermesConfirmChoice, rememberMode?: 'session' | 'always' | null) => {
    if (submitting) return;
    setSubmitting(choice);
    if (choice === 'deny') onResolve('cancel');
    else if (choice === 'session') onResolve('confirm', 'session');
    else if (choice === 'always') onResolve('confirm', 'always');
    else onResolve(choice, rememberMode ?? null);
  };

  // 危险色左条（Hermes 无此概念但保留安全语义——细条不是卡）
  const dangerAccent = highRisk ? '#c0392b' : 'rgba(0,0,0,.12)';

  return (
    <div
      className="w-full min-w-0 max-w-full"
      data-testid="action-card"
      style={{ borderLeft: `2px solid ${dangerAccent}`, paddingLeft: 8 }}
    >
      <HermesToolRow
        title={
          <span style={{ color: highRisk ? '#c0392b' : '#333' }}>
            {meta.icon} {meta.title}：{entry.target}
          </span>
        }
        status="pending"
        meta={
          <span className="break-all">
            {entry.fileName ? `${entry.fileName}${formatSize(entry.sizeBytes) ? ` · ${formatSize(entry.sizeBytes)}` : ''}` : formatSize(entry.sizeBytes) || ''}
            {entry.sha256 ? ` · ${entry.sha256.slice(0, 12)}…` : ''}
          </span>
        }
        approval={
          <div className="pl-5 pt-1">
            <HermesConfirmBar
              tone={highRisk ? 'danger' : 'accent'}
              runLabel={`确认${entry.action === 'upload' ? '上传' : entry.action === 'payment' ? '支付' : '执行'}`}
              onResolve={handleResolve}
              description={entry.description || `${meta.title}：${entry.target}`}
              expandableText={
                entry.sha256
                  ? `目标：${entry.target}\n文件：${entry.fileName ?? ''}${formatSize(entry.sizeBytes) ? ` · ${formatSize(entry.sizeBytes)}` : ''}\n指纹：${entry.sha256}`
                  : undefined
              }
              expandLabel="详情"
            />
          </div>
        }
      >
        {entry.sha256 && (
          <pre className={TOOL_PRE_CLASS}>
            指纹：{entry.sha256}
          </pre>
        )}
      </HermesToolRow>
    </div>
  );
}
