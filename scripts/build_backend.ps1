# build_backend.ps1 - Build gaussian-backend.exe (onedir, recommended first)
#
# Usage:
#   .\scripts\build_backend.ps1
#   .\scripts\build_backend.ps1 -PythonPath D:\...\python.exe
#
# M4 note:
#   The base env retains an old pathlib 1.0.1 backport dist-info (metadata only,
#   no package code), which makes PyInstaller 6.x exit immediately. This script
#   only RENAMES that dist-info temporarily and restores it in finally - it does
#   not uninstall or delete anything; the env ends identical to before.
#   Backup: docs/backups_20261020/pathlib-1.0.1.dist-info.bak
#
# Reminders:
#   - uvicorn must run workers=1 (scheduler is an in-process singleton)
#   - Frozen Sobko child needs SOBKO_PYTHON_EXE
#   - Gaussian / Multiwfn / VMD are external, not bundled

param(
    [string]$PythonPath = "D:\YDW\Trae_Gromacs\miniconda3\python.exe",
    [string]$SitePackages = "D:\YDW\Trae_Gromacs\miniconda3\Lib\site-packages",
    [switch]$OneFile
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

Write-Host "=== Gaussian Backend Build (onedir) ===" -ForegroundColor Cyan
Write-Host "Project root: $projectRoot"
Write-Host "Python: $PythonPath"

if (-not (Test-Path $PythonPath)) {
    Write-Host "ERROR: Python not found: $PythonPath" -ForegroundColor Red
    exit 1
}

$distInfo = Join-Path $SitePackages "pathlib-1.0.1.dist-info"
$renamed = Join-Path $SitePackages "pathlib-1.0.1.dist-info.__tmp_rename"
$renamedBack = $false
$buildOk = $false

Write-Host "Cleaning old build..."
Remove-Item -Path "build" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -Path "dist" -Recurse -Force -ErrorAction SilentlyContinue

$spec = "packaging\gaussian-backend.spec"

try {
    if (Test-Path $distInfo) {
        Rename-Item $distInfo $renamed
        $renamedBack = $true
        Write-Host "Temporarily hid pathlib backport metadata (will restore)." -ForegroundColor DarkYellow
    }

    $ver = & $PythonPath -m PyInstaller --version 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller not available: $ver"
    }
    Write-Host "PyInstaller version: $ver"

    # m3: 当前只实现 onedir spec（gaussian-backend.spec），没有独立的 one-file spec；
    # one-file 开关尚未实现，直接拒绝，避免"开关开启却仍打 onedir、找不到 exe 还报成功"。
    if ($OneFile) {
        throw "ONE-FILE 打包尚未实现：当前仅支持 onedir。请去掉 -OneFile 开关，或先补充独立 one-file spec。"
    }
    Write-Host "Building ONEDIR..." -ForegroundColor Green
    & $PythonPath -m PyInstaller --clean -y --distpath dist $spec

    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller build failed (exit $LASTEXITCODE)"
    }
    $buildOk = $true
}
catch {
    Write-Host "BUILD ERROR: $_" -ForegroundColor Red
}
finally {
    if ($renamedBack -and (Test-Path $renamed)) {
        Rename-Item $renamed $distInfo
        Write-Host "Restored pathlib backport metadata." -ForegroundColor DarkGreen
    }
}

if (-not $buildOk) {
    Write-Host "=== BUILD FAILED (metadata already restored) ===" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "=== Build Complete ===" -ForegroundColor Green

$exe = "dist\gaussian-backend\gaussian-backend.exe"
if (Test-Path $exe) {
    $size = (Get-Item $exe).Length / 1MB
    Write-Host "Output: $exe"
    Write-Host ("Size: {0:N1} MB" -f $size)
} else {
    # m3: 预期 onedir exe 缺失属于构建失败，不能只 WARNING 后以 0 退出
    Write-Host "ERROR: Expected onedir exe not found at $exe" -ForegroundColor Red
    Get-ChildItem -Path "dist" -Recurse -Filter "*.exe" -ErrorAction SilentlyContinue | Select-Object FullName
    exit 1
}

Write-Host ""
Write-Host "Next: run smoke test"
Write-Host "  .\scripts\smoke_test_backend.ps1"
exit 0
