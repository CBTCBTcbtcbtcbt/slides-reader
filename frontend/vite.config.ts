import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Vite 是前端开发服务器和构建工具。
// 这里通过 proxy 把 `/api` 请求转发到后端，避免前端代码写死完整后端地址。
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
});
