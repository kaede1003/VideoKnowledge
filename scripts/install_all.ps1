# Windows PowerShell 5.1 compatible bootstrap. No remote script execution.
[CmdletBinding()]
param(
    [ValidateSet('all','core','models','text','vision','asr','speaker','review','video','diagnose')]
    [string]$Profile = 'all',
    [ValidateSet('keep','legacy','ollama17','qwen17','qwen06','whisper-large','whisper-turbo')]
    [string]$AsrProfile = 'keep',
    [string]$OllamaAsrModel = '',
    [switch]$Plan,
    [switch]$Yes,
    [switch]$SkipSystemTools
)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $Root
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUNBUFFERED = '1'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$OutputEncoding = [Console]::OutputEncoding

function Test-ProjectPython {
    param([string]$Exe, [string[]]$Prefix = @())
    if (-not $Exe) { return $false }
    try {
        & $Exe @Prefix -c "import struct,sys;sys.exit(0 if sys.version_info[:2] in ((3,11),(3,12)) and struct.calcsize('P')==8 else 2)" *> $null
        return $LASTEXITCODE -eq 0
    } catch { return $false }
}

function Find-Python {
    $launcher = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($launcher) {
        foreach ($version in @('-3.11','-3.12')) {
            if (Test-ProjectPython -Exe $launcher.Source -Prefix @($version)) {
                $line = & $launcher.Source $version -c 'import sys;print(sys.executable)'
                return ([string]($line | Select-Object -Last 1)).Trim()
            }
        }
    }
    $candidates = @()
    $command = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($command) { $candidates += $command.Source }
    foreach ($base in @($env:LOCALAPPDATA, $env:ProgramFiles)) {
        if ($base) {
            foreach ($version in @('311','312')) {
                $candidates += (Join-Path $base "Programs\Python\Python$version\python.exe")
                $candidates += (Join-Path $base "Python$version\python.exe")
            }
        }
    }
    foreach ($candidate in $candidates) {
        if ((Test-Path -LiteralPath $candidate) -and (Test-ProjectPython -Exe $candidate)) { return $candidate }
    }
    return $null
}

try {
    $VenvPython = Join-Path $Root '.venv\Scripts\python.exe'
    $Diagnostic = $Plan -or ($Profile -eq 'diagnose')
    if (Test-Path -LiteralPath $VenvPython) {
        if (-not (Test-ProjectPython -Exe $VenvPython)) {
            throw 'Existing .venv is not a usable 64-bit Python 3.11/3.12. It was NOT deleted. Repair/choose that environment before continuing.'
        }
        $Python = $VenvPython
    } else {
        $Python = Find-Python
        if (-not $Python) {
            if ($Diagnostic -or $SkipSystemTools) { throw 'Python 3.11/3.12 x64 not found. No system software was installed.' }
            $winget = Get-Command winget.exe -ErrorAction SilentlyContinue
            if (-not $winget) { throw 'Python and WinGet were not found. Install Python 3.11 x64 from python.org, then rerun INSTALL_ALL.bat.' }
            Write-Host '[MISSING] Python 3.11 x64 is required.'
            $Allowed = $Yes.IsPresent
            if (-not $Allowed) {
                $Allowed = (Read-Host 'Install Python.Python.3.11 using WinGet and accept its agreements? [Y/N]') -match '^(y|yes)$'
            }
            if (-not $Allowed) { throw 'Python installation not approved. No environment was deleted.' }
            & $winget.Source install --id Python.Python.3.11 --exact --source winget --scope user --accept-source-agreements --accept-package-agreements --disable-interactivity
            if ($LASTEXITCODE -ne 0) { throw "Python installer exited $LASTEXITCODE. Review its output and rerun." }
            $Python = Find-Python
            if (-not $Python) { throw 'Python installation finished but the interpreter is not visible yet. Reopen this terminal and rerun.' }
        }
        if (-not $Diagnostic) {
            if (Test-Path -LiteralPath (Join-Path $Root '.venv')) {
                throw 'An incomplete .venv exists. It was NOT overwritten. Inspect/repair it before rerunning.'
            }
            Write-Host '[INFO] Creating this project .venv; no global pip installation.'
            & $Python -m venv (Join-Path $Root '.venv')
            if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed.' }
            $Python = $VenvPython
        }
    }
    $runnerArgs = @('-u', (Join-Path $PSScriptRoot 'install_all.py'), '--profile', $Profile, '--asr-profile', $AsrProfile)
    if ($OllamaAsrModel) { $runnerArgs += @('--ollama-asr-model', $OllamaAsrModel) }
    if ($Plan) { $runnerArgs += '--plan' }
    if ($Yes) { $runnerArgs += '--yes' }
    if ($SkipSystemTools) { $runnerArgs += '--skip-system-tools' }
    & $Python @runnerArgs
    exit $LASTEXITCODE
} catch {
    Write-Host ('[ERROR] ' + $_.Exception.Message)
    Write-Host '[HELP] Existing notes, model caches and ASR_SETTINGS.bat are unchanged.'
    exit 1
}
