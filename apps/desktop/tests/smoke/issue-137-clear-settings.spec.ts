import { expect, test } from '@playwright/test';
import { buildMockBridgeScript } from './mocks';

async function injectMockAndGoto(page: import('@playwright/test').Page) {
  await page.addInitScript({
    content: buildMockBridgeScript({
      config: {
        agents: {
          defaults: {
            name: 'miqi',
            workspace: 'C:/old-workspace',
            model: 'openai/gpt-4.1',
            temperature: 0.2,
            maxTokens: 4096,
          },
        },
        tools: {
          web: {
            search: {
              provider: 'hybrid',
              apiKey: 'BSA-old',
              ollamaApiBase: 'https://old-search.example',
              ollamaApiKey: 'search-old',
            },
            fetch: {
              provider: 'hybrid',
              ollamaApiBase: 'https://old-fetch.example',
              ollamaApiKey: 'fetch-old',
            },
          },
          papers: {
            provider: 'semantic_scholar',
            semanticScholarApiKey: 's2-old',
          },
        },
      },
    }),
  });
  await page.goto('/');
  await page.waitForSelector('#root', { state: 'visible' });
}

test('issue #137: clearing workspace and model sends explicit empty values', async ({ page }) => {
  await injectMockAndGoto(page);

  await page.getByText('System Settings').click();

  const workspaceInput = page.getByPlaceholder('~/.miqi/workspace');
  const modelInput = page.getByPlaceholder('provider/model-name');
  await expect(workspaceInput).toHaveValue('C:/old-workspace');
  await expect(modelInput).toHaveValue('openai/gpt-4.1');

  await workspaceInput.fill('');
  await modelInput.fill('');
  const generalPanel = workspaceInput.locator('xpath=ancestor::div[contains(@class, "p-6")][1]');
  await generalPanel.locator('button').nth(1).click();

  const updates = await page.evaluate(() => window.__miqiMock.getConfigUpdates());
  expect(updates).toHaveLength(1);
  expect(updates[0]).toEqual({
    agents: {
      defaults: {
        name: 'miqi',
        workspace: '',
        model: '',
        temperature: 0.2,
        maxTokens: 4096,
      },
    },
  });
});

test('issue #137: clearing web tool keys sends explicit empty values', async ({ page }) => {
  await injectMockAndGoto(page);

  await page.getByText('System Settings').click();
  await page.locator('[role="tab"]').filter({ hasText: 'Web' }).click();

  const braveKeyInput = page.getByPlaceholder('BSA...');
  const searchBaseInput = page.getByPlaceholder('https://ollama.com').first();
  const searchKeyInput = page.getByPlaceholder('ollama-key...').first();
  const fetchBaseInput = page.locator('input[value="https://old-fetch.example"]');
  const fetchKeyInput = page.locator('input[value="fetch-old"]');
  const s2KeyInput = page.locator('input[value="s2-old"]');

  await expect(braveKeyInput).toHaveValue('BSA-old');
  await expect(searchBaseInput).toHaveValue('https://old-search.example');
  await expect(searchKeyInput).toHaveValue('search-old');
  await expect(fetchBaseInput).toHaveValue('https://old-fetch.example');
  await expect(fetchKeyInput).toHaveValue('fetch-old');
  await expect(s2KeyInput).toHaveValue('s2-old');

  await braveKeyInput.fill('');
  await searchBaseInput.fill('');
  await searchKeyInput.fill('');
  await fetchBaseInput.fill('');
  await fetchKeyInput.fill('');
  await s2KeyInput.fill('');

  const webToolsPanel = braveKeyInput.locator('xpath=ancestor::div[contains(@class, "p-6")][1]');
  await webToolsPanel.locator('button').last().click();

  const updates = await page.evaluate(() => window.__miqiMock.getConfigUpdates());
  expect(updates).toHaveLength(1);
  expect(updates[0]).toEqual({
    tools: {
      web: {
        search: {
          provider: 'hybrid',
          apiKey: '',
          ollamaApiBase: '',
          ollamaApiKey: '',
        },
        fetch: {
          provider: 'hybrid',
          ollamaApiBase: '',
          ollamaApiKey: '',
        },
      },
      papers: {
        provider: 'semantic_scholar',
        semanticScholarApiKey: '',
      },
    },
  });
});
