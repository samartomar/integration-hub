import path from "path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// https://vite.dev/config/
export default defineConfig({
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    globals: true,
  },
  base: "/",
  plugins: [react()],
  optimizeDeps: {
    include: ["axios", "react", "react-dom"],
  },
  server: {
    port: 5173,
    strictPort: true,
  },
  resolve: {
    alias: {
      // Work around axios exports resolution in Vite (avoids "Failed to resolve entry" error)
      axios: path.resolve(__dirname, "node_modules/axios/index.js"),
      // Ensure react is resolved from frontend when bundling frontend-shared (outside project root)
      "react": path.resolve(__dirname, "node_modules/react"),
      "react-dom": path.resolve(__dirname, "node_modules/react-dom"),
    },
  },
});
