import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const isProd = process.env.NODE_ENV === "production";
const isElectron = process.env.ELECTRON === "1" || process.env.ELECTRON === "true";

export default defineConfig({
  plugins: [react()],
  base: isElectron ? "./" : isProd ? "/web/" : "/",
  server: {
    host: true,
    port: 8100,
    strictPort: true,
  },
  build: {
    outDir: "dist",
  },
});
