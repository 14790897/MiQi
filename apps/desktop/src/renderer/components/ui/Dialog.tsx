import * as DialogPrimitive from '@radix-ui/react-dialog';
import { cn } from '../../lib/utils';
import { type ComponentPropsWithoutRef, forwardRef } from 'react';
import { X } from 'lucide-react';

export const Dialog = DialogPrimitive.Root;
export const DialogTrigger = DialogPrimitive.Trigger;

export const DialogContent = forwardRef<
  HTMLDivElement,
  ComponentPropsWithoutRef<typeof DialogPrimitive.Content> & {
    hideClose?: boolean;
  }
>(({ className, children, hideClose, ...props }, ref) => (
  <DialogPrimitive.Portal>
    <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-black/40 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0" />
    <DialogPrimitive.Content
      ref={ref}
      className={cn(
        'fixed left-1/2 top-1/2 z-50 -translate-x-1/2 -translate-y-1/2 rounded-xl border border-[var(--border)] bg-[var(--surface-elevated)] shadow-lg p-6 w-full max-w-md',
        className
      )}
      {...props}
    >
      {children}
      {!hideClose && (
        <DialogPrimitive.Close className="absolute right-4 top-4 rounded-sm text-[var(--text-faint)] hover:text-[var(--text)] transition-colors">
          <X size={16} />
        </DialogPrimitive.Close>
      )}
    </DialogPrimitive.Content>
  </DialogPrimitive.Portal>
));
DialogContent.displayName = 'DialogContent';

export const DialogHeader = ({ className, ...props }: ComponentPropsWithoutRef<'div'>) => (
  <div className={cn('mb-4', className)} {...props} />
);

export const DialogTitle = ({ className, ...props }: ComponentPropsWithoutRef<'h2'>) => (
  <DialogPrimitive.Title
    className={cn('text-lg font-semibold text-[var(--text)]', className)}
    {...props}
  />
);

export const DialogDescription = ({ className, ...props }: ComponentPropsWithoutRef<'p'>) => (
  <DialogPrimitive.Description
    className={cn('text-sm text-[var(--text-muted)]', className)}
    {...props}
  />
);
