#!/usr/bin/env bash
set -euo pipefail

SCRIPT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WIDGET_ROOT="$(cd "$SCRIPT_ROOT/.." && pwd)"

cd "$WIDGET_ROOT"
npm run build
npm run validate-widget
npm run upload-widget
npm run invalidate-widget
