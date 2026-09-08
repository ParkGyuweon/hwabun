[CmdletBinding()]
param(
    [ValidateSet('up', 'start-q1', 'stop-q1', 'run-batch', 'validate', 'status', 'down')]
    [string]$Action = 'status'
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

function Invoke-SparkSubmit {
    param(
        [Parameter(Mandatory)][string]$JobPath,
        [string[]]$JobArguments = @()
    )

    $submitArguments = @(
        'exec', '-T', 'spark-master',
        '/opt/spark/bin/spark-submit',
        '--master', 'spark://spark-master:7077',
        '--deploy-mode', 'client',
        '--conf', 'spark.driver.host=spark-master',
        '--conf', 'spark.driver.bindAddress=0.0.0.0',
        $JobPath
    ) + $JobArguments

    Invoke-Compose -Arguments $submitArguments
}

function Invoke-BatchPipeline {
    Invoke-SparkSubmit -JobPath '/opt/project/streaming/jobs/clean_events_job.py' -JobArguments @(
        '--input-path', "$dataRoot/raw_events",
        '--cleaned-path', "$dataRoot/processed/cleaned_events",
        '--bad-path', "$dataRoot/processed/bad_events",
        '--duplicate-path', "$dataRoot/processed/duplicate_events"
    )
    Invoke-SparkSubmit -JobPath '/opt/project/streaming/jobs/derive_facts_job.py' -JobArguments @(
        '--input-path', "$dataRoot/processed/cleaned_events",
        '--sessionized-path', "$dataRoot/processed/sessionized_events",
        '--product-fact-path', "$dataRoot/processed/product_event_fact",
        '--section-dwell-path', "$dataRoot/processed/section_dwell_agg",
        '--content-interest-path', "$dataRoot/processed/content_interest_fact",
        '--dim-product-path', "$dataRoot/processed/dim_product",
        '--dim-brand-path', "$dataRoot/processed/dim_brand",
        '--product-catalog-path', '/opt/project/batch/ingest/data/products_200.json',
        '--behavior-weights-path', '/opt/project/frontend/src/types/log.ts'
    )
    $martArguments = @(
        '--sessionized-path', "$dataRoot/processed/sessionized_events",
        '--product-fact-path', "$dataRoot/processed/product_event_fact",
        '--dim-product-path', "$dataRoot/processed/dim_product",
        '--product-ingredient-path', '/opt/project/batch/ingest/data/serving/product_ingredient.csv',
        '--ingredient-vocab-path', '/opt/project/batch/ingest/data/serving/ingredient_vocab.csv',
        '--funnel-session-path', "$dataRoot/processed/funnel_session_fact",
        '--product-daily-path', "$dataRoot/marts/product_daily_kpi",
        '--funnel-daily-path', "$dataRoot/marts/funnel_daily_kpi",
        '--ingredient-weekly-path', "$dataRoot/marts/ingredient_weekly_interest",
        '--category-price-path', "$dataRoot/marts/category_price_reference",
        '--banner-daily-path', "$dataRoot/marts/banner_daily",
        '--user-trait-daily-path', "$dataRoot/marts/user_trait_daily",
        '--cross-brand-daily-path', "$dataRoot/marts/cross_brand_daily",
        '--baseline-path', "$dataRoot/marts/analytics_baseline",
        '--trait-weights-path', '/opt/project/contracts/user-trait-weights.json',
        '--feature-vocab-path', '/opt/project/contracts/product-feature-vocab.json',
        '--affinity-lift-path', '/opt/project/batch/ingest/data/affinity_lift.csv',
        '--behavior-weights-path', '/opt/project/frontend/src/types/log.ts'
    )
    if ($env:BASELINE_POLICY_VERSION -and $env:BASELINE_START_DATE -and $env:BASELINE_END_DATE) {
        $martArguments += @(
            '--baseline-policy-version', $env:BASELINE_POLICY_VERSION,
            '--baseline-start-date', $env:BASELINE_START_DATE,
            '--baseline-end-date', $env:BASELINE_END_DATE
        )
    }
    Invoke-SparkSubmit -JobPath '/opt/project/streaming/jobs/build_marts_job.py' -JobArguments $martArguments
    Invoke-PipelineValidation
}

function Invoke-PipelineValidation {
    Invoke-SparkSubmit -JobPath '/opt/project/streaming/jobs/validate_pipeline_job.py' -JobArguments @(
        '--raw-path', "$dataRoot/raw_events",
        '--cleaned-path', "$dataRoot/processed/cleaned_events",
        '--bad-path', "$dataRoot/processed/bad_events",
        '--duplicate-path', "$dataRoot/processed/duplicate_events",
        '--sessionized-path', "$dataRoot/processed/sessionized_events",
        '--product-fact-path', "$dataRoot/processed/product_event_fact",
        '--section-dwell-path', "$dataRoot/processed/section_dwell_agg",
        '--content-interest-path', "$dataRoot/processed/content_interest_fact",
        '--dim-product-path', "$dataRoot/processed/dim_product",
        '--dim-brand-path', "$dataRoot/processed/dim_brand",
        '--funnel-session-path', "$dataRoot/processed/funnel_session_fact",
        '--product-daily-path', "$dataRoot/marts/product_daily_kpi",
        '--funnel-daily-path', "$dataRoot/marts/funnel_daily_kpi",
        '--ingredient-weekly-path', "$dataRoot/marts/ingredient_weekly_interest",
        '--category-price-path', "$dataRoot/marts/category_price_reference",
        '--banner-daily-path', "$dataRoot/marts/banner_daily",
        '--user-trait-daily-path', "$dataRoot/marts/user_trait_daily",
        '--cross-brand-daily-path', "$dataRoot/marts/cross_brand_daily",
        '--baseline-path', "$dataRoot/marts/analytics_baseline",
        '--report-path', "$dataRoot/validation/pipeline-report.json",
        '--require-events'
    )
}

Push-Location $repoRoot
try {
    switch ($Action) {
        'up' {
            & (Join-Path $repoRoot 'infra\create-network.ps1')
            if ($LASTEXITCODE -ne 0) {
                throw 'Docker 공용 Network 생성에 실패했습니다.'
            }
            Invoke-Compose -Arguments @(
                'up', '-d', '--build', '--wait',
                'kafka', 'spark-master', 'spark-worker', 'spark-history'
            )
        }
        'start-q1' {
            Invoke-Compose -Arguments @('--profile', 'streaming', 'up', '-d', 'spark-raw-sink')
        }
        'stop-q1' {
            Invoke-Compose -Arguments @('--profile', 'streaming', 'stop', 'spark-raw-sink')
        }
        'run-batch' {
            Invoke-BatchPipeline
        }
        'validate' {
            Invoke-PipelineValidation
        }
        'status' {
            Invoke-Compose -Arguments @('--profile', 'streaming', 'ps')
        }
        'down' {
            Invoke-Compose -Arguments @('down')
        }
    }
}
finally {
    Pop-Location
}
