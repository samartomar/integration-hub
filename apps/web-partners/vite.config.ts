/// <reference types="vitest" />
import path from "path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const vendorApiBaseUrl = process.env.VITE_VENDOR_API_BASE_URL ?? "";

export default defineConfig({
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    globals: true,
  },
  base: "/",
  plugins: [react()],
  optimizeDeps: {
    include: ["axios", "react", "react-dom", "react-router-dom"],
  },
  resolve: {
    dedupe: ["react", "react-dom", "react-router-dom"],
    alias: {
      "frontend-shared/ErrorFallback": path.resolve(__dirname, "../../packages/ui-shared/src/components/ErrorFallback.tsx"),
      "frontend-shared": path.resolve(__dirname, "../../packages/ui-shared/src"),
      // Work around axios exports resolution in Vite (avoids "Failed to resolve entry" error)
      axios: path.resolve(__dirname, "node_modules/axios/index.js"),
      // Ensure react subpaths resolve from vendor's node_modules (fixes bundling frontend-shared)
      "react": path.resolve(__dirname, "node_modules/react"),
      "react-dom": path.resolve(__dirname, "node_modules/react-dom"),
      "react/jsx-dev-runtime": path.resolve(__dirname, "node_modules/react/jsx-dev-runtime.js"),
      "react/jsx-runtime": path.resolve(__dirname, "node_modules/react/jsx-runtime.js"),
    },
  },
  server: {
    port: 5174,
    strictPort: true,
    proxy: vendorApiBaseUrl
      ? {
          "/v1": {
            target: vendorApiBaseUrl.replace(/\/$/, ""),
            changeOrigin: true,
            secure: false,
          },
        }
      : {},
  },
});
