import { useState } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../ui/Dialog';

interface InputDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  label: string;
  defaultValue?: string;
  onConfirm: (value: string) => void;
}

/** Title + text input + Confirm/Cancel — powered by Radix Dialog. */
export function InputDialog({
  open,
  onOpenChange,
  title,
  label,
  defaultValue = '',
  onConfirm,
}: InputDialogProps) {
  const [value, setValue] = useState(defaultValue);

  const handleConfirm = () => {
    const trimmed = value.trim();
    if (trimmed) {
      onConfirm(trimmed);
      onOpenChange(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="w-[380px]" hideClose>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
        </DialogHeader>
        <input
          type="text"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') handleConfirm();
            if (e.key === 'Escape') onOpenChange(false);
          }}
          placeholder={label}
          className="w-full px-3 py-2 text-sm rounded-lg border border-[var(--border)] bg-[var(--background)] text-[var(--text)] placeholder:text-[var(--text-faint)] focus:outline-none focus:border-[var(--border-strong)]"
          autoFocus
        />
        <div className="flex items-center justify-end gap-2 mt-4">
          <button
            onClick={() => onOpenChange(false)}
            className="px-3 py-1.5 text-sm text-[var(--text-muted)] hover:text-[var(--text)] transition-colors"
          >
            取消
          </button>
          <button
            onClick={handleConfirm}
            disabled={!value.trim()}
            className="px-4 py-1.5 rounded-lg bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-white text-sm font-medium transition-all disabled:opacity-50"
          >
            确定
          </button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
