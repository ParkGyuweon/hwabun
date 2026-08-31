$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$composeFile = Join-Path $PSScriptRoot 'docker-compose.yml'

$topic = $env:ACTIVITY_EVENTS_TOPIC
if ([string]::IsNullOrWhiteSpace($topic)) {
    $topic = 'activity-events'
}

$partitions = $env:ACTIVITY_EVENTS_PARTITIONS
if ([string]::IsNullOrWhiteSpace($partitions)) {
    $partitions = '3'
}

$replicationFactor = $env:KAFKA_TOPIC_REPLICATION_FACTOR
if ([string]::IsNullOrWhiteSpace($replicationFactor)) {
    $replicationFactor = '1'
}

$retentionMs = $env:KAFKA_TOPIC_RETENTION_MS
if ([string]::IsNullOrWhiteSpace($retentionMs)) {
    $retentionMs = '86400000'
}

$createArgs = @(
    '/opt/kafka/bin/kafka-topics.sh',
    '--bootstrap-server', 'kafka:19092',
    '--create',
    '--if-not-exists',
    '--topic', $topic,
    '--partitions', $partitions,
    '--replication-factor', $replicationFactor,
    '--config', 'cleanup.policy=delete',
    '--config', "retention.ms=$retentionMs"
)

& docker compose --file $composeFile exec -T kafka @createArgs
if ($LASTEXITCODE -ne 0) {
    throw "Kafka Topic 생성에 실패했습니다: $topic"
}

$describeArgs = @(
    '/opt/kafka/bin/kafka-topics.sh',
    '--bootstrap-server', 'kafka:19092',
    '--describe',
    '--topic', $topic
)

& docker compose --file $composeFile exec -T kafka @describeArgs
if ($LASTEXITCODE -ne 0) {
    throw "Kafka Topic 조회에 실패했습니다: $topic"
}
