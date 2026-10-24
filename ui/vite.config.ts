import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// base "./" keeps the build host-agnostic: the FastAPI server at /, or any static host under a sub-path.
export default defineConfig({
  base: "./",
  plugins: [react()],
  build: { outDir: "dist", emptyOutDir: true, target: "es2022" },
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8000",
      "/ws": { target: "ws://127.0.0.1:8000", ws: true },
    },
  },
});
