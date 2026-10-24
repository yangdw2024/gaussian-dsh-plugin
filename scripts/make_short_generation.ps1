# 从旧 generation 目录派生新的短名 generation 目录
#
# 背景：DSH 的 generationId() = safeName + "+" + version + "+" + lockfileHash[0:12]
#       package name "@gaussian/dsh-plugin-gaussian" 会变成 "gaussian+dsh-plugin-gaussian"，
#       使 generation 目录名长达 79 字符，导致 Windows 深层路径击穿 MAX_PATH 260，
#       PyInstaller onedir 后端的 .pyd 无法加载（ModuleNotFoundError / 文件名或扩展名太长）。
#
# 本脚本用 robocopy 做真实文件复制（不走 junction / symlink），创建短名 generation 目录。
#
# 重要：清理长路径目录必须用 robocopy /MIR 空镜像，而不是 Remove-Item，
#       因为 PowerShell 的 Remove-Item 也会撞 260 字符限制。
#
# 用法：
#   powershell -ExecutionPolicy Bypass -File scripts\make_short_generation.ps1 `
#       -OldId "gaussian+dsh-plugin-gaussian+0.2.0+77ad64375b1b" `
#       -NewId "@gd+gp+0.2.0" -NewScope "gd" -NewName "gp"

param(
    [string]$OldId = "gaussian+dsh-plugin-gaussian+0.2.0+77ad64375b1b",
    [string]$NewId = "@gd+gp+0.2.0",
    [string]$NewScope = "gd",
    [string]$NewName = "gp"
)

$ErrorActionPreference = "Stop"

$Live = Join-Path $env:APPDATA "dsh-desktop\harness\profiles\.generations\live"
$Old  = Join-Path $Live $OldId
$New  = Join-Path $Live $NewId
$Tmp  = Join-Path $Live ".tmp-shortgen"

# 用 robocopy /MIR 对一个空目录做镜像 = 长路径安全的删除
function Remove-LongPath {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return }
    $Empty = Join-Path $env:TEMP ".empty-mirror"
    if (-not (Test-Path -LiteralPath $Empty)) { New-Item -ItemType Directory -Force -Path $Empty | Out-Null }
    $r = Start-Process -FilePath "robocopy.exe" `
        -ArgumentList @("`"$Empty`"", "`"$Path`"", "/MIR", "/R:0", "/W:0", "/NFL", "/NDL", "/NJH", "/NJS") `
        -Wait -PassThru -NoNewWindow
    if ($r.ExitCode -ge 8) { throw "robocopy /MIR 清理失败 exit=$($r.ExitCode): $Path" }
    Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction SilentlyContinue
    if (Test-Path -LiteralPath $Path) { throw "清理后仍存在: $Path" }
}

Write-Host "[1/6] 校验旧 generation"
if (-not (Test-Path -LiteralPath $Old)) { throw "旧 generation 不存在: $Old" }
if (-not (Test-Path -LiteralPath (Join-Path $Old "generation.json"))) { throw "旧 generation 缺少 generation.json" }
Write-Host "      OK: $Old"

Write-Host "[2/6] 清理中转目录"
Remove-LongPath -Path $Tmp

# robocopy 复制：/E 所有子目录 /SL 复制联接本体
# 排除旧包名路径与历史备份目录（节省 ~1GB，且避免深路径问题）
Write-Host "[3/6] robocopy 复制到中转目录"
$rc = Start-Process -FilePath "robocopy.exe" `
    -ArgumentList @(
        "`"$Old`"", "`"$Tmp`"",
        "/E", "/SL", "/R:1", "/W:1", "/NFL", "/NDL", "/NJH", "/NJS",
        "/XD",
        "`"$(Join-Path $Old 'node_modules\@gaussian')`"",
        "`"runtimes.old-*`"",
        "`"dist`"",
        "`"build`""
    ) -Wait -PassThru -NoNewWindow
if ($rc.ExitCode -ge 8) { throw "robocopy 失败，exit=$($rc.ExitCode)" }
Write-Host "      robocopy exit=$($rc.ExitCode)"

Write-Host "[4/6] 重建 node_modules/$NewScope/$NewName（真实副本，非联接）"
$SrcPkg = Join-Path $Tmp "source\gaussian+dsh-plugin-gaussian"
if (-not (Test-Path -LiteralPath $SrcPkg)) { throw "中转目录缺少 source 快照: $SrcPkg" }
$DstPkg = Join-Path $Tmp "node_modules\$NewScope\$NewName"
New-Item -ItemType Directory -Force -Path (Split-Path $DstPkg) | Out-Null
$rc2 = Start-Process -FilePath "robocopy.exe" `
    -ArgumentList @("`"$SrcPkg`"", "`"$DstPkg`"", "/E", "/SL", "/R:1", "/W:1", "/NFL", "/NDL", "/NJH", "/NJS",
                    "/XD", "`"runtimes.old-*`"", "`"dist`"", "`"build`"") `
    -Wait -PassThru -NoNewWindow
if ($rc2.ExitCode -ge 8) { throw "robocopy(pkg) 失败，exit=$($rc2.ExitCode)" }
Write-Host "      robocopy exit=$($rc2.ExitCode)"

$Exe = Join-Path $DstPkg "runtimes\win32-x64\gaussian-backend\gaussian-backend.exe"
if (-not (Test-Path -LiteralPath $Exe)) { throw "新包内找不到 gaussian-backend.exe: $Exe" }
$exeSize = (Get-Item $Exe).Length
Write-Host "      [OK] exe 就位 $exeSize B"

Write-Host "[5/6] 更新 generation.json 中的包名"
$GenJson = Join-Path $Tmp "generation.json"
if (Test-Path -LiteralPath $GenJson) {
    $g = Get-Content $GenJson -Raw -Encoding UTF8 | ConvertFrom-Json
    $g.pluginName = "@$NewScope/$NewName"
    $g | ConvertTo-Json -Depth 10 | Set-Content $GenJson -Encoding UTF8
    Write-Host "      generation.json pluginName -> @$NewScope/$NewName"
}

Write-Host "[6/6] 原子改名 .tmp-shortgen -> $NewId"
if (Test-Path -LiteralPath $New) { throw "目标已存在，拒绝覆盖: $New" }
Move-Item -LiteralPath $Tmp -Destination $New
Write-Host "      [OK] 新 generation: $New"

# 路径长度体检
Write-Host ""
Write-Host "最长路径体检："
$Longest = @(Get-ChildItem -LiteralPath $New -Recurse -File -Force -ErrorAction SilentlyContinue |
    Sort-Object { $_.FullName.Length } -Descending | Select-Object -First 5)
foreach ($f in $Longest) {
    $mark = if ($f.FullName.Length -gt 240) { "  << 超 240" } else { "" }
    Write-Host ("  {0,4}  {1}{2}" -f $f.FullName.Length, $f.FullName, $mark)
}
