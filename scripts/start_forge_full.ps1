param(
  [int]$BackendPort = 8010,
  [int]$FrontendPort = 3001
)

$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$FrontendDir = Join-Path $Root "forge_frontend_next"

if (-not (Test-Path $FrontendDir)) {
  throw "Next frontend directory not found: $FrontendDir"
}

if (-not (Test-Path (Join-Path $FrontendDir "node_modules"))) {
  throw "Missing frontend dependencies. Run: cd $FrontendDir; npm install"
}

$PythonCmd = (Get-Command "python.exe" -ErrorAction SilentlyContinue)
if (-not $PythonCmd) {
  $PythonCmd = (Get-Command "python" -ErrorAction SilentlyContinue)
}
if (-not $PythonCmd) {
  throw "Python was not found on PATH."
}

$NpmCmd = (Get-Command "npm.cmd" -ErrorAction SilentlyContinue)
if (-not $NpmCmd) {
  $NpmCmd = (Get-Command "npm.exe" -ErrorAction SilentlyContinue)
}
if (-not $NpmCmd) {
  $NpmCmd = (Get-Command "npm" -ErrorAction SilentlyContinue)
}
if (-not $NpmCmd) {
  throw "npm was not found on PATH."
}

Write-Host "Starting WebGAL Forge full stack..."
Write-Host "  Backend : http://127.0.0.1:$BackendPort"
Write-Host "  Frontend: http://127.0.0.1:$FrontendPort"
Write-Host ""
Write-Host "Press Ctrl+C to stop both services."
Write-Host ""

$BackendJob = Start-Job -Name "webgal-forge-backend" -ScriptBlock {
  param($PythonExe, $WorkDir, $Port)
  Set-Location $WorkDir
  & $PythonExe -m uvicorn webgal_backend.app:app --host 0.0.0.0 --port $Port 2>&1 |
    ForEach-Object { "[backend]  $_" }
} -ArgumentList $PythonCmd.Source, $Root.Path, $BackendPort

$FrontendJob = Start-Job -Name "webgal-forge-frontend" -ScriptBlock {
  param($NpmExe, $WorkDir, $Port, $BackendPort)
  Set-Location $WorkDir
  $env:FORGE_BACKEND_URL = "http://127.0.0.1:$BackendPort"
  & $NpmExe run dev -- --hostname 127.0.0.1 --port $Port 2>&1 |
    ForEach-Object { "[frontend] $_" }
} -ArgumentList $NpmCmd.Source, $FrontendDir, $FrontendPort, $BackendPort

try {
  while ($true) {
    Receive-Job -Job $BackendJob, $FrontendJob

    $runningJobs = @($BackendJob, $FrontendJob) | Where-Object {
      $_.State -eq "Running" -or $_.State -eq "NotStarted"
    }

    if ($runningJobs.Count -eq 0) {
      break
    }

    Start-Sleep -Milliseconds 250
  }

  Receive-Job -Job $BackendJob, $FrontendJob

  $failedJobs = @($BackendJob, $FrontendJob) | Where-Object { $_.State -eq "Failed" }
  if ($failedJobs.Count -gt 0) {
    throw "One or more services exited with errors."
  }
} finally {
  Write-Host ""
  Write-Host "Stopping WebGAL Forge services..."

  foreach ($job in @($BackendJob, $FrontendJob)) {
    if ($job.State -eq "Running" -or $job.State -eq "NotStarted") {
      Stop-Job -Job $job -ErrorAction SilentlyContinue
    }
    Receive-Job -Job $job -ErrorAction SilentlyContinue
    Remove-Job -Job $job -Force -ErrorAction SilentlyContinue
  }

  Write-Host "Stopped."
}
