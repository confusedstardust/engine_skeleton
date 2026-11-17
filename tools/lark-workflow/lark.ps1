param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$CliArguments
)

# Use the same private app credentials and user login as the bridge.
$ErrorActionPreference = 'Stop'
$taskLarkRoot = Join-Path $env:USERPROFILE '.lark-channel'
$taskLarkEnv = @{
    LARK_CHANNEL = '1'
    LARK_CHANNEL_HOME = $taskLarkRoot
    LARK_CHANNEL_PROFILE = 'narrativeos'
    LARK_CHANNEL_CONFIG = Join-Path $taskLarkRoot 'profiles/narrativeos/lark-cli-source/config.json'
    LARKSUITE_CLI_CONFIG_DIR = Join-Path $taskLarkRoot 'profiles/narrativeos/lark-cli'
}
$taskPreviousEnv = @{}
try {
    foreach ($taskKey in $taskLarkEnv.Keys) {
        $taskPreviousEnv[$taskKey] = [Environment]::GetEnvironmentVariable($taskKey, 'Process')
        [Environment]::SetEnvironmentVariable($taskKey, $taskLarkEnv[$taskKey], 'Process')
    }
    & lark-cli @CliArguments
    $taskExitCode = $LASTEXITCODE
} finally {
    foreach ($taskKey in $taskPreviousEnv.Keys) {
        if ($null -eq $taskPreviousEnv[$taskKey]) {
            Remove-Item -LiteralPath "Env:$taskKey" -ErrorAction SilentlyContinue
        } else {
            [Environment]::SetEnvironmentVariable($taskKey, $taskPreviousEnv[$taskKey], 'Process')
        }
    }
}
exit $taskExitCode
