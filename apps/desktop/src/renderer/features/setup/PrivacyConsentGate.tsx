import { useState } from 'react';
import { Check, Languages, X } from 'lucide-react';
import { Button } from '../../components/ui/Button';
import { cn } from '../../lib/utils';
import {
  PRIVACY_TEXTS,
  PRIVACY_VERSION,
  detectPrivacyLanguage,
  type PrivacyLanguage,
} from '../../lib/privacy';

/**
 * 首次启动的隐私协议确认门 (#837)。
 *
 * 无安装向导的分发形式（portable/zip）与升级用户在应用内看到本页；
 * 同意状态写入 localStorage，协议版本更新时（PRIVACY_VERSION 递增）
 * 会再次要求确认。拒绝则关闭窗口退出应用。
 */
export function PrivacyConsentGate({ onAgree }: { onAgree: () => void }) {
  const [language, setLanguage] = useState<PrivacyLanguage>(() => detectPrivacyLanguage());

  const decline = () => {
    // 主窗口 close 后 window-all-closed → app.quit()（非 macOS）。
    window.close();
  };

  return (
    <div
      className="flex h-screen flex-col items-center justify-center px-6 py-8"
      style={{ background: 'var(--background)' }}
      data-testid="privacy-consent-gate"
    >
      <div className="flex w-full max-w-2xl flex-col overflow-hidden rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface)] shadow-xl">
        {/* Header */}
        <div className="flex items-center justify-between gap-3 border-b border-[var(--border-subtle)] px-6 py-4">
          <div className="min-w-0">
            <h1 className="text-lg font-semibold text-[var(--text)]">
              {language === 'zh-CN' ? '隐私协议' : 'Privacy Agreement'}
            </h1>
            <p className="mt-0.5 text-xs text-[var(--text-muted)]">
              {language === 'zh-CN' ? '版本 ' : 'Version '}
              {PRIVACY_VERSION}
              <span className="mx-1.5 text-[var(--text-faint)]">·</span>
              {language === 'zh-CN'
                ? '使用 MiqroForge Desktop 前，请阅读并同意本协议'
                : 'Please read and accept this agreement before using MiqroForge Desktop'}
            </p>
          </div>
          <div className="flex shrink-0 items-center gap-0.5 rounded-lg border border-[var(--border)] bg-[var(--surface-muted)]/60 p-0.5">
            {(['zh-CN', 'en-US'] as const).map((lang) => (
              <button
                key={lang}
                onClick={() => setLanguage(lang)}
                aria-pressed={language === lang}
                className={cn(
                  'rounded-md px-2 py-1 text-xs font-medium transition-colors',
                  language === lang
                    ? 'bg-[var(--accent-soft)] text-[var(--accent)]'
                    : 'text-[var(--text-muted)] hover:text-[var(--text)]'
                )}
              >
                {lang === 'zh-CN' ? '中文' : 'English'}
              </button>
            ))}
            <Languages size={12} className="mr-1 text-[var(--text-faint)]" />
          </div>
        </div>

        {/* Scrollable agreement text */}
        <div className="max-h-[52vh] overflow-y-auto px-6 py-4">
          <pre
            className="whitespace-pre-wrap break-words font-sans text-[13px] leading-relaxed text-[var(--text)]"
            data-testid="privacy-consent-text"
          >
            {PRIVACY_TEXTS[language]}
          </pre>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between gap-3 border-t border-[var(--border-subtle)] bg-[var(--surface-muted)]/40 px-6 py-4">
          <p className="min-w-0 text-xs text-[var(--text-faint)]">
            {language === 'zh-CN'
              ? '同意状态保存在本机，协议更新时需重新确认。'
              : 'Consent is stored locally; re-confirmation is required when the agreement is updated.'}
          </p>
          <div className="flex shrink-0 items-center gap-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={decline}
              data-testid="privacy-consent-decline"
            >
              <X size={14} />
              {language === 'zh-CN' ? '拒绝并退出' : 'Decline and Exit'}
            </Button>
            <Button size="sm" onClick={onAgree} data-testid="privacy-consent-agree">
              <Check size={14} />
              {language === 'zh-CN' ? '同意并继续' : 'Agree and Continue'}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
