param(
    [string]$Source = $PSScriptRoot + "\..",
    [string]$RuntimeHost = "",
    [switch]$DryRun
)
$ErrorActionPreference = 'Stop'

# Keep this script ASCII-safe at the logic level; messages use English + short CJK.

$SrcRoot = (Resolve-Path $Source).Path
$RuntimesSrc = Join-Path $SrcRoot "runtimes"

if (-not (Test-Path $RuntimesSrc)) {
    Write-Host "[ERR] runtimes not found: $RuntimesSrc" -ForegroundColor Red
    exit 1
}

# ---- 1. Resolve generation root ----
if (-not $RuntimeHost) {
    $profiles = Join-Path $env:APPDATA "dsh-desktop\harness\profiles"
    $desired = Join-Path $profiles "desired.json"
    if (Test-Path $desired) {
        $gen = (Get-Content $desired -Raw | ConvertFrom-Json).plugins |
               Where-Object { $_.name -eq '@gd/gp' } |
               Select-Object -First 1
    }
}
$genRoot = $RuntimeHost
if (-not $genRoot) {
    $profiles = Join-Path $env:APPDATA "dsh-desktop\harness\profiles"
    $genDirs = Get-ChildItem -Path (Join-Path $profiles ".generations\live") -Directory -ErrorAction SilentlyContinue |
               Where-Object { $_.Name -like 'gaussian+dsh-plugin-gaussian*' } |
               Sort-Object LastWriteTime -Descending
    if ($genDirs.Count -eq 0) {
        Write-Host "[ERR] no generation dir found under .generations\live" -ForegroundColor Red
        exit 1
    }
    $genRoot = $genDirs[0].FullName
}

Write-Host "[INFO] generation : $genRoot"

$snapshotRuntime = Join-Path $genRoot "source\gaussian+dsh-plugin-gaussian\runtimes"

# ---- 2. Show path budget ----
$exeName = "gaussian-backend.exe"
$deployedExe = Join-Path $snapshotRuntime "win32-x64\gaussian-backend\$exeName"
Write-Host "[INFO] deploy root : $snapshotRuntime"
Write-Host "[INFO] exe path len: $($deployedExe.Length) chars"

# The deepest real file inside the package historically is ~110 chars below
# _internal root. Guard against crossing MAX_PATH (260).
$budget = 260 - ($snapshotRuntime.Length)
Write-Host "[INFO] MAX_PATH budget for package = $budget chars (need >= ~180)"

if ($DryRun) {
    Write-Host "[DRY-RUN] would copy runtimes -> $snapshotRuntime"
    exit 0
}

# ---- 3. Sync runtimes into snapshot (independent copy) ----
if (Test-Path $snapshotRuntime) {
    $bak = "$snapshotRuntime.old-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
    Move-Item -LiteralPath $snapshotRuntime -Destination $bak
    Write-Host "[INFO] old runtimes backed up -> $(Split-Path $bak -Leaf)"
}

# Use robocopy for speed on 2000+ files
$rc = Start-Process -FilePath "robocopy.exe" `
      -ArgumentList @($RuntimesSrc, $snapshotRuntime, "/E", "/NFL", "/NDL", "/NJH", "/NJS", "/NP") `
      -NoNewWindow -Wait -PassThru
if ($rc.ExitCode -ge 8) {
    Write-Host "[ERR] robocopy failed with exit $($rc.ExitCode)" -ForegroundColor Red
    exit 1
}
Write-Host "[OK] runtimes synced into snapshot"

# ---- 4. Strip over-long documentation files (keep binaries intact) ----
$checker = Join-Path $PSScriptRoot "check_long_paths.ps1"
if (Test-Path $checker) {
    & powershell -NoProfile -ExecutionPolicy Bypass -File $checker -Root $snapshotRuntime -Limit 240 -Fix
    $lc = $LASTEXITCODE
    if ($lc -eq 2) {
        Write-Host "[WARN] still over limit; shortening deployment needed" -ForegroundColor Yellow
    }
} else {
    Write-Host "[WARN] check_long_paths.ps1 missing, skipping length audit" -ForegroundColor Yellow
}
