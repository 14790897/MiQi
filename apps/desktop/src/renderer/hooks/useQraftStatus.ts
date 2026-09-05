import { useEffect, useState } from 'react';
import type { QraftStatus } from '../../shared/ipc';

/**
 * 共享 Qraft 登录态（#835 登录门控）。
 *
 * 复用 QraftPage 的 status + onStatusChanged 模式，供设置页 / Providers 页
 * 判断「是否已登录」，在未登录时禁用模型选择并引导登录。
 */
export function useQraftStatus() {
  const [status, setStatus] = useState<QraftStatus | null>(null);

  useEffect(() => {
    let alive = true;
    let gotEvent = false; // 事件已到 → 初始快照视为过期，避免覆盖更新的状态
    let unsubscribe: (() => void) | undefined;

    try {
      window.miqi.qraft
        .status()
        .then((s) => {
          if (alive && !gotEvent) setStatus(s);
        })
        .catch(() => {
          /* IPC 未就绪时保持空状态 */
        });
      unsubscribe = window.miqi.qraft.onStatusChanged((next) => {
        gotEvent = true;
        setStatus(next);
      });
    } catch {
      /* 旧版 preload（如 smoke mock）可能没有 qraft 命名空间 */
    }

    return () => {
      alive = false;
      unsubscribe?.();
    };
  }, []);

  return { status, loggedIn: status?.loggedIn === true };
}
