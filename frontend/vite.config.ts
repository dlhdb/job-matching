import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  server: {
    // 開發時由 Vite 提供前端，API 轉給 uv run src/app.py 起的 FastAPI
    proxy: { "/api": "http://127.0.0.1:8000" },
  },
});
