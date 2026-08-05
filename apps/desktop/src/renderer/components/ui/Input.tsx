import { cn } from '../../lib/utils';
import { type InputHTMLAttributes, forwardRef } from 'react';

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...props }, ref) => {
    return (
      <input
        ref={ref}
        className={cn(
          'flex h-10 w-full rounded-[10px] border border-[var(--border-strong)] bg-[var(--surface)] px-3 py-1 text-body-sm text-[var(--text)] placeholder:text-[var(--placeholder)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)]/20 focus:border-[var(--accent)] transition-colors',
          className
        )}
        {...props}
      />
    );
  }
);
Input.displayName = 'Input';
