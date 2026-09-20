[CmdletBinding()]
param(
    [ValidateSet('up', 'start-q1', 'stop-q1', 'run-batch', 'validate', 'status', 'down')]
    [string]$Action = 'status',

    # 시작 단계. Q2 는 cleaned_events 를 통째로 다시 만들어 오래 걸리므로,
    # Fact·Mart 만 고쳤을 때 되돌릴 이유가 없다 (에서 81분을 버렸다).
    [ValidateSet('q2', 'q3', 'q4')]
    [string]$From = 'q2'
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
$dataRoot = if ($env:PIPELINE_DATA_ROOT) {
    $env:PIPELINE_DATA_ROOT.TrimEnd('/')
} else {
    '/opt/project/data'
}

$composeBaseArgs = @()
if (Test-Path $sparkEnv) {
    $composeBaseArgs += @('--env-file', $sparkEnv)
    # --env-file 은 compose 서비스 환경에만 닿는다. --commons-hash-salt 는 이
    # 스크립트의 프로세스 환경을 읽으므로 여기서 따로 들여온다. 이미 설정돼
    # 있으면 그쪽을 쓴다.
    if (-not $env:COMMONS_HASH_SALT) {
        $saltLine = Select-String -Path $sparkEnv -Pattern '^COMMONS_HASH_SALT=' |
            Select-Object -Last 1
        if ($saltLine) {
            $env:COMMONS_HASH_SALT = $saltLine.Line -replace '^COMMONS_HASH_SALT=', ''
        }
    }
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
    param([string]$FromStage = 'q2')

    if ($FromStage -eq 'q2') {
        Invoke-SparkSubmit -JobPath '/opt/project/streaming/jobs/clean_events_job.py' -JobArguments @(
            '--input-path', "$dataRoot/raw_events",
            '--cleaned-path', "$dataRoot/processed/cleaned_events",
            '--bad-path', "$dataRoot/processed/bad_events",
            '--duplicate-path', "$dataRoot/processed/duplicate_events"
        )
    }
    $deriveArguments = @(
        '--input-path', "$dataRoot/processed/cleaned_events",
        '--sessionized-path', "$dataRoot/processed/sessionized_events",
        '--product-fact-path', "$dataRoot/processed/product_event_fact",
        '--purchase-fact-path', "$dataRoot/processed/purchase_fact",
        '--purchase-reason-fact-path', "$dataRoot/processed/purchase_reason_fact",
        '--review-event-fact-path', "$dataRoot/processed/review_event_fact",
        '--section-dwell-path', "$dataRoot/processed/section_dwell_agg",
        '--content-interest-path', "$dataRoot/processed/content_interest_fact",
        '--dim-product-path', "$dataRoot/processed/dim_product",
        '--dim-brand-path', "$dataRoot/processed/dim_brand",
        '--product-catalog-path', '/opt/project/batch/ingest/data/products_200.json',
        '--registered-product-path', '/opt/project/batch/ingest/data/serving/registered_products.jsonl',
        '--behavior-weights-path', '/opt/project/frontend/src/types/log.ts',
        '--commons-hash-salt', $env:COMMONS_HASH_SALT
    )
    if ($env:REGISTERED_PRODUCT_BRAND_PATH) {
        $deriveArguments += @(
            '--registered-product-brand-path', $env:REGISTERED_PRODUCT_BRAND_PATH
        )
    }
    if ($FromStage -ne 'q4') {
        Invoke-SparkSubmit -JobPath '/opt/project/streaming/jobs/derive_facts_job.py' -JobArguments $deriveArguments
    }
    $martArguments = @(
        '--sessionized-path', "$dataRoot/processed/sessionized_events",
        '--product-fact-path', "$dataRoot/processed/product_event_fact",
        '--purchase-fact-path', "$dataRoot/processed/purchase_fact",
        '--purchase-reason-fact-path', "$dataRoot/processed/purchase_reason_fact",
        '--dim-product-path', "$dataRoot/processed/dim_product",
        '--product-ingredient-path', '/opt/project/batch/ingest/data/serving/product_ingredient.csv',
        '--ingredient-vocab-path', '/opt/project/batch/ingest/data/serving/ingredient_vocab.csv',
        '--funnel-session-path', "$dataRoot/processed/funnel_session_fact",
        '--product-daily-path', "$dataRoot/marts/product_daily_kpi",
        '--funnel-daily-path', "$dataRoot/marts/funnel_daily_kpi",
        '--brand-daily-path', "$dataRoot/marts/brand_daily_kpi",
        '--product-repurchase-path', "$dataRoot/marts/product_repurchase_daily",
        '--brand-repurchase-path', "$dataRoot/marts/brand_repurchase_daily",
        '--purchase-reason-path', "$dataRoot/marts/purchase_reason_daily",
        '--reason-trait-map-path', '/opt/project/contracts/purchase-reason-trait-map.json',
        '--ingredient-weekly-path', "$dataRoot/marts/ingredient_weekly_interest",
        '--category-price-path', "$dataRoot/marts/category_price_reference",
        '--persona-segment-path', "$dataRoot/marts/persona_segment_daily_kpi",
        '--persona-bridge-path', '/opt/project/contracts/persona/data/pcall/bridge_persona_segment.jsonl',
        '--price-band-path', "$dataRoot/marts/brand_price_band_daily_kpi",
        '--banner-daily-path', "$dataRoot/marts/banner_daily",
        '--user-trait-daily-path', "$dataRoot/marts/user_trait_daily",
        '--cross-brand-daily-path', "$dataRoot/marts/cross_brand_daily",
        '--baseline-path', "$dataRoot/marts/analytics_baseline",
        '--trait-weights-path', '/opt/project/contracts/user-trait-weights.json',
        '--feature-vocab-path', '/opt/project/contracts/product-feature-vocab.json',
        '--affinity-lift-path', '/opt/project/batch/ingest/data/affinity_lift.csv',
        '--behavior-weights-path', '/opt/project/frontend/src/types/log.ts',
        '--dim-brand-path', "$dataRoot/processed/dim_brand",
        '--brand-cohort-path', "$dataRoot/marts/brand_cohort_dim",
        '--commons-cohort-path', "$dataRoot/marts/commons_cohort_weekly",
        '--content-interest-path', "$dataRoot/processed/content_interest_fact",
        '--section-dwell-path', "$dataRoot/processed/section_dwell_agg",
        '--content-daily-path', "$dataRoot/marts/content_daily_kpi",
        '--content-conversion-path', "$dataRoot/marts/content_conversion_daily",
        '--behavior-conversion-path', "$dataRoot/marts/behavior_conversion_daily",
        '--friction-daily-path', "$dataRoot/marts/friction_daily",
        '--exit-daily-path', "$dataRoot/marts/exit_daily",
        '--entry-source-daily-path', "$dataRoot/marts/entry_source_daily",
        '--product-exit-daily-path', "$dataRoot/marts/product_exit_daily",
        '--segment-content-daily-path', "$dataRoot/marts/segment_content_daily",
        '--segment-price-band-path', "$dataRoot/marts/segment_price_band_daily_kpi",
        '--cleaned-path', "$dataRoot/processed/cleaned_events",
        '--event-daily-path', "$dataRoot/marts/event_daily"
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
        '--purchase-fact-path', "$dataRoot/processed/purchase_fact",
        '--purchase-reason-fact-path', "$dataRoot/processed/purchase_reason_fact",
        '--review-event-fact-path', "$dataRoot/processed/review_event_fact",
        '--section-dwell-path', "$dataRoot/processed/section_dwell_agg",
        '--content-interest-path', "$dataRoot/processed/content_interest_fact",
        '--dim-product-path', "$dataRoot/processed/dim_product",
        '--dim-brand-path', "$dataRoot/processed/dim_brand",
        '--funnel-session-path', "$dataRoot/processed/funnel_session_fact",
        '--product-daily-path', "$dataRoot/marts/product_daily_kpi",
        '--funnel-daily-path', "$dataRoot/marts/funnel_daily_kpi",
        '--brand-daily-path', "$dataRoot/marts/brand_daily_kpi",
        '--product-repurchase-path', "$dataRoot/marts/product_repurchase_daily",
        '--brand-repurchase-path', "$dataRoot/marts/brand_repurchase_daily",
        '--purchase-reason-path', "$dataRoot/marts/purchase_reason_daily",
        '--reason-trait-map-path', '/opt/project/contracts/purchase-reason-trait-map.json',
        '--behavior-weights-path', '/opt/project/frontend/src/types/log.ts',
        '--ingredient-weekly-path', "$dataRoot/marts/ingredient_weekly_interest",
        '--category-price-path', "$dataRoot/marts/category_price_reference",
        '--persona-segment-path', "$dataRoot/marts/persona_segment_daily_kpi",
        '--price-band-path', "$dataRoot/marts/brand_price_band_daily_kpi",
        '--brand-cohort-path', "$dataRoot/marts/brand_cohort_dim",
        '--commons-cohort-path', "$dataRoot/marts/commons_cohort_weekly",
        '--banner-daily-path', "$dataRoot/marts/banner_daily",
        '--user-trait-daily-path', "$dataRoot/marts/user_trait_daily",
        '--cross-brand-daily-path', "$dataRoot/marts/cross_brand_daily",
        '--baseline-path', "$dataRoot/marts/analytics_baseline",
        '--content-daily-path', "$dataRoot/marts/content_daily_kpi",
        '--content-conversion-path', "$dataRoot/marts/content_conversion_daily",
        '--behavior-conversion-path', "$dataRoot/marts/behavior_conversion_daily",
        '--friction-daily-path', "$dataRoot/marts/friction_daily",
        '--exit-daily-path', "$dataRoot/marts/exit_daily",
        '--entry-source-daily-path', "$dataRoot/marts/entry_source_daily",
        '--product-exit-daily-path', "$dataRoot/marts/product_exit_daily",
        '--segment-content-daily-path', "$dataRoot/marts/segment_content_daily",
        '--segment-price-band-path', "$dataRoot/marts/segment_price_band_daily_kpi",
        '--event-daily-path', "$dataRoot/marts/event_daily",
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
            Invoke-BatchPipeline -FromStage $From
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
