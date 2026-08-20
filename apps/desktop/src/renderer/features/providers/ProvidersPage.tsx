import { useState, useEffect, useCallback } from 'react';
import { ErrorBoundary } from '../../components/ErrorBoundary';
import {
  Zap,
  Server,
  Globe,
  HardDrive,
  CheckCircle,
  Circle,
  AlertCircle,
  XCircle,
  Edit2,
  TestTube2,
  Eye,
  EyeOff,
  Save,
  X,
  Loader2,
  ChevronDown,
  ChevronRight,
  Play,
} from 'lucide-react';
import { cn } from '../../lib/utils';
import { sanitizeUiMessage } from '../../lib/sanitizeUiMessage';
import { useRestartRequired } from '../../contexts/RestartRequiredContext';
import type { ProviderInfo } from '../../../shared/ipc';

const DOMESTIC_NAMES = new Set([
  'dashscope',
  'zhipu',
  'moonshot',
  'minimax',
  'siliconflow',
  'volcengine',
]);

function getCategory(p: ProviderInfo): 'gateway' | 'domestic' | 'local' | 'international' {
  if (p.is_local) return 'local';
  if (p.is_gateway) return 'gateway';
  if (DOMESTIC_NAMES.has(p.name)) return 'domestic';
  return 'international';
}

type VerificationStatus = NonNullable<ProviderInfo['verification_status']>;

function getVerificationStatus(provider: ProviderInfo): VerificationStatus {
  if (!provider.configured) return 'missing';
  return provider.verification_status ?? 'unverified';
}

function getStatusMeta(provider: ProviderInfo) {
  const status = getVerificationStatus(provider);
  if (status === 'success') {
    return {
      label: '验证成功',
      icon: CheckCircle,
      tone: 'success',
      title: provider.verified_at ? `上次验证：${provider.verified_at}` : '已通过连接测试',
    };
  }
  if (status === 'failed') {
    return {
      label: '验证失败',
      icon: XCircle,
      tone: 'danger',
      title: provider.verification_message ?? '最近一次连接测试失败',
    };
  }
  if (status === 'unverified') {
    return {
      label: '已填写，未验证',
      icon: AlertCircle,
      tone: 'warning',
      title: '已保存配置，但还没有通过连接测试',
    };
  }
  return {
    label: '未填写',
    icon: Circle,
    tone: 'muted',
    title: '还没有填写 API Key 或 API Base',
  };
}

function statusClass(tone: string) {
  if (tone === 'success') return 'text-[var(--success)]';
  if (tone === 'danger') return 'text-[var(--danger)]';
  if (tone === 'warning') return 'text-[var(--warning)]';
  return 'text-[var(--border)]';
}

function statusBadgeClass(tone: string) {
  if (tone === 'success') {
    return 'bg-[color-mix(in_srgb,var(--success)_15%,transparent)] text-[var(--success)]';
  }
  if (tone === 'danger') {
    return 'bg-[color-mix(in_srgb,var(--danger)_15%,transparent)] text-[var(--danger)]';
  }
  if (tone === 'warning') {
    return 'bg-[color-mix(in_srgb,var(--warning)_15%,transparent)] text-[var(--warning)]';
  }
  return 'bg-[var(--surface-muted)] text-[var(--text-faint)]';
}

import { EditSheet, ExtraHeadersField } from './components/EditProviderSheet';
import { PROVIDER_DISPLAY_NAMES, PROVIDER_SUGGESTED_MODELS } from '../../lib/providers';

interface ProviderRowProps {
  provider: ProviderInfo;
  onEdit: (p: ProviderInfo) => void;
  onTest: (p: ProviderInfo) => void;
  onActivate: (p: ProviderInfo) => void;
  testingName: string | null;
  activatingName: string | null;
  activeProvider?: string | null;
}

function ProviderRow({
  provider,
  onEdit,
  onTest,
  onActivate,
  testingName,
  activatingName,
  activeProvider,
}: ProviderRowProps) {
  const label = PROVIDER_DISPLAY_NAMES[provider.name] ?? provider.display_name;
  const isTesting = testingName === provider.name;
  const isActivating = activatingName === provider.name;
  const statusMeta = getStatusMeta(provider);
  const StatusIcon = statusMeta.icon;
  const isActive = provider.name === activeProvider;

  return (
    <div
      className={cn(
        'flex items-center gap-3 px-4 py-2.5 hover:bg-[var(--surface-muted)] transition-colors group',
        isActive && 'bg-[var(--accent-soft)]/40'
      )}
    >
      <div className={cn('shrink-0', statusClass(statusMeta.tone))} title={statusMeta.title}>
        <StatusIcon size={14} />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-sm text-[var(--text)] truncate">{label}</span>
          {isActive && (
            <span className="text-size-2xs px-1.5 py-0.5 rounded bg-[var(--accent)] text-white shrink-0">
              当前使用
            </span>
          )}
        </div>
        {provider.configured && (
          <div className="flex items-center gap-2 mt-0.5">
            {provider.api_key_hint && (
              <span className="text-xs text-[var(--text-faint)] font-mono">
                {provider.api_key_hint}
              </span>
            )}
            {provider.configured_model && (
              <span className="text-xs text-[var(--text-faint)] truncate max-w-[160px]">
                模型：{provider.configured_model}
              </span>
            )}
          </div>
        )}
      </div>
      <span
        className={cn(
          'text-xs px-2 py-0.5 rounded-full shrink-0',
          provider.is_gateway
            ? 'bg-[color-mix(in_srgb,var(--info)_15%,transparent)] text-[var(--info)]'
            : provider.is_local
              ? 'bg-[color-mix(in_srgb,var(--warning)_15%,transparent)] text-[var(--warning)]'
              : 'bg-[var(--surface-muted)] text-[var(--text-muted)]'
        )}
      >
        {provider.is_gateway ? '网关' : provider.is_local ? '本地' : provider.provider_type}
      </span>
      <span
        className={cn(
          'text-xs px-2 py-0.5 rounded-full shrink-0',
          statusBadgeClass(statusMeta.tone)
        )}
        title={statusMeta.title}
      >
        {statusMeta.label}
      </span>
      <div className="flex items-center gap-1 shrink-0">
        {provider.configured && !isActive && (
          <button
            onClick={() => onActivate(provider)}
            disabled={isActivating}
            title="启用为当前模型"
            className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-medium border transition-colors disabled:opacity-50"
            style={{
              borderColor: 'color-mix(in srgb, var(--info) 45%, transparent)',
              background: 'color-mix(in srgb, var(--info) 10%, transparent)',
              color: 'var(--info)',
            }}
          >
            {isActivating ? <Loader2 size={13} className="animate-spin" /> : <Play size={13} />}
            启用
          </button>
        )}
        {isActive && (
          <span
            className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-medium shrink-0"
            style={{
              background: 'color-mix(in srgb, var(--success) 18%, transparent)',
              color: 'var(--success)',
              border: '1px solid color-mix(in srgb, var(--success) 35%, transparent)',
            }}
          >
            <CheckCircle size={13} />
            使用中
          </span>
        )}
        <button
          onClick={() => onTest(provider)}
          disabled={isTesting}
          title="测试连接"
          className="p-1.5 rounded-md text-[var(--text-faint)] hover:text-[var(--accent)] hover:bg-[var(--accent-soft)] transition-colors disabled:opacity-40"
        >
          {isTesting ? <Loader2 size={14} className="animate-spin" /> : <TestTube2 size={14} />}
        </button>
        <button
          onClick={() => onEdit(provider)}
          title="编辑 Provider"
          className="p-1.5 rounded-md text-[var(--text-faint)] hover:text-[var(--text)] hover:bg-[var(--surface-muted)] transition-colors"
        >
          <Edit2 size={14} />
        </button>
      </div>
    </div>
  );
}

interface CategorySectionProps {
  title: string;
  icon: React.ReactNode;
  providers: ProviderInfo[];
  onEdit: (p: ProviderInfo) => void;
  onTest: (p: ProviderInfo) => void;
  onActivate: (p: ProviderInfo) => void;
  testingName: string | null;
  activatingName: string | null;
  activeProvider?: string | null;
}

function CategorySection({
  title,
  icon,
  providers,
  onEdit,
  onTest,
  onActivate,
  testingName,
  activatingName,
  activeProvider,
}: CategorySectionProps) {
  if (providers.length === 0) return null;
  const filledCount = providers.filter((p) => p.configured).length;
  return (
    <div>
      <div className="flex items-center gap-2 px-4 py-2 text-xs font-semibold uppercase tracking-widest text-[var(--text-faint)] border-b border-[var(--border-subtle)]">
        {icon}
        {title}
        <span className="ml-auto font-normal normal-case tracking-normal">
          {filledCount}/{providers.length} 已填写
        </span>
      </div>
      <div className="divide-y divide-[var(--border-subtle)]">
        {providers.map((p) => (
          <ProviderRow
            key={p.name}
            provider={p}
            onEdit={onEdit}
            onTest={onTest}
            onActivate={onActivate}
            testingName={testingName}
            activatingName={activatingName}
            activeProvider={activeProvider}
          />
        ))}
      </div>
    </div>
  );
}

export function ProvidersPage() {
  const { markRestartRequired } = useRestartRequired();
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [editProvider, setEditProvider] = useState<ProviderInfo | null>(null);
  const [testingName, setTestingName] = useState<string | null>(null);
  const [activatingName, setActivatingName] = useState<string | null>(null);
  const [activeModel, setActiveModel] = useState('');
  const [activeProvider, setActiveProvider] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const result = await window.miqi.providers.list();
      setProviders(result.providers);
      setActiveModel(result.active_model ?? '');
      setActiveProvider(result.active_provider ?? null);
    } catch {
      // silent — runtime may not be running
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const handleTest = async (p: ProviderInfo) => {
    if (!p.configured) {
      return;
    }
    setTestingName(p.name);
    try {
      await window.miqi.providers.test(
        p.name,
        undefined,
        p.api_base ?? undefined,
        p.configured_model || undefined
      );
    } catch {
      // providers.test persists failed verification for saved configs.
    } finally {
      setTestingName(null);
      void load();
    }
  };

  const handleActivate = async (p: ProviderInfo) => {
    if (!p.configured) return;
    const fallbackModel = (PROVIDER_SUGGESTED_MODELS[p.name] ?? [])[0];
    const model = p.configured_model || fallbackModel;
    if (!model) {
      setEditProvider(p);
      return;
    }
    setActivatingName(p.name);
    try {
      await window.miqi.providers.update(p.name, undefined, undefined, undefined, model);
      markRestartRequired();
      await load();
    } finally {
      setActivatingName(null);
    }
  };

  const gateways = providers.filter((p) => getCategory(p) === 'gateway');
  const international = providers.filter((p) => getCategory(p) === 'international');
  const domestic = providers.filter((p) => getCategory(p) === 'domestic');
  const local = providers.filter((p) => getCategory(p) === 'local');
  const filledCount = providers.filter((p) => p.configured).length;
  const verifiedCount = providers.filter((p) => getVerificationStatus(p) === 'success').length;
  const activeProviderLabel = activeProvider
    ? (PROVIDER_DISPLAY_NAMES[activeProvider] ?? activeProvider)
    : '未匹配';
  const activeProviderInfo = activeProvider
    ? providers.find((provider) => provider.name === activeProvider)
    : null;

  return (
    <div className="flex flex-col h-full bg-[var(--background)]">
      <div className="flex items-center justify-between px-6 py-4 border-b border-[var(--border-subtle)] bg-[var(--surface)] shrink-0">
        <div>
          <h1 className="text-base font-semibold text-[var(--text)]">模型提供商</h1>
          <p className="text-xs text-[var(--text-muted)] mt-0.5">
            {loading
              ? '加载中…'
              : `${filledCount} / ${providers.length} 已填写，${verifiedCount} 个验证成功`}
          </p>
          {!loading && (
            <p className="text-xs text-[var(--text-faint)] mt-1">
              当前默认模型：{activeModel || '未设置'} · 匹配 Provider：{activeProviderLabel}
            </p>
          )}
        </div>
        <div className="flex items-center gap-2">
          {activeProviderInfo && (
            <button
              onClick={() => setEditProvider(activeProviderInfo)}
              className="text-xs text-[var(--accent)] hover:text-[var(--accent-hover)] transition-colors px-2 py-1 rounded bg-[var(--accent-soft)]"
            >
              编辑当前模型
            </button>
          )}
          <button
            onClick={load}
            className="text-xs text-[var(--text-faint)] hover:text-[var(--text-muted)] transition-colors px-2 py-1 rounded"
          >
            Refresh
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto">
        {loading ? (
          <div className="flex items-center justify-center h-40 text-sm text-[var(--text-faint)]">
            <Loader2 size={16} className="animate-spin mr-2" /> 正在加载…
          </div>
        ) : providers.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-40 gap-2 text-sm text-[var(--text-faint)]">
            <Server size={24} />
            <span>MiqroForge 运行时未启动</span>
          </div>
        ) : (
          <div className="divide-y divide-[var(--border-subtle)]">
            <CategorySection
              title="网关"
              icon={
                <>
                  <Globe size={12} className="icon-mono" />
                  <span className="icon-color text-xs leading-none">🌐</span>
                </>
              }
              providers={gateways}
              onEdit={setEditProvider}
              onTest={handleTest}
              onActivate={handleActivate}
              testingName={testingName}
              activatingName={activatingName}
              activeProvider={activeProvider}
            />
            <CategorySection
              title="国际"
              icon={
                <>
                  <Zap size={12} className="icon-mono" />
                  <span className="icon-color text-xs leading-none">⚡</span>
                </>
              }
              providers={international}
              onEdit={setEditProvider}
              onTest={handleTest}
              onActivate={handleActivate}
              testingName={testingName}
              activatingName={activatingName}
              activeProvider={activeProvider}
            />
            <CategorySection
              title="国内"
              icon={
                <>
                  <Server size={12} className="icon-mono" />
                  <span className="icon-color text-xs leading-none">🖥️</span>
                </>
              }
              providers={domestic}
              onEdit={setEditProvider}
              onTest={handleTest}
              onActivate={handleActivate}
              testingName={testingName}
              activatingName={activatingName}
              activeProvider={activeProvider}
            />
            <CategorySection
              title="本地"
              icon={
                <>
                  <HardDrive size={12} className="icon-mono" />
                  <span className="icon-color text-xs leading-none">💾</span>
                </>
              }
              providers={local}
              onEdit={setEditProvider}
              onTest={handleTest}
              onActivate={handleActivate}
              testingName={testingName}
              activatingName={activatingName}
              activeProvider={activeProvider}
            />
          </div>
        )}
      </div>

      {editProvider && (
        <ErrorBoundary
          fallback={(error, reset) => (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30">
              <div className="bg-[var(--surface-elevated)] border border-[var(--border)] rounded-xl shadow-xl p-6 max-w-sm">
                <p className="text-sm text-[var(--danger)] mb-3">
                  编辑面板加载失败: {error.message}
                </p>
                <div className="flex gap-2">
                  <button
                    onClick={reset}
                    className="px-3 py-1.5 rounded-md bg-[var(--accent)] text-white text-xs"
                  >
                    重试
                  </button>
                  <button
                    onClick={() => setEditProvider(null)}
                    className="px-3 py-1.5 rounded-md border border-[var(--border)] text-xs"
                    style={{ color: 'var(--text-muted)' }}
                  >
                    关闭
                  </button>
                </div>
              </div>
            </div>
          )}
        >
          <EditSheet provider={editProvider} onClose={() => setEditProvider(null)} onSaved={load} />
        </ErrorBoundary>
      )}
    </div>
  );
}
