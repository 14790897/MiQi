import { describe, expect, it } from 'vitest';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { ActionCard, type ActionCardEntry } from './ActionCard';

function entry(overrides: Partial<ActionCardEntry> = {}): ActionCardEntry {
  return {
    action: 'upload',
    target: 'Qraft',
    fileName: 'workflow.json',
    sizeBytes: 23 * 1024,
    sha256: 'deadbeef1234567890abcdef',
    ...overrides,
  };
}

function render(e: ActionCardEntry): string {
  return renderToStaticMarkup(createElement(ActionCard, { entry: e, onResolve: () => {} }));
}

describe('ActionCard (#646-v2)', () => {
  it('upload: renders target + file + size + hash + confirm', () => {
    const html = render(entry());
    expect(html).toContain('即将上传数据');
    expect(html).toContain('Qraft');
    expect(html).toContain('workflow.json');
    expect(html).toContain('23.0 KB');
    expect(html).toContain('deadbeef1234');
    expect(html).toContain('确认上传');
  });

  it('payment / delete / external: distinct titles', () => {
    expect(render(entry({ action: 'payment' }))).toContain('即将产生费用');
    expect(render(entry({ action: 'delete' }))).toContain('即将删除数据');
    expect(render(entry({ action: 'external' }))).toContain('即将外发数据');
  });

  it('no hash → fingerprint row hidden', () => {
    const html = render(entry({ sha256: undefined }));
    expect(html).not.toContain('指纹');
  });
});
