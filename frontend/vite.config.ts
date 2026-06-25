import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

const backendUrl = process.env.SLIDES_READER_BACKEND_URL || "http://127.0.0.1:8000";

// Vite 是前端开发服务器和构建工具。
// 这里通过 proxy 把 `/api` 请求转发到后端；一键启动脚本会在端口变化时传入实际后端地址。
export default defineConfig({
  plugins: [react()],
  test: {
    // jsdom 在 Node.js 测试进程里模拟浏览器 DOM，让 React 组件测试可以使用 document 和 window。
    environment: "jsdom",
    // setupFiles 会在每个测试文件前执行，用来注册 Testing Library 的额外断言。
    setupFiles: "./src/test/setup.ts",
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: backendUrl,
        changeOrigin: true,
      },
    },
  },
});
