# Version-specific workaround: 0.7.1 advertises --skip-check-lark-cli for
# `run`, but does not forward it into Supervisor.startProfile.
$ErrorActionPreference = 'Stop'
$taskNpmRoot = (& npm root -g).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Cannot locate global npm packages' }
$taskPackageRoot = Join-Path $taskNpmRoot 'lark-channel-bridge'
$taskVersion = (Get-Content (Join-Path $taskPackageRoot 'package.json') -Raw | ConvertFrom-Json).version
if ($taskVersion -ne '0.7.1') {
    throw "Workaround is scoped to bridge 0.7.1; inspect version $taskVersion before applying it"
}
$taskCliPath = Join-Path $taskPackageRoot 'dist/cli.js'
$taskOriginal = [IO.File]::ReadAllText($taskCliPath)
if ($taskOriginal.Contains('skipCheckLarkCli: this.opts.skipCheckLarkCli')) {
    Write-Output 'Bridge 0.7.1 preflight workaround already applied'
    exit 0
}
$taskNormalized = $taskOriginal.Replace("`r`n", "`n")
$taskOldConstructor = 'new Supervisor({ configPath, rootDir: appPaths2.rootDir })'
$taskOldPreflight = "await preFlightChecks({`n        bridgeConfig: cfg,"
if (($taskNormalized.Split($taskOldConstructor).Count - 1) -ne 2 -or
    ($taskNormalized.Split($taskOldPreflight).Count - 1) -ne 1) {
    throw 'Unexpected bridge code shape; no files changed'
}
$taskBackupDir = Join-Path $env:USERPROFILE '.lark-channel/compat'
New-Item -ItemType Directory -Path $taskBackupDir -Force | Out-Null
$taskBackupPath = Join-Path $taskBackupDir 'bridge-0.7.1-cli.original.js'
if (-not (Test-Path $taskBackupPath)) { Copy-Item -LiteralPath $taskCliPath -Destination $taskBackupPath }
$taskPatched = $taskNormalized.Replace(
    $taskOldConstructor,
    'new Supervisor({ configPath, rootDir: appPaths2.rootDir, skipCheckLarkCli: opts.skipCheckLarkCli })'
).Replace($taskOldPreflight, "await preFlightChecks({`n        skipCheckLarkCli: this.opts.skipCheckLarkCli,`n        bridgeConfig: cfg,")
[IO.File]::WriteAllText($taskCliPath, $taskPatched, [Text.UTF8Encoding]::new($false))
& node --check $taskCliPath
if ($LASTEXITCODE -ne 0) {
    [IO.File]::WriteAllText($taskCliPath, $taskOriginal, [Text.UTF8Encoding]::new($false))
    throw 'Syntax check failed; original bridge restored'
}
Write-Output 'Bridge 0.7.1 now forwards --skip-check-lark-cli; original preserved under ~/.lark-channel/compat/'
