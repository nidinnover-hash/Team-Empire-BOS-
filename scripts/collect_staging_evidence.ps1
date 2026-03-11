param(
    [string]$BaseUrl = $env:STAGING_BASE_URL,
    [string]$Org1Token = $env:STAGING_ORG1_TOKEN,
    [string]$Org2Token = $env:STAGING_ORG2_TOKEN,
    [string]$PgConn = $env:STAGING_PGCONN,
    [string]$EnvFile = ".env.staging",
    [string]$OutFile = "STAGING_VERIFICATION_NOTES.md"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Ensure-Value {
    param(
        [string]$Name,
        [string]$Value
    )
    if ([string]::IsNullOrWhiteSpace($Value)) {
        throw "Missing required value: $Name"
    }
}

function Load-EnvFile {
    param([string[]]$Paths)
    foreach ($path in $Paths) {
        if (-not (Test-Path $path)) {
            continue
        }
        Get-Content -Path $path | ForEach-Object {
            $line = $_.Trim()
            if ($line.Length -eq 0 -or $line.StartsWith("#")) {
                return
            }
            $parts = $line.Split("=", 2)
            if ($parts.Count -ne 2) {
                return
            }
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
}

function Try-ParseJson {
    param([string]$Text)
    try {
        return $Text | ConvertFrom-Json -ErrorAction Stop
    }
    catch {
        return $null
    }
}

function Resolve-OrgToken {
    param(
        [string]$CurrentToken,
        [string]$BaseUrl,
        [string]$Email,
        [string]$Password,
        [string]$OrganizationId,
        [string]$Label
    )
    if (-not [string]::IsNullOrWhiteSpace($CurrentToken)) {
        return $CurrentToken
    }

    Ensure-Value -Name "$Label EMAIL" -Value $Email
    Ensure-Value -Name "$Label PASSWORD" -Value $Password
    Ensure-Value -Name "$Label ID" -Value $OrganizationId

    $loginUrl = "$BaseUrl/api/v1/auth/login"
    try {
        $resp = Invoke-WebRequest -Method "POST" -Uri $loginUrl -ContentType "application/x-www-form-urlencoded" -Body @{
            username = $Email
            password = $Password
            organization_id = $OrganizationId
        } -TimeoutSec 60
        $obj = Try-ParseJson -Text ([string]$resp.Content)
        if ($obj -and $obj.access_token) {
            return [string]$obj.access_token
        }
        throw "Login response for $Label did not include access_token."
    }
    catch {
        throw "Failed to obtain token for $Label via /api/v1/auth/login: $($_.Exception.Message)"
    }
}

function Invoke-Api {
    param(
        [string]$Method,
        [string]$Url,
        [string]$Token,
        $Body = $null
    )

    $headers = @{}
    if (-not [string]::IsNullOrWhiteSpace($Token)) {
        $headers["Authorization"] = "Bearer $Token"
    }

    $params = @{
        Method = $Method
        Uri = $Url
        Headers = $headers
        TimeoutSec = 60
    }

    if ($null -ne $Body) {
        $params["ContentType"] = "application/json"
        $params["Body"] = ($Body | ConvertTo-Json -Depth 20 -Compress)
    }

    try {
        $resp = Invoke-WebRequest @params
        return [PSCustomObject]@{
            Status = [int]$resp.StatusCode
            Body = [string]$resp.Content
        }
    }
    catch {
        $status = 0
        $body = $_.Exception.Message
        $respProp = $_.Exception.PSObject.Properties["Response"]
        if ($respProp -and $null -ne $respProp.Value) {
            $response = $respProp.Value
            try {
                $status = [int]$response.StatusCode.value__
            }
            catch {}
            try {
                $reader = New-Object System.IO.StreamReader($response.GetResponseStream())
                $body = $reader.ReadToEnd()
            }
            catch {}
        }
        return [PSCustomObject]@{
            Status = $status
            Body = [string]$body
        }
    }
}

function Run-Sql {
    param([string]$Sql)
    if ([string]::IsNullOrWhiteSpace($PgConn)) {
        return "No SQL output: STAGING_PGCONN not set."
    }
    $psqlCandidates = @(
        "psql",
        "C:\Program Files\PostgreSQL\17\bin\psql.exe",
        "C:\Program Files\PostgreSQL\16\bin\psql.exe"
    )
    $psqlCmd = $null
    foreach ($candidate in $psqlCandidates) {
        if ($candidate -eq "psql") {
            $cmd = Get-Command psql -ErrorAction SilentlyContinue
            if ($cmd) {
                $psqlCmd = $cmd.Source
                break
            }
        }
        elseif (Test-Path $candidate) {
            $psqlCmd = $candidate
            break
        }
    }
    if (-not $psqlCmd) {
        return "SQL command failed: psql not found in PATH or default install paths."
    }
    try {
        $result = & $psqlCmd $PgConn -c $Sql 2>&1 | Out-String
        return $result.Trim()
    }
    catch {
        return "SQL command failed: $($_.Exception.Message)"
    }
}

function Format-ApiResult {
    param(
        [string]$Title,
        $Result
    )
    return @(
        $Title,
        "status: $($Result.Status)",
        "body:",
        '```json',
        (($Result.Body | Out-String).Trim()),
        '```'
    ) -join "`n"
}

$envFileCandidates = @(
    $EnvFile,
    (Join-Path (Get-Location) ".env.staging"),
    (Join-Path $PSScriptRoot "..\.env.staging"),
    (Join-Path (Get-Location) ".staging.env")
)
Load-EnvFile -Paths $envFileCandidates

if ([string]::IsNullOrWhiteSpace($BaseUrl)) { $BaseUrl = $env:STAGING_BASE_URL }
if ([string]::IsNullOrWhiteSpace($PgConn)) { $PgConn = $env:STAGING_PGCONN }

Ensure-Value -Name "STAGING_BASE_URL" -Value $BaseUrl
$Org1Token = Resolve-OrgToken -CurrentToken $Org1Token -BaseUrl $BaseUrl -Email $env:STAGING_ORG1_EMAIL -Password $env:STAGING_ORG1_PASSWORD -OrganizationId $env:STAGING_ORG1_ID -Label "STAGING_ORG1"
$Org2Token = Resolve-OrgToken -CurrentToken $Org2Token -BaseUrl $BaseUrl -Email $env:STAGING_ORG2_EMAIL -Password $env:STAGING_ORG2_PASSWORD -OrganizationId $env:STAGING_ORG2_ID -Label "STAGING_ORG2"

$notes = New-Object System.Collections.Generic.List[string]
$notes.Add("# BOS Staging Verification Notes")
$notes.Add("")

# 1. HEALTH + REVISION
$health = Invoke-Api -Method "GET" -Url "$BaseUrl/health" -Token ""
$alembicVersionOut = Run-Sql -Sql "SELECT version_num FROM alembic_version;"
$notes.Add("## 1. HEALTH + REVISION")
$notes.Add((Format-ApiResult -Title "[curl output]" -Result $health))
$notes.Add("[SQL output]")
$notes.Add('```sql')
$notes.Add($alembicVersionOut)
$notes.Add('```')
$notes.Add("")

# 2. TENANT ISOLATION
$createBundle = Invoke-Api -Method "POST" -Url "$BaseUrl/api/v1/product-bundles" -Token $Org1Token -Body @{
    name = "iso-test"
    bundle_price = 100
}
$bundleObj = Try-ParseJson -Text $createBundle.Body
$bundleId = $null
if ($bundleObj -and $bundleObj.id) { $bundleId = [int]$bundleObj.id }

$addItem = $null
$org2Read = $null
if ($bundleId) {
    $addItem = Invoke-Api -Method "POST" -Url "$BaseUrl/api/v1/product-bundles/$bundleId/items" -Token $Org1Token -Body @{
        product_id = 1
        quantity = 2
        unit_price = 50
    }
    $org2Read = Invoke-Api -Method "GET" -Url "$BaseUrl/api/v1/product-bundles/$bundleId/items" -Token $Org2Token
}
else {
    $addItem = [PSCustomObject]@{ Status = 0; Body = "Skipped: bundle create failed." }
    $org2Read = [PSCustomObject]@{ Status = 0; Body = "Skipped: bundle create failed." }
}
$notes.Add("## 2. TENANT ISOLATION")
$notes.Add((Format-ApiResult -Title "[create bundle response]" -Result $createBundle))
$notes.Add((Format-ApiResult -Title "[add item response]" -Result $addItem))
$notes.Add((Format-ApiResult -Title "[org2 read response]" -Result $org2Read))
$notes.Add("")

# 3. QUOTE APPROVAL
$createQuoteForApproval = Invoke-Api -Method "POST" -Url "$BaseUrl/api/v1/quotes" -Token $Org1Token -Body @{
    title = "approval-smoke"
}
$quoteObj = Try-ParseJson -Text $createQuoteForApproval.Body
$quoteId = $null
if ($quoteObj -and $quoteObj.id) { $quoteId = [int]$quoteObj.id }

$createApproval = $null
$firstDecide = $null
$secondDecide = $null
$quoteApprovalRow = ""
if ($quoteId) {
    $createApproval = Invoke-Api -Method "POST" -Url "$BaseUrl/api/v1/quote-approvals" -Token $Org1Token -Body @{
        quote_id = $quoteId
        level = 1
        approver_user_id = 1
    }
    $approvalObj = Try-ParseJson -Text $createApproval.Body
    if ($approvalObj -and $approvalObj.id) {
        $approvalId = [int]$approvalObj.id
        $firstDecide = Invoke-Api -Method "PUT" -Url "$BaseUrl/api/v1/quote-approvals/$approvalId/decide" -Token $Org1Token -Body @{
            status = "approved"
            reason = "ok"
        }
        $secondDecide = Invoke-Api -Method "PUT" -Url "$BaseUrl/api/v1/quote-approvals/$approvalId/decide" -Token $Org1Token -Body @{
            status = "rejected"
            reason = "late"
        }
        $quoteApprovalRow = Run-Sql -Sql "SELECT id, organization_id, status, reason, decided_at FROM quote_approvals WHERE id = $approvalId;"
    }
    else {
        $firstDecide = [PSCustomObject]@{ Status = 0; Body = "Skipped: create approval failed." }
        $secondDecide = [PSCustomObject]@{ Status = 0; Body = "Skipped: create approval failed." }
        $quoteApprovalRow = "Skipped: create approval failed."
    }
}
else {
    $createApproval = [PSCustomObject]@{ Status = 0; Body = "Skipped: quote create failed." }
    $firstDecide = [PSCustomObject]@{ Status = 0; Body = "Skipped: quote create failed." }
    $secondDecide = [PSCustomObject]@{ Status = 0; Body = "Skipped: quote create failed." }
    $quoteApprovalRow = "Skipped: quote create failed."
}
$notes.Add("## 3. QUOTE APPROVAL")
$notes.Add((Format-ApiResult -Title "[create approval response]" -Result $createApproval))
$notes.Add((Format-ApiResult -Title "[first decide response]" -Result $firstDecide))
$notes.Add((Format-ApiResult -Title "[second decide response]" -Result $secondDecide))
$notes.Add("[DB row]")
$notes.Add('```sql')
$notes.Add($quoteApprovalRow)
$notes.Add('```')
$notes.Add("")

# 4. FORECAST UPSERT
$forecast1 = Invoke-Api -Method "POST" -Url "$BaseUrl/api/v1/forecast-rollups" -Token $Org1Token -Body @{
    period = "2026-Q4"
    period_type = "quarterly"
    group_by = "team"
    group_value = "East"
    committed = 100
    best_case = 120
    pipeline = 150
    weighted_pipeline = 110
    closed_won = 70
    target = 200
    attainment_pct = 35
}
$forecast2 = Invoke-Api -Method "POST" -Url "$BaseUrl/api/v1/forecast-rollups" -Token $Org1Token -Body @{
    period = "2026-Q4"
    period_type = "quarterly"
    group_by = "team"
    group_value = "East"
    committed = 130
    best_case = 150
    pipeline = 180
    weighted_pipeline = 125
    closed_won = 90
    target = 220
    attainment_pct = 41
}
$forecastCount = Run-Sql -Sql @"
SELECT organization_id, period, group_by, group_value, COUNT(*) c
FROM forecast_rollups
WHERE period='2026-Q4' AND group_by='team' AND group_value='East'
GROUP BY 1,2,3,4;
"@
$notes.Add("## 4. FORECAST UPSERT")
$notes.Add((Format-ApiResult -Title "[first response]" -Result $forecast1))
$notes.Add((Format-ApiResult -Title "[second response]" -Result $forecast2))
$notes.Add("[DB count query]")
$notes.Add('```sql')
$notes.Add($forecastCount)
$notes.Add('```')
$notes.Add("")

# 5. CONVERSION UPSERT
$conv1 = Invoke-Api -Method "POST" -Url "$BaseUrl/api/v1/conversion-funnels" -Token $Org1Token -Body @{
    period = "2026-03"
    period_type = "monthly"
    from_stage = "lead"
    to_stage = "qualified"
    entered_count = 100
    converted_count = 40
    conversion_rate = 40
    avg_time_hours = 48
    median_time_hours = 36
}
$conv2 = Invoke-Api -Method "POST" -Url "$BaseUrl/api/v1/conversion-funnels" -Token $Org1Token -Body @{
    period = "2026-03"
    period_type = "monthly"
    from_stage = "lead"
    to_stage = "qualified"
    entered_count = 100
    converted_count = 45
    conversion_rate = 45
    avg_time_hours = 44
    median_time_hours = 32
}
$convCount = Run-Sql -Sql @"
SELECT organization_id, period, from_stage, to_stage, COUNT(*) c
FROM conversion_funnels
WHERE period='2026-03' AND from_stage='lead' AND to_stage='qualified'
GROUP BY 1,2,3,4;
"@
$notes.Add("## 5. CONVERSION UPSERT")
$notes.Add((Format-ApiResult -Title "[first response]" -Result $conv1))
$notes.Add((Format-ApiResult -Title "[second response]" -Result $conv2))
$notes.Add("[DB count query]")
$notes.Add('```sql')
$notes.Add($convCount)
$notes.Add('```')
$notes.Add("")

# 6. AUTOMATION TEMPLATES
$tmplGet = Invoke-Api -Method "GET" -Url "$BaseUrl/api/v1/automations/templates" -Token $Org1Token
$tmplGetObj = Try-ParseJson -Text $tmplGet.Body
$templateId = $null
if ($tmplGetObj -and $tmplGetObj.Count -gt 0 -and $tmplGetObj[0].id) {
    $templateId = [string]$tmplGetObj[0].id
}
$tmplPost = $null
if (-not [string]::IsNullOrWhiteSpace($templateId)) {
    $tmplPost = Invoke-Api -Method "POST" -Url "$BaseUrl/api/v1/automations/templates/$templateId/create" -Token $Org1Token
}
else {
    $tmplPost = [PSCustomObject]@{ Status = 0; Body = "Skipped: no template id from GET response." }
}
$notes.Add("## 6. AUTOMATION TEMPLATES")
$notes.Add((Format-ApiResult -Title "[GET response]" -Result $tmplGet))
$notes.Add((Format-ApiResult -Title "[POST response]" -Result $tmplPost))
$notes.Add("")

# 7. PROTECTED FIELD IMMUTABILITY
$createQuote = Invoke-Api -Method "POST" -Url "$BaseUrl/api/v1/quotes" -Token $Org1Token -Body @{
    title = "immut-test"
}
$createQuoteObj = Try-ParseJson -Text $createQuote.Body
$immutQuoteId = $null
if ($createQuoteObj -and $createQuoteObj.id) { $immutQuoteId = [int]$createQuoteObj.id }

$updateQuote = $null
$quoteRow = ""
if ($immutQuoteId) {
    $updateQuote = Invoke-Api -Method "PUT" -Url "$BaseUrl/api/v1/quotes/$immutQuoteId" -Token $Org1Token -Body @{
        title = "changed"
        id = 99999
        organization_id = 999
        created_by_user_id = 999
    }
    $quoteRow = Run-Sql -Sql "SELECT id, organization_id, created_by_user_id, title FROM quotes WHERE id = $immutQuoteId;"
}
else {
    $updateQuote = [PSCustomObject]@{ Status = 0; Body = "Skipped: quote create failed." }
    $quoteRow = "Skipped: quote create failed."
}
$notes.Add("## 7. PROTECTED FIELD IMMUTABILITY")
$notes.Add((Format-ApiResult -Title "[create quote response]" -Result $createQuote))
$notes.Add((Format-ApiResult -Title "[update response]" -Result $updateQuote))
$notes.Add("[DB row]")
$notes.Add('```sql')
$notes.Add($quoteRow)
$notes.Add('```')
$notes.Add("")

# 8. AUDIT CORRECTNESS + DUPLICATION
$auditRows = Run-Sql -Sql @"
SELECT id, created_at, organization_id, actor_user_id, event_type, entity_type, entity_id
FROM events
WHERE created_at > NOW() - INTERVAL '30 minutes'
ORDER BY created_at DESC
LIMIT 200;
"@
$auditDupes = Run-Sql -Sql @"
WITH x AS (
  SELECT
    organization_id, event_type, entity_type, COALESCE(entity_id,-1) AS entity_id, created_at,
    LAG(created_at) OVER (
      PARTITION BY organization_id, event_type, entity_type, COALESCE(entity_id,-1)
      ORDER BY created_at
    ) AS prev_created_at
  FROM events
  WHERE created_at > NOW() - INTERVAL '30 minutes'
)
SELECT *
FROM x
WHERE prev_created_at IS NOT NULL
  AND created_at - prev_created_at <= INTERVAL '2 seconds'
ORDER BY created_at DESC
LIMIT 100;
"@
$notes.Add("## 8. AUDIT CORRECTNESS + DUPLICATION")
$notes.Add("[recent audit rows]")
$notes.Add('```sql')
$notes.Add($auditRows)
$notes.Add('```')
$notes.Add("[duplicate detector output]")
$notes.Add('```sql')
$notes.Add($auditDupes)
$notes.Add('```')
$notes.Add("")

$notes -join "`n" | Set-Content -Path $OutFile -Encoding UTF8
Write-Host "Wrote staging evidence to $OutFile"
