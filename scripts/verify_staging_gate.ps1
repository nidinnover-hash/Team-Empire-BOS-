param(
    [string]$EnvFile = ".env.staging",
    [string]$OutFile = "STAGING_GATE_REPORT.md",
    [string]$OutJsonFile = "STAGING_GATE_REPORT.json",
    [ValidateSet("full", "preflight")]
    [string]$Mode = "full",
    [switch]$SkipMigrationRun,
    [switch]$DrySeed,
    [switch]$RequireCurrentHead,
    [switch]$AllowMain,
    [switch]$FailFast,
    [string]$ExpectedHostRegex = "",
    [string]$ExpectedDatabaseName = "",
    [ValidateSet("all", "state", "sql", "upgrade1", "upgrade2", "seed")]
    [string]$ResumeFrom = "all",
    [int]$RetryCount = 2,
    [int]$RetryDelaySeconds = 3,
    [int]$StepTimeoutSeconds = 180
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ExitCodes = @{
    PASS = 0
    CONNECTION = 10
    ALEMBIC_STATE = 20
    MIGRATION_FAIL = 30
    SEED_FAIL = 40
    DRIFT_DETECTED = 50
    MIGRATION_LOCKED = 60
    STEP_TIMEOUT = 70
}

$md = New-Object System.Collections.Generic.List[string]
$report = [ordered]@{
    generated_at = (Get-Date -Format o)
    config = [ordered]@{
        env_file = $EnvFile
        out_file = $OutFile
        out_json_file = $OutJsonFile
        mode = $Mode
        skip_migration_run = [bool]$SkipMigrationRun
        dry_seed = [bool]$DrySeed
        require_current_head = [bool]$RequireCurrentHead
        allow_main = [bool]$AllowMain
        fail_fast = [bool]$FailFast
        expected_host_regex = $ExpectedHostRegex
        expected_database_name = $ExpectedDatabaseName
        resume_from = $ResumeFrom
        retry_count = $RetryCount
        retry_delay_seconds = $RetryDelaySeconds
        step_timeout_seconds = $StepTimeoutSeconds
    }
    run_metadata = [ordered]@{}
    env_validation = [ordered]@{}
    target = [ordered]@{}
    checkpoints = [ordered]@{}
    phase_durations_ms = [ordered]@{}
    commands = @()
    sql_checks = $null
    drift_fingerprint = [ordered]@{}
    stop_reason_code = ""
    verdict = ""
    exit_code = -1
    reasons = @()
}

$PhaseOrder = @{
    state = 1
    sql = 2
    upgrade1 = 3
    upgrade2 = 4
    seed = 5
}
$StartPhase = $(if ($ResumeFrom -eq "all") { "state" } else { $ResumeFrom })
$StartPhaseIndex = $PhaseOrder[$StartPhase]
$script:phaseTimers = @{}

function Add-MdBlock {
    param(
        [string]$Title,
        [string]$Body
    )
    $safeBody = Sanitize-Text -Text $Body
    $md.Add("### $Title")
    $md.Add('```text')
    $md.Add(($safeBody | Out-String).Trim())
    $md.Add('```')
    $md.Add("")
}

function Sanitize-Text {
    param([string]$Text)
    if ($null -eq $Text) { return "" }
    $safe = $Text
    $safe = $safe -replace "(postgresql\+asyncpg://[^:\s]+:)[^@\s]+(@)", '$1***$2'
    $safe = $safe -replace "(postgres://[^:\s]+:)[^@\s]+(@)", '$1***$2'
    $safe = $safe -replace "([Bb]earer\s+)[A-Za-z0-9\-\._~\+\/]+=*", '$1***'
    $safe = $safe -replace "(STAGING_ORG1_PASSWORD|STAGING_ORG2_PASSWORD|STAGING_PGCONN)\s*[:=]\s*\S+", '$1=***'
    return $safe
}

function Set-CheckpointStatus {
    param(
        [string]$Name,
        [ValidateSet("pass", "fail", "skipped")]
        [string]$Status,
        [string]$Detail = ""
    )
    $report.checkpoints[$Name] = [ordered]@{
        status = $Status
        detail = $Detail
        at = (Get-Date -Format o)
    }
}

function Start-Phase {
    param([string]$Name)
    if (-not $script:phaseTimers) {
        $script:phaseTimers = @{}
    }
    $script:phaseTimers[$Name] = [System.Diagnostics.Stopwatch]::StartNew()
}

function End-Phase {
    param([string]$Name)
    if ($script:phaseTimers -and $script:phaseTimers.ContainsKey($Name)) {
        $sw = $script:phaseTimers[$Name]
        $sw.Stop()
        $report.phase_durations_ms[$Name] = [int64]$sw.ElapsedMilliseconds
        $script:phaseTimers.Remove($Name) | Out-Null
    }
}

function Mask-ConnectionString {
    param([string]$Value)
    if ([string]::IsNullOrWhiteSpace($Value)) {
        return "<empty>"
    }
    return ($Value -replace "(postgresql\+asyncpg://[^:]+:)[^@]+(@.*)", '$1***$2')
}

function Load-EnvFile {
    param([string]$Path)
    if (-not (Test-Path $Path)) {
        throw "Env file not found: $Path"
    }
    Get-Content -Path $Path | ForEach-Object {
        $line = $_.Trim()
        if ($line.Length -eq 0 -or $line.StartsWith("#")) { return }
        $parts = $line.Split("=", 2)
        if ($parts.Count -ne 2) { return }
        $key = $parts[0].Trim()
        $value = $parts[1].Trim()
        if ($value.StartsWith('"') -and $value.EndsWith('"')) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        if ($value.StartsWith("'") -and $value.EndsWith("'")) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        [Environment]::SetEnvironmentVariable($key, $value, "Process")
    }
}

function Validate-StagingPgConn {
    param([string]$Value)
    $errors = @()
    $warnings = @()
    if ([string]::IsNullOrWhiteSpace($Value)) {
        $errors += "STAGING_PGCONN is missing."
        return [PSCustomObject]@{ errors = $errors; warnings = $warnings }
    }
    if ($Value.Contains("<") -or $Value.Contains(">")) {
        $errors += "STAGING_PGCONN contains placeholder markers '<' or '>'."
    }
    if ($Value -match "postgresql\+asyncpg://[^:]+:\[[^\]]+\]@") {
        $errors += "Password appears wrapped in [] which breaks auth parsing."
    }
    if (-not ($Value -like "postgresql+asyncpg://*")) {
        $errors += "STAGING_PGCONN must start with postgresql+asyncpg://"
    }
    if (-not ($Value -match "\?ssl=require($|&)" -or $Value -match "\?sslmode=require($|&)")) {
        $warnings += "No explicit SSL query option found (ssl=require or sslmode=require)."
    }
    return [PSCustomObject]@{ errors = $errors; warnings = $warnings }
}

function Invoke-ExternalCommand {
    param(
        [string]$Label,
        [string]$Exe,
        [string[]]$ArgList
    )
    $output = ""
    $exitCode = 1
    try {
        $psi = New-Object System.Diagnostics.ProcessStartInfo
        $psi.FileName = $Exe
        $psi.UseShellExecute = $false
        $psi.RedirectStandardOutput = $true
        $psi.RedirectStandardError = $true
        $quotedArgs = @()
        foreach ($arg in $ArgList) {
            if ($arg -match '\s|"') {
                $escaped = $arg.Replace('"', '\"')
                $quotedArgs += '"' + $escaped + '"'
            }
            else {
                $quotedArgs += $arg
            }
        }
        $psi.Arguments = ($quotedArgs -join " ")

        $p = New-Object System.Diagnostics.Process
        $p.StartInfo = $psi
        [void]$p.Start()
        $finished = $p.WaitForExit($StepTimeoutSeconds * 1000)
        if (-not $finished) {
            try { $p.Kill() } catch {}
            $output = "Step timeout after $StepTimeoutSeconds seconds."
            $exitCode = $ExitCodes.STEP_TIMEOUT
        }
        else {
            $stdout = $p.StandardOutput.ReadToEnd()
            $stderr = $p.StandardError.ReadToEnd()
            $output = (@($stdout, $stderr) -join [Environment]::NewLine).Trim()
            $exitCode = [int]$p.ExitCode
        }
        $p.Dispose()
    }
    catch {
        $output = $_.Exception.Message
        $exitCode = 1
    }
    $result = [PSCustomObject]@{
        label = $Label
        command = "$Exe $($ArgList -join ' ')"
        exit_code = $exitCode
        output = (Sanitize-Text -Text $output)
    }
    $script:report.commands += $result
    Add-MdBlock -Title "$Label (exit=$exitCode)" -Body $output
    return $result
}

function Invoke-ExternalCommandRetriable {
    param(
        [string]$Label,
        [string]$Exe,
        [string[]]$ArgList
    )
    $attempt = 1
    $maxAttempts = 1 + [Math]::Max(0, $RetryCount)
    while ($attempt -le $maxAttempts) {
        $attemptLabel = "$Label (attempt $attempt/$maxAttempts)"
        $result = Invoke-ExternalCommand -Label $attemptLabel -Exe $Exe -ArgList $ArgList
        if ($result.exit_code -eq 0) {
            return $result
        }
        if ($attempt -lt $maxAttempts -and (Is-TransientErrorText -Text $result.output)) {
            $md.Add("Retrying '$Label' after transient failure ($RetryDelaySeconds s delay).")
            $md.Add("")
            Start-Sleep -Seconds $RetryDelaySeconds
            $attempt += 1
            continue
        }
        return $result
    }
    return $result
}

function Invoke-PythonHereScript {
    param(
        [string]$Label,
        [string]$Script
    )
    $tmp = New-TemporaryFile
    try {
        Set-Content -Path $tmp -Value $Script -Encoding UTF8
        return Invoke-ExternalCommand -Label $Label -Exe ".\.venv\Scripts\python.exe" -ArgList @($tmp)
    }
    finally {
        Remove-Item -Path $tmp -Force -ErrorAction SilentlyContinue
    }
}

function Invoke-PythonHereScriptRetriable {
    param(
        [string]$Label,
        [string]$Script
    )
    $attempt = 1
    $maxAttempts = 1 + [Math]::Max(0, $RetryCount)
    while ($attempt -le $maxAttempts) {
        $attemptLabel = "$Label (attempt $attempt/$maxAttempts)"
        $result = Invoke-PythonHereScript -Label $attemptLabel -Script $Script
        if ($result.exit_code -eq 0) {
            return $result
        }
        if ($attempt -lt $maxAttempts -and (Is-TransientErrorText -Text $result.output)) {
            $md.Add("Retrying '$Label' after transient failure ($RetryDelaySeconds s delay).")
            $md.Add("")
            Start-Sleep -Seconds $RetryDelaySeconds
            $attempt += 1
            continue
        }
        return $result
    }
    return $result
}

function Write-Reports {
    $md -join "`n" | Set-Content -Path $OutFile -Encoding UTF8
    ($report | ConvertTo-Json -Depth 20) | Set-Content -Path $OutJsonFile -Encoding UTF8
}

function Finalize-AndExit {
    param(
        [int]$Code,
        [string]$Verdict,
        [string]$Reason,
        [string]$ReasonCode = "GENERAL"
    )
    $report.verdict = $Verdict
    $report.exit_code = $Code
    $report.stop_reason_code = $ReasonCode
    $report.reasons += $Reason
    $md.Add("## Final Verdict")
    $md.Add("$Verdict")
    $md.Add("")
    $md.Add("Reason: $Reason")
    $md.Add("Reason code: $ReasonCode")
    $md.Add("")
    $md.Add("## Checkpoints")
    foreach ($cp in $report.checkpoints.GetEnumerator()) {
        $md.Add("- $($cp.Key): $($cp.Value.status) ($($cp.Value.detail))")
    }
    $md.Add("")
    $md.Add("## Phase Durations (ms)")
    foreach ($pd in $report.phase_durations_ms.GetEnumerator()) {
        $md.Add("- $($pd.Key): $($pd.Value)")
    }
    $md.Add("")
    $md.Add("Exit code: $Code")
    $md.Add("")
    $md.Add("## One Command")
    $md.Add('powershell -ExecutionPolicy Bypass -File .\scripts\verify_staging_gate.ps1')
    $md.Add("")
    $md.Add("## Pass/Fail Criteria")
    $md.Add("- PASS: current=heads aligned, upgrade #1 exit=0, upgrade #2 exit=0, seed exit=0.")
    $md.Add("- FAIL: any non-zero exit, duplicate object errors, or missing critical objects in A-F.")
    $md.Add("- STOP: connection/auth errors, missing alembic_version, or drift indicators.")
    $md.Add("")
    $md.Add("## Stop Reason Codes")
    $md.Add("- CONN_AUTH: connection/auth/SSL failure")
    $md.Add("- DNS_FAIL: hostname resolution failure")
    $md.Add("- ENV_INVALID: malformed or placeholder env values")
    $md.Add("- TARGET_GUARD: host/db guard mismatch")
    $md.Add("- ALEMBIC_STATE: current/heads mismatch or state command failure")
    $md.Add("- ALEMBIC_DRIFT: schema drift indicators detected")
    $md.Add("- STEP_TIMEOUT: command exceeded timeout")
    $md.Add("- MIGRATION_LOCK: concurrent migration lock held")
    $md.Add("- MIGRATION_FAIL: upgrade failure")
    $md.Add("- SEED_FAIL: seeding failure")
    $md.Add("- PREFLIGHT_FAIL: preflight checks failed")
    Write-Reports
    Write-Host "Wrote $OutFile"
    Write-Host "Wrote $OutJsonFile"
    exit $Code
}

function Get-TargetInfo {
    $script = @'
import json, os
from sqlalchemy.engine.url import make_url
u = make_url(os.environ["DATABASE_URL"])
print(json.dumps({
  "driver": u.drivername,
  "host": u.host,
  "port": u.port,
  "database": u.database,
  "username": u.username
}))
'@
    $res = Invoke-PythonHereScript -Label "parse DATABASE_URL target" -Script $script
    if ($res.exit_code -ne 0) {
        return $null
    }
    try {
        return ($res.output | ConvertFrom-Json)
    }
    catch {
        return $null
    }
}

function Test-DnsResolution {
    param([string]$HostName)
    if ([string]::IsNullOrWhiteSpace($HostName)) {
        return [PSCustomObject]@{ ok = $false; output = "Host is empty." }
    }
    $result = Invoke-ExternalCommandRetriable -Label "dns resolve host" -Exe "nslookup" -ArgList @($HostName)
    $ok = ($result.exit_code -eq 0) -and ($result.output -match "Address|Addresses") -and -not ($result.output -match "timed out|\*\*\* Request")
    return [PSCustomObject]@{
        ok = $ok
        output = $result.output
        exit_code = $result.exit_code
    }
}

function Test-MigrationLockAvailability {
    $lockScript = @'
import asyncio, json, os
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
LOCK_KEY = 93746123
async def main():
    engine = create_async_engine(os.environ["DATABASE_URL"])
    async with engine.connect() as conn:
        row = (await conn.execute(text("SELECT pg_try_advisory_lock(:k) AS acquired"), {"k": LOCK_KEY})).mappings().first()
        acquired = bool(row["acquired"])
        if acquired:
            await conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": LOCK_KEY})
        print(json.dumps({"acquired": acquired}))
    await engine.dispose()
asyncio.run(main())
'@
    $res = Invoke-PythonHereScriptRetriable -Label "migration advisory lock check" -Script $lockScript
    if ($res.exit_code -ne 0) {
        return [PSCustomObject]@{ ok = $false; output = $res.output; acquired = $false; exit_code = $res.exit_code }
    }
    try {
        $obj = $res.output | ConvertFrom-Json
        return [PSCustomObject]@{ ok = [bool]$obj.acquired; output = $res.output; acquired = [bool]$obj.acquired; exit_code = 0 }
    }
    catch {
        return [PSCustomObject]@{ ok = $false; output = $res.output; acquired = $false; exit_code = 1 }
    }
}

function Test-DrySeedPrerequisites {
    $drySeedScript = @'
import asyncio, json, os
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
required = [
  "STAGING_ORG1_EMAIL","STAGING_ORG1_PASSWORD","STAGING_ORG1_ID",
  "STAGING_ORG2_EMAIL","STAGING_ORG2_PASSWORD","STAGING_ORG2_ID"
]
missing = [k for k in required if not (os.getenv(k) or "").strip()]
async def main():
    engine = create_async_engine(os.environ["DATABASE_URL"])
    async with engine.connect() as conn:
        rows = (await conn.execute(text("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema='public' AND table_name IN ('users','organizations')
            ORDER BY table_name
        """))).mappings().all()
    await engine.dispose()
    print(json.dumps({"missing_env": missing, "tables": [r["table_name"] for r in rows]}))
asyncio.run(main())
'@
    $res = Invoke-PythonHereScriptRetriable -Label "dry-seed prerequisites" -Script $drySeedScript
    if ($res.exit_code -ne 0) {
        return [PSCustomObject]@{ ok = $false; output = $res.output; exit_code = $res.exit_code }
    }
    try {
        $obj = $res.output | ConvertFrom-Json
        $missing = @($obj.missing_env).Count
        $tables = @($obj.tables)
        $ok = ($missing -eq 0) -and ($tables -contains "users") -and ($tables -contains "organizations")
        return [PSCustomObject]@{ ok = $ok; output = $res.output; exit_code = 0 }
    }
    catch {
        return [PSCustomObject]@{ ok = $false; output = $res.output; exit_code = 1 }
    }
}

function Test-PostUpgradeSchemaSanity {
    $sanityScript = @'
import asyncio, json, os
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

expected_tables = [
    "deals",
    "organization_memberships",
    "organization_role_permissions",
    "audit_logs",
]
expected_indexes = [
    "ix_organization_memberships_organization_id",
    "ix_organization_memberships_user_id",
    "ix_organization_role_permissions_organization_id",
    "ix_organization_role_permissions_permission",
]

async def main():
    engine = create_async_engine(os.environ["DATABASE_URL"])
    out = {"tables": {}, "indexes": {}}
    async with engine.connect() as conn:
        for t in expected_tables:
            row = (await conn.execute(text("""
                SELECT COUNT(*) AS cnt FROM information_schema.tables
                WHERE table_schema='public' AND table_name=:t
            """), {"t": t})).mappings().first()
            out["tables"][t] = int(row["cnt"]) > 0
        for i in expected_indexes:
            row = (await conn.execute(text("""
                SELECT COUNT(*) AS cnt FROM pg_indexes
                WHERE schemaname='public' AND indexname=:i
            """), {"i": i})).mappings().first()
            out["indexes"][i] = int(row["cnt"]) > 0
    await engine.dispose()
    out["ok"] = all(out["tables"].values()) and all(out["indexes"].values())
    print(json.dumps(out))

asyncio.run(main())
'@
    $res = Invoke-PythonHereScriptRetriable -Label "post-upgrade schema sanity" -Script $sanityScript
    if ($res.exit_code -ne 0) {
        return [PSCustomObject]@{ ok = $false; output = $res.output; exit_code = $res.exit_code }
    }
    try {
        $obj = $res.output | ConvertFrom-Json
        return [PSCustomObject]@{ ok = [bool]$obj.ok; output = $res.output; exit_code = 0 }
    }
    catch {
        return [PSCustomObject]@{ ok = $false; output = $res.output; exit_code = 1 }
    }
}

function Is-ConnectionLikeError {
    param([string]$Text)
    return ($Text -match "SASL authentication failed|getaddrinfo failed|Access is denied|Name or service not known|connection refused|ssl|ECONN|could not connect|authentication failed|Timeout expired|Step timeout")
}

function Is-DriftLikeError {
    param([string]$Text)
    return ($Text -match "relation `"alembic_version`" does not exist|relation `"deals`" does not exist|UndefinedTableError")
}

function Is-TransientErrorText {
    param([string]$Text)
    return ($Text -match "getaddrinfo failed|Temporary failure|timed out|connection reset|network is unreachable|server closed the connection unexpectedly|could not connect|Step timeout")
}

function Get-ReasonCodeFromText {
    param(
        [string]$Text,
        [string]$Default
    )
    if ($Text -match "getaddrinfo failed|Name or service not known|Temporary failure") { return "DNS_FAIL" }
    if ($Text -match "SASL authentication failed|authentication failed|ssl|certificate") { return "CONN_AUTH" }
    if ($Text -match "Step timeout|timed out|Timeout expired") { return "STEP_TIMEOUT" }
    if (Is-DriftLikeError -Text $Text) { return "ALEMBIC_DRIFT" }
    if (Is-ConnectionLikeError -Text $Text) { return "CONN_AUTH" }
    return $Default
}

function Resolve-StageExitCode {
    param(
        [object]$Result,
        [int]$DefaultExitCode
    )
    if ($null -ne $Result -and $Result.exit_code -eq $ExitCodes.STEP_TIMEOUT) {
        return $ExitCodes.STEP_TIMEOUT
    }
    return $DefaultExitCode
}

function Should-RunPhase {
    param([string]$PhaseName)
    return ($PhaseOrder[$PhaseName] -ge $StartPhaseIndex)
}

function Get-RunMetadata {
    $branch = ""
    $commit = ""
    try {
        $branch = (& git rev-parse --abbrev-ref HEAD 2>$null).Trim()
    }
    catch {
        $branch = ""
    }
    try {
        $commit = (& git rev-parse HEAD 2>$null).Trim()
    }
    catch {
        $commit = ""
    }
    return [ordered]@{
        git_branch = $branch
        git_commit = $commit
        host_name = $env:COMPUTERNAME
        resume_from = $ResumeFrom
        start_phase = $StartPhase
    }
}

function Add-DriftFingerprint {
    param(
        [string]$CurrentRevision,
        [string]$HeadRevision,
        [bool]$StateAligned
    )
    $alembicRows = -1
    $dealsPresent = $false
    $dirtyTablesCount = -1
    $dirtyIndexesCount = -1
    $dirtyConstraintsCount = -1
    $expectedIndexesCount = -1
    if ($null -ne $report.sql_checks) {
        try { $alembicRows = [int](@($report.sql_checks.A_alembic_row_count)[0].alembic_rows) } catch {}
        try { $dealsPresent = (@($report.sql_checks.G_deals_exists).Count -gt 0) } catch {}
        try { $dirtyTablesCount = @($report.sql_checks.C_dirty_tables).Count } catch {}
        try { $dirtyIndexesCount = @($report.sql_checks.D_dirty_indexes).Count } catch {}
        try { $dirtyConstraintsCount = @($report.sql_checks.E_dirty_constraints).Count } catch {}
        try { $expectedIndexesCount = @($report.sql_checks.F_expected_indexes).Count } catch {}
    }
    $fp = [ordered]@{
        current_revision = $CurrentRevision
        head_revision = $HeadRevision
        state_aligned = $StateAligned
        alembic_row_count = $alembicRows
        deals_present = $dealsPresent
        dirty_tables_count = $dirtyTablesCount
        dirty_indexes_count = $dirtyIndexesCount
        dirty_constraints_count = $dirtyConstraintsCount
        expected_indexes_count = $expectedIndexesCount
    }
    $payload = ($fp | ConvertTo-Json -Compress)
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        $hashBytes = $sha.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($payload))
    }
    finally {
        $sha.Dispose()
    }
    $hash = ([BitConverter]::ToString($hashBytes) -replace "-", "").ToLowerInvariant()
    $fp["fingerprint_sha256"] = $hash
    $report.drift_fingerprint = $fp
    $md.Add("## Drift Fingerprint")
    foreach ($k in $fp.Keys) {
        $md.Add("- ${k}: $($fp[$k])")
    }
    $md.Add("")
}

# Header
$md.Add("# Staging Gate Verification Report")
$md.Add("")
$md.Add("Generated: $($report.generated_at)")
$md.Add("")

$report.run_metadata = Get-RunMetadata
$md.Add("## Run Metadata Lock")
$md.Add("- git branch: $($report.run_metadata.git_branch)")
$md.Add("- git commit: $($report.run_metadata.git_commit)")
$md.Add("- host: $($report.run_metadata.host_name)")
$md.Add("- resume from: $($report.run_metadata.resume_from)")
$md.Add("")

if ($Mode -eq "full" -and $report.run_metadata.git_branch -eq "main" -and -not $AllowMain) {
    Set-CheckpointStatus -Name "branch_guard" -Status "fail" -Detail "Full gate blocked on main branch."
    Finalize-AndExit -Code $ExitCodes.CONNECTION -Verdict "STOP" -Reason "Refusing full gate run on main branch without -AllowMain." -ReasonCode "TARGET_GUARD"
}
Set-CheckpointStatus -Name "branch_guard" -Status "pass" -Detail "Branch guard passed."

Start-Phase -Name "env_validation"
Load-EnvFile -Path $EnvFile
$pgConn = $env:STAGING_PGCONN
$validation = Validate-StagingPgConn -Value $pgConn
$report.env_validation = [ordered]@{
    masked_staging_pgconn = (Mask-ConnectionString -Value $pgConn)
    errors = @($validation.errors)
    warnings = @($validation.warnings)
}

$md.Add("## Environment Validation")
$md.Add("- Env file: $EnvFile")
$md.Add("- STAGING_PGCONN (masked): $(Mask-ConnectionString -Value $pgConn)")
$md.Add("- Errors: $(@($validation.errors).Count)")
foreach ($e in @($validation.errors)) { $md.Add("  - $e") }
$md.Add("- Warnings: $(@($validation.warnings).Count)")
foreach ($w in @($validation.warnings)) { $md.Add("  - $w") }
$md.Add("")

if (@($validation.errors).Count -gt 0) {
    Set-CheckpointStatus -Name "env_validation" -Status "fail" -Detail "Invalid STAGING_PGCONN format."
    End-Phase -Name "env_validation"
    Finalize-AndExit -Code $ExitCodes.CONNECTION -Verdict "STOP" -Reason "Invalid STAGING_PGCONN format." -ReasonCode "ENV_INVALID"
}
Set-CheckpointStatus -Name "env_validation" -Status "pass" -Detail "Environment values loaded and validated."
End-Phase -Name "env_validation"

Start-Phase -Name "target_parse"
$env:DATABASE_URL = $pgConn

$target = Get-TargetInfo
if ($null -eq $target) {
    Set-CheckpointStatus -Name "target_parse" -Status "fail" -Detail "Failed to parse DATABASE_URL target."
    End-Phase -Name "target_parse"
    Finalize-AndExit -Code $ExitCodes.CONNECTION -Verdict "STOP" -Reason "Failed to parse DATABASE_URL target." -ReasonCode "ENV_INVALID"
}
$report.target = $target
Set-CheckpointStatus -Name "target_parse" -Status "pass" -Detail "DATABASE_URL parsed successfully."
End-Phase -Name "target_parse"
$md.Add("## Target Guard")
$md.Add("- host: $($target.host)")
$md.Add("- port: $($target.port)")
$md.Add("- database: $($target.database)")
$md.Add("- driver: $($target.driver)")
$md.Add("")

Start-Phase -Name "target_guard"
if ($target.host -match "(?i)prod|production") {
    Set-CheckpointStatus -Name "target_guard" -Status "fail" -Detail "Target host appears production-like."
    End-Phase -Name "target_guard"
    Finalize-AndExit -Code $ExitCodes.CONNECTION -Verdict "STOP" -Reason "Target host appears production-like." -ReasonCode "TARGET_GUARD"
}
if (-not [string]::IsNullOrWhiteSpace($ExpectedHostRegex) -and -not ($target.host -match $ExpectedHostRegex)) {
    Set-CheckpointStatus -Name "target_guard" -Status "fail" -Detail "Host does not match ExpectedHostRegex."
    End-Phase -Name "target_guard"
    Finalize-AndExit -Code $ExitCodes.CONNECTION -Verdict "STOP" -Reason "Target host does not match ExpectedHostRegex." -ReasonCode "TARGET_GUARD"
}
if (-not [string]::IsNullOrWhiteSpace($ExpectedDatabaseName) -and ($target.database -ne $ExpectedDatabaseName)) {
    Set-CheckpointStatus -Name "target_guard" -Status "fail" -Detail "Database does not match ExpectedDatabaseName."
    End-Phase -Name "target_guard"
    Finalize-AndExit -Code $ExitCodes.CONNECTION -Verdict "STOP" -Reason "Target database does not match ExpectedDatabaseName." -ReasonCode "TARGET_GUARD"
}
Set-CheckpointStatus -Name "target_guard" -Status "pass" -Detail "Target host/database guard checks passed."
End-Phase -Name "target_guard"

Start-Phase -Name "dns_check"
$dns = Test-DnsResolution -HostName $target.host
if (-not $dns.ok) {
    Set-CheckpointStatus -Name "dns_check" -Status "fail" -Detail "DNS lookup failed."
    End-Phase -Name "dns_check"
    Finalize-AndExit -Code $ExitCodes.CONNECTION -Verdict "STOP" -Reason "DNS lookup failed for target host." -ReasonCode "DNS_FAIL"
}
Set-CheckpointStatus -Name "dns_check" -Status "pass" -Detail "DNS resolved target host."
End-Phase -Name "dns_check"

$current = $null
$heads = $null
$stateAligned = $true
$currentRevision = ""
$headRevision = ""
$ranStatePhase = $false
$ranSqlPhase = $false

if (Should-RunPhase -PhaseName "state") {
    Start-Phase -Name "state_check"
    $ranStatePhase = $true
    $current = Invoke-ExternalCommandRetriable -Label "alembic current" -Exe ".\.venv\Scripts\python.exe" -ArgList @("-m", "alembic", "current")
    if ($FailFast -and $current.exit_code -ne 0) {
        $baseCode = $(if (Is-ConnectionLikeError $current.output) { $ExitCodes.CONNECTION } else { $ExitCodes.ALEMBIC_STATE })
        $code = Resolve-StageExitCode -Result $current -DefaultExitCode $baseCode
        Add-DriftFingerprint -CurrentRevision $currentRevision -HeadRevision $headRevision -StateAligned $false
        Set-CheckpointStatus -Name "state_check" -Status "fail" -Detail "alembic current failed."
        $reasonCode = Get-ReasonCodeFromText -Text $current.output -Default "ALEMBIC_STATE"
        End-Phase -Name "state_check"
        Finalize-AndExit -Code $code -Verdict "STOP" -Reason "alembic current failed in fail-fast mode." -ReasonCode $reasonCode
    }

    $heads = Invoke-ExternalCommandRetriable -Label "alembic heads" -Exe ".\.venv\Scripts\python.exe" -ArgList @("-m", "alembic", "heads")
    if ($FailFast -and $heads.exit_code -ne 0) {
        $baseCode = $(if (Is-ConnectionLikeError $heads.output) { $ExitCodes.CONNECTION } else { $ExitCodes.ALEMBIC_STATE })
        $code = Resolve-StageExitCode -Result $heads -DefaultExitCode $baseCode
        Add-DriftFingerprint -CurrentRevision $currentRevision -HeadRevision $headRevision -StateAligned $false
        Set-CheckpointStatus -Name "state_check" -Status "fail" -Detail "alembic heads failed."
        $reasonCode = Get-ReasonCodeFromText -Text $heads.output -Default "ALEMBIC_STATE"
        End-Phase -Name "state_check"
        Finalize-AndExit -Code $code -Verdict "STOP" -Reason "alembic heads failed in fail-fast mode." -ReasonCode $reasonCode
    }

    if ($current.output -match "([0-9A-Za-z_]+)\s+\(head\)") { $currentRevision = $Matches[1] }
    if ($heads.output -match "([0-9A-Za-z_]+)\s+\(head\)") { $headRevision = $Matches[1] }
    $stateAligned = ($current.exit_code -eq 0) -and ($heads.exit_code -eq 0) -and ($currentRevision -ne "") -and ($currentRevision -eq $headRevision)

    $md.Add("## Alembic State")
    $md.Add("- current exit: $($current.exit_code)")
    $md.Add("- heads exit: $($heads.exit_code)")
    $md.Add("- current revision: $currentRevision")
    $md.Add("- heads revision: $headRevision")
    $md.Add("- aligned current=heads: $stateAligned")
    $md.Add("")
    if ($stateAligned) {
        Set-CheckpointStatus -Name "state_check" -Status "pass" -Detail "alembic current and heads aligned."
    }
    else {
        Set-CheckpointStatus -Name "state_check" -Status "fail" -Detail "alembic current and heads not aligned."
    }
    if ($RequireCurrentHead -and [string]::IsNullOrWhiteSpace($currentRevision)) {
        Set-CheckpointStatus -Name "state_check" -Status "fail" -Detail "RequireCurrentHead enabled and current revision is empty."
        End-Phase -Name "state_check"
        Add-DriftFingerprint -CurrentRevision $currentRevision -HeadRevision $headRevision -StateAligned $false
        Finalize-AndExit -Code $ExitCodes.ALEMBIC_STATE -Verdict "STOP" -Reason "alembic current did not return a head revision under -RequireCurrentHead." -ReasonCode "ALEMBIC_STATE"
    }
    End-Phase -Name "state_check"
}
else {
    $md.Add("## Alembic State")
    $md.Add("- skipped (resume_from=$ResumeFrom)")
    $md.Add("")
    Set-CheckpointStatus -Name "state_check" -Status "skipped" -Detail "Skipped by resume_from."
}

if ($Mode -eq "preflight") {
    Set-CheckpointStatus -Name "sql_checks" -Status "skipped" -Detail "Preflight mode."
    Set-CheckpointStatus -Name "migration_lock" -Status "skipped" -Detail "Preflight mode."
    Set-CheckpointStatus -Name "upgrade1" -Status "skipped" -Detail "Preflight mode."
    Set-CheckpointStatus -Name "upgrade2" -Status "skipped" -Detail "Preflight mode."
    Set-CheckpointStatus -Name "seed" -Status "skipped" -Detail "Preflight mode."
    Set-CheckpointStatus -Name "schema_sanity" -Status "skipped" -Detail "Preflight mode."
    if (-not $stateAligned) {
        Add-DriftFingerprint -CurrentRevision $currentRevision -HeadRevision $headRevision -StateAligned $stateAligned
        Finalize-AndExit -Code $ExitCodes.ALEMBIC_STATE -Verdict "STOP" -Reason "Preflight failed: alembic state is not aligned." -ReasonCode "PREFLIGHT_FAIL"
    }
    Add-DriftFingerprint -CurrentRevision $currentRevision -HeadRevision $headRevision -StateAligned $stateAligned
    Finalize-AndExit -Code $ExitCodes.PASS -Verdict "PREFLIGHT PASS" -Reason "DNS + target + alembic state checks passed." -ReasonCode "GENERAL"
}

$sqlChecksScript = @'
import asyncio, json, os
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

queries = {
  "A_alembic_row_count": "SELECT COUNT(*) AS alembic_rows FROM alembic_version;",
  "B_alembic_revision": "SELECT version_num AS current_revision FROM alembic_version;",
  "C_dirty_tables": """
    SELECT table_name FROM information_schema.tables
    WHERE table_schema='public' AND table_name IN
    ('chat_messages','scheduler_job_runs','organization_memberships','organization_role_permissions')
    ORDER BY table_name;
  """,
  "D_dirty_indexes": """
    SELECT tablename, indexname FROM pg_indexes
    WHERE schemaname='public' AND tablename IN
    ('chat_messages','scheduler_job_runs','organization_memberships','organization_role_permissions')
    ORDER BY tablename, indexname;
  """,
  "E_dirty_constraints": """
    SELECT t.relname AS table_name, c.conname AS constraint_name, c.contype
    FROM pg_constraint c
    JOIN pg_class t ON t.oid = c.conrelid
    JOIN pg_namespace n ON n.oid = t.relnamespace
    WHERE n.nspname='public'
      AND t.relname IN ('chat_messages','scheduler_job_runs','organization_memberships','organization_role_permissions')
    ORDER BY t.relname, c.conname;
  """,
  "F_expected_indexes": """
    SELECT indexname, tablename FROM pg_indexes
    WHERE schemaname='public' AND indexname IN (
      'ix_chat_messages_organization_id','ix_chat_messages_created_at','ix_chat_messages_org_created',
      'ix_scheduler_job_runs_org_id','ix_scheduler_job_runs_job_name','ix_scheduler_job_runs_status',
      'ix_scheduler_job_runs_started_at','ix_scheduler_job_runs_finished_at','ix_scheduler_job_runs_org_job_started',
      'ix_organization_memberships_organization_id','ix_organization_memberships_user_id',
      'ix_organization_role_permissions_organization_id','ix_organization_role_permissions_permission','ix_organization_role_permissions_role'
    ) ORDER BY indexname;
  """,
  "G_deals_exists": """
    SELECT table_name FROM information_schema.tables
    WHERE table_schema='public' AND table_name='deals';
  """
}

async def main():
    out = {}
    engine = create_async_engine(os.environ["DATABASE_URL"])
    async with engine.connect() as conn:
        for k, q in queries.items():
            rows = (await conn.execute(text(q))).mappings().all()
            out[k] = [dict(r) for r in rows]
    await engine.dispose()
    print(json.dumps(out))

asyncio.run(main())
'@

$sqlChecks = $null
if (Should-RunPhase -PhaseName "sql") {
    Start-Phase -Name "sql_checks"
    $ranSqlPhase = $true
    $sqlChecks = Invoke-PythonHereScriptRetriable -Label "SQL checks A-F" -Script $sqlChecksScript
    if ($sqlChecks.exit_code -eq 0) {
        try { $report.sql_checks = ($sqlChecks.output | ConvertFrom-Json) } catch { $report.sql_checks = $null }
    }

    if ($FailFast -and $sqlChecks.exit_code -ne 0) {
        $baseCode = $(if (Is-DriftLikeError $sqlChecks.output) { $ExitCodes.DRIFT_DETECTED } elseif (Is-ConnectionLikeError $sqlChecks.output) { $ExitCodes.CONNECTION } else { $ExitCodes.ALEMBIC_STATE })
        $code = Resolve-StageExitCode -Result $sqlChecks -DefaultExitCode $baseCode
        Add-DriftFingerprint -CurrentRevision $currentRevision -HeadRevision $headRevision -StateAligned $stateAligned
        Set-CheckpointStatus -Name "sql_checks" -Status "fail" -Detail "SQL checks failed."
        $reasonCode = Get-ReasonCodeFromText -Text $sqlChecks.output -Default "ALEMBIC_STATE"
        End-Phase -Name "sql_checks"
        Finalize-AndExit -Code $code -Verdict "STOP" -Reason "SQL checks failed in fail-fast mode." -ReasonCode $reasonCode
    }

    if ($ranStatePhase -and -not $stateAligned) {
        Add-DriftFingerprint -CurrentRevision $currentRevision -HeadRevision $headRevision -StateAligned $stateAligned
        Set-CheckpointStatus -Name "sql_checks" -Status "fail" -Detail "State not aligned."
        End-Phase -Name "sql_checks"
        Finalize-AndExit -Code $ExitCodes.ALEMBIC_STATE -Verdict "MANUAL RECONCILIATION REQUIRED" -Reason "alembic current/heads not aligned." -ReasonCode "ALEMBIC_STATE"
    }
    if ($sqlChecks.exit_code -ne 0) {
        $baseCode = $(if (Is-DriftLikeError $sqlChecks.output) { $ExitCodes.DRIFT_DETECTED } elseif (Is-ConnectionLikeError $sqlChecks.output) { $ExitCodes.CONNECTION } else { $ExitCodes.ALEMBIC_STATE })
        $code = Resolve-StageExitCode -Result $sqlChecks -DefaultExitCode $baseCode
        Add-DriftFingerprint -CurrentRevision $currentRevision -HeadRevision $headRevision -StateAligned $stateAligned
        Set-CheckpointStatus -Name "sql_checks" -Status "fail" -Detail "SQL checks command failed."
        $reasonCode = Get-ReasonCodeFromText -Text $sqlChecks.output -Default "ALEMBIC_STATE"
        End-Phase -Name "sql_checks"
        Finalize-AndExit -Code $code -Verdict "MANUAL RECONCILIATION REQUIRED" -Reason "SQL checks failed." -ReasonCode $reasonCode
    }
    if ($null -ne $report.sql_checks) {
        $rowCount = @($report.sql_checks.A_alembic_row_count)[0].alembic_rows
        $dealsCount = @($report.sql_checks.G_deals_exists).Count
        if ($rowCount -ne 1 -or $dealsCount -eq 0) {
            Add-DriftFingerprint -CurrentRevision $currentRevision -HeadRevision $headRevision -StateAligned $stateAligned
            Set-CheckpointStatus -Name "sql_checks" -Status "fail" -Detail "Schema drift detected."
            End-Phase -Name "sql_checks"
            Finalize-AndExit -Code $ExitCodes.DRIFT_DETECTED -Verdict "STOP" -Reason "Schema drift detected (alembic row count != 1 or deals missing)." -ReasonCode "ALEMBIC_DRIFT"
        }
    }
    Set-CheckpointStatus -Name "sql_checks" -Status "pass" -Detail "SQL checks passed."
    End-Phase -Name "sql_checks"
}
else {
    $md.Add("## SQL Checks")
    $md.Add("- skipped (resume_from=$ResumeFrom)")
    $md.Add("")
    Set-CheckpointStatus -Name "sql_checks" -Status "skipped" -Detail "Skipped by resume_from."
}

if ($ranStatePhase -or $ranSqlPhase) {
    Add-DriftFingerprint -CurrentRevision $currentRevision -HeadRevision $headRevision -StateAligned $stateAligned
}

if ($SkipMigrationRun) {
    Set-CheckpointStatus -Name "migration_lock" -Status "skipped" -Detail "SkipMigrationRun enabled."
    Set-CheckpointStatus -Name "upgrade1" -Status "skipped" -Detail "SkipMigrationRun enabled."
    Set-CheckpointStatus -Name "upgrade2" -Status "skipped" -Detail "SkipMigrationRun enabled."
    Set-CheckpointStatus -Name "seed" -Status "skipped" -Detail "SkipMigrationRun enabled."
    Set-CheckpointStatus -Name "schema_sanity" -Status "skipped" -Detail "SkipMigrationRun enabled."
    Finalize-AndExit -Code $ExitCodes.PASS -Verdict "STATE-ONLY PASS" -Reason "current=heads aligned and SQL checks passed." -ReasonCode "GENERAL"
}

if ((Should-RunPhase -PhaseName "upgrade1") -or (Should-RunPhase -PhaseName "upgrade2")) {
    Start-Phase -Name "migration_lock"
    $lockCheck = Test-MigrationLockAvailability
    if (-not $lockCheck.ok) {
        Set-CheckpointStatus -Name "migration_lock" -Status "fail" -Detail "Migration lock unavailable or check failed."
        $reasonCode = Get-ReasonCodeFromText -Text $lockCheck.output -Default "MIGRATION_LOCK"
        $exitCode = $(if ($lockCheck.exit_code -eq $ExitCodes.STEP_TIMEOUT) { $ExitCodes.STEP_TIMEOUT } else { $ExitCodes.MIGRATION_LOCKED })
        End-Phase -Name "migration_lock"
        Finalize-AndExit -Code $exitCode -Verdict "STOP" -Reason "Migration lock check failed or lock is held by another process." -ReasonCode $reasonCode
    }
    Set-CheckpointStatus -Name "migration_lock" -Status "pass" -Detail "No concurrent migration lock detected."
    End-Phase -Name "migration_lock"
}
else {
    Set-CheckpointStatus -Name "migration_lock" -Status "skipped" -Detail "No migration phase scheduled for this run."
}

$upgrade1 = $null
if (Should-RunPhase -PhaseName "upgrade1") {
    Start-Phase -Name "upgrade1"
    $upgrade1 = Invoke-ExternalCommandRetriable -Label "alembic upgrade head #1" -Exe ".\.venv\Scripts\python.exe" -ArgList @("-m", "alembic", "upgrade", "head")
    if ($upgrade1.exit_code -ne 0) {
        $baseCode = $(if (Is-DriftLikeError $upgrade1.output) { $ExitCodes.DRIFT_DETECTED } elseif (Is-ConnectionLikeError $upgrade1.output) { $ExitCodes.CONNECTION } else { $ExitCodes.MIGRATION_FAIL })
        $code = Resolve-StageExitCode -Result $upgrade1 -DefaultExitCode $baseCode
        Set-CheckpointStatus -Name "upgrade1" -Status "fail" -Detail "First upgrade failed."
        $reasonCode = Get-ReasonCodeFromText -Text $upgrade1.output -Default "MIGRATION_FAIL"
        End-Phase -Name "upgrade1"
        Finalize-AndExit -Code $code -Verdict "FAIL" -Reason "First upgrade failed." -ReasonCode $reasonCode
    }
    Set-CheckpointStatus -Name "upgrade1" -Status "pass" -Detail "First upgrade succeeded."
    End-Phase -Name "upgrade1"
}
else {
    $md.Add("## Migration Run #1")
    $md.Add("- skipped (resume_from=$ResumeFrom)")
    $md.Add("")
    Set-CheckpointStatus -Name "upgrade1" -Status "skipped" -Detail "Skipped by resume_from."
}

$upgrade2 = $null
if (Should-RunPhase -PhaseName "upgrade2") {
    Start-Phase -Name "upgrade2"
    $upgrade2 = Invoke-ExternalCommandRetriable -Label "alembic upgrade head #2 (no-op)" -Exe ".\.venv\Scripts\python.exe" -ArgList @("-m", "alembic", "upgrade", "head")
    if ($upgrade2.exit_code -ne 0) {
        $baseCode = $(if (Is-DriftLikeError $upgrade2.output) { $ExitCodes.DRIFT_DETECTED } elseif (Is-ConnectionLikeError $upgrade2.output) { $ExitCodes.CONNECTION } else { $ExitCodes.MIGRATION_FAIL })
        $code = Resolve-StageExitCode -Result $upgrade2 -DefaultExitCode $baseCode
        Set-CheckpointStatus -Name "upgrade2" -Status "fail" -Detail "Second no-op upgrade failed."
        $reasonCode = Get-ReasonCodeFromText -Text $upgrade2.output -Default "MIGRATION_FAIL"
        End-Phase -Name "upgrade2"
        Finalize-AndExit -Code $code -Verdict "FAIL" -Reason "Second no-op upgrade failed." -ReasonCode $reasonCode
    }
    Set-CheckpointStatus -Name "upgrade2" -Status "pass" -Detail "Second no-op upgrade succeeded."
    End-Phase -Name "upgrade2"
}
else {
    $md.Add("## Migration Run #2")
    $md.Add("- skipped (resume_from=$ResumeFrom)")
    $md.Add("")
    Set-CheckpointStatus -Name "upgrade2" -Status "skipped" -Detail "Skipped by resume_from."
}

$seed = $null
if (Should-RunPhase -PhaseName "seed") {
    Start-Phase -Name "seed"
    if ($DrySeed) {
        $drySeed = Test-DrySeedPrerequisites
        if (-not $drySeed.ok) {
            Set-CheckpointStatus -Name "seed" -Status "fail" -Detail "Dry seed prerequisite check failed."
            $reasonCode = Get-ReasonCodeFromText -Text $drySeed.output -Default "SEED_FAIL"
            $baseCode = $(if (Is-ConnectionLikeError $drySeed.output) { $ExitCodes.CONNECTION } else { $ExitCodes.SEED_FAIL })
            $code = Resolve-StageExitCode -Result $drySeed -DefaultExitCode $baseCode
            End-Phase -Name "seed"
            Finalize-AndExit -Code $code -Verdict "FAIL" -Reason "Dry-seed prerequisite check failed." -ReasonCode $reasonCode
        }
        Set-CheckpointStatus -Name "seed" -Status "pass" -Detail "Dry seed prerequisite check passed."
        Add-MdBlock -Title "seed staging users (dry-run surrogate)" -Body $drySeed.output
    }
    else {
        $seed = Invoke-ExternalCommandRetriable -Label "seed staging users" -Exe ".\.venv\Scripts\python.exe" -ArgList @("scripts/seed_staging_users.py")
        if ($seed.exit_code -ne 0) {
            $baseCode = $(if (Is-ConnectionLikeError $seed.output) { $ExitCodes.CONNECTION } else { $ExitCodes.SEED_FAIL })
            $code = Resolve-StageExitCode -Result $seed -DefaultExitCode $baseCode
            Set-CheckpointStatus -Name "seed" -Status "fail" -Detail "Seed execution failed."
            $reasonCode = Get-ReasonCodeFromText -Text $seed.output -Default "SEED_FAIL"
            End-Phase -Name "seed"
            Finalize-AndExit -Code $code -Verdict "FAIL" -Reason "Seed failed." -ReasonCode $reasonCode
        }
        Set-CheckpointStatus -Name "seed" -Status "pass" -Detail "Seed execution succeeded."
    }
    End-Phase -Name "seed"
}
else {
    $md.Add("## Seed")
    $md.Add("- skipped (resume_from=$ResumeFrom)")
    $md.Add("")
    Set-CheckpointStatus -Name "seed" -Status "skipped" -Detail "Skipped by resume_from."
}

Start-Phase -Name "schema_sanity"
$sanity = Test-PostUpgradeSchemaSanity
if (-not $sanity.ok) {
    Set-CheckpointStatus -Name "schema_sanity" -Status "fail" -Detail "Post-upgrade schema sanity failed."
    $reasonCode = Get-ReasonCodeFromText -Text $sanity.output -Default "ALEMBIC_DRIFT"
    End-Phase -Name "schema_sanity"
    Finalize-AndExit -Code $ExitCodes.DRIFT_DETECTED -Verdict "FAIL" -Reason "Post-upgrade schema sanity checks failed." -ReasonCode $reasonCode
}
Set-CheckpointStatus -Name "schema_sanity" -Status "pass" -Detail "Post-upgrade schema sanity passed."
Add-MdBlock -Title "post-upgrade schema sanity result" -Body $sanity.output
End-Phase -Name "schema_sanity"

Finalize-AndExit -Code $ExitCodes.PASS -Verdict "PASS" -Reason "Migration chain clean, no-op confirmed, seed succeeded." -ReasonCode "GENERAL"
