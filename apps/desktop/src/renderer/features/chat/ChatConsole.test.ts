/**
 * ChatConsole 回归测试（#858 → #905）。
 *
 * 回归点：fast（极速）模式也必须渲染思考块——之前 ChatConsole 用
 * `reasoningMode !== 'fast'` 把 ThinkBlock 过滤掉，导致极速模式下
 * 思考过程消失（#858）。#905 移除该门控后，测试直接覆盖渲染路径：
 * ThinkingBlockGroup 在 fast/think 两种模式下都输出思考内容。
 *
 * 门控回归防护：渲染决策收拢在 `shouldRenderThinkingGroup`（ChatConsole
 * 调用处即用它）——若有人把 fast 门控加回，该函数的测试立即失败。
 * 组件级渲染由 ThinkingBlockGroup/ThinkBlock 测试覆盖（含
 * fallbackMode='fast' 组合）；完整 ChatConsole 集成渲染依赖大量
 * window.miqi mock，成本高，由上面两个层级补齐。
 */
import { describe, expect, it } from 'vitest';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { ThinkingBlockGroup, shouldRenderThinkingGroup, sessionMsgsToUi } from './ChatConsole';

describe('ChatConsole thinking block regression (#858 → #905)', () => {
  it('门控决策点：fast/think 两种模式都渲染思考块组（#783 决策）', () => {
    // #858 教训：门控曾加在调用处导致 fast 模式思考过程消失。
    // 决策点恒真——任何模式都必须渲染，回归锁定。
    expect(shouldRenderThinkingGroup('fast')).toBe(true);
    expect(shouldRenderThinkingGroup('think')).toBe(true);
  });
  it('fast 模式：思考块组完整渲染（🚀 快速思考 + 内容）', () => {
    const markup = renderToStaticMarkup(
      createElement(ThinkingBlockGroup, {
        thinking: {
          reasoning: '1. 理解需求\n- 要点一',
          isLiveReasoning: true,
          reasoningMode: 'fast',
        },
        fallbackMode: 'think',
      })
    );
    expect(markup).toContain('🚀');
    expect(markup).toContain('快速思考');
    expect(markup).toContain('理解需求');
    expect(markup).toContain('要点一');
    // 头部存在
    expect(markup).toContain('MiqroForge');
  });

  it('think 模式：思考块组完整渲染（🧠 深度思考 + 内容）', () => {
    const markup = renderToStaticMarkup(
      createElement(ThinkingBlockGroup, {
        thinking: {
          reasoning: '深入分析',
          reasoningMode: 'think',
        },
        fallbackMode: 'think',
      })
    );
    expect(markup).toContain('🧠');
    expect(markup).toContain('深度思考');
    expect(markup).toContain('深入分析');
  });

  it('消息未带模式时回退到全局模式', () => {
    const markup = renderToStaticMarkup(
      createElement(ThinkingBlockGroup, {
        thinking: { reasoning: '回退模式' },
        fallbackMode: 'fast',
      })
    );
    expect(markup).toContain('快速思考');
  });

  it('历史恢复链路：后端 reasoning_mode（下划线）→ progress 行带 reasoningMode', () => {
    // #905 review P1 链路：turn_runner 以 reasoning_mode（snake_case）持久化，
    // 前端 collapseAssistantMessagesWithinTurns 必须读该字段（读驼峰
    // reasoningMode 会静默丢失，历史恢复仍回退全局模式）。
    const raw = [
      { role: 'user', content: '问题', timestamp: '2026-09-01T00:00:00Z' },
      {
        role: 'assistant',
        content: '回答',
        reasoning_content: '思考内容',
        reasoning_mode: 'fast',
        timestamp: '2026-09-01T00:00:01Z',
      },
    ];
    const ui = sessionMsgsToUi(raw);
    const thinking = ui.find((m) => m.role === 'progress' && m.reasoning);
    expect(thinking?.reasoningMode).toBe('fast');
  });
});
