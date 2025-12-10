import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 开发环境用根路径，生产构建用 /web/ 与后端挂载保持一致
const isProd = process.env.NODE_ENV === "production";

export default defineConfig({
  plugins: [react()],
  base: isProd ? "/web/" : "/",
  server: {
    host: true, // 推荐，不用写 0.0.0.0
    port: 8100,
    strictPort: true, // 强制使用 8100
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "dist",
  },
});
