import { createContext, useContext, useState, useCallback, type ReactNode } from 'react';

/**
 * 重启需求标记（issue #789 配置热生效）。
 * 仅「C 类必须重启」的配置变更（Python 路径、WSL distro 等进程级配置）
 * 才调用 markRestartRequired；A 类（保存即生效）与 B 类（对新建会话生效）
 * 不应触发重启提示。
 */
interface RestartRequiredContextValue {
  restartRequired: boolean;
  /** 重启原因（如「Python 解释器路径」「WSL 发行版」），无原因时传 undefined */
  restartReason: string | null;
  markRestartRequired: (reason?: string) => void;
  clearRestartRequired: () => void;
}

const RestartRequiredContext = createContext<RestartRequiredContextValue>({
  restartRequired: false,
  restartReason: null,
  markRestartRequired: () => {},
  clearRestartRequired: () => {},
});

export function RestartRequiredProvider({ children }: { children: ReactNode }) {
  const [restartRequired, setRestartRequired] = useState(false);
  const [restartReason, setRestartReason] = useState<string | null>(null);

  const markRestartRequired = useCallback((reason?: string) => {
    setRestartRequired(true);
    if (reason) setRestartReason(reason);
  }, []);
  const clearRestartRequired = useCallback(() => {
    setRestartRequired(false);
    setRestartReason(null);
  }, []);

  return (
    <RestartRequiredContext.Provider
      value={{ restartRequired, restartReason, markRestartRequired, clearRestartRequired }}
    >
      {children}
    </RestartRequiredContext.Provider>
  );
}

export function useRestartRequired() {
  return useContext(RestartRequiredContext);
}
