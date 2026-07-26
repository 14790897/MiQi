import { CheckCircle, XCircle, AlertCircle, Circle } from 'lucide-react';
import type { ProviderInfo } from '../../../shared/ipc';

type VerificationStatus = NonNullable<ProviderInfo['verification_status']>;

export function getVerificationStatus(provider: ProviderInfo): VerificationStatus {
  if (!provider.configured) return 'missing';
  return provider.verification_status ?? 'unverified';
}

export function getStatusMeta(provider: ProviderInfo) {
  const status = getVerificationStatus(provider);
  if (status === 'success') return { label: '验证成功', icon: CheckCircle, tone: 'success' as const, title: provider.verified_at ? `上次验证：${provider.verified_at}` : '已通过连接测试' };
  if (status === 'failed') return { label: '验证失败', icon: XCircle, tone: 'danger' as const, title: provider.verification_message ?? '最近一次连接测试失败' };
  if (status === 'unverified') return { label: '已填写，未验证', icon: AlertCircle, tone: 'warning' as const, title: '已保存配置，但还没有通过连接测试' };
  return { label: '未填写', icon: Circle, tone: 'muted' as const, title: '还没有填写 API Key 或 API Base' };
}

export function statusClass(tone: string) {
  if (tone === 'success') return 'text-[var(--success)]';
  if (tone === 'danger') return 'text-[var(--danger)]';
  if (tone === 'warning') return 'text-[var(--warning)]';
  return 'text-[var(--border)]';
}

export function statusBadgeClass(tone: string) {
  if (tone === 'success') return 'bg-[color-mix(in_srgb,var(--success)_15%,transparent)] text-[var(--success)]';
  if (tone === 'danger') return 'bg-[color-mix(in_srgb,var(--danger)_15%,transparent)] text-[var(--danger)]';
  if (tone === 'warning') return 'bg-[color-mix(in_srgb,var(--warning)_15%,transparent)] text-[var(--warning)]';
  return 'bg-[var(--surface-muted)] text-[var(--text-faint)]';
}
