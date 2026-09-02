[CmdletBinding()]
param(
    [switch]$RequireRawSink
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Get-Response {
    param([Parameter(Mandatory)][string]$Uri)

    try {
        return Invoke-WebRequest -Uri $Uri -TimeoutSec 10
    }
    catch {
        throw "Spark 상태 Endpoint에 연결하지 못했습니다 ($Uri): $($_.Exception.Message)"
    }
}

$masterResponse = Get-Response -Uri 'http://localhost:18080/json/'
$historyResponse = Get-Response -Uri 'http://localhost:18081/'
$master = $masterResponse.Content | ConvertFrom-Json
$activeApps = @($master.activeapps)
$completedApps = @($master.completedapps)
$rawSink = @($activeApps | Where-Object { $_.name -eq 'raw-events-ingest' })

$result = [ordered]@{
    status = 'passed'
    master_ui = 'http://localhost:18080'
    history_ui = 'http://localhost:18081'
    alive_workers = [int]$master.aliveworkers
    active_applications = $activeApps.Count
    completed_applications = $completedApps.Count
    raw_sink_running = $rawSink.Count -gt 0
}

$failures = @()
if ($masterResponse.StatusCode -ne 200) {
    $failures += "Master UI HTTP $($masterResponse.StatusCode)"
}
if ($historyResponse.StatusCode -ne 200) {
    $failures += "History Server HTTP $($historyResponse.StatusCode)"
}
if ($result.alive_workers -lt 1) {
    $failures += '활성 Spark Worker가 없습니다.'
}
if ($RequireRawSink -and -not $result.raw_sink_running) {
    $failures += 'Q1 Raw sink(raw-events-ingest)가 실행 중이 아닙니다.'
}

if ($failures.Count -gt 0) {
    $result.status = 'failed'
    $result.failures = $failures
}

$result | ConvertTo-Json
if ($result.status -ne 'passed') {
    exit 1
}
