import { existsSync, statSync } from "node:fs";
import { logStep, logSuccess, widgetCssPath, widgetJsPath, fail } from "./utils.js";

function assertFile(path, label) {
  if (!existsSync(path)) {
    fail(`Build validation failed: ${label} is missing.`);
  }
  if (statSync(path).size === 0) {
    fail(`Build validation failed: ${label} is empty.`);
  }
}

logStep("Validating widget build artifacts...");
assertFile(widgetJsPath, "dist/widget.js");
assertFile(widgetCssPath, "dist/widget.css");
logSuccess("Build validated");
