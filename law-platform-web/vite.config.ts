/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react';
import { defineConfig, loadEnv } from 'vite';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '.', 'VITE_');
  const proxyTarget = env.VITE_API_PROXY_TARGET || 'http://127.0.0.1:3000';

  return {
    plugins: [react()],
    server: {
      host: '0.0.0.0',
      port: 5173,
      strictPort: true,
      proxy: {
        '/api': { target: proxyTarget, changeOrigin: false },
        '/attachments': { target: proxyTarget, changeOrigin: false },
      },
    },
    preview: {
      host: '0.0.0.0',
      port: 5173,
      strictPort: true,
      proxy: {
        '/api': { target: proxyTarget, changeOrigin: false },
        '/attachments': { target: proxyTarget, changeOrigin: false },
      },
    },
    test: {
      environment: 'jsdom',
      setupFiles: './src/test/setup.ts',
      include: ['src/**/*.test.{ts,tsx}'],
      css: true,
      coverage: { reporter: ['text', 'html'] },
    },
  };
});
