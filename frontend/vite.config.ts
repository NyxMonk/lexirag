/// <reference types="vitest/config" />
import path from "node:path";
import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

// The project root .env is shared by backend, frontend and scripts.
const envDir = path.resolve(__dirname, "..");

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, envDir, "");
  const port = Number(env.FRONTEND_PORT || 5173);

  return {
    envDir,
    plugins: [react()],
    resolve: {
      alias: { "@": path.resolve(__dirname, "src") },
    },
    server: {
      host: "localhost",
      port,
      strictPort: true,
    },
    preview: { port, strictPort: true },
    test: {
      environment: "jsdom",
      globals: true,
      setupFiles: ["./src/test/setup.ts"],
      css: false,
    },
  };
});
