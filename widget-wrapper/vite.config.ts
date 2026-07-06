import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const buildTarget = process.env.WIDGET_BUILD_TARGET || "es";
const isIifeBuild = buildTarget === "iife";
const isMinifiedBuild = process.env.WIDGET_MINIFY === "true";

export default defineConfig({
  plugins: [react()],
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
