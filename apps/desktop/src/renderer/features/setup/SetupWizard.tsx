import { useState, useEffect } from 'react'
import { Button } from '../../components/ui/Button'
import { Input } from '../../components/ui/Input'
import { cn } from '../../lib/utils'
import {
  Check,
  X,
  Loader2,
  ArrowRight,
  ArrowLeft,
  Zap,
  Key,
  Settings,
} from 'lucide-react'
import type { ProviderInfo, PythonCheckResult, RuntimeStatus } from '../../../shared/ipc'

type Step = 'welcome' | 'environment' | 'provider' | 'finish'

export function SetupWizard({ onComplete }: { onComplete: () => void }) {
  const [step, setStep] = useState<Step>('welcome')
  const [pyCheck, setPyCheck] = useState<PythonCheckResult | null>(null)
  const [checking, setChecking] = useState(false)

  // Provider form state
  const [providers, setProviders] = useState<ProviderInfo[]>([])
  const [selectedProvider, setSelectedProvider] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [apiBase, setApiBase] = useState('')
  const [modelName, setModelName] = useState('')
  const [testResult, setTestResult] = useState<'idle' | 'testing' | 'ok' | 'error'>('idle')
  const [testError, setTestError] = useState('')

  // Load providers on mount
  useEffect(() => {
    window.miqi.providers.list().then((r) => {
      setProviders(r.providers.filter((p) => !p.is_local))
    }).catch(() => {})
  }, [])

  // Run python check
  const runCheck = async () => {
    setChecking(true)
    try {
      const result = await window.miqi.python.check()
      setPyCheck(result)
    } catch {
      setPyCheck({ ok: false, python_version: 'unknown', issues: ['Failed to check Python'], config_exists: false })
    }
    setChecking(false)
  }

  // Test provider connection
  const testProvider = async () => {
    if (!selectedProvider || !apiKey) return
    setTestResult('testing')
    setTestError('')
    try {
      const result = await window.miqi.providers.test(selectedProvider, apiKey, apiBase || undefined)
      setTestResult('ok')
    } catch (e: any) {
      setTestResult('error')
      setTestError(e.message ?? String(e))
    }
  }

  // Save config and finish
  const saveConfig = async () => {
    const provider = providers.find((p) => p.name === selectedProvider)
    if (!provider) return

    const providerKey = provider.name

    await window.miqi.config.update({
      config: {
        agents: {
          defaults: {
            model: modelName || `${providerKey}/default`,
          },
        },
        providers: {
          [providerKey]: {
            apiKey: apiKey,
            apiBase: apiBase || null,
          },
        },
      },
    })
  }

  const handleFinish = async () => {
    await saveConfig()
    await window.miqi.runtime.start()
    onComplete()
  }

  // ---- Render steps ----

  const renderWelcome = () => (
    <div className="flex flex-col items-center text-center gap-4">
      <div className="w-16 h-16 rounded-2xl bg-[var(--accent-soft)] flex items-center justify-center mb-2">
        <Zap size={32} className="text-[var(--accent)]" />
      </div>
      <h1 className="text-2xl font-semibold text-[var(--text)]">Welcome to MiQi Desktop</h1>
      <p className="text-sm text-[var(--text-muted)] max-w-sm leading-relaxed">
        MiQi Desktop is a native companion for your local AI agent.
        Let's get you set up with a provider so you can start chatting.
      </p>
      <Button onClick={() => setStep('environment')} className="mt-4">
        Get Started
        <ArrowRight size={16} />
      </Button>
    </div>
  )

  const renderEnvironment = () => (
    <div className="flex flex-col gap-4">
      <h2 className="text-lg font-semibold text-[var(--text)]">Environment Check</h2>
      <p className="text-sm text-[var(--text-muted)]">
        We'll check that Python and MiQi are available on your system.
      </p>

      {!pyCheck ? (
        <Button onClick={runCheck} disabled={checking} variant="outline" className="self-start">
          {checking && <Loader2 size={14} className="animate-spin" />}
          Run Check
        </Button>
      ) : (
        <div className="flex flex-col gap-2 bg-[var(--surface-muted)] rounded-lg p-4 text-sm">
          <CheckItem
            label="Python"
            ok={pyCheck.ok}
            detail={pyCheck.python_version}
          />
          {pyCheck.issues.map((issue, i) => (
            <div key={i} className="flex items-center gap-2 text-[var(--danger)] text-xs">
              <X size={12} /> {issue}
            </div>
          ))}
          <CheckItem
            label="Config exists"
            ok={!pyCheck.config_exists}
            detail={pyCheck.config_exists ? 'Already configured' : 'Not yet configured'}
          />
        </div>
      )}

      <div className="flex gap-2 mt-4">
        <Button variant="ghost" onClick={() => setStep('welcome')}>
          <ArrowLeft size={16} /> Back
        </Button>
        <Button
          onClick={() => setStep('provider')}
          disabled={!pyCheck?.ok}
        >
          Continue <ArrowRight size={16} />
        </Button>
      </div>
    </div>
  )

  const renderProvider = () => (
    <div className="flex flex-col gap-4">
      <h2 className="text-lg font-semibold text-[var(--text)]">Configure Provider</h2>
      <p className="text-sm text-[var(--text-muted)]">
        Choose an LLM provider and enter your API key. You can change this later.
      </p>

      {/* Provider selector */}
      <div className="flex flex-col gap-1.5">
        <label className="text-xs font-medium text-[var(--text-muted)]">Provider</label>
        <select
          value={selectedProvider}
          onChange={(e) => {
            setSelectedProvider(e.target.value)
            const p = providers.find((p) => p.name === e.target.value)
            if (p) setApiBase(p.default_api_base)
            setTestResult('idle')
          }}
          className="h-9 rounded-lg border border-[var(--border)] bg-[var(--surface)] px-3 text-sm text-[var(--text)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)]/30"
        >
          <option value="">Select a provider...</option>
          {providers.filter((p) => !p.is_local).map((p) => (
            <option key={p.name} value={p.name}>
              {p.display_name}
            </option>
          ))}
        </select>
      </div>

      {/* API Key */}
      <div className="flex flex-col gap-1.5">
        <label className="text-xs font-medium text-[var(--text-muted)]">
          API Key {selectedProvider && providers.find((p) => p.name === selectedProvider)?.env_key && (
            <span className="text-[var(--text-faint)]">
              (env: {providers.find((p) => p.name === selectedProvider)!.env_key})
            </span>
          )}
        </label>
        <Input
          type="password"
          value={apiKey}
          onChange={(e) => { setApiKey(e.target.value); setTestResult('idle') }}
          placeholder="sk-..."
        />
      </div>

      {/* API Base */}
      <div className="flex flex-col gap-1.5">
        <label className="text-xs font-medium text-[var(--text-muted)]">API Base URL (optional)</label>
        <Input
          value={apiBase}
          onChange={(e) => setApiBase(e.target.value)}
          placeholder="https://api.openai.com/v1"
        />
      </div>

      {/* Model name */}
      <div className="flex flex-col gap-1.5">
        <label className="text-xs font-medium text-[var(--text-muted)]">Default Model (optional)</label>
        <Input
          value={modelName}
          onChange={(e) => setModelName(e.target.value)}
          placeholder={`${selectedProvider || 'provider'}/model-name`}
        />
      </div>

      {/* Test button */}
      {selectedProvider && apiKey && (
        <div>
          <Button
            variant="outline"
            size="sm"
            onClick={testProvider}
            disabled={testResult === 'testing'}
          >
            {testResult === 'testing' && <Loader2 size={14} className="animate-spin" />}
            Test Connection
          </Button>
          {testResult === 'ok' && (
            <span className="ml-2 text-xs text-[var(--success)] flex items-center gap-1 inline-flex">
              <Check size={12} /> Connected
            </span>
          )}
          {testResult === 'error' && (
            <span className="ml-2 text-xs text-[var(--danger)]">{testError}</span>
          )}
        </div>
      )}

      <div className="flex gap-2 mt-4">
        <Button variant="ghost" onClick={() => setStep('environment')}>
          <ArrowLeft size={16} /> Back
        </Button>
        <Button
          onClick={() => setStep('finish')}
          disabled={!selectedProvider || !apiKey || testResult !== 'ok'}
        >
          Continue <ArrowRight size={16} />
        </Button>
      </div>
    </div>
  )

  const renderFinish = () => (
    <div className="flex flex-col items-center text-center gap-4">
      <div className="w-12 h-12 rounded-full bg-[var(--success)]/20 flex items-center justify-center">
        <Check size={24} className="text-[var(--success)]" />
      </div>
      <h2 className="text-xl font-semibold text-[var(--text)]">You're all set!</h2>
      <p className="text-sm text-[var(--text-muted)] max-w-sm">
        MiQi is configured and ready. Click below to save your settings and launch the chat console.
      </p>
      <Button onClick={handleFinish} className="mt-2">
        <Key size={16} />
        Save & Launch
      </Button>
    </div>
  )

  return (
    <div className="flex items-center justify-center h-full bg-[var(--background)]">
      <div className="w-full max-w-lg bg-[var(--surface-elevated)] border border-[var(--border)] rounded-xl shadow-sm p-8">
        {/* Step indicators */}
        <div className="flex items-center justify-center gap-2 mb-8">
          {(['welcome', 'environment', 'provider', 'finish'] as Step[]).map((s, i) => (
            <div key={s} className="flex items-center gap-2">
              <div className={cn(
                'w-7 h-7 rounded-full flex items-center justify-center text-xs font-medium transition-colors',
                step === s ? 'bg-[var(--accent)] text-white' : 'bg-[var(--surface-muted)] text-[var(--text-muted)]',
              )}>
                {i + 1}
              </div>
              {i < 3 && <div className="w-6 h-px bg-[var(--border)]" />}
            </div>
          ))}
        </div>

        {step === 'welcome' && renderWelcome()}
        {step === 'environment' && renderEnvironment()}
        {step === 'provider' && renderProvider()}
        {step === 'finish' && renderFinish()}
      </div>
    </div>
  )
}

function CheckItem({ label, ok, detail }: { label: string; ok: boolean; detail?: string }) {
  return (
    <div className="flex items-center gap-2">
      {ok
        ? <Check size={14} className="text-[var(--success)] shrink-0" />
        : <X size={14} className="text-[var(--danger)] shrink-0" />
      }
      <span className={ok ? 'text-[var(--text)]' : 'text-[var(--danger)]'}>{label}</span>
      {detail && <span className="text-[var(--text-faint)] text-xs">{detail}</span>}
    </div>
  )
}
