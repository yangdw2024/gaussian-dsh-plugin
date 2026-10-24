param(
    [string]$Root = "runtimes",
    [int]$Limit = 260,
    [switch]$Fix,
    [switch]$Quiet
)
$ErrorActionPreference = 'Stop'

function Get-LongPathCount {
    param([string]$BasePath, [int]$MaxLen)
    if (-not (Test-Path $BasePath)) { return @{ Count = 0; Longest = 0; Samples = @() } }
    $items = Get-ChildItem -Path $BasePath -Recurse -File -Force -ErrorAction SilentlyContinue
    $longest = 0
    $over = New-Object System.Collections.ArrayList
    foreach ($f in $items) {
        $len = $f.FullName.Length
        if ($len -gt $longest) { $longest = $len }
        if ($len -gt $MaxLen) { [void]$over.Add($f) }
    }
    return @{ Count = $over.Count; Longest = $longest; Samples = $over }
}

if (-not (Test-Path $Root)) {
    if (-not $Quiet) { Write-Host "[SKIP] runtimes 目录不存在: $Root" }
    exit 0
}

$result = Get-LongPathCount -BasePath $Root -MaxLen $Limit

if (-not $Quiet) {
    Write-Host "[INFO] 扫描根目录 : $Root"
    Write-Host "[INFO] 最长文件路径: $($result.Longest) 字符"
    Write-Host "[INFO] 超过 $Limit 字符: $($result.Count) 个"
}

if ($result.Count -eq 0) {
    if (-not $Quiet) { Write-Host "[OK] 全部路径长度不超过 $Limit，PyInstaller onedir 可安全启动" }
    exit 0
}

if (-not $Fix) {
    Write-Host "[ERR] 发现 $($result.Count) 个超长路径，PyInstaller bootloader 在 MAX_PATH 之外会静默失败。" -ForegroundColor Red
    Write-Host "[ERR] 前 5 个示例:" -ForegroundColor Red
    $result.Samples | Select-Object -First 5 | ForEach-Object {
        $rel = $_.FullName.Substring((Resolve-Path $Root).Path.Length + 1)
        Write-Host "      $($_.FullName.Length) 字符  $rel"
    }
    Write-Host "提示：加 -Fix 删除纯文档/许可类超长文件（不影响运行）" -ForegroundColor Yellow
    exit 1
}

# ---- 修复模式：优先删除安全可删的文档类超长文件 ----
$safePatterns = @(
    '\.dist-info[\\/]licenses[\\/]',
    '\.dist-info[\\/]LICENSE',
    '\.dist-info[\\/]COPYING',
    '\.dist-info[\\/]NOTICE',
    '\.dist-info[\\/]AUTHORS',
    '_tcl_data[\\/].*[\\/]demos[\\/]',
    '\.(md|rst|txt)$'
)
$removed = 0
$remaining = New-Object System.Collections.ArrayList

foreach ($f in $result.Samples) {
    $path = $f.FullName
    $isSafe = $false
    foreach ($p in $safePatterns) {
        if ($path -match $p) { $isSafe = $true; break }
    }
    if ($isSafe) {
        try {
            Remove-Item -LiteralPath $path -Force -ErrorAction Stop
            $removed++
        } catch {
            [void]$remaining.Add($f)
        }
    } else {
        [void]$remaining.Add($f)
    }
}

#if (-not $Quiet) { Write-Host "[INFO] 已删除 $removed 个超长文档类文件" }

if (-not $Quiet) {
    Write-Host "[INFO] 已删除 $removed 个超长文档/许可类文件（不影响运行）"
    if ($remaining.Count -gt 0) {
        Write-Host "[WARN] 仍有 $($remaining.Count) 个超长路径文件无法通过删除解决:" -ForegroundColor Yellow
        $remaining | Select-Object -First 5 | ForEach-Object { Write-Host "       $($_.FullName.Length) 字符  $($_.Name)" }
        Write-Host "[WARN] 若仍超限，请缩短部署根目录（如改用短路径 junction 或启用系统 LongPathsEnabled）" -ForegroundColor Yellow
    }
}

$after = Get-LongPathCount -BasePath $Root -MaxLen $Limit
if (-not $Quiet) {
    Write-Host "[RESULT] 修复后 最长路径=$($after.Longest) 字符, 超限=$($after.Count) 个"
}

if ($after.Count -eq 0) {
    if (-not $Quiet) { Write-Host "[OK] 长路径问题已消除" -ForegroundColor Green }
    exit 0
} else {
    exit 2
}
