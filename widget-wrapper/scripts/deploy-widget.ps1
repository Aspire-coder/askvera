$ErrorActionPreference = "Stop"

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$widgetRoot = Split-Path -Parent $scriptRoot

Push-Location $widgetRoot
try {
    node ./scripts/deploy-widget.js @args
}
finally {
    Pop-Location
}
