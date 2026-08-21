/**
 * Citation 渲染验证页：真实 MarkdownContent + 【n】引用 + 参考文献。
 */
import React from 'react';
import { createRoot } from 'react-dom/client';
import { MarkdownContent } from '../../src/renderer/features/chat/components/MarkdownContent';

const MD = `冷冻造粒对 MOF 的 BET 损失影响较小【1】，而挤压成型损失约 8.7%【2】。

\`\`\`mermaid
flowchart TD
  A[原料] --> B{造粒方式}
  B -->|冷冻| C[损失 ~0%]
  B -->|挤压| D[损失 ~8.7%]
\`\`\`

### 参考文献

【1】 Freeze granulation of MOF materials
Journal of Materials Chemistry A, 2025
DOI: 10.1039/d5ta00001a

【2】 Extrusion shaping of metal-organic frameworks
Microporous and Mesoporous Materials, 2024
DOI: 10.1016/j.micromeso.2024.112233`;

function App() {
  return (
    <div style={{ background: '#f5f6e5', minHeight: '100vh', padding: 24, fontFamily: 'system-ui' }}>
      <div style={{ maxWidth: 640, background: '#fff', border: '1px solid #e4e4e0', borderRadius: 12, padding: 16 }}>
        <MarkdownContent content={MD} />
      </div>
    </div>
  );
}

createRoot(document.getElementById('root')!).render(<App />);
