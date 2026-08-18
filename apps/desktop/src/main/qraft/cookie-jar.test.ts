import { describe, expect, it } from 'vitest';
import { CookieJar, collectSetCookieHeaders, parseSetCookieValue } from './cookie-jar';
import type { HeadersLike } from './cookie-jar';

function headers(record: Record<string, string>): HeadersLike {
  const lower: Record<string, string> = {};
  for (const [k, v] of Object.entries(record)) lower[k.toLowerCase()] = v;
  return {
    get: (name) => lower[name.toLowerCase()] ?? null,
    getSetCookie: () => (lower['set-cookie'] ? [lower['set-cookie']] : []),
  };
}

describe('parseSetCookieValue', () => {
  it('解析 name=value 并忽略属性', () => {
    expect(parseSetCookieValue('Authorization=686cc118-bc52; Path=/')).toEqual({
      name: 'Authorization',
      value: '686cc118-bc52',
    });
  });

  it('解析失败返回 null', () => {
    expect(parseSetCookieValue('no-equals-sign')).toBeNull();
    expect(parseSetCookieValue('')).toBeNull();
  });
});

describe('collectSetCookieHeaders', () => {
  it('优先使用 getSetCookie()', () => {
    const h: HeadersLike = {
      get: () => null,
      getSetCookie: () => ['A=1; Path=/', 'B=2; Path=/'],
    };
    expect(collectSetCookieHeaders(h)).toEqual(['A=1; Path=/', 'B=2; Path=/']);
  });

  it('无 getSetCookie 时按 "name=" 起始切分 get 结果（不误伤 Expires 内的逗号）', () => {
    const h: HeadersLike = {
      get: (name) =>
        name === 'set-cookie'
          ? 'A=1; Path=/, B=2; Expires=Wed, 21 Oct 2026 07:28:00 GMT; Path=/'
          : null,
    };
    expect(collectSetCookieHeaders(h)).toEqual([
      'A=1; Path=/',
      'B=2; Expires=Wed, 21 Oct 2026 07:28:00 GMT; Path=/',
    ]);
  });

  it('无 cookie 时返回空数组', () => {
    expect(collectSetCookieHeaders(headers({}))).toEqual([]);
  });
});

describe('CookieJar', () => {
  it('从响应保存 cookie 并序列化为 Cookie 头', () => {
    const jar = new CookieJar();
    jar.storeFromResponse({ headers: headers({ 'Set-Cookie': 'Authorization=uuid-123; Path=/' }) });
    expect(jar.get('Authorization')).toBe('uuid-123');
    expect(jar.header()).toBe('Authorization=uuid-123');
  });

  it('空值 / max-age<=0（含 -1）表示删除', () => {
    const jar = new CookieJar();
    jar.set('Authorization', 'uuid-123');
    jar.storeFromResponse({ headers: headers({ 'Set-Cookie': 'Authorization=; Path=/' }) });
    expect(jar.get('Authorization')).toBeUndefined();
    jar.set('Authorization', 'uuid-123');
    jar.storeFromResponse({
      headers: headers({ 'Set-Cookie': 'Authorization=x; Max-Age=0; Path=/' }),
    });
    expect(jar.get('Authorization')).toBeUndefined();
    jar.set('Authorization', 'uuid-123');
    jar.storeFromResponse({
      headers: headers({ 'Set-Cookie': 'Authorization=x; Max-Age=-1; Path=/' }),
    });
    expect(jar.get('Authorization')).toBeUndefined();
  });

  it('多对 cookie 拼接顺序稳定', () => {
    const jar = new CookieJar();
    jar.set('A', '1');
    jar.set('B', '2');
    expect(jar.header()).toBe('A=1; B=2');
  });

  it('clear 清空全部', () => {
    const jar = new CookieJar();
    jar.set('A', '1');
    jar.clear();
    expect(jar.isEmpty()).toBe(true);
    expect(jar.header()).toBe('');
  });
});
