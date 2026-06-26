import { cn } from '../../lib/utils'
import { type TextareaHTMLAttributes, forwardRef } from 'react'

export interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  allowResize?: boolean
}

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ className, allowResize = false, style, ...props }, ref) => {
    return (
      <textarea
        ref={ref}
        className={cn(
          'flex w-full rounded-lg border border-[var(--border)] bg-[var(--surface)] px-3 py-2 text-sm text-[var(--text)] placeholder:text-[var(--text-faint)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)]/30 focus:border-[var(--accent)] transition-colors',
          !allowResize && 'resize-none',
          className,
        )}
        style={{
          overflow: allowResize ? 'auto' : 'hidden',
          ...style,
        }}
        {...props}
      />
    )
  },
)
Textarea.displayName = 'Textarea'
