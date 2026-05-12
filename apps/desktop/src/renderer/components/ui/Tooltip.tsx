import * as TooltipPrimitive from '@radix-ui/react-tooltip'
import { cn } from '../../lib/utils'
import { type ComponentPropsWithoutRef, forwardRef } from 'react'

export const TooltipProvider = TooltipPrimitive.Provider

export const Tooltip = ({ children, content, side = 'top' }: {
  children: React.ReactNode
  content: string
  side?: 'top' | 'bottom' | 'left' | 'right'
}) => (
  <TooltipPrimitive.Root delayDuration={300}>
    <TooltipPrimitive.Trigger asChild>{children}</TooltipPrimitive.Trigger>
    <TooltipPrimitive.Portal>
      <TooltipPrimitive.Content
        side={side}
        sideOffset={4}
        className="z-50 rounded-md bg-[var(--text)] px-3 py-1.5 text-xs text-[var(--surface)] shadow-md animate-in fade-in-0 zoom-in-95"
      >
        {content}
        <TooltipPrimitive.Arrow className="fill-[var(--text)]" />
      </TooltipPrimitive.Content>
    </TooltipPrimitive.Portal>
  </TooltipPrimitive.Root>
)
