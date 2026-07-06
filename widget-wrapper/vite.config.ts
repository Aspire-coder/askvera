import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const buildTarget = process.env.WIDGET_BUILD_TARGET || "es";
const isIifeBuild = buildTarget === "iife";
const isMinifiedBuild = process.env.WIDGET_MINIFY === "true";
const sdkName = process.env.npm_package_name || "@askvera/widget";
const sdkVersion = process.env.npm_package_version || "1.0.0";
const buildDate = process.env.ASKVERA_BUILD_DATE || new Date().toISOString();
const buildCommit = process.env.GITHUB_SHA?.slice(0, 7) || process.env.ASKVERA_BUILD_COMMIT || "unknown";

export default defineConfig({
  plugins: [react()],
  define: {
    __ASKVERA_SDK_NAME__: JSON.stringify(sdkName),
    __ASKVERA_SDK_VERSION__: JSON.stringify(sdkVersion),
    __ASKVERA_BUILD_DATE__: JSON.stringify(buildDate),
    __ASKVERA_BUILD_COMMIT__: JSON.stringify(buildCommit)
  },
  build: {
    emptyOutDir: buildTarget === "es",
    minify: isMinifiedBuild ? "oxc" : false,
    sourcemap: true,
    lib: {
      entry: "src/generic-widget/index.ts",
      name: "AskVeraWidget",
      formats: [isIifeBuild ? "iife" : "es"],
      fileName: () => {
        if (isIifeBuild) return isMinifiedBuild ? "widget.min.js" : "widget.js";
        return "widget.es.js";
      },
      cssFileName: isIifeBuild && isMinifiedBuild ? "widget.min" : "widget"
    }
  }
});
