/**
 * Qraft 登录 IPC 注册（issue #726）。
 *
 * 全部在主进程完成（不依赖 Python bridge）：safeStorage 加密落盘、
 * electron.net.fetch 走系统代理发请求。渲染进程只提交手机号 + 密码，
 * 密码进入主进程后即加密，日志与返回体均不含凭据。
 */

import { electron } from '../../shared/electron';
import { join } from 'path';
import {
  IPC,
  IPC_EVENTS,
  QraftLoginInput,
  type QraftLoginResult,
  type QraftStatus,
} from '../../shared/ipc';
import { createQraftClient, type QraftLogger } from './client';
import { QraftService } from './service';
import { QraftStore } from './store';

const { ipcMain, app, net, safeStorage, BrowserWindow } = electron;

let service: QraftService | null = null;

function getService(): QraftService {
  if (service) return service;
  const log: QraftLogger = (level, message) => {
    // 主进程 console 已被 index.ts 接管写入日志文件（带脱敏），
    // 这里补一个来源前缀便于在日志页按 "qraft" 过滤。
    const line = `[qraft] ${message}`;
    if (level === 'ERROR') console.error(line);
    else if (level === 'WARN') console.warn(line);
    else console.log(line);
  };
  const store = new QraftStore(
    // 打包版在 userData 下；开发模式 userData 已按工作区隔离（见 index.ts）。
    // E2E 通过 MIQI_QRAFT_STORE 环境变量指向临时目录，避免污染开发态并支持预置登录态。
    process.env.MIQI_QRAFT_STORE?.trim() || join(app.getPath('userData'), 'qraft-auth.json'),
    safeStorage,
    log
  );
  service = new QraftService({
    client: createQraftClient({ fetch: (url, init) => net.fetch(url, init) }),
    store,
    log,
    onStatusChanged: (status: QraftStatus) => {
      for (const win of BrowserWindow.getAllWindows()) {
        if (!win.isDestroyed()) win.webContents.send(IPC_EVENTS.QRAFT_STATUS_CHANGED, status);
      }
    },
  });
  return service;
}

export function registerQraftIpcHandlers(): void {
  ipcMain.handle(IPC.QRAFT_LOGIN, async (_event, payload: unknown): Promise<QraftLoginResult> => {
    const input = QraftLoginInput.parse(payload);
    return getService().login(input.phone, input.password, {
      env: input.env,
      baseUrl: input.baseUrl,
      clientId: input.clientId,
      clientSecret: input.clientSecret,
      redirectUri: input.redirectUri,
    });
  });

  ipcMain.handle(IPC.QRAFT_STATUS, async (): Promise<QraftStatus> => {
    return getService().status();
  });

  ipcMain.handle(IPC.QRAFT_REFRESH, async (): Promise<QraftLoginResult> => {
    return getService().refreshNow();
  });

  ipcMain.handle(IPC.QRAFT_LOGOUT, async (): Promise<{ ok: boolean }> => {
    getService().logout();
    return { ok: true };
  });
}
