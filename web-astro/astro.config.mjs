// Astro 配置 —— 墨境写作 InkRealm 前端（整站换框架：RhineLab 暖色档案风格）
// 生产环境：astro build 输出到 ./dist，由 FastAPI 静态托管（server/main.py 挂载 web/）。
// 开发环境：/api 代理到本地 FastAPI（127.0.0.1:8723），无需 CORS。
import { defineConfig } from 'astro/config';
import vue from '@astrojs/vue';

export default defineConfig({
  integrations: [vue()],
  output: 'static',
  server: { host: '127.0.0.1', port: 4321 },
  vite: {
    server: {
      proxy: {
        // 开发态把 /api 转发给 FastAPI，保持相对路径一致（生产由 FastAPI 自身处理）
        '/api': { target: 'http://127.0.0.1:8723', changeOrigin: true },
      },
    },
  },
});
