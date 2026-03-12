param(
    [switch]$SkipMigrationRun,
    [switch]$DrySeed,
    [switch]$RequireCurrentHead,
    [switch]$AllowMain,
    [switch]$FailFast,
    [string]$EnvFile = ".env.staging",
    [string]$OutFile = "STAGING_GATE_REPORT.md",
    [string]$OutJsonFile = "STAGING_GATE_REPORT.json",
    [string]$ExpectedHostRegex = "",
    [string]$ExpectedDatabaseName = "",
    [ValidateSet("full", "preflight")]
    [string]$Mode = "full",
    [ValidateSet("all", "state", "sql", "upgrade1", "upgrade2", "seed")]
    [string]$ResumeFrom = "all",
    [int]$RetryCount = 2,
    [int]$RetryDelaySeconds = 3,
    [int]$StepTimeoutSeconds = 180
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path ".\scripts\verify_staging_gate.ps1")) {
    throw "Missing script: .\scripts\verify_staging_gate.ps1"
}

$args = @(
    "-ExecutionPolicy", "Bypass",
    "-File", ".\scripts\verify_staging_gate.ps1",
    "-EnvFile", $EnvFile,
    "-OutFile", $OutFile,
    "-OutJsonFile", $OutJsonFile,
    "-Mode", $Mode,
    "-ResumeFrom", $ResumeFrom,
    "-RetryCount", "$RetryCount",
    "-RetryDelaySeconds", "$RetryDelaySeconds",
    "-StepTimeoutSeconds", "$StepTimeoutSeconds"
)
if ($SkipMigrationRun) {
    $args += "-SkipMigrationRun"
}
if ($DrySeed) {
    $args += "-DrySeed"
}
if ($RequireCurrentHead) {
    $args += "-RequireCurrentHead"
}
if ($AllowMain) {
    $args += "-AllowMain"
}
if ($FailFast) {
    $args += "-FailFast"
}
if (-not [string]::IsNullOrWhiteSpace($ExpectedHostRegex)) {
    $args += @("-ExpectedHostRegex", $ExpectedHostRegex)
}
if (-not [string]::IsNullOrWhiteSpace($ExpectedDatabaseName)) {
    $args += @("-ExpectedDatabaseName", $ExpectedDatabaseName)
}

Write-Host "Running staging gate..."
& powershell @args
$exitCode = $LASTEXITCODE
Write-Host "staging gate exit=$exitCode"

if (Test-Path $OutFile) {
    Write-Host "report: $OutFile"
} else {
    Write-Host "report not found: $OutFile"
}
if (Test-Path $OutJsonFile) {
    Write-Host "report json: $OutJsonFile"
} else {
    Write-Host "report json not found: $OutJsonFile"
}

exit $exitCode
