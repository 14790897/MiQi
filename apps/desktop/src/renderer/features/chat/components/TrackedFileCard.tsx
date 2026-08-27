import { useState } from 'react';
import { BookOpen, X, Pencil, FileText, Eye, GitCompare, Star, FolderOpen, Copy, Check, AlertTriangle } from 'lucide-react';
import type { FileCheckStatus } from '../../../../shared/ipc';

export interface TrackedFile {
  path: string;
  name: string;
  op: 'read' | 'write' | 'edit' | 'delete';
  lastSeen: number;
  truncated?: boolean;
}

export const OFFICE_FILE_RE_LEGACY = /\\.(docx|xlsx|pptx|ppt)$/i;

/** #790: 资产路径不可达的错误态文案（错误类型 / 原因 / 建议）。 */
function assetErrorInfo(
  file: TrackedFile,
  status?: FileCheckStatus
): { label: string; hint: string; color: string } | null {
  if (!status || status === 'ok') return null;
  switch (status) {
    case 'truncated':
      return { label: '路径截断', hint: '路径在进度消息中被截断，无法定位或打开', color: 'var(--warning)' };
    case 'outside':
      return { label: '路径越界', hint: '路径不在工作区内，请检查沙箱/路径映射', color: 'var(--warning)' };
    case 'permission':
      return { label: '权限不足', hint: '文件存在但无读取权限，请检查文件权限', color: 'var(--warning)' };
    case 'not_found': {
      // 近期写入的 write/edit 文件不可达 → 大概率是沙箱镜像未回写完成（#474）
      const recentWrite =
        (file.op === 'write' || file.op === 'edit') && Date.now() - file.lastSeen < 120_000;
      return recentWrite
        ? { label: '文件不存在', hint: '刚写入的文件可能仍在沙箱镜像中，等待同步…', color: 'var(--danger)' }
        : { label: '文件不存在', hint: '文件可能已被删除，可重新生成产物', color: 'var(--danger)' };
    }
  }
}

export function TrackedFileCard({
  file,
  isResult,
  status,
  onPreview,
  onDiff,
  onReveal,
  onCopyPath,
}: {
  file: TrackedFile;
  /** issue #607: result assets get accent border/background + Star + 结果 badge. */
  isResult?: boolean;
  /** #790: 可达性校验结果（未校验时为 undefined → 按可达处理）。 */
  status?: FileCheckStatus;
  onPreview: () => void;
  onDiff?: () => void;
  /** issue #607: 定位 → reveal the file in the OS file manager (results only). */
  onReveal?: () => void;
  /** #790: 复制原始路径（经主进程 clipboard，file:// 下 navigator.clipboard 不可用）。 */
  onCopyPath?: (path: string) => void;
}) {
  const opColor: Record<TrackedFile['op'], string> = {
    read: 'var(--info)',
    edit: 'var(--warning)',
    write: 'var(--accent)',
    delete: 'var(--danger)',
  };
  const OpIcon = file.op === 'read' ? BookOpen : file.op === 'delete' ? X : Pencil;
  const OP_LABELS: Record<TrackedFile['op'], string> = {
    read: '读取',
    write: '写入',
    edit: '编辑',
    delete: '删除',
  };
  const displayPath = file.path.replace(/\\\\/g, '/');
  const isOfficeFile = OFFICE_FILE_RE_LEGACY.test(file.path);

  const [copied, setCopied] = useState(false);
  const assetError = assetErrorInfo(file, status) ?? (file.truncated
    ? { label: '路径截断', hint: '路径在进度消息中被截断', color: 'var(--warning)' }
    : null);
  const unavailable = !!assetError;

  const copyPath = () => {
    if (!onCopyPath) return;
    onCopyPath(file.path);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <div
      className="rounded-lg p-2.5"
      style={{
        border: isResult
          ? '1px solid color-mix(in srgb, var(--accent) 55%, transparent)'
          : '1px solid var(--border-subtle)',
        background: isResult
          ? 'color-mix(in srgb, var(--accent) 5%, var(--surface))'
          : 'var(--surface)',
      }}
    >
      <div className="flex items-start gap-2 mb-1">
        <FileText size={14} className="shrink-0 mt-0.5" style={{ color: opColor[file.op] }} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5 flex-wrap mb-0.5">
            {isResult && (
              <Star
                size={12}
                fill="currentColor"
                className="shrink-0"
                style={{ color: 'var(--accent)' }}
              />
            )}
            <span className="text-size-2xs font-medium truncate" style={{ color: 'var(--text)' }} title={displayPath}>
              {file.name.length > 30 ? file.name.slice(0, 28) + '…' : file.name}
            </span>
            <span
              className="text-size-2xs px-1.5 py-0.5 rounded font-semibold shrink-0"
              data-testid={`file-op-${file.op}`}
              style={{ background: `color-mix(in srgb, ${opColor[file.op]} 15%, transparent)`, color: opColor[file.op] }}
            >
              {OP_LABELS[file.op]}
            </span>
            {isResult && (
              <span
                className="text-size-2xs px-1.5 py-0.5 rounded font-semibold shrink-0"
                data-testid="file-result-badge"
                style={{ background: 'color-mix(in srgb, var(--accent) 15%, transparent)', color: 'var(--accent)' }}
              >
                结果
              </span>
            )}
            {isOfficeFile && (
              <span
                className="text-size-2xs px-1.5 py-0.5 rounded font-semibold shrink-0"
                data-testid="file-office-badge"
                style={{ background: 'var(--surface-muted)', color: 'var(--text-faint)' }}
              >
                文档
              </span>
            )}
          </div>
        </div>
      </div>
      {assetError ? (
        /* #790: 路径不可达错误态 —— 类型 / 原因与建议 / 原始路径（可复制） */
        <div
          className="w-full rounded-md px-2 py-1.5 flex flex-col gap-1"
          data-testid="file-error-block"
          style={{
            border: `1px solid color-mix(in srgb, ${assetError.color} 45%, transparent)`,
            background: `color-mix(in srgb, ${assetError.color} 8%, var(--surface))`,
          }}
        >
          <div className="flex items-center gap-1.5 min-w-0">
            <AlertTriangle size={11} className="shrink-0" style={{ color: assetError.color }} />
            <span className="text-size-2xs font-semibold shrink-0" data-testid="file-error-label" style={{ color: assetError.color }}>
              {assetError.label}
            </span>
            <span className="text-size-2xs truncate" style={{ color: 'var(--text-faint)' }}>
              {assetError.hint}
            </span>
            <button
              type="button"
              onClick={copyPath}
              disabled={!onCopyPath}
              title="复制原始路径"
              data-testid="file-copy-path-btn"
              className="ml-auto shrink-0 p-0.5 rounded transition-colors"
              style={{ color: copied ? 'var(--accent)' : 'var(--text-faint)' }}
            >
              {copied ? <Check size={11} /> : <Copy size={11} />}
            </button>
          </div>
          <div
            className="truncate font-mono text-[10px]"
            title={file.path}
            data-testid="file-error-path"
            style={{ color: 'var(--text-muted)' }}
          >
            {file.path}
          </div>
        </div>
      ) : (
        <div className="flex gap-1.5">
          {onReveal && isResult && (
            <button
              onClick={onReveal}
              disabled={unavailable}
              className="flex-1 flex items-center justify-center gap-1 py-1 rounded-md text-size-2xs transition-colors disabled:opacity-40"
              style={{ border: '1px solid var(--border)', color: 'var(--text-muted)' }}
              title="在文件管理器中定位"
              data-testid="file-reveal-btn"
            >
              <FolderOpen size={10} />定位
            </button>
          )}
          {onDiff && (file.op === 'write' || file.op === 'edit') && (
            <button
              onClick={onDiff}
              disabled={unavailable || isOfficeFile}
              className="flex-1 flex items-center justify-center gap-1 py-1 rounded-md text-size-2xs transition-colors disabled:opacity-40"
              style={{ border: '1px solid var(--border)', color: isOfficeFile ? 'var(--text-faint)' : 'var(--warning)', opacity: isOfficeFile ? 0.55 : 1 }}
              title="二进制 Office 文件不支持差异对比"
            >
              <GitCompare size={10} />差异
            </button>
          )}
          <button
            onClick={onPreview}
            disabled={unavailable}
            className="flex-1 flex items-center justify-center gap-1 py-1 rounded-md text-size-2xs transition-colors disabled:opacity-40"
            style={{ border: '1px solid var(--border)', color: 'var(--text-muted)' }}
            title="预览文件"
            data-testid="file-preview-btn"
          >
            <Eye size={10} />预览
          </button>
        </div>
      )}
    </div>
  );
}
