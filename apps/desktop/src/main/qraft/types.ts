/**
 * Qraft OAuth2 登录共享类型。
 *
 * 依据《Qraft OAuth2 接入实测文档》(issue #726)：
 * - access_token 实测有效期约 2 小时（expires_in=7199），并非官方的 24 小时；
 * - refresh_token 不轮换（刷新返回同一个值），不要依赖轮换语义；
 * - userinfo 响应无 picture 字段；
 * - 授权确认必须走 POST /oauth2/doConfirm；authorize 不传 state。
 */

export type QraftEnv = 'test' | 'prod';

/** 每个环境默认接入配置（生产环境凭据可在设置页"高级设置"中覆盖）。 */
export interface QraftEnvConfig {
  /** API 基础地址，如 https://test.forge.miqroera.com/api */
  baseUrl: string;
  clientId: string;
  clientSecret: string;
}

export const QRAFT_ENV_DEFAULTS: Record<QraftEnv, QraftEnvConfig> = {
  test: {
    baseUrl: 'https://test.forge.miqroera.com/api',
    clientId: 'miqi',
    clientSecret: 'miqi123456',
  },
  prod: {
    baseUrl: 'https://forge.miqroera.com/api',
    clientId: 'miqi',
    clientSecret: '',
  },
};

/** 登录请求携带的可选覆盖项（设置页"高级设置"）。 */
export interface QraftLoginOptions {
  env?: QraftEnv;
  baseUrl?: string;
  clientId?: string;
  clientSecret?: string;
  /** OAuth 回调地址；留空则自动生成 loopback 地址（随机端口）。 */
  redirectUri?: string;
}

/** Qraft 账号信息（来自 login 响应与 /oauth2/userinfo）。 */
export interface QraftAccount {
  /** 手机号（登录表单提交，登录响应不返回 phone）。 */
  phone: string;
  /** userinfo 的 sub（与登录响应的 userId 一致）。 */
  sub: string;
  username: string;
  nickname: string;
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
  /** 平台登录态 cookie（服务端下发 Set-Cookie: Authorization=<uuid>）。 */
  cookie: string;
  account: QraftAccount;
  tokens: QraftTokens;
}

/** 登录/刷新/登出等操作返回给渲染进程的统一结果。 */
export interface QraftLoginResult {
  ok: boolean;
  account?: QraftAccount;
  /** 失败时的稳定错误码（见 QraftErrorCode）。 */
  code?: QraftErrorCode;
  /** 面向用户的错误提示（中文，可直接展示）。 */
  message?: string;
}

/** 渲染进程查询到的当前登录态。 */
export interface QraftStatus {
  loggedIn: boolean;
  account?: QraftAccount;
  env?: QraftEnv;
  baseUrl?: string;
  /** access_token 到期时间（epoch 毫秒）。 */
  expiresAt?: number;
  /** 计划中的自动刷新时间（epoch 毫秒）。 */
  refreshScheduledAt?: number;
  /** 最近一次自动/手动刷新失败的错误码，刷新成功后清除。 */
  refreshError?: QraftErrorCode;
  /** 刷新失败且凭据不可用，需要重新登录。 */
  requiresRelogin?: boolean;
}

/** 稳定错误码，渲染进程据此展示对应修复指引。 */
export type QraftErrorCode =
  | 'IP_NOT_WHITELISTED' // 出口 IP 未加白（nginx 统一 403）
  | 'NETWORK_UNREACHABLE' // 请求随机超时/连接失败（实测 HTTP 000），重试后仍失败
  | 'LOGIN_FAILED' // 平台登录失败（密码错误 / 账号异常等）
  | 'PUBLIC_KEY_EXTRACT_FAILED' // 无法从登录页 JS bundle 提取 RSA 公钥
  | 'SESSION_EXPIRED' // 登录态 cookie 失效，被 302 到登录页
  | 'AUTHORIZE_FAILED' // 授权流程失败（doConfirm / 取 code 环节）
  | 'TOKEN_EXCHANGE_FAILED' // code 换 token 失败
  | 'REFRESH_FAILED' // refresh_token 刷新失败
  | 'USERINFO_FAILED' // 获取用户信息失败
  | 'LOGIN_CANCELLED' // 浏览器登录窗口在完成授权前被关闭
  | 'BROWSER_LOGIN_FAILED' // 浏览器登录路径失败（页面打不开 / 等待授权超时）
  | 'INVALID_CONFIG' // client_secret / redirect_uri 等接入配置缺失或非法
  | 'INTERNAL';
