# smoke_test_backend.ps1 — 冒烟测试 gaussian-backend.exe
#
# 启动 exe，检查 /v1/health，然后关闭。
# 用于验证打包后的 exe 能正常启动、依赖完整。

$ErrorActionPreference = "Continue"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

Write-Host "=== Gaussian Backend Smoke Test ===" -ForegroundColor Cyan

# 找 exe
$exePaths = @(
    "runtimes\win32-x64\gaussian-backend\gaussian-backend.exe",
    "dist\gaussian-backend\gaussian-backend.exe",
    "dist\gaussian-backend.exe",
    "dist\onedir\gaussian-backend\gaussian-backend.exe"
)

$exe = $null
foreach ($p in $exePaths) {
    if (Test-Path $p) {
        $exe = $p
        break
    }
}

if (-not $exe) {
    Write-Host "ERROR: gaussian-backend.exe not found. Run build first." -ForegroundColor Red
    exit 1
}

Write-Host "Using: $exe"

# 设置环境变量
$env:GAUSSIAN_BACKEND_PORT = "8799"  # 用不同端口避免冲突
$env:GAUSSIAN_MANAGED_TOKEN = "smoke_test_token"

# 启动 exe
Write-Host "Starting backend..."
$proc = Start-Process -FilePath $exe -PassThru -NoNewWindow `
    -RedirectStandardOutput "smoke_stdout.log" `
    -RedirectStandardError "smoke_stderr.log"

Write-Host "PID: $($proc.Id)"

# 轮询 health 端点
$ready = $false
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 1
    try {
        $resp = Invoke-RestMethod -Uri "http://127.0.0.1:8799/v1/health" -TimeoutSec 2
        if ($resp.ok -and $resp.service -eq "gaussian-dsh-backend") {
            $ready = $true
            Write-Host "HEALTH OK after $($i+1)s" -ForegroundColor Green
            Write-Host "  Version: $($resp.version)"
            Write-Host "  Instance: $($resp.instance_id)"
            break
        }
    } catch {
        # 还没就绪
    }
}

if (-not $ready) {
    Write-Host "HEALTH CHECK FAILED (timeout 30s)" -ForegroundColor Red
    Write-Host "=== stderr ==="
    Get-Content "smoke_stderr.log" -ErrorAction SilentlyContinue | Select-Object -Last 30
    Write-Host "=== stdout ==="
    Get-Content "smoke_stdout.log" -ErrorAction SilentlyContinue | Select-Object -Last 30
    Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
    exit 1
}

# 测试 capabilities 端点
Write-Host ""
Write-Host "Testing /v1/postprocess/capabilities..."
try {
    $cap = Invoke-RestMethod -Uri "http://127.0.0.1:8799/v1/postprocess/capabilities" -TimeoutSec 5
    Write-Host "  formchk: $($cap.formchk.exists)"
    Write-Host "  multiwfn: $($cap.multiwfn.exists)"
    Write-Host "  vmd: $($cap.vmd.exists)"
} catch {
    Write-Host "  WARNING: capabilities endpoint failed: $_" -ForegroundColor Yellow
}

# 关闭后端（用 shutdown API）
Write-Host ""
Write-Host "Shutting down backend..."
try {
    Invoke-RestMethod -Uri "http://127.0.0.1:8799/v1/admin/shutdown" `
        -Method Post `
        -Headers @{ "Authorization" = "Bearer smoke_test_token" } `
        -TimeoutSec 5 | Out-Null
} catch {
    Write-Host "  shutdown API failed, killing process..." -ForegroundColor Yellow
    Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
}

# 等待退出
Start-Sleep -Seconds 2
if (-not $proc.HasExited) {
    Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
}

# 清理日志
Remove-Item "smoke_stdout.log" -ErrorAction SilentlyContinue
Remove-Item "smoke_stderr.log" -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "=== Smoke Test PASSED ===" -ForegroundColor Green
