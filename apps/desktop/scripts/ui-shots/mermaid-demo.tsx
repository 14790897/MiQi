/**
 * Mermaid 渲染验证页：真实 MermaidBlock + 一个 flowchart。
 */
import React from 'react';
import { createRoot } from 'react-dom/client';
import { MermaidBlock } from '../../src/renderer/features/chat/components/MermaidBlock';

const FLOW = `flowchart TD
  A[MOF 原料] --> B{造粒方式}
  B -->|冷冻造粒| C[BET 损失 ~0%]
  B -->|挤压成型| D[损失 ~8.7%]
  B -->|喷雾干燥| E[损失 ~15%]
  C --> F[工艺推荐]
  D --> F
  E --> F`;

function App() {
  return (
    <div style={{ background: '#f5f6e5', minHeight: '100vh', padding: 24, fontFamily: 'system-ui' }}>
      <div style={{ maxWidth: 640 }}>
        <div style={{ fontSize: 13, color: '#888', marginBottom: 8 }}>流式中（占位符）</div>
        <MermaidBlock source={FLOW} streaming />
        <div style={{ fontSize: 13, color: '#888', margin: '16px 0 8px' }}>完成后（渲染 SVG）</div>
        <MermaidBlock source={FLOW} />
        <div style={{ fontSize: 13, color: '#888', margin: '16px 0 8px' }}>语法错误（降级代码块）</div>
        <MermaidBlock source="flowchart TD\n  A[broken" />
      </div>
    </div>
  );
}

createRoot(document.getElementById('root')!).render(<App />);
