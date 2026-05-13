import { cn } from '../lib/utils'
import {
  MessageSquare,
  FolderOpen,
  Cpu,
  Radio,
  ShieldAlert,
  Clock,
  BookOpen,
  Wrench,
  Settings,
  type LucideIcon,
} from 'lucide-react'

interface NavItem {
  id: string
  label: string
  icon: LucideIcon
}

const NAV_ITEMS: NavItem[] = [
  { id: 'chat', label: '对话', icon: MessageSquare },
  { id: 'sessions', label: '会话', icon: FolderOpen },
  { id: 'providers', label: 'Provider', icon: Cpu },
  { id: 'channels', label: '渠道', icon: Radio },
  { id: 'approvals', label: '命令审批', icon: ShieldAlert },
  { id: 'cron', label: '定时任务', icon: Clock },
  { id: 'memory', label: '记忆', icon: BookOpen },
  { id: 'skills', label: '技能', icon: Wrench },
  { id: 'workspace', label: '工作区', icon: FolderOpen },
  { id: 'settings', label: '设置', icon: Settings },
]

interface SidebarProps {
  activeNav: string
  onNavChange: (id: string) => void
}

export function Sidebar({ activeNav, onNavChange }: SidebarProps) {
  return (
    <div className="flex flex-col w-[220px] shrink-0 border-r border-[var(--border-subtle)] bg-[var(--surface)]">
      {/* App title */}
      <div className="flex items-center gap-2 h-12 px-4 border-b border-[var(--border-subtle)]">
        <div className="w-6 h-6 rounded-md bg-[var(--accent)] flex items-center justify-center text-white text-xs font-bold">
          M
        </div>
        <span className="text-sm font-semibold text-[var(--text)]">MiQi</span>
      </div>

      {/* Navigation */}
      <nav className="flex-1 p-2 flex flex-col gap-0.5">
        {NAV_ITEMS.map((item) => {
          const isActive = activeNav === item.id
          const Icon = item.icon
          return (
            <button
              key={item.id}
              onClick={() => onNavChange(item.id)}
              className={cn(
                'flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-colors text-left w-full',
                isActive
                  ? 'bg-[var(--accent-soft)] text-[var(--accent)] font-medium'
                  : 'text-[var(--text-muted)] hover:bg-[var(--surface-muted)] hover:text-[var(--text)]',
              )}
            >
              <Icon size={18} />
              {item.label}
            </button>
          )
        })}
      </nav>
    </div>
  )
}
