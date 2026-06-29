import React, { useState, useEffect } from 'react'
import { Shield, Plus, Trash2, Save, Loader2 } from 'lucide-react'
import { cn } from '../../lib/utils'

interface PathRule {
  path: string
  mode: 'read' | 'write' | 'none'
  recursive: boolean
}

interface PermissionsConfig {
  filesystem: {
    rules: PathRule[]
    default_mode: 'read' | 'write' | 'none'
  }
  network: 'allow_all' | 'block_all' | 'allow_list'
  exec_approval: 'never' | 'dangerous' | 'always'
}

const DEFAULT_CONFIG: PermissionsConfig = {
  filesystem: { rules: [], default_mode: 'read' },
  network: 'allow_all',
  exec_approval: 'dangerous',
}

export function PermissionsPage() {
  const [config, setConfig] = useState<PermissionsConfig>(DEFAULT_CONFIG)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    (async () => {
      try {
        const result = await window.miqi.permissions.get()
        if (result) setConfig({ ...DEFAULT_CONFIG, ...(result as unknown as PermissionsConfig) })
      } catch { /* use defaults */ }
      setLoading(false)
    })()
  }, [])

  const addRule = () => {
    setConfig((prev) => ({
      ...prev,
      filesystem: {
        ...prev.filesystem,
        rules: [...prev.filesystem.rules, { path: '', mode: 'read' as const, recursive: true }],
      },
    }))
  }

  const updateRule = (index: number, field: keyof PathRule, value: string | boolean) => {
    setConfig((prev) => {
      const rules = [...prev.filesystem.rules]
      rules[index] = { ...rules[index], [field]: value }
      return { ...prev, filesystem: { ...prev.filesystem, rules } }
    })
  }

  const removeRule = (index: number) => {
    setConfig((prev) => ({
      ...prev,
      filesystem: {
        ...prev.filesystem,
        rules: prev.filesystem.rules.filter((_, i) => i !== index),
      },
    }))
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      await window.miqi.permissions.update(config as unknown as Record<string, unknown>)
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch (e) {
      console.error('Failed to save permissions:', e)
    }
    setSaving(false)
  }

  if (loading) return <div className="p-4 flex items-center gap-2"><Loader2 className="animate-spin" size={16} /> Loading...</div>

  return (
    <div className="p-4 max-w-2xl">
      <h2 className="text-lg font-bold mb-4 flex items-center gap-2">
        <Shield size={20} /> Permissions
      </h2>

      {/* Filesystem Rules */}
      <section className="mb-6">
        <h3 className="text-sm font-semibold mb-2">Filesystem Rules</h3>
        <div className="space-y-2 mb-2">
          {config.filesystem.rules.map((rule, i) => (
            <div key={i} className="flex items-center gap-2">
              <input
                type="text"
                value={rule.path}
                onChange={(e) => updateRule(i, 'path', e.target.value)}
                placeholder="/path/to/directory"
                className="flex-1 px-2 py-1 text-sm border rounded bg-[var(--surface)]"
              />
              <select
                value={rule.mode}
                onChange={(e) => updateRule(i, 'mode', e.target.value)}
                className="px-2 py-1 text-sm border rounded bg-[var(--surface)]"
              >
                <option value="read">Read</option>
                <option value="write">Write</option>
                <option value="none">None</option>
              </select>
              <label className="flex items-center gap-1 text-xs text-[var(--text-muted)]">
                <input
                  type="checkbox"
                  checked={rule.recursive}
                  onChange={(e) => updateRule(i, 'recursive', e.target.checked)}
                />
                Recursive
              </label>
              <button onClick={() => removeRule(i)} className="text-red-400 hover:text-red-600">
                <Trash2 size={14} />
              </button>
            </div>
          ))}
        </div>
        <button onClick={addRule} className="flex items-center gap-1 text-xs text-[var(--accent)] hover:underline">
          <Plus size={12} /> Add Rule
        </button>
      </section>

      {/* Network Policy */}
      <section className="mb-6">
        <h3 className="text-sm font-semibold mb-2">Network Policy</h3>
        <select
          value={config.network}
          onChange={(e) => setConfig((prev) => ({ ...prev, network: e.target.value as PermissionsConfig['network'] }))}
          className="px-2 py-1 text-sm border rounded bg-[var(--surface)]"
        >
          <option value="allow_all">Allow All</option>
          <option value="block_all">Block All</option>
          <option value="allow_list">Allow List</option>
        </select>
      </section>

      {/* Exec Approval */}
      <section className="mb-6">
        <h3 className="text-sm font-semibold mb-2">Shell Command Approval</h3>
        <select
          value={config.exec_approval}
          onChange={(e) => setConfig((prev) => ({ ...prev, exec_approval: e.target.value as PermissionsConfig['exec_approval'] }))}
          className="px-2 py-1 text-sm border rounded bg-[var(--surface)]"
        >
          <option value="never">Never (no approval)</option>
          <option value="dangerous">Dangerous only (default)</option>
          <option value="always">Always require approval</option>
        </select>
      </section>

      {/* Save */}
      <button
        onClick={handleSave}
        disabled={saving}
        className={cn(
          'flex items-center gap-2 px-4 py-2 rounded text-white text-sm transition-colors',
          saved ? 'bg-green-500' : 'bg-[var(--accent)] hover:opacity-90',
        )}
      >
        {saving ? <Loader2 className="animate-spin" size={14} /> : saved ? '✓' : <Save size={14} />}
        {saved ? 'Saved!' : 'Save'}
      </button>
    </div>
  )
}
