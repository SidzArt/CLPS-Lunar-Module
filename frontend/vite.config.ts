import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ isSsrBuild }) => ({
  plugins: [react()],
  server: {
    proxy: {
      "/api": {
        target: process.env.BACKEND_ORIGIN || "http://127.0.0.1:8000",
        changeOrigin: true,
      },
      "/storage": {
        target: process.env.BACKEND_ORIGIN || "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
  build: isSsrBuild
    ? undefined
    : {
        rollupOptions: {
          output: {
            manualChunks(id) {
              if (id.includes("node_modules/three") || id.includes("@react-three")) {
                return "three-vendor";
              }
              if (id.includes("node_modules/react") || id.includes("react-router-dom")) {
                return "react-vendor";
              }
              return undefined;
            },
          },
        },
      },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    exclude: ["tests/e2e/**", "node_modules/**", "dist/**"],
  },
}));
