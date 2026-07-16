#!/usr/bin/env bash
set -euo pipefail

SCRIPT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WIDGET_ROOT="$(cd "$SCRIPT_ROOT/.." && pwd)"

cd "$WIDGET_ROOT"
node ./scripts/deploy-widget.js "$@"
