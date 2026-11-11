param([switch]$CheckOnly, [switch]$RebuildEmbeddings)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

if (-not (Test-Path -LiteralPath '.env')) {
    Copy-Item -LiteralPath '.env.example' -Destination '.env'
}
$config = @{}
foreach ($line in Get-Content -LiteralPath '.env' -Encoding UTF8) {
    if ($line -match '^\s*([A-Z_][A-Z0-9_]*)\s*=\s*(.*?)\s*$') {
        $config[$Matches[1]] = $Matches[2].Trim('"').Trim("'")
    }
}
$required = @('NEO4J_PASSWORD', 'LLM_BASE_URL', 'LLM_MODEL', 'LLM_API_KEY', 'EMBEDDING_BASE_URL', 'EMBEDDING_MODEL', 'EMBEDDING_API_KEY', 'EMBEDDING_DIMENSIONS')
$missing = @($required | Where-Object { -not $config[$_] })
if ($missing.Count -gt 0) {
    Write-Host ('Fill these fields in .env: ' + ($missing -join ', '))
    exit 1
}
docker compose config --quiet
if ($LASTEXITCODE -ne 0) { throw 'Invalid Compose configuration' }
if ($CheckOnly) {
    Write-Host 'Required configuration is present. API connectivity has not been tested.'
    exit 0
}
docker compose build
if ($LASTEXITCODE -ne 0) { throw 'Docker image build failed' }
if ($RebuildEmbeddings) {
    docker compose run --rm initialize python -m scripts.initialize_system --rebuild-embeddings
    if ($LASTEXITCODE -ne 0) { throw 'Embedding rebuild failed' }
}
docker compose up -d
if ($LASTEXITCODE -ne 0) { throw 'Startup failed; inspect docker compose logs initialize' }
$port = if ($config['WEB_PORT']) { $config['WEB_PORT'] } else { '8081' }
Write-Host "Open http://localhost:$port . Startup may take a minute; use docker compose ps to inspect status."
