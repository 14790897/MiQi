import { BookOpen, X, Pencil, FileText, Eye, GitCompare } from 'lucide-react';

export interface TrackedFile {
  path: string;
  name: string;
  op: 'read' | 'write' | 'edit' | 'delete';
  lastSeen: number;
  truncated?: boolean;
}

export const OFFICE_FILE_RE_LEGACY = /\.(docx|xlsx|pptx|ppt)$/i;

export function TrackedFileCard({
  file,
  onPreview,
  onDiff,
}: {
  file: TrackedFile;
  onPreview: () => void;
  onDiff?: () => void;
}) {
  const opColor: Record<TrackedFile['op'], string> = {
    read: 'var(--info)',
    edit: 'var(--warning)',
    write: 'var(--accent)',
    delete: 'var(--danger)',
  };
  const OpIcon = file.op === 'read' ? BookOpen : file.op === 'delete' ? X : Pencil;
  const displayPath = file.path.replace(/\\/g, '/');
  const isOfficeFile = OFFICE_FILE_RE_LEGACY.test(file.path);

  return (
    <div className="rounded-lg p-2.5" style={{ border: '1px solid var(--border-subtle)', background: 'var(--surface)' }}>
      <div className="flex items-start gap-2 mb-1">
        <FileText size={14} className="shrink-0 mt-0.5" style={{ color: opColor[file.op] }} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5 flex-wrap mb-0.5">
            <span className="text-[12px] font-medium truncate" style={{ color: 'var(--text)' }} title={displayPath}>
              {file.name.length > 30 ? file.name.slice(0, 28) + '…' : file.name}
            </span>
            <span className="text-[9px] px-1.5 py-0.5 rounded font-semibold shrink-0"
                  style={{ background: `color-mix(in srgb, ${opColor[file.op]} 15%, transparent)`, color: opColor[file.op] }}>
              {file.op.toUpperCase()}
            </span>
            {isOfficeFile && (
              <span className="text-[9px] px-1.5 py-0.5 rounded font-semibold shrink-0"
                    style={{ background: 'var(--surface-muted)', color: 'var(--text-faint)' }}>
                OFFICE
              </span>
            )}
          </div>
        </div>
      </div>
      {file.truncated ? (
        <div className="w-full flex items-center justify-center gap-1 py-1 rounded-md text-[11px]"
             style={{ border: '1px solid var(--border-subtle)', color: 'var(--text-faint)', background: 'var(--surface-muted)' }}
             title="Path was truncated in progress message">
          <span className="text-[10px]">Path incomplete</span>
        </div>
      ) : (
        <div className="flex gap-1.5">
          {onDiff && (file.op === 'write' || file.op === 'edit') && (
            <button onClick={onDiff} disabled={isOfficeFile}
                    className="flex-1 flex items-center justify-center gap-1 py-1 rounded-md text-[11px] transition-colors"
                    style={{ border: '1px solid var(--border)', color: isOfficeFile ? 'var(--text-faint)' : 'var(--warning)', opacity: isOfficeFile ? 0.55 : 1 }}
                    title="Diff is not available for Office binary files">
              <GitCompare size={10} />Diff
            </button>
          )}
          <button onClick={onPreview} className="flex-1 flex items-center justify-center gap-1 py-1 rounded-md text-[11px] transition-colors"
                  style={{ border: '1px solid var(--border)', color: 'var(--text-muted)' }}
                  title="预览文件" data-testid="file-preview-btn">
            <Eye size={10} />Preview
          </button>
        </div>
      )}
    </div>
  );
}
