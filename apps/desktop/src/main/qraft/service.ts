/**
 * QraftService — 登录态的生命周期编排：
 *   登录（平台登录 → 授权码流程 → userinfo）→ 加密落盘 → 自动刷新调度
 *   → 状态事件推送 → 退出登录清理。
 *
 * 刷新策略按实测数据：access_token 约 2 小时（expires_in=7199），
 * 提前 15 分钟用 refresh_token 刷新；刷新失败标记 requiresRelogin，
 * 由设置页引导用户重新登录。
 */

import { CookieJar } from './cookie-jar';
import { QraftClient, QraftError, type QraftLogger, type ResolvedQraftConfig } from './client';
import { maskSecret } from './rsa';
import { QraftStore } from './store';
import {
  QRAFT_ENV_DEFAULTS,
  testEnvClientSecret,
  type QraftAccount,
  type QraftEnv,
  type QraftErrorCode,
  type QraftLoginOptions,
  type QraftLoginResult,
  type QraftStatus,
  type QraftStoredState,
  type QraftTokens,
} from './types';

/** 到期前提前刷新的提前量（15 分钟）。 */
const REFRESH_ADVANCE_MS = 15 * 60_000;
/** 刷新失败后的退避重试间隔（30 分钟后再试一次，之后依赖手动刷新/重登）。 */
const REFRESH_RETRY_MS = 30 * 60_000;

export interface QraftServiceOptions {
  client: QraftClient;
  store: QraftStore;
  log: QraftLogger;
  /** 状态变化时回调（ipc 层把最新状态推给所有窗口）。 */
  onStatusChanged?: (status: QraftStatus) => void;
  /** 生成 loopback 回调地址（随机端口），测试可注入固定值。 */
  makeRedirectUri?: () => string;
}

export function defaultRedirectUri(): string {
  // 1024–65535 随机端口；测试环境不校验注册值，生产环境需与注册值一致
  //（可在设置页"高级设置"中覆盖）。
  const port = 1024 + Math.floor(Math.random() * (65535 - 1024));
  return `http://localhost:${port}/callback`;
}

/**
 * 解析登录配置：用户覆盖 > 同环境上次登录存下的配置 > 环境默认值。
 * 上次存储只在与目标环境一致时复用 —— 防止切到生产环境时串用测试环境的
 * baseUrl / clientSecret / loopback redirect_uri。
 */
export function resolveConfig(
  opts: QraftLoginOptions,
  stored: QraftStoredState | null,
  makeRedirectUri: () => string
): ResolvedQraftConfig {
  const env: QraftEnv = opts.env ?? stored?.env ?? 'test';
  const defaults = QRAFT_ENV_DEFAULTS[env];
  const storedMatches = stored && stored.env === env ? stored : null;
  return {
    baseUrl: opts.baseUrl ?? storedMatches?.baseUrl ?? defaults.baseUrl,
    clientId: opts.clientId ?? storedMatches?.clientId ?? defaults.clientId,
    clientSecret:
      opts.clientSecret ??
      storedMatches?.clientSecret ??
      (env === 'test' ? testEnvClientSecret() : ''),
    redirectUri:
      opts.redirectUri ??
      storedMatches?.redirectUri ??
      // 测试环境不校验注册值，可自动生成 loopback 地址；
      // 生产环境必须使用注册值，缺失时由 validateConfig 拒绝。
      (env === 'test' ? makeRedirectUri() : ''),
  };
}

function validateConfig(config: ResolvedQraftConfig, env: QraftEnv): void {
  if (!/^https:\/\/.+/i.test(config.baseUrl)) {
    throw new QraftError('INVALID_CONFIG', 'Qraft 基础地址必须是 https:// 开头的完整 URL');
  }
  if (!config.clientId) {
    throw new QraftError('INVALID_CONFIG', 'client_id 不能为空');
  }
  if (!config.clientSecret) {
    throw new QraftError(
      'INVALID_CONFIG',
      'client_secret 未配置：请在设置页"高级设置"中填写，或通过 QRAFT_TEST_CLIENT_SECRET 环境变量注入（测试环境）'
    );
  }
  if (env === 'prod' && !config.redirectUri) {
    throw new QraftError(
      'INVALID_CONFIG',
      '生产环境必须使用在 Qraft 平台注册的 redirect_uri，请在设置页"高级设置"中填写'
    );
  }
  if (config.redirectUri && !/^https?:\/\//i.test(config.redirectUri)) {
    throw new QraftError('INVALID_CONFIG', 'redirect_uri 必须是 http(s):// 开头的完整地址');
  }
}

export class QraftService {
  private jar = new CookieJar();
  private refreshTimer: ReturnType<typeof setTimeout> | null = null;
  private refreshScheduledAt: number | null = null;
  private refreshError: QraftErrorCode | null = null;
  private requiresRelogin = false;

  constructor(private readonly options: QraftServiceOptions) {
    // 应用启动时恢复登录态并重建刷新调度。
    const stored = this.options.store.load();
    if (stored) {
      this.restoreJar(stored);
      this.scheduleRefresh(stored);
    }
  }

  private restoreJar(stored: QraftStoredState): void {
    // 登录态 cookie 序列化格式为 "Authorization=<uuid>; ..."（可能为空）。
    for (const pair of stored.cookie.split(';')) {
      const trimmed = pair.trim();
      const eq = trimmed.indexOf('=');
      if (eq > 0) this.jar.set(trimmed.slice(0, eq), trimmed.slice(eq + 1));
    }
  }

  // ── 对外操作 ──────────────────────────────────────────────────────────

  async login(
    phone: string,
    password: string,
    opts: QraftLoginOptions = {}
  ): Promise<QraftLoginResult> {
    try {
      const stored = this.options.store.current;
      const env: QraftEnv = opts.env ?? stored?.env ?? 'test';
      const config = resolveConfig(
        opts,
        stored,
        this.options.makeRedirectUri ?? defaultRedirectUri
      );
      validateConfig(config, env);
      this.options.log('INFO', `qraft: 开始登录（环境 ${env}，${config.baseUrl}）`);

      this.jar.clear();
      const loginAccount = await this.options.client.platformLogin(
        config,
        phone,
        password,
        this.jar
      );
      const tokens = await this.options.client.authorizeFlow(config, this.jar);

      // 登录后展示账号信息以 userinfo 为准（实测响应无 picture 字段）；
      // userinfo 失败不阻断登录 —— 回退用平台登录响应里的 nickname/username。
      let account: QraftAccount = { phone, ...loginAccount };
      try {
        const info = await this.options.client.getUserInfo(config, tokens.accessToken);
        account = { phone, ...info, sub: info.sub || loginAccount.sub };
      } catch (err) {
        this.options.log(
          'WARN',
          `qraft: userinfo 获取失败（${err instanceof QraftError ? err.code : err}），回退使用登录响应信息`
        );
      }

      this.persistLogin(env, config, account, tokens);
      this.options.log('INFO', `qraft: 登录完成（${account.nickname || account.username}）`);
      return { ok: true, account };
    } catch (err) {
      this.options.log('ERROR', `qraft: 登录失败（${err instanceof QraftError ? err.code : err}）`);
      return this.errorResult(err);
    }
  }

  /**
   * 浏览器登录路径：Qraft 授权页修复后，用户在页面自行登录并点击"同意"，
   * 授权回调里的 code 由 IPC 层拦截后传入，这里换取 token 并完成登录。
   */
  async loginWithCode(code: string, opts: QraftLoginOptions = {}): Promise<QraftLoginResult> {
    try {
      const stored = this.options.store.current;
      const env: QraftEnv = opts.env ?? stored?.env ?? 'test';
      const config = resolveConfig(
        opts,
        stored,
        this.options.makeRedirectUri ?? defaultRedirectUri
      );
      validateConfig(config, env);
      this.options.log('INFO', `qraft: 浏览器登录：换取 token（code ${maskSecret(code, 6, 0)}）`);

      this.jar.clear();
      const tokens = await this.options.client.exchangeCode(config, code);

      // 浏览器路径没有平台登录响应，账号信息以 userinfo 为准
      //（实测响应无 picture 字段、也不含手机号）。
      let account: QraftAccount = { phone: '', sub: '', username: '', nickname: '' };
      try {
        const info = await this.options.client.getUserInfo(config, tokens.accessToken);
        account = { phone: '', ...info };
      } catch (err) {
        this.options.log(
          'WARN',
          `qraft: 浏览器登录 userinfo 获取失败（${err instanceof QraftError ? err.code : err}），账号信息留空`
        );
      }

      this.persistLogin(env, config, account, tokens);
      this.options.log(
        'INFO',
        `qraft: 浏览器登录完成（${account.nickname || account.username || account.sub}）`
      );
      return { ok: true, account };
    } catch (err) {
      this.options.log(
        'ERROR',
        `qraft: 浏览器登录失败（${err instanceof QraftError ? err.code : err}）`
      );
      return this.errorResult(err);
    }
  }

  /**
   * 供 IPC 层在打开登录窗口前解析接入配置 —— 窗口里的 authorize URL 与
   * 之后换 token 必须使用同一份配置（同一 redirect_uri）。
   */
  resolveLoginConfig(opts: QraftLoginOptions): ResolvedQraftConfig {
    const stored = this.options.store.current;
    const env: QraftEnv = opts.env ?? stored?.env ?? 'test';
    const config = resolveConfig(opts, stored, this.options.makeRedirectUri ?? defaultRedirectUri);
    validateConfig(config, env);
    return config;
  }

  /** 保存登录态 + 重置刷新状态 + 调度自动刷新 + 推送状态事件。 */
  private persistLogin(
    env: QraftEnv,
    config: ResolvedQraftConfig,
    account: QraftAccount,
    tokens: QraftTokens
  ): void {
    const state: QraftStoredState = {
      version: 1,
      env,
      baseUrl: config.baseUrl,
      clientId: config.clientId,
      clientSecret: config.clientSecret,
      redirectUri: config.redirectUri,
      cookie: this.jar.header(),
      account,
      tokens,
    };
    this.options.store.save(state);
    this.refreshError = null;
    this.requiresRelogin = false;
    this.scheduleRefresh(state);
    this.emitStatus();
  }

  private errorResult(err: unknown): QraftLoginResult {
    if (err instanceof QraftError) return { ok: false, code: err.code, message: err.message };
    return {
      ok: false,
      code: 'INTERNAL',
      message: err instanceof Error ? err.message : String(err),
    };
  }

  status(): QraftStatus {
    const state = this.options.store.current;
    if (!state) return { loggedIn: false };
    const now = Date.now();
    return {
      loggedIn: true,
      account: state.account,
      env: state.env,
      baseUrl: state.baseUrl,
      expiresAt: state.tokens.expiresAt,
      refreshScheduledAt: this.refreshScheduledAt ?? undefined,
      refreshError: this.refreshError ?? undefined,
      requiresRelogin:
        this.requiresRelogin ||
        // 已过期且最近一次自动刷新失败 → 引导重新登录
        (this.refreshError !== null && now > state.tokens.expiresAt),
    };
  }

  logout(): void {
    this.cancelRefresh();
    this.jar.clear();
    this.options.store.clear();
    this.refreshError = null;
    this.requiresRelogin = false;
    this.options.log('INFO', 'qraft: 已退出登录（cookie 与 token 均已清除）');
    this.emitStatus();
  }

  /** 手动刷新（设置页"刷新"按钮）。 */
  async refreshNow(): Promise<QraftLoginResult> {
    const state = this.options.store.current;
    if (!state) return { ok: false, code: 'INVALID_CONFIG', message: '尚未登录' };
    try {
      await this.doRefresh(state);
      this.refreshError = null;
      this.requiresRelogin = false;
      this.emitStatus();
      return { ok: true, account: state.account };
    } catch (err) {
      this.options.log(
        'ERROR',
        `qraft: 手动刷新失败（${err instanceof QraftError ? err.code : err}）`
      );
      if (err instanceof QraftError) {
        this.refreshError = err.code;
        this.requiresRelogin = true;
        this.emitStatus();
        return { ok: false, code: err.code, message: err.message };
      }
      return {
        ok: false,
        code: 'INTERNAL',
        message: err instanceof Error ? err.message : String(err),
      };
    }
  }

  // ── 自动刷新调度 ──────────────────────────────────────────────────────

  /** 到期前 15 分钟刷新；刷新失败 30 分钟后重试一次。 */
  private scheduleRefresh(state: QraftStoredState): void {
    this.cancelRefresh();
    const now = Date.now();
    const expiresAt = state.tokens.expiresAt;
    if (now >= expiresAt) {
      // 已过期（应用重启后）：立即尝试刷新。
      const delay = 0;
      this.refreshScheduledAt = now;
      this.refreshTimer = setTimeout(() => void this.tickRefresh(state), delay);
      return;
    }
    const delay = Math.max(0, expiresAt - REFRESH_ADVANCE_MS - now);
    this.refreshScheduledAt = now + delay;
    this.refreshTimer = setTimeout(() => void this.tickRefresh(state), delay);
    this.options.log('INFO', `qraft: 已调度自动刷新（${Math.round(delay / 60_000)} 分钟后）`);
  }

  private cancelRefresh(): void {
    if (this.refreshTimer !== null) {
      clearTimeout(this.refreshTimer);
      this.refreshTimer = null;
    }
    this.refreshScheduledAt = null;
  }

  private async tickRefresh(state: QraftStoredState): Promise<void> {
    try {
      await this.doRefresh(state);
      this.refreshError = null;
      this.requiresRelogin = false;
      this.emitStatus();
    } catch (err) {
      const code = err instanceof QraftError ? err.code : 'REFRESH_FAILED';
      this.options.log('ERROR', `qraft: 自动刷新失败（${code}），30 分钟后重试`);
      this.refreshError = code;
      this.requiresRelogin = true;
      this.refreshScheduledAt = Date.now() + REFRESH_RETRY_MS;
      this.refreshTimer = setTimeout(() => void this.tickRefresh(state), REFRESH_RETRY_MS);
      this.emitStatus();
    }
  }

  /** 刷新进行中的去重：手动刷新与自动刷新并发时共享同一次请求，避免
   *  两次 refreshTokens 并发写盘、后写覆盖新 token（若服务端启用轮换语义）。 */
  private inFlightRefresh: Promise<void> | null = null;

  private doRefresh(state: QraftStoredState): Promise<void> {
    if (this.inFlightRefresh) return this.inFlightRefresh;
    this.inFlightRefresh = this.runRefresh(state).finally(() => {
      this.inFlightRefresh = null;
    });
    return this.inFlightRefresh;
  }

  private async runRefresh(state: QraftStoredState): Promise<void> {
    const config: ResolvedQraftConfig = {
      baseUrl: state.baseUrl,
      clientId: state.clientId,
      clientSecret: state.clientSecret,
      redirectUri: state.redirectUri,
    };
    const tokens = await this.options.client.refreshTokens(config, state.tokens.refreshToken);
    // 实测 refresh_token 不轮换（返回同一个）；若服务端未来启用轮换，
    // 以响应中的新值为准，旧值在服务端已失效。
    const next: QraftStoredState = { ...state, tokens };
    this.options.store.save(next);
    this.scheduleRefresh(next);
  }

  private emitStatus(): void {
    try {
      this.options.onStatusChanged?.(this.status());
    } catch {
      /* 回调异常不影响主流程 */
    }
  }
}
