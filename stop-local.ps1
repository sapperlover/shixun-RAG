$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$stateFile = Join-Path $PSScriptRoot '.cache/local-processes.json'
if (-not (Test-Path -LiteralPath $stateFile)) { Write-Host 'No local process record.'; exit 0 }
$state = Get-Content -LiteralPath $stateFile -Raw | ConvertFrom-Json
foreach ($kind in @('api', 'web')) {
    $processId = $state.$kind
    $recordedStart = $state.($kind + '_started')
    if (-not $processId) { continue }
    $process = Get-CimInstance Win32_Process -Filter ('ProcessId = ' + $processId)
    if (-not $process) { continue }
    $recordedUtc = if ($recordedStart -is [DateTime]) { $recordedStart.ToUniversalTime() } elseif ($recordedStart) { [DateTimeOffset]::Parse($recordedStart).UtcDateTime } else { $null }
    if (-not $recordedUtc -or [Math]::Abs(($process.CreationDate.ToUniversalTime() - $recordedUtc).TotalSeconds) -gt 2) {
        throw "Process identity changed for $kind; refusing to stop it."
    }
    if ($kind -eq 'api') {
        $expected = (Resolve-Path -LiteralPath '.venv/Scripts/python.exe').Path
        if ($process.ExecutablePath -ne $expected -or $process.CommandLine -notmatch 'scripts.serve_api') { throw 'API process is not from this project' }
    } elseif ($process.Name -ne 'cmd.exe' -or $process.CommandLine -notmatch 'npm.cmd run dev.*--port 8081') {
        throw 'Web process is not the recorded development server'
    }
    taskkill.exe /PID $processId /T /F | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Could not stop $kind" }
}
Write-Host 'Stopped this project local API and web. Neo4j data and container are preserved.'
