# deploy_runtime.ps1 - 把 onedir 产物部署到 DSH runtimes 约定目录并生成 sha256 清单
#
# 用法：
#   .\scripts\deploy_runtime.ps1
#
# 产物布局（对齐参考插件 @aifs）：
#   runtimes/win32-x64/runtime.json
#   runtimes/win32-x64/gaussian-backend/gaussian-backend.exe
#   runtimes/win32-x64/gaussian-backend/_internal/...
#
# runtime.json 供前端 managed spawn 定位 exe 并做完整性校验。

param(
    [string]$Version = "0.2.0",
    [string]$Python = "3.13.13"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

$src = "dist\gaussian-backend"
$runtimeDir = "runtimes\win32-x64"
$dst = Join-Path $runtimeDir "gaussian-backend"

if (-not (Test-Path (Join-Path $src "gaussian-backend.exe"))) {
    Write-Host "ERROR: built exe not found. Run build_backend.ps1 first." -ForegroundColor Red
    exit 1
}

Write-Host "Deploying $src -> $dst" -ForegroundColor Cyan
Remove-Item $dst -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $dst | Out-Null
Copy-Item (Join-Path $src "*") $dst -Recurse -Force

# 部署内嵌 OpenBabel 运行时（便携，不要求目标机安装）
$obSrc = "thirdparty\openbabel"
$obDst = Join-Path $runtimeDir "openbabel"
if (Test-Path $obSrc) {
    Remove-Item $obDst -Recurse -Force -ErrorAction SilentlyContinue
    Copy-Item $obSrc $obDst -Recurse -Force
    Write-Host "Embedded OpenBabel deployed -> $obDst" -ForegroundColor DarkGreen
}

# 生成 sha256 清单（相对 runtimeDir 的路径）
$files = @()
Get-ChildItem $dst -Recurse -File | ForEach-Object {
    $rel = $_.FullName.Substring((Resolve-Path $runtimeDir).Path.Length + 1)
    $hash = (Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLower()
    $files += [ordered]@{ path = ($rel -replace "\\", "/"); sha256 = $hash }
}

$manifest = [ordered]@{
    version = $Version
    target  = "win32-x64"
    executable = "gaussian-backend/gaussian-backend.exe"
    python  = $Python
    files   = $files
}

$manifest | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $runtimeDir "runtime.json") -Encoding utf8

Write-Host "Deployed $($files.Count) files." -ForegroundColor Green
Write-Host "Manifest: $runtimeDir\runtime.json"
Write-Host "Exe:      $dst\gaussian-backend.exe"
