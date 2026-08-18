import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { mkdtempSync, rmSync } from 'fs';
import { tmpdir } from 'os';
import { join } from 'path';
import { QraftService, resolveConfig, defaultRedirectUri } from './service';
import { QraftStore } from './store';
import { QraftError, type QraftClient, type QraftLogger } from './client';
import type { QraftStoredState, QraftTokens } from './types';

const noopLog = (() => undefined) as unknown as QraftLogger;

function makeTokens(overrides: Partial<QraftTokens> = {}): QraftTokens {
  return {
    accessToken: 'ACCESS-TOKEN',
    refreshToken: 'REFRESH-TOKEN',
    openid: 'OPENID',
    expiresAt: Date.now() + 7_199_000, // 实测 expires_in=7199
    ...overrides,
  };
}

function makeStoredState(overrides: Partial<QraftStoredState> = {}): QraftStoredState {
  return {
    version: 1,
    env: 'test',
    baseUrl: 'https://test.forge.miqroera.com/api',
    clientId: 'miqi',
    clientSecret: 'test-client-secret',
    redirectUri: 'http://localhost:38000/callback',
    cookie: 'Authorization=uuid-1',
    account: { phone: '18500000000', sub: '19', username: 'U-HKY4-GB4E', nickname: 'MiQi测试' },
    tokens: makeTokens(),
    ...overrides,
  };
}

interface ClientStub {
  platformLogin: ReturnType<typeof vi.fn>;
  authorizeFlow: ReturnType<typeof vi.fn>;
  exchangeCode: ReturnType<typeof vi.fn>;
  refreshTokens: ReturnType<typeof vi.fn>;
  getUserInfo: ReturnType<typeof vi.fn>;
}

function makeClientStub(): ClientStub {
  return {
    platformLogin: vi.fn(),
    authorizeFlow: vi.fn(),
    exchangeCode: vi.fn(),
    refreshTokens: vi.fn(),
    getUserInfo: vi.fn(),
  };
}

let dir: string;
let store: QraftStore;
let statusEvents: unknown[];

beforeEach(() => {
  dir = mkdtempSync(join(tmpdir(), 'qraft-service-'));
  store = new QraftStore(join(dir, 'qraft-auth.json'), null, noopLog);
  statusEvents = [];
  // 测试环境 client_secret 不落仓库，测试从环境变量注入
  process.env.QRAFT_TEST_CLIENT_SECRET = 'test-env-secret';
});
afterEach(() => {
  rmSync(dir, { recursive: true, force: true });
  delete process.env.QRAFT_TEST_CLIENT_SECRET;
  vi.useRealTimers();
});

function makeService(clientStub: ClientStub): QraftService {
  return new QraftService({
    client: clientStub as unknown as QraftClient,
    store,
    log: noopLog,
    makeRedirectUri: () => 'http://localhost:38000/callback',
    onStatusChanged: (status) => statusEvents.push(status),
  });
}

describe('resolveConfig', () => {
  it('未提供任何参数时使用测试环境默认值 + 生成 loopback 回调', () => {
    const config = resolveConfig({}, null, () => 'http://localhost:39999/callback');
    expect(config.baseUrl).toBe('https://test.forge.miqroera.com/api');
    expect(config.clientId).toBe('miqi');
    // client_secret 来自 QRAFT_TEST_CLIENT_SECRET 环境变量（不落仓库）
    expect(config.clientSecret).toBe('test-env-secret');
    expect(config.redirectUri).toBe('http://localhost:39999/callback');
  });

  it('生产环境默认 client_secret 为空、不自动生成 redirect_uri（需注册值）', () => {
    const config = resolveConfig({ env: 'prod' }, null, () => 'http://localhost:1/callback');
    expect(config.baseUrl).toBe('https://forge.miqroera.com/api');
    expect(config.clientSecret).toBe('');
    expect(config.redirectUri).toBe('');
  });

  it('用户覆盖优先于环境默认与上次存储', () => {
    const stored = makeStoredState({ env: 'test', baseUrl: 'https://old.example.com/api' });
    const config = resolveConfig(
      { baseUrl: 'https://new.example.com/api', clientSecret: 'secret-2' },
      stored,
      () => 'http://localhost:2/callback'
    );
    expect(config.baseUrl).toBe('https://new.example.com/api');
    expect(config.clientSecret).toBe('secret-2');
    expect(config.clientId).toBe('miqi');
  });

  it('redirect_uri 复用同环境上次存储值（同一登录态内保持一致）', () => {
    const stored = makeStoredState({ redirectUri: 'http://localhost:38000/callback' });
    const config = resolveConfig({}, stored, () => 'http://localhost:9/callback');
    expect(config.redirectUri).toBe('http://localhost:38000/callback');
  });

  it('切到生产环境时不串用测试环境存储的配置（baseUrl/secret/redirect_uri）', () => {
    const stored = makeStoredState({
      env: 'test',
      baseUrl: 'https://test.forge.miqroera.com/api',
      clientSecret: 'test-client-secret',
      redirectUri: 'http://localhost:38000/callback',
    });
    const config = resolveConfig({ env: 'prod' }, stored, () => 'http://localhost:9/callback');
    expect(config.baseUrl).toBe('https://forge.miqroera.com/api');
    expect(config.clientSecret).toBe('');
    expect(config.redirectUri).toBe('');
  });
});

describe('defaultRedirectUri', () => {
  it('生成带随机端口的 loopback 回调', () => {
    const uri = defaultRedirectUri();
    expect(uri).toMatch(/^http:\/\/localhost:\d+\/callback$/);
    const port = Number(uri.match(/:(\d+)\//)?.[1]);
    expect(port).toBeGreaterThanOrEqual(1024);
    expect(port).toBeLessThanOrEqual(65535);
  });
});

describe('QraftService.login', () => {
  it('成功登录：平台登录 → 授权码流程 → userinfo → 落盘 → 推送状态', async () => {
    const stub = makeClientStub();
    stub.platformLogin.mockResolvedValue({
      sub: '19',
      username: 'U-HKY4-GB4E',
      nickname: '平台昵称',
    });
    stub.authorizeFlow.mockResolvedValue(makeTokens());
    stub.getUserInfo.mockResolvedValue({
      sub: '19',
      username: 'U-HKY4-GB4E',
      nickname: 'MiQi测试',
    });
    const service = makeService(stub);

    const result = await service.login('18500000000', 'password');
    expect(result.ok).toBe(true);
    expect(result.account).toEqual({
      phone: '18500000000',
      sub: '19',
      username: 'U-HKY4-GB4E',
      nickname: 'MiQi测试',
    });

    const status = service.status();
    expect(status.loggedIn).toBe(true);
    expect(status.account?.nickname).toBe('MiQi测试');
    expect(status.requiresRelogin).toBe(false);
    // 密码只传给 platformLogin，且 store 中不保存密码
    expect(store.current?.account.phone).toBe('18500000000');
    expect(JSON.stringify(store.current)).not.toContain('password');
    expect(statusEvents.length).toBeGreaterThan(0);
    // 自动刷新已调度（到期前 15 分钟）
    expect(status.refreshScheduledAt).toBeGreaterThan(Date.now());
  });

  it('userinfo 失败不阻断登录，回退平台登录响应信息', async () => {
    const stub = makeClientStub();
    stub.platformLogin.mockResolvedValue({ sub: '19', username: 'U', nickname: '登录昵称' });
    stub.authorizeFlow.mockResolvedValue(makeTokens());
    stub.getUserInfo.mockRejectedValue(new QraftError('USERINFO_FAILED', 'userinfo boom'));
    const service = makeService(stub);

    const result = await service.login('18500000000', 'p');
    expect(result.ok).toBe(true);
    expect(result.account?.nickname).toBe('登录昵称');
  });

  it('client_secret 缺失（生产默认）报 INVALID_CONFIG，不发任何请求', async () => {
    const stub = makeClientStub();
    const service = makeService(stub);
    const result = await service.login('18500000000', 'p', { env: 'prod' });
    expect(result.ok).toBe(false);
    expect(result.code).toBe('INVALID_CONFIG');
    expect(stub.platformLogin).not.toHaveBeenCalled();
  });

  it('生产环境未填注册 redirect_uri 报 INVALID_CONFIG（不自动生成 loopback）', async () => {
    const stub = makeClientStub();
    const service = makeService(stub);
    const result = await service.login('18500000000', 'p', {
      env: 'prod',
      clientSecret: 'prod-secret',
    });
    expect(result.ok).toBe(false);
    expect(result.code).toBe('INVALID_CONFIG');
    expect(result.message).toContain('redirect_uri');
    expect(stub.platformLogin).not.toHaveBeenCalled();
  });

  it('登录失败返回错误码与提示，不落盘', async () => {
    const stub = makeClientStub();
    stub.platformLogin.mockRejectedValue(new QraftError('LOGIN_FAILED', '登录失败：密码错误'));
    const service = makeService(stub);
    const result = await service.login('18500000000', 'bad');
    expect(result).toEqual({ ok: false, code: 'LOGIN_FAILED', message: '登录失败：密码错误' });
    expect(store.current).toBeNull();
    expect(service.status().loggedIn).toBe(false);
  });
});

describe('QraftService.loginWithCode（浏览器登录路径）', () => {
  it('成功：code 换 token → userinfo → 落盘 → 推送状态（账号信息以 userinfo 为准）', async () => {
    const stub = makeClientStub();
    stub.exchangeCode.mockResolvedValue(makeTokens());
    stub.getUserInfo.mockResolvedValue({
      sub: '19',
      username: 'U-BROWSER',
      nickname: '浏览器用户',
    });
    const service = makeService(stub);

    const result = await service.loginWithCode('browser-code', { env: 'test' });
    expect(result.ok).toBe(true);
    expect(result.account).toEqual({
      phone: '', // 浏览器路径无手机号
      sub: '19',
      username: 'U-BROWSER',
      nickname: '浏览器用户',
    });

    const status = service.status();
    expect(status.loggedIn).toBe(true);
    expect(status.account?.nickname).toBe('浏览器用户');
    expect(store.current?.tokens.accessToken).toBe('ACCESS-TOKEN');
    // 浏览器路径没有平台登录 cookie
    expect(store.current?.cookie).toBe('');
    expect(statusEvents.length).toBeGreaterThan(0);
  });

  it('userinfo 失败不阻断登录，账号信息留空', async () => {
    const stub = makeClientStub();
    stub.exchangeCode.mockResolvedValue(makeTokens());
    stub.getUserInfo.mockRejectedValue(new QraftError('USERINFO_FAILED', 'boom'));
    const service = makeService(stub);

    const result = await service.loginWithCode('browser-code');
    expect(result.ok).toBe(true);
    expect(result.account).toEqual({ phone: '', sub: '', username: '', nickname: '' });
    expect(service.status().loggedIn).toBe(true);
  });

  it('换 token 失败返回错误码，不落盘', async () => {
    const stub = makeClientStub();
    stub.exchangeCode.mockRejectedValue(new QraftError('TOKEN_EXCHANGE_FAILED', 'code 无效'));
    const service = makeService(stub);

    const result = await service.loginWithCode('stale-code');
    expect(result).toEqual({ ok: false, code: 'TOKEN_EXCHANGE_FAILED', message: 'code 无效' });
    expect(store.current).toBeNull();
    expect(service.status().loggedIn).toBe(false);
  });
});

describe('QraftService 自动刷新', () => {
  it('到期前 15 分钟自动刷新；刷新成功更新 token 并重新调度', async () => {
    vi.useFakeTimers();
    const stub = makeClientStub();
    stub.platformLogin.mockResolvedValue({ sub: '1', username: 'u', nickname: 'n' });
    stub.authorizeFlow.mockResolvedValue(makeTokens());
    stub.getUserInfo.mockResolvedValue({ sub: '1', username: 'u', nickname: 'n' });
    // 惰性计算 expiresAt：假时钟推进后每次刷新都返回"从现在起 2 小时"，
    // 避免桩数据里的固定过期时间被时间推进越过导致循环刷新。
    stub.refreshTokens.mockImplementation(async () =>
      makeTokens({ accessToken: 'ACCESS-NEW', expiresAt: Date.now() + 7_199_000 })
    );
    const service = makeService(stub);
    await service.login('18500000000', 'p');

    const delay = 7_199_000 - 15 * 60_000; // expires_in - 15min
    await vi.advanceTimersByTimeAsync(delay + 100);
    expect(stub.refreshTokens).toHaveBeenCalledTimes(1);
    expect(store.current?.tokens.accessToken).toBe('ACCESS-NEW');
    expect(service.status().refreshError).toBeUndefined();
    expect(service.status().requiresRelogin).toBe(false);
    // 重新调度了下一次刷新
    expect(service.status().refreshScheduledAt).toBeGreaterThan(Date.now());
  });

  it('自动刷新失败标记 requiresRelogin，30 分钟后重试', async () => {
    vi.useFakeTimers();
    const stub = makeClientStub();
    stub.platformLogin.mockResolvedValue({ sub: '1', username: 'u', nickname: 'n' });
    stub.authorizeFlow.mockResolvedValue(makeTokens());
    stub.getUserInfo.mockResolvedValue({ sub: '1', username: 'u', nickname: 'n' });
    stub.refreshTokens.mockRejectedValue(new QraftError('REFRESH_FAILED', 'refresh_token 无效'));
    const service = makeService(stub);
    await service.login('18500000000', 'p');

    const delay = 7_199_000 - 15 * 60_000;
    await vi.advanceTimersByTimeAsync(delay + 100);
    expect(stub.refreshTokens).toHaveBeenCalledTimes(1);
    expect(service.status().refreshError).toBe('REFRESH_FAILED');
    expect(service.status().requiresRelogin).toBe(true);

    // 30 分钟后自动重试一次
    await vi.advanceTimersByTimeAsync(30 * 60_000 + 100);
    expect(stub.refreshTokens).toHaveBeenCalledTimes(2);
  });

  it('应用启动时恢复登录态并调度刷新', () => {
    vi.useFakeTimers();
    store.save(makeStoredState({ tokens: makeTokens({ expiresAt: Date.now() + 7_199_000 }) }));
    const stub = makeClientStub();
    const service = makeService(stub);
    expect(service.status().loggedIn).toBe(true);
    expect(service.status().refreshScheduledAt).toBeGreaterThan(Date.now());
  });
});

describe('QraftService 手动刷新与退出', () => {
  it('refreshNow 成功后清除刷新错误', async () => {
    const stub = makeClientStub();
    stub.refreshTokens.mockResolvedValue(makeTokens({ accessToken: 'NEW' }));
    store.save(makeStoredState());
    const service = makeService(stub);
    const result = await service.refreshNow();
    expect(result.ok).toBe(true);
    expect(store.current?.tokens.accessToken).toBe('NEW');
  });

  it('refreshNow 失败返回错误并标记需重新登录', async () => {
    const stub = makeClientStub();
    stub.refreshTokens.mockRejectedValue(new QraftError('REFRESH_FAILED', '无效'));
    store.save(makeStoredState());
    const service = makeService(stub);
    const result = await service.refreshNow();
    expect(result.ok).toBe(false);
    expect(result.code).toBe('REFRESH_FAILED');
    expect(service.status().requiresRelogin).toBe(true);
  });

  it('logout 清除 cookie 与 token，推送未登录状态', async () => {
    const stub = makeClientStub();
    store.save(makeStoredState());
    const service = makeService(stub);
    expect(service.status().loggedIn).toBe(true);

    service.logout();
    expect(service.status().loggedIn).toBe(false);
    expect(store.current).toBeNull();
    expect(statusEvents.some((s) => (s as { loggedIn: boolean }).loggedIn === false)).toBe(true);
  });
});
