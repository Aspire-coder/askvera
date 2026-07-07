$ErrorActionPreference = "Stop"

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$widgetRoot = Split-Path -Parent $scriptRoot

Push-Location $widgetRoot
try {
    npm run build
    npm run validate-widget
    npm run upload-widget
    npm run invalidate-widget
}
finally {
    Pop-Location
}
