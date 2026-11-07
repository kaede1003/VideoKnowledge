param(
    [string]$ExtensionId = '',
    [switch]$CheckOnly
)
$ErrorActionPreference = 'Stop'
try {
    if (-not $ExtensionId) {
        Write-Host 'Copy the 32-character extension ID from edge://extensions/ or the Video Knowledge settings page.'
        $ExtensionId = Read-Host 'Extension ID'
    }
    $ExtensionId = $ExtensionId.Trim()
    if ($ExtensionId -cnotmatch '^[a-p]{32}$') { throw 'Invalid extension ID. Expected exactly 32 lower-case letters a-p.' }
    $origin = 'chrome-extension://' + $ExtensionId
    Write-Host ('This extension: ' + $origin)
    Write-Host 'Local Ollama needs NO API key. This utility does not stop any processes or change OLLAMA_HOST.'
    if (-not $CheckOnly) {
        $priorUser = [Environment]::GetEnvironmentVariable('OLLAMA_ORIGINS', 'User')
        $values = @([Environment]::GetEnvironmentVariable('OLLAMA_ORIGINS','Machine'), $priorUser, $env:OLLAMA_ORIGINS)
        $items = @(($values -join ',').Split(',') | ForEach-Object { $_.Trim() } | Where-Object { $_ })
        $merged = (@($items + $origin | Select-Object -Unique) -join ',')
        $backupDir = Join-Path $env:LOCALAPPDATA 'VideoKnowledge\origin-backups'
        New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
        $backup = Join-Path $backupDir ('origins-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '.json')
        @{ previousUserValue = $priorUser; extensionOrigin = $origin; time = (Get-Date).ToString('o') } |
            ConvertTo-Json | Set-Content -Path $backup -Encoding UTF8
        [Environment]::SetEnvironmentVariable('OLLAMA_ORIGINS', $merged, 'User')
        $env:OLLAMA_ORIGINS = $merged
        Write-Host '[OK] Added only this extension origin. Existing allowed origins have been retained.'
        Write-Host ('Backup: ' + $backup)
        if ($items -contains '*' -or $items -contains 'chrome-extension://*') {
            Write-Warning 'Your previous configuration already allowed broad origins. This utility retained it, but did not add that wildcard.'
        }
        Write-Host 'IMPORTANT: Quit Ollama from the system tray, then reopen it from the Windows Start menu.'
        Write-Host 'Closing its window, reloading Edge, or restarting only ASR is not enough.'
        Write-Host 'Finish or cancel your current model tasks before restarting Ollama.'
        Write-Host 'After restart, run CHECK_OLLAMA_ORIGIN.bat and verify inference in the extension settings.'
    }
    function Check-Endpoint([string]$Path, [string]$Method, [bool]$WithOrigin) {
        $request = [System.Net.HttpWebRequest]::Create('http://127.0.0.1:11434' + $Path)
        $request.Proxy = $null
        $request.Method = $Method
        $request.Timeout = 6000
        if ($WithOrigin) { $request.Headers['Origin'] = $origin }
        if ($Method -eq 'OPTIONS') { $request.Headers['Access-Control-Request-Method'] = 'POST'; $request.Headers['Access-Control-Request-Headers'] = 'content-type' }
        $response = $null
        try {
            $response = $request.GetResponse()
            return [int]$response.StatusCode
        } catch [System.Net.WebException] {
            if ($_.Exception.Response) { $response = $_.Exception.Response; return [int]$response.StatusCode }
            return 0
        } finally { if ($response) { $response.Close() } }
    }
    $plain = Check-Endpoint '/api/tags' 'GET' $false
    $with = Check-Endpoint '/api/tags' 'GET' $true
    $preflight = Check-Endpoint '/v1/chat/completions' 'OPTIONS' $true
    Write-Host ('HTTP tags without Origin: ' + $plain)
    Write-Host ('HTTP tags with this Origin: ' + $with)
    Write-Host ('HTTP POST preflight with this Origin: ' + $preflight)
    if ($plain -eq 0) { Write-Warning 'Cannot reach local Ollama. Start Ollama; ASR on 8765 is a different service.' }
    elseif ($plain -eq 200 -and ($with -eq 403 -or $preflight -eq 403)) {
        Write-Warning 'The running service rejects this origin. After saving, fully quit and reopen Ollama.'
    } elseif ($plain -eq 200 -and $with -eq 200 -and $preflight -ge 200 -and $preflight -lt 300) {
        Write-Host '[OK] Local origin checks passed. This is NOT a real model inference test; use the extension Verify button next.'
    } else { Write-Warning 'Unexpected response. Check Ollama logs, local proxy settings and endpoint. Do not insert a cloud API key.' }
    exit 0
} catch {
    Write-Host ('[ERROR] ' + $_.Exception.Message) -ForegroundColor Red
    exit 1
}
