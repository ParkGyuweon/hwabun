[CmdletBinding()]
param(
    [ValidateRange(10, 180)]
    [int]$TimeoutSeconds = 90
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw 'Docker CLI를 찾을 수 없습니다. Docker Desktop 또는 Docker Engine을 먼저 실행하세요.'
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$kafkaCompose = Join-Path $repoRoot 'infra\kafka\docker-compose.yml'
$sparkCompose = Join-Path $repoRoot 'infra\spark\docker-compose.yml'
$sparkEnv = Join-Path $repoRoot 'infra\spark\.env'
$runner = Join-Path $repoRoot 'infra\spark\run-pipeline.ps1'
$dataRoot = '/opt/project/data'

$composeBaseArgs = @()
if (Test-Path $sparkEnv) {
    $composeBaseArgs += @('--env-file', $sparkEnv)
}
$composeBaseArgs += @('-f', $kafkaCompose, '-f', $sparkCompose)

function Invoke-Compose {
    param([Parameter(Mandatory)][string[]]$Arguments)

    & docker compose @composeBaseArgs @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose 실행에 실패했습니다: $($Arguments -join ' ')"
    }
}

function Test-RawEvent {
    param([Parameter(Mandatory)][string]$EventId)

    & docker compose @composeBaseArgs exec -T spark-master `
        /opt/spark/bin/spark-submit `
        --master spark://spark-master:7077 `
        --deploy-mode client `
        --conf spark.driver.host=spark-master `
        --conf spark.driver.bindAddress=0.0.0.0 `
        /opt/project/infra/spark/assert_raw_event.py `
        --raw-path "$dataRoot/raw_events" `
        --event-id $EventId `
        --expected-count 1

    return $LASTEXITCODE -eq 0
}

Push-Location $repoRoot
try {
    & $runner up
    if ($LASTEXITCODE -ne 0) {
        throw 'Spark 기반 서비스를 시작하지 못했습니다.'
    }
    & $runner start-q1
    if ($LASTEXITCODE -ne 0) {
        throw 'Q1 Raw sink를 시작하지 못했습니다.'
    }

    $now = [DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ss.fffZ')
    $eventId = "evt-e2e-$([Guid]::NewGuid().ToString('N'))"
    $event = [ordered]@{
        schema_version = '0.2.0-draft'
        event_id = $eventId
        event_name = 'product_view'
        intent = 'interest'
        occurred_at = $now
        persona_id = 'PC-E2E-001'
        session_id = "session-e2e-$eventId"
        page_view_id = "page-view-e2e-$eventId"
        sequence_no = 1
        page_type = 'product_detail'
        product_id = 'P-E2E-001'
        actor_type = 'synthetic'
        environment = 'local'
        received_at = $now
        source = 'simulator'
        request_id = "request-e2e-$eventId"
        event_index = 1
        properties = [ordered]@{
            navigation_source = 'e2e_verification'
            scenario_id = 'spark_infrastructure'
            simulation_run_id = $eventId
            generator_type = 'powershell'
        }
    }
    $eventJson = $event | ConvertTo-Json -Compress -Depth 4

    $eventJson | & docker compose @composeBaseArgs exec -T kafka `
        /opt/kafka/bin/kafka-console-producer.sh `
        --bootstrap-server kafka:19092 `
        --topic activity-events
    if ($LASTEXITCODE -ne 0) {
        throw 'E2E 검증 이벤트를 Kafka에 전송하지 못했습니다.'
    }
    Write-Host "Kafka에 E2E 이벤트를 전송했습니다: $eventId"

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $found = $false
    do {
        Start-Sleep -Seconds 10
        if (Test-RawEvent -EventId $eventId) {
            $found = $true
            break
        }
        Write-Host 'Raw 적재를 기다리는 중입니다...'
    } while ((Get-Date) -lt $deadline)

    if (-not $found) {
        throw "Q1 Raw sink가 제한 시간 내 event_id=$eventId 를 적재하지 못했습니다."
    }

    Invoke-Compose -Arguments @('--profile', 'streaming', 'up', '-d', '--force-recreate', 'spark-raw-sink')
    Start-Sleep -Seconds 10
    if (-not (Test-RawEvent -EventId $eventId)) {
        throw "Q1 재시작 후 event_id=$eventId 의 Raw 적재 상태가 보존되지 않았습니다."
    }

    & $runner run-batch
    if ($LASTEXITCODE -ne 0) {
        throw 'Q2~Q5 batch 파이프라인 또는 불변성 검증에 실패했습니다.'
    }

    $reportPath = Join-Path $repoRoot 'data\validation\pipeline-report.json'
    if (-not (Test-Path $reportPath)) {
        throw "검증 보고서를 찾을 수 없습니다: $reportPath"
    }
    $report = Get-Content -Raw $reportPath | ConvertFrom-Json
    if ($report.status -ne 'passed') {
        throw "파이프라인 검증 보고서 상태가 passed가 아닙니다: $($report.status)"
    }

    Write-Host "E2E 검증이 통과했습니다: event_id=$eventId, validation=$($report.status)"
}
finally {
    Pop-Location
}
