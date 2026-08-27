/**
 * 常驻免责声明 — issue #836
 *
 * 需求：每个会话的消息流底部（输入框下方）常驻一行免责声明，
 * 弱化展示（小字号 + --text-faint），随会话切换自动跟随当前会话。
 *
 * 文案集中在此常量文件（配置化），便于法务/产品修订；支持中/英。
 * 默认文案（待法务/产品最终确认，issue #836 示例）：
 *   「AI 生成内容仅供参考，可能存在错误，请自行核实关键信息」
 */

export const DISCLAIMER_TEXTS: Record<string, string> = {
  zh: 'AI 生成内容仅供参考，可能存在错误，请自行核实关键信息',
  en: 'AI-generated content is for reference only and may contain errors. Please verify critical information yourself.',
};

/**
 * 根据环境语言（Chromium locale，跟随系统语言）返回免责声明文案。
 * 只取 language tag 的基础语言（zh-CN → zh），未知语言回退中文。
 * navigator 守卫仅用于 Node 环境（e2e 断言可直接复用本常量）。
 */
export function getDisclaimerText(): string {
  const base = (typeof navigator !== 'undefined' ? navigator.language : 'zh-CN')
    .toLowerCase()
    .split('-')[0];
  return DISCLAIMER_TEXTS[base] ?? DISCLAIMER_TEXTS.zh;
}
