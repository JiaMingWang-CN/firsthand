import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 前端只通过 /api 访问后端；后端默认监听 127.0.0.1:8000（见 docs/phase6.md）。
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5180,
    proxy: { '/api': { target: 'http://127.0.0.1:8000', changeOrigin: false } },
  },
  // 组件测试（vitest + happy-dom）；适配层的纯函数测试仍用 node --test（test/adapt.test.mjs）
  test: { environment: 'happy-dom', include: ['test/**/*.spec.js'] },
})
