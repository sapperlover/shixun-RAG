param(
    [Parameter(Mandatory=$true)][string]$InputPdf,
    [Parameter(Mandatory=$true)][string]$OutputJsonl,
    [ValidateRange(800,4000)][int]$RenderWidth = 1800,
    [string]$PageNumbers = ''
)
# Run with Windows PowerShell 5 (powershell.exe), not PowerShell 7.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Storage.StorageFile,Windows.Storage,ContentType=WindowsRuntime]
$null = [Windows.Data.Pdf.PdfDocument,Windows.Data.Pdf,ContentType=WindowsRuntime]
$null = [Windows.Storage.Streams.InMemoryRandomAccessStream,Windows.Storage.Streams,ContentType=WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder,Windows.Graphics.Imaging,ContentType=WindowsRuntime]
$null = [Windows.Media.Ocr.OcrEngine,Windows.Foundation,ContentType=WindowsRuntime]
$null = [Windows.Globalization.Language,Windows.Globalization,ContentType=WindowsRuntime]

function Await-WinRT($Operation, $ResultType) {
    $method = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
        $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
        $_.IsGenericMethod -eq ($null -ne $ResultType) -and (
            ($null -ne $ResultType -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1') -or
            ($null -eq $ResultType -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncAction')
        )
    } | Select-Object -First 1
    if ($ResultType) { $method = $method.MakeGenericMethod($ResultType) }
    $task = $method.Invoke($null, @($Operation))
    $task.Wait()
    if ($ResultType) { $task.Result }
}

$source = (Resolve-Path -LiteralPath $InputPdf).Path
$target = [IO.Path]::GetFullPath($OutputJsonl)
if (Test-Path -LiteralPath $target) { throw "Output exists; select a new path: $target" }
$language = New-Object Windows.Globalization.Language('zh-Hans-CN')
$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($language)
if ($null -eq $engine) { throw 'Windows Simplified Chinese OCR language is not installed.' }
$file = Await-WinRT ([Windows.Storage.StorageFile]::GetFileFromPathAsync($source)) ([Windows.Storage.StorageFile])
$pdf = Await-WinRT ([Windows.Data.Pdf.PdfDocument]::LoadFromFileAsync($file)) ([Windows.Data.Pdf.PdfDocument])
$hasher = [Security.Cryptography.SHA256]::Create()
$sourceStream = [IO.File]::OpenRead($source)
try { $hash = ([BitConverter]::ToString($hasher.ComputeHash($sourceStream))).Replace('-','').ToLowerInvariant() }
finally { $sourceStream.Dispose(); $hasher.Dispose() }
$records = New-Object 'System.Collections.Generic.List[string]'
$selectedPages = @()
if ($PageNumbers) {
    $selectedPages = @($PageNumbers.Split(',') | ForEach-Object { [int]$_.Trim() } | Sort-Object -Unique)
    if (@($selectedPages | Where-Object { $_ -lt 1 -or $_ -gt $pdf.PageCount }).Count -gt 0) {
        throw 'Selected page is outside the PDF page range.'
    }
}
for ($i=0; $i -lt $pdf.PageCount; $i++) {
    if ($selectedPages.Count -gt 0 -and ($i+1) -notin $selectedPages) { continue }
    $page = $pdf.GetPage($i)
    $stream = New-Object Windows.Storage.Streams.InMemoryRandomAccessStream
    $bitmap = $null
    try {
        $options = New-Object Windows.Data.Pdf.PdfPageRenderOptions
        $options.DestinationWidth = $RenderWidth
        Await-WinRT ($page.RenderToStreamAsync($stream,$options)) $null
        $decoder = Await-WinRT ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
        $bitmap = Await-WinRT ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
        $result = Await-WinRT ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
        # OcrResult.Text flattens the page; preserve the engine's detected lines.
        $raw = ($result.Lines | ForEach-Object { $_.Text }) -join "`n"
        # Remove only spaces between adjacent Han characters; preserve numbers and symbols.
        $clean = [regex]::Replace($raw, '(?<=[\u3400-\u4DBF\u4E00-\u9FFF])[\t ]+(?=[\u3400-\u4DBF\u4E00-\u9FFF])', '')
        $record = [ordered]@{
            source_file = [IO.Path]::GetFileName($source)
            source_sha256 = $hash
            page = $i+1
            page_count = $pdf.PageCount
            raw_text = $raw
            text = $clean
            ocr = $true
            needs_review = $true
            ocr_engine = 'Windows.Media.Ocr'
            ocr_language = 'zh-Hans-CN'
            render_width = $RenderWidth
        }
        $records.Add(($record | ConvertTo-Json -Compress))
    } finally {
        if ($null -ne $bitmap) { $bitmap.Dispose() }
        $stream.Dispose()
        $page.Dispose()
    }
}
$parent = [IO.Path]::GetDirectoryName($target)
[IO.Directory]::CreateDirectory($parent) | Out-Null
# Write only after every page succeeds. CreateNew prevents concurrent overwrite.
$outStream = [IO.File]::Open($target,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write)
$writer = New-Object IO.StreamWriter($outStream,(New-Object Text.UTF8Encoding($false)))
try { foreach ($record in $records) { $writer.WriteLine($record) } }
finally { $writer.Dispose() }
Write-Output "OCR completed: $($records.Count) selected pages -> $target"
