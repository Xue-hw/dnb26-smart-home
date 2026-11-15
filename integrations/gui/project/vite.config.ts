import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  return {
    plugins: [react()],
    resolve: {
      alias: { '@': path.resolve(import.meta.dirname, 'src') },
    },
    server: {
      proxy: {
        '/api': {
          target: env.VITE_DEV_API_TARGET || 'http://localhost:8000',
          changeOrigin: true,
        },
        '/uploads': {
          target: env.VITE_DEV_API_TARGET || 'http://localhost:8000',
          changeOrigin: true,
        },
      },
    },
    build: {
      outDir: 'dist',
      emptyOutDir: true,
      sourcemap: false,
      // 历史页为独立懒加载模块，包含按需引入的 ECharts；首屏不加载该模块。
      chunkSizeWarningLimit: 600,
    },
  };
});
