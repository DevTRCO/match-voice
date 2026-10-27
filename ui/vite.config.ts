import { readdirSync, renameSync, rmSync } from "node:fs";
import { join } from "node:path";
import { defineConfig } from "vite";
import type { Plugin } from "vite";
import react from "@vitejs/plugin-react";

/** The public static build: mock4.html (the game-first demo) becomes the start page, the React guided run moves to app.html,
 *  and the other design mocks in public/ (mock*.html) are working files for the dev server that must not ship. */
function dropMocks(): Plugin {
  let outDir = "";
  return {
    name: "drop-mocks",
    apply: "build",
    configResolved(c) { outDir = c.build.outDir.startsWith("/") ? c.build.outDir : join(c.root, c.build.outDir); },
    closeBundle() {
      renameSync(join(outDir, "index.html"), join(outDir, "app.html"));
      renameSync(join(outDir, "mock4.html"), join(outDir, "index.html"));
      for (const f of readdirSync(outDir)) if (/^mock.*\.html$/.test(f)) rmSync(join(outDir, f));
    },
  };
}

// base "./" keeps the build host-agnostic: the FastAPI server at /, GitHub Pages under /match-voice/, or any static host
// under any sub-path. Every runtime fetch resolves against document.baseURI (feed.ts, crowd.ts), never against "/".
export default defineConfig(({ mode }) => ({
  base: "./",
  plugins: [react(), ...(mode === "static" ? [dropMocks()] : [])],
  build: { outDir: "dist", emptyOutDir: true, target: "es2022" },
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8000",
      "/ws": { target: "ws://127.0.0.1:8000", ws: true },
    },
  },
}));
