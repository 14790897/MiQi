export function DiffView({ diff }: { diff: string }) {
  const lines = diff.split('\n');
  const isNewFile = lines.some((l) => l.startsWith('--- /dev/null'));
  return (
    <div className="overflow-x-auto text-xs font-mono leading-5" style={{ background: 'var(--surface)' }}>
      {lines.map((line, i) => {
        let bg = 'transparent';
        let color = 'var(--text-muted)';
        if (line.startsWith('+++ b/')) { bg = 'rgba(34,197,94,0.08)'; color = '#4ade80'; }
        else if (line.startsWith('--- /dev/null')) { color = 'var(--text-faint)'; }
        else if (line.startsWith('---')) { color = 'var(--text-faint)'; }
        else if (line.startsWith('@@')) { bg = isNewFile ? 'rgba(34,197,94,0.08)' : 'rgba(96,165,250,0.08)'; color = isNewFile ? '#4ade80' : 'var(--info)'; }
        else if (line.startsWith('+')) { bg = 'rgba(34,197,94,0.10)'; color = '#4ade80'; }
        else if (line.startsWith('-')) { bg = 'rgba(239,68,68,0.10)'; color = '#f87171'; }
        return (
          <div key={i} style={{ background: bg, color, paddingLeft: 12, paddingRight: 12, whiteSpace: 'pre', minWidth: '100%', display: 'block' }}>
            {line || '\u00a0'}
          </div>
        );
      })}
    </div>
  );
}
