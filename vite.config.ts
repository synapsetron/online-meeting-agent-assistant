import { defineConfig, build as viteBuild, type Plugin } from "vite";
import { resolve } from "path";
import { copyFileSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from "fs";
import react from "@vitejs/plugin-react";

function chromeExtension(): Plugin {
  return {
    name: "chrome-extension",
    async closeBundle() {
      mkdirSync("dist/icons", { recursive: true });
      for (const file of readdirSync("icons")) {
        if (file.endsWith(".png")) {
          copyFileSync(`icons/${file}`, `dist/icons/${file}`);
        }
      }

      const manifest = JSON.parse(readFileSync("manifest.json", "utf-8"));
      manifest.action.default_popup = "src/popup/index.html";
      manifest.options_page = "src/options/index.html";
      manifest.background.service_worker = "service-worker.js";
      manifest.content_scripts[0].js = ["content.js"];
      writeFileSync("dist/manifest.json", JSON.stringify(manifest, null, 2));

      // Rebuild content script as IIFE — Chrome content scripts don't support ES modules
      await viteBuild({
        configFile: false,
        resolve: {
          alias: { "@": resolve(__dirname, "src") },
        },
        build: {
          outDir: "dist",
          emptyOutDir: false,
          copyPublicDir: false,
          rollupOptions: {
            input: { content: resolve(__dirname, "src/content/main.ts") },
            output: {
              format: "iife",
              entryFileNames: "content.js",
              inlineDynamicImports: true,
            },
          },
        },
        logLevel: "warn",
      });
    },
  };
}

export default defineConfig({
  plugins: [react(), chromeExtension()],
  resolve: {
    alias: { "@": resolve(__dirname, "src") },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
    rollupOptions: {
      input: {
        popup: resolve(__dirname, "src/popup/index.html"),
        options: resolve(__dirname, "src/options/index.html"),
        offscreen: resolve(__dirname, "src/offscreen/offscreen.html"),
        background: resolve(__dirname, "src/background/service-worker.ts"),
      },
      output: {
        entryFileNames: (chunk) => {
          if (chunk.name === "background") return "service-worker.js";
          if (chunk.name === "offscreen") return "offscreen.js";
          return "assets/[name]-[hash].js";
        },
        chunkFileNames: "assets/[name]-[hash].js",
        assetFileNames: "assets/[name]-[hash][extname]",
      },
    },
  },
});
