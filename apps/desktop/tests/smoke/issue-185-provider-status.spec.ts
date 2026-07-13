import { test, expect } from '@playwright/test';
import { buildMockBridgeScript } from './mocks';

test('Provider settings shows filled, verified, failed, and active provider states', async ({ page }) => {
  await page.addInitScript({
    content: buildMockBridgeScript({
      activeModel: 'deepseek-chat',
      activeProvider: 'deepseek',
      providers: [
        {
          name: 'deepseek',
          display_name: 'DeepSeek',
          env_key: 'DEEPSEEK_API_KEY',
          provider_type: 'openai',
          is_gateway: false,
          is_local: false,
          default_api_base: '',
          configured: true,
          api_key_hint: 'sk-t...seek',
          api_base: null,
          configured_model: 'deepseek-chat',
          verification_status: 'success',
          verified_at: '2026-07-09T00:00:00+00:00',
        },
        {
          name: 'openrouter',
          display_name: 'OpenRouter',
          env_key: 'OPENROUTER_API_KEY',
          provider_type: 'openai',
          is_gateway: true,
          is_local: false,
          default_api_base: 'https://openrouter.ai/api/v1',
          configured: true,
          api_key_hint: 'sk-o...uter',
          api_base: 'https://openrouter.ai/api/v1',
          verification_status: 'unverified',
        },
        {
          name: 'openai',
          display_name: 'OpenAI',
          env_key: 'OPENAI_API_KEY',
          provider_type: 'openai',
          is_gateway: false,
          is_local: false,
          default_api_base: '',
          configured: true,
          api_key_hint: 'sk-o...enai',
          api_base: null,
          verification_status: 'failed',
          verification_message: 'Provider test failed',
        },
        {
          name: 'anthropic',
          display_name: 'Anthropic',
          env_key: 'ANTHROPIC_API_KEY',
          provider_type: 'anthropic',
          is_gateway: false,
          is_local: false,
          default_api_base: '',
          configured: false,
          api_key_hint: null,
          api_base: null,
          verification_status: 'missing',
        },
      ],
    }),
  });

  await page.goto('/');
  await page.waitForSelector('#root', { state: 'visible' });
  await page.getByText('System Settings').click();
  await page.getByRole('tab', { name: '模型' }).click();

  await expect(page.getByText('模型提供商')).toBeVisible();
  await expect(page.getByText(/当前默认模型：deepseek-chat/)).toBeVisible();
  await expect(page.getByText(/匹配 Provider：DeepSeek/)).toBeVisible();
  await expect(page.getByText('当前使用')).toBeVisible();
  await expect(page.getByText('验证成功', { exact: true })).toBeVisible();
  await expect(page.getByText('已填写，未验证', { exact: true })).toBeVisible();
  await expect(page.getByText('验证失败', { exact: true })).toBeVisible();
  await expect(page.getByText('未填写', { exact: true })).toBeVisible();
});
