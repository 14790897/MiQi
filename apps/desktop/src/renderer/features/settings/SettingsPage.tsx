import { useState, useEffect, useRef } from 'react'
import { Button } from '../../components/ui/Button'
import { ScrollArea } from '../../components/ui/ScrollArea'
import { cn } from '../../lib/utils'
import { RefreshCw, Download } from 'lucide-react'
import { useRuntime } from '../../contexts/RuntimeContext'

export function SettingsPage() {
  const { logs, refreshLogs } = useRuntime()
  const [autoScroll, setAutoScroll] = useState(true)
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (autoScroll && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [logs, autoScroll])

  const handleExport = () => {
    const text = logs.join('\n')
    const blob = new Blob([text], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `miqi-logs-${new Date().toISOString().slice(0, 10)}.txt`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between px-6 py-4 border-b border-[var(--border-subtle)]">
        <div>
          <h2 className="text-sm font-semibold text-[var(--text)]">Runtime Logs</h2>
          <p className="text-xs text-[var(--text-faint)] mt-0.5">
            Bridge process output and diagnostics
          </p>
        </div>
        <div className="flex items-center gap-2">
          <label className="flex items-center gap-1.5 text-xs text-[var(--text-muted)] cursor-pointer">
            <input
              type="checkbox"
              checked={autoScroll}
              onChange={(e) => setAutoScroll(e.target.checked)}
              className="rounded"
            />
            Auto-scroll
          </label>
          <Button variant="ghost" size="icon" onClick={refreshLogs}>
            <RefreshCw size={14} />
          </Button>
          <Button variant="outline" size="sm" onClick={handleExport}>
            <Download size={14} /> Export
          </Button>
        </div>
      </div>

      <ScrollArea className="flex-1">
        <div
          ref={scrollRef}
          className="p-4 font-mono text-xs leading-relaxed text-[var(--text)] overflow-y-auto h-full"
        >
          {logs.length === 0 ? (
            <div className="flex items-center justify-center h-full text-[var(--text-muted)] py-16">
              No logs yet. Start the runtime to see output.
            </div>
          ) : (
            logs.map((line, i) => (
              <div
                key={i}
                className={cn(
                  'py-0.5',
                  line.includes('[ERROR]') || line.includes('ERROR')
                    ? 'text-[var(--danger)]'
                    : line.includes('[WARNING]') || line.includes('WARNING')
                      ? 'text-[var(--warning)]'
                      : 'text-[var(--text-muted)]',
                )}
              >
                {line}
              </div>
            ))
          )}
        </div>
      </ScrollArea>
    </div>
  )
}