import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

const apiProxy = {
  target: process.env.VITE_PROXY_TARGET || 'http://127.0.0.1:8000',
  changeOrigin: true,
};

export default defineConfig({
  plugins: [react()],
  test: {
    exclude: ['e2e/**', '**/node_modules/**', '**/dist/**'],
  },
  server: {
    port: 5173,
    proxy: {
      '/api': apiProxy,
    },
  },
  preview: {
    port: 5173,
    proxy: {
      '/api': apiProxy,
    },
  },
});
