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
  QraftBrowserLoginInput,
  type QraftLoginResult,
  type QraftStatus,
} from '../../shared/ipc';
import {
  QraftError,
  buildAuthorizeUrl,
  createQraftClient,
  extractCodeForRedirect,
  type QraftLogger,
  type ResolvedQraftConfig,
} from './client';
import { QraftService } from './service';
import { QraftStore } from './store';

const { ipcMain, app, net, safeStorage, BrowserWindow, session } = electron;

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

/** 浏览器登录窗口等待用户完成授权的超时时间。 */
const BROWSER_LOGIN_TIMEOUT_MS = 5 * 60_000;

/**
 * 浏览器登录：打开 Qraft 授权页，用户在页面完成登录并点击"同意"
 *（Qraft 授权页修复后按钮可用）。拦截跳转回 redirect_uri 的 code，
 * 拦截到即关闭窗口。窗口提前关闭 → LOGIN_CANCELLED。
 */
function openBrowserLoginWindow(config: ResolvedQraftConfig): Promise<string> {
  return new Promise<string>((resolve, reject) => {
    // 独立 partition：登录窗口的 cookie 与主应用隔离，完成后整体清理，
    // 不残留平台登录态（token 才是后续凭证）。
    const loginSession = session.fromPartition('qraft-login', { cache: false });
    const win = new BrowserWindow({
      width: 960,
      height: 720,
      title: 'Qraft 平台登录',
      autoHideMenuBar: true,
      webPreferences: {
        session: loginSession,
        contextIsolation: true,
        nodeIntegration: false,
        sandbox: true,
      },
    });

    let settled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let cookiePoller: ReturnType<typeof setInterval> | null = null;
    let redirectedToAuthorize = false;
    const settle = (fn: () => void) => {
      if (settled) return;
      settled = true;
      if (timer !== null) clearTimeout(timer);
      if (cookiePoller !== null) clearInterval(cookiePoller);
      fn();
      void loginSession.clearStorageData().catch(() => {});
    };

    // 安全加固：授权窗口只允许在 Qraft 平台 origin 内导航，其余目标一律
    // 拦截；页面发起的 window.open 一律拒绝。服务端 302（登录跳转/授权
    // 回调）走 will-redirect，不受 will-navigate 限制，回调仍由 captureCode
    // 拦截后立即关窗。
    const qraftOrigin = new URL(config.baseUrl).origin;
    win.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
    win.webContents.on('will-navigate', (event, url) => {
      let allowed = false;
      try {
        allowed = new URL(url).origin === qraftOrigin;
      } catch {
        allowed = false;
      }
      if (!allowed) {
        console.warn(`[qraft] 阻止授权窗口导航到非平台地址（${url.slice(0, 120)}）`);
        event.preventDefault();
      }
    });

    // 实测：平台 SPA 登录成功后停留在首页，不会自动回到授权流程。
    // 登录态 cookie 出现即说明登录完成 —— 主动把窗口带回 authorize。
    const origin = new URL(config.baseUrl).origin;
    cookiePoller = setInterval(() => {
      if (settled || redirectedToAuthorize) return;
      void loginSession.cookies
        .get({ url: origin, name: 'Authorization' })
        .then((cookies) => {
          if (settled || redirectedToAuthorize) return;
          if (cookies.length > 0) {
            redirectedToAuthorize = true;
            console.log('[qraft] 浏览器登录：检测到平台登录态，回到授权流程');
            void win.loadURL(buildAuthorizeUrl(config)).catch(() => {});
          }
        })
        .catch(() => {});
    }, 1000);

    const captureCode = (url: string): void => {
      const code = extractCodeForRedirect(url, config.redirectUri);
      if (!code) return;
      console.log(`[qraft] 浏览器登录：捕获授权回调 code（${code.slice(0, 6)}…）`);
      settle(() => {
        win.destroy();
        resolve(code);
      });
    };

    // 302 重定向（服务端）与普通导航（授权页 JS 跳转）都会走到这里。
    win.webContents.on('will-redirect', (_event, url) => captureCode(url));
    win.webContents.on('did-navigate', (_event, url) => captureCode(url));
    win.webContents.on('did-navigate-in-page', (_event, url) => captureCode(url));

    win.on('closed', () => {
      settle(() => reject(new QraftError('LOGIN_CANCELLED', '已取消：登录窗口在完成授权前被关闭')));
    });

    timer = setTimeout(() => {
      settle(() => {
        win.destroy();
        reject(
          new QraftError('BROWSER_LOGIN_FAILED', '浏览器登录超时（5 分钟未完成授权），请重试')
        );
      });
    }, BROWSER_LOGIN_TIMEOUT_MS);

    void win.loadURL(buildAuthorizeUrl(config)).catch(() => {
      settle(() => {
        win.destroy();
        reject(new QraftError('BROWSER_LOGIN_FAILED', '无法打开 Qraft 登录页，请检查网络后重试'));
      });
    });
  });
}

export function registerQraftIpcHandlers(): void {
  ipcMain.handle(IPC.QRAFT_LOGIN, async (_event, payload: unknown): Promise<QraftLoginResult> => {
    const parsed = QraftLoginInput.safeParse(payload);
    if (!parsed.success) {
      return { ok: false, code: 'INVALID_CONFIG', message: '登录参数非法，请检查手机号与高级设置' };
    }
    const input = parsed.data;
    return getService().login(input.phone, input.password, {
      env: input.env,
      baseUrl: input.baseUrl,
      clientId: input.clientId,
      clientSecret: input.clientSecret,
      redirectUri: input.redirectUri,
    });
  });

  ipcMain.handle(
    IPC.QRAFT_BROWSER_LOGIN,
    async (_event, payload: unknown): Promise<QraftLoginResult> => {
      const parsed = QraftBrowserLoginInput.safeParse(payload);
      if (!parsed.success) {
        return {
          ok: false,
          code: 'INVALID_CONFIG',
          message: '浏览器登录参数非法，请检查高级设置',
        };
      }
      const input = parsed.data;
      const svc = getService();
      try {
        const config = svc.resolveLoginConfig({
          env: input.env,
          baseUrl: input.baseUrl,
          clientId: input.clientId,
          clientSecret: input.clientSecret,
          redirectUri: input.redirectUri,
        });
        console.log(`[qraft] 浏览器登录：打开授权页（${config.baseUrl}）`);
        const code = await openBrowserLoginWindow(config);
        // 换 token 必须与窗口里 authorize 用的是同一个 redirect_uri。
        return await svc.loginWithCode(code, {
          env: input.env,
          baseUrl: input.baseUrl,
          clientId: input.clientId,
          clientSecret: input.clientSecret,
          redirectUri: config.redirectUri,
        });
      } catch (err) {
        console.error(`[qraft] 浏览器登录失败（${err instanceof QraftError ? err.code : err}）`);
        if (err instanceof QraftError) return { ok: false, code: err.code, message: err.message };
        return {
          ok: false,
          code: 'INTERNAL',
          message: err instanceof Error ? err.message : String(err),
        };
      }
    }
  );

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
