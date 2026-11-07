param(
    [Parameter(Mandatory = $true)][string]$ProjectRoot,
    [int]$Port = 8765
)
$ErrorActionPreference = 'Stop'

try {
    $root = [IO.Path]::GetFullPath($ProjectRoot).TrimEnd('\')
    $expectedPython = [IO.Path]::GetFullPath((Join-Path $root '.venv\Scripts\python.exe'))
    $candidates = @(Get-CimInstance -ClassName Win32_Process -Filter "Name='python.exe' OR Name='pythonw.exe'")
    $matched = @()
    foreach ($item in $candidates) {
        $line = [string]$item.CommandLine
        $path = [string]$item.ExecutablePath
        $isServer = $line -match '(-m\s+uvicorn\s+server\.app:app)(\s|$)'
        $isOurEnv = $line.IndexOf($expectedPython, [StringComparison]::OrdinalIgnoreCase) -ge 0 -or
            [string]::Equals($path, $expectedPython, [StringComparison]::OrdinalIgnoreCase)
        if ($isServer -and $isOurEnv) { $matched += $item }
    }

    if ($matched.Count -eq 0) {
        $owners = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty OwningProcess -Unique)
        if ($owners.Count -gt 0) {
            Write-Host "[WARN] Port $Port is in use, but its process did not match this project."
            Write-Host '[WARN] No unrelated process was terminated.'
            exit 2
        }
        Write-Host '[OK] No VideoKnowledge server process is running in this project.'
        exit 0
    }
    $stopMarker = Join-Path $root ".venv\.vkn_stop_requested"
    Set-Content -Path $stopMarker -Value "user-stop" -Encoding Ascii
    foreach ($item in $matched) {
        $targetId = [int]$item.ProcessId
        Write-Host "[INFO] Terminating VideoKnowledge ASR PID $targetId"
        Stop-Process -Id $targetId -Force -ErrorAction Stop
    }
    Start-Sleep -Milliseconds 400
    $left = @($matched | Where-Object { Get-Process -Id $_.ProcessId -ErrorAction SilentlyContinue })
    if ($left.Count -gt 0) {
        Write-Host '[ERROR] A matching ASR process is still alive.'
        exit 1
    }
    Write-Host '[OK] Matching ASR processes stopped. Other Python processes were not touched.'
    exit 0
} catch {
    Write-Host ('[ERROR] Shutdown failed: ' + $_.Exception.Message)
    exit 1
}
