param(
    [ValidateSet('run', 'start', 'stop', 'status', 'restart')]
    [string]$Action = 'run'
)

$ErrorActionPreference = 'Stop'
$workspace = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
if (-not (Get-Command lark-channel-bridge -ErrorAction SilentlyContinue)) {
    throw 'Install first: npm install -g lark-channel-bridge@0.7.1'
}
if (-not (Get-Command codex -ErrorAction SilentlyContinue)) {
    throw 'Codex CLI is missing from PATH. Install/login before running the bridge.'
}
if ($Action -eq 'run') {
    $taskBridgeArguments = @('run', '--profile', 'narrativeos', '--agent', 'codex', '--workspace', $workspace)
    # The existing private CLI binding is verified independently via lark.ps1.
    # Avoid the 0.7.1 Windows background preflight misdetecting it as Hermes.
    if (Test-Path (Join-Path $env:USERPROFILE '.lark-channel/profiles/narrativeos/lark-cli/lark-channel/config.json')) {
        $taskBridgeArguments += '--skip-check-lark-cli'
    }
    & lark-channel-bridge @taskBridgeArguments
} elseif ($Action -eq 'start' -and (Test-Path (Join-Path $env:USERPROFILE '.lark-channel/daemon/narrativeos/launcher.cmd'))) {
    # Reuse the registered launcher and its verified environment.
    & lark-channel-bridge restart --profile narrativeos
} else {
    & lark-channel-bridge $Action --profile narrativeos
}
exit $LASTEXITCODE
