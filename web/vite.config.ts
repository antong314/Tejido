import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Build output is consumed by FastAPI, which mounts `web/dist` as a static
// file directory and rewrites `GET /s/<session_id>` to serve `index.html`.
// During development, `npm run dev` runs Vite on :5173 and proxies API
// calls to the FastAPI server on :8000.

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: false,
      },
    },
  },
});
