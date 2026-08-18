import { describe, expect, it } from 'vitest';
import { generateKeyPairSync, privateDecrypt, constants } from 'node:crypto';
import {
  encryptPasswordRsa,
  extractPublicKeyFromBundle,
  findEraBundleUrls,
  maskSecret,
} from './rsa';

function makeKeyPair(): { publicPem: string; privatePem: string } {
  const { publicKey, privateKey } = generateKeyPairSync('rsa', {
    modulusLength: 2048,
    publicKeyEncoding: { type: 'spki', format: 'pem' },
    privateKeyEncoding: { type: 'pkcs8', format: 'pem' },
  });
  return { publicPem: publicKey, privatePem: privateKey };
}

describe('encryptPasswordRsa', () => {
  it('使用 PKCS#1 v1.5 填充加密，私钥可解密还原明文（与 JSEncrypt 默认一致）', () => {
    const { publicPem, privatePem } = makeKeyPair();
    const encrypted = encryptPasswordRsa('not-a-real-password', publicPem);
    // Base64 输出
    expect(encrypted).toMatch(/^[A-Za-z0-9+/]+=*$/);
    const decrypted = privateDecrypt(
      { key: privatePem, padding: constants.RSA_PKCS1_PADDING },
      Buffer.from(encrypted, 'base64')
    ).toString('utf8');
    expect(decrypted).toBe('not-a-real-password');
  });

  it('中文密码可正常加解密', () => {
    const { publicPem, privatePem } = makeKeyPair();
    const encrypted = encryptPasswordRsa('密码测试', publicPem);
    const decrypted = privateDecrypt(
      { key: privatePem, padding: constants.RSA_PKCS1_PADDING },
      Buffer.from(encrypted, 'base64')
    ).toString('utf8');
    expect(decrypted).toBe('密码测试');
  });
});

describe('extractPublicKeyFromBundle', () => {
  it('从 JS bundle 内容提取 BEGIN PUBLIC KEY 块（字符串字面量中的 \\n 转义被归一化）', () => {
    const pem =
      '-----BEGIN PUBLIC KEY-----\nMIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA\nAwIDAQAB\n-----END PUBLIC KEY-----';
    const bundle = `var a=1;var pub="${pem.replace(/\n/g, '\\n')}";function x(){}`;
    expect(extractPublicKeyFromBundle(bundle)).toBe(pem);
  });

  it('支持真实换行的模板字符串形式', () => {
    const pem =
      '-----BEGIN PUBLIC KEY-----\nMIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA\nAwIDAQAB\n-----END PUBLIC KEY-----';
    const bundle = `const key = \`${pem}\`;`;
    expect(extractPublicKeyFromBundle(bundle)).toBe(pem);
  });

  it('无公钥时返回 null', () => {
    expect(extractPublicKeyFromBundle('var a = 1;')).toBeNull();
  });
});

describe('findEraBundleUrls', () => {
  const loginPageUrl = 'https://test.forge.miqroera.com/login';

  it('提取 era-index-*.js 脚本地址（相对路径解析为绝对 URL）', () => {
    const html = `
      <html><head>
        <script src="/static/js/era-index-abc123.js"></script>
        <script src="https://cdn.example.com/other.js"></script>
        <script src="/assets/vendor-1.js"></script>
      </head></html>`;
    expect(findEraBundleUrls(html, loginPageUrl)).toEqual([
      'https://test.forge.miqroera.com/static/js/era-index-abc123.js',
    ]);
  });

  it('忽略带版本查询参数的 era bundle 的 query 后仍可匹配', () => {
    const html = `<script src="/js/era-index-main.js?v=20260813"></script>`;
    expect(findEraBundleUrls(html, loginPageUrl)).toEqual([
      'https://test.forge.miqroera.com/js/era-index-main.js?v=20260813',
    ]);
  });

  it('无 era bundle 时返回空数组', () => {
    expect(findEraBundleUrls('<script src="/app.js"></script>', loginPageUrl)).toEqual([]);
  });
});

describe('maskSecret', () => {
  it('长值只保留首尾各 4 个字符', () => {
    const token = 'x'.repeat(40); // 合成假 token，避免触发硬编码凭据扫描
    const masked = maskSecret(token);
    expect(masked).toBe('xxxx…xxxx');
    // 中间部分绝不出现在脱敏结果里
    expect(masked).not.toContain(token.slice(4, 20));
  });

  it('tail=0 时不得泄露完整值（slice(-0) 会返回整个字符串）', () => {
    const code = 'VWEM98W74FDoNGXvBazCF2xuPv15s4LMeINsXtqg2d9u8yi415yKd3IpExDu';
    const masked = maskSecret(code, 6, 0);
    expect(masked).toBe('VWEM98…');
    expect(masked).not.toContain('VWEM98W74FDo');
    expect(masked.length).toBeLessThan(15);
  });

  it('空值返回占位', () => {
    expect(maskSecret('')).toBe('(empty)');
    expect(maskSecret(null)).toBe('(empty)');
  });

  it('短值全部打码', () => {
    expect(maskSecret('abc')).toBe('***');
  });
});
