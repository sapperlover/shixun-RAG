param([switch]$SkipInitialize, [switch]$RebuildEmbeddings)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not $SkipInitialize) {
    & (Join-Path $PSScriptRoot 'start.ps1') -CheckOnly
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    py -3.11 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.11 is required' }
    & $python -m pip install -r backend/requirements.lock
    if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed' }
}
foreach ($port in @(8001, 8081)) {
    if (Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue) {
        throw "Local port $port is already in use."
    }
}
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --wait --wait-timeout 120 neo4j
if ($LASTEXITCODE -ne 0) { throw 'Neo4j did not become ready' }
$env:PYTHONPATH = Join-Path $PSScriptRoot 'backend'
$env:NEO4J_URI = 'bolt://127.0.0.1:7688'
if (-not $SkipInitialize) {
    $initializeArgs = @('-m', 'scripts.initialize_system')
    if ($RebuildEmbeddings) { $initializeArgs += '--rebuild-embeddings' }
    & $python @initializeArgs
    if ($LASTEXITCODE -ne 0) { throw 'Initialization failed' }
}
if (-not (Test-Path -LiteralPath 'frontend/node_modules')) {
    Push-Location -LiteralPath (Join-Path $PSScriptRoot 'frontend')
    try {
        npm.cmd ci
        if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed' }
    } finally { Pop-Location }
}
$logDir = Join-Path $PSScriptRoot '.cache'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$api = Start-Process -FilePath $python -ArgumentList '-m','scripts.serve_api' -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logDir 'api.out.log') -RedirectStandardError (Join-Path $logDir 'api.err.log')
$env:VITE_API_TARGET = 'http://127.0.0.1:8001'
$web = Start-Process -FilePath 'cmd.exe' -ArgumentList '/d','/c','npm.cmd run dev -- --host 127.0.0.1 --port 8081 --strictPort' -WorkingDirectory (Join-Path $PSScriptRoot 'frontend') -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logDir 'web.out.log') -RedirectStandardError (Join-Path $logDir 'web.err.log')
@{ api = $api.Id; web = $web.Id; api_started = $api.StartTime.ToUniversalTime().ToString('o'); web_started = $web.StartTime.ToUniversalTime().ToString('o') } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $logDir 'local-processes.json') -Encoding UTF8
Write-Host 'Open http://localhost:8081 . Logs are in .cache; process IDs are in local-processes.json.'
