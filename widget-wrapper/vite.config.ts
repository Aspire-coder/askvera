import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const isMinifiedBuild = process.env.WIDGET_MINIFY === "true";
const sdkName = process.env.npm_package_name || "@askvera/widget";
const sdkVersion = process.env.npm_package_version || "1.0.0";
const buildDate = process.env.ASKVERA_BUILD_DATE || new Date().toISOString();
const buildCommit = process.env.GITHUB_SHA?.slice(0, 7) || process.env.ASKVERA_BUILD_COMMIT || "unknown";

export default defineConfig({
  plugins: [react()],
  define: {
    process: "undefined",
    "process.env.NODE_ENV": JSON.stringify("production"),
    __ASKVERA_SDK_NAME__: JSON.stringify(sdkName),
    __ASKVERA_SDK_VERSION__: JSON.stringify(sdkVersion),
    __ASKVERA_BUILD_DATE__: JSON.stringify(buildDate),
    __ASKVERA_BUILD_COMMIT__: JSON.stringify(buildCommit)
  },
  build: {
    emptyOutDir: true,
    minify: isMinifiedBuild ? "oxc" : false,
    sourcemap: false,
    lib: {
      entry: "src/sdk/index.ts",
      name: "AskVera",
      formats: ["iife"],
      fileName: () => "widget.js",
      cssFileName: "widget"
    }
  }
});
