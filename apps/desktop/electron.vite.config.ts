import { resolve } from 'path';
import { defineConfig, externalizeDepsPlugin } from 'electron-vite';
import tailwindcss from '@tailwindcss/vite';
import pkg from './package.json';

export default defineConfig({
  main: {
    plugins: [externalizeDepsPlugin()],
    build: {
      outDir: 'out/main',
      rollupOptions: {
        input: {
          'electron-trampoline': resolve(__dirname, 'src/main/electron-trampoline.js'),
          index: resolve(__dirname, 'src/main/index.ts'),
        },
      },
    },
  },
  preload: {
    // Do NOT use externalizeDepsPlugin() for preload — sandbox mode cannot
    // require() npm packages at runtime, so all dependencies must be bundled.
    plugins: [],
    build: {
      outDir: 'out/preload',
      rollupOptions: {
        input: {
          index: resolve(__dirname, 'src/preload/index.ts'),
        },
      },
    },
  },
  renderer: {
    root: resolve(__dirname, 'src/renderer'),
    // 固定 IPv4 回环：Windows 网络过滤组件（WFP 过滤器）可能劫持 IPv6 回环 ::1，
    // 而 Node 25 把 localhost 解析为 ::1，Vite 默认只绑 ::1，Electron 加载 dev
    // server 就会 ERR_CONNECTION_TIMED_OUT。
    server: {
      host: '127.0.0.1',
    },
    define: {
      __APP_VERSION__: JSON.stringify(pkg.version),
    },
    build: {
      outDir: 'out/renderer',
      rollupOptions: {
        input: {
          index: resolve(__dirname, 'src/renderer/index.html'),
          splash: resolve(__dirname, 'src/renderer/splash.html'),
        },
      },
    },
    plugins: [tailwindcss()],
    resolve: {
      alias: {
        '@': resolve(__dirname, 'src/renderer'),
        '@shared': resolve(__dirname, 'src/shared'),
      },
    },
  },
});
