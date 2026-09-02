$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$networkName = 'a306-data'

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw 'Docker CLI를 찾을 수 없습니다. Docker Desktop 또는 Docker Engine을 먼저 실행하세요.'
}

$existingNetworks = @(
    & docker network ls --filter "name=^${networkName}$" --format '{{.Name}}'
)
if ($LASTEXITCODE -ne 0) {
    throw 'Docker network 목록을 조회하지 못했습니다.'
}

if ($existingNetworks -notcontains $networkName) {
    & docker network create $networkName | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Docker network 생성에 실패했습니다: $networkName"
    }
}

Write-Output "Docker network '$networkName' is ready."
