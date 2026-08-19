/**
 * Qraft OAuth2 登录 — 主进程内部类型。
 *
 * 渲染进程与主进程共用的协议类型（QraftAccount / QraftErrorCode /
 * QraftLoginResult / QraftStatus）统一定义在 apps/desktop/src/shared/ipc.ts，
 * 这里直接复用并 re-export，避免两份声明漂移。
 *
 * 依据《Qraft OAuth2 接入实测文档》(issue #726)：
 * - access_token 实测有效期约 2 小时（expires_in=7199），并非官方的 24 小时；
 * - refresh_token 不轮换（刷新返回同一个值），不要依赖轮换语义；
 * - userinfo 响应无 picture 字段；
 * - 授权确认必须走 POST /oauth2/doConfirm（授权页修复前）；authorize 不传 state。
 */

export type { QraftAccount, QraftErrorCode, QraftLoginResult, QraftStatus } from '../../shared/ipc';
import type { QraftAccount } from '../../shared/ipc';

export type QraftEnv = 'test' | 'prod';

/** 每个环境默认接入配置。client_secret 不写入仓库：经环境变量注入或用户在设置页填写。 */
export interface QraftEnvConfig {
  /** API 基础地址，如 https://test.forge.miqroera.com/api */
  baseUrl: string;
  clientId: string;
}

export const QRAFT_ENV_DEFAULTS: Record<QraftEnv, QraftEnvConfig> = {
  test: {
    baseUrl: 'https://test.forge.miqroera.com/api',
    clientId: 'miqi',
  },
  prod: {
    baseUrl: 'https://forge.miqroera.com/api',
    clientId: 'miqi',
  },
};

/**
 * 测试环境 client_secret。当前处于测试阶段，开箱即用优先，默认值硬编码；
 * 可经 QRAFT_TEST_CLIENT_SECRET 环境变量覆盖（转正式环境接入前应移除默认值）。
 */
export function testEnvClientSecret(): string {
  return process.env.QRAFT_TEST_CLIENT_SECRET?.trim() || 'miqi123456';
}

/**
 * 生产环境 client_secret。测试阶段同样提供硬编码默认值（开箱即用），
 * 可经 QRAFT_PROD_CLIENT_SECRET 环境变量覆盖（转正式环境接入前应移除默认值）。
 * 注意：生产环境仍必须填写在平台注册的 redirect_uri（见 service.validateConfig）。
 */
export function prodEnvClientSecret(): string {
  return process.env.QRAFT_PROD_CLIENT_SECRET?.trim() || 'miqi123456';
}

/** 登录请求携带的可选覆盖项（设置页"高级设置"）。 */
export interface QraftLoginOptions {
  env?: QraftEnv;
  baseUrl?: string;
  clientId?: string;
  clientSecret?: string;
  /** OAuth 回调地址；测试环境自动生成 loopback 地址，生产环境必须填注册值。 */
  redirectUri?: string;
}

/** 换 token / 刷新后落盘保存的凭据。 */
export interface QraftTokens {
  accessToken: string;
  refreshToken: string;
  openid: string;
  idToken?: string;
  /** access_token 到期时间（epoch 毫秒），按实测 expires_in=7199 计算。 */
  expiresAt: number;
}

/** 持久化的完整登录态（加密落盘）。 */
export interface QraftStoredState {
  version: 1;
  env: QraftEnv;
  baseUrl: string;
  clientId: string;
  clientSecret: string;
  redirectUri: string;
  /** 平台登录态 cookie（服务端下发 Set-Cookie: Authorization=<uuid>）；浏览器登录路径为空。 */
  cookie: string;
  account: QraftAccount;
  tokens: QraftTokens;
}
