# 修复 DSH generation 中插件包缺失 runtimes/ 的问题。
# 原因：DSH 安装本地目录插件时会生成一份 package.json 精简"shim"包放进
# node_modules/@gd/gp，只含 lib/ 等入口文件，不含
# .gitignore 忽略的 runtimes/ 二进制；而 src/index.js 的 packagedExecutable()
# 按 fileURLToPath(new URL("../runtimes/", import.meta.url)) 解析，于是 managed
# 模式永远判"未找到 exe"。本脚本把该 shim 换成指向完整快照的目录联接（junction）。
param(
  [string]$GenerationsRoot = "$env:APPDATA\dsh-desktop\harness\profiles\.generations\live",
  [string]$PluginDirName   = "gaussian+dsh-plugin-gaussian+0.2.0+77ad64375b1b",
  [switch]$DryRun
)
$ErrorActionPreference = "Stop"

$base   = Join-Path $GenerationsRoot $PluginDirName
$target = Join-Path $base "source\gaussian+dsh-plugin-gaussian"
$shim   = Join-Path $base "node_modules\@gaussian\dsh-plugin-gaussian"

if (-not (Test-Path $target)) { throw "快照目录不存在: $target" }

# 校验快照本身健康：exe 必须存在并与 runtime.json 清单 sha256 一致
$exe = Join-Path $target "runtimes\win32-x64\gaussian-backend\gaussian-backend.exe"
$man = Join-Path $target "runtimes\win32-x64\runtime.json"
if (-not (Test-Path $exe)) { throw "快照内缺 exe: $exe" }
if (-not (Test-Path $man)) { throw "快照内缺清单: $man" }
$json = (Get-Content $man -Raw -Encoding utf8).TrimStart([char]0xFEFF) | ConvertFrom-Json
$entry = $json.files | Where-Object { $_.path -eq $json.executable } | Select-Object -First 1
if (-not $entry) { throw "清单中找不到 executable 条目: $($json.executable)" }
$actual = (Get-FileHash $exe -Algorithm SHA256).Hash.ToLower()
if ($actual -ne $entry.sha256.ToLower()) { throw "exe sha256 与清单不符: $actual != $($entry.sha256)" }
if ($json.version -ne "0.2.0" -or $json.target -ne "win32-x64") {
  throw "清单 version/target 不符: $($json.version)/$($json.target)"
}
Write-Host "[OK] 快照健康: exe $((Get-Item $exe).Length) B, sha256 前16位 $($actual.Substring(0,16))"

if ($DryRun) { Write-Host "[DryRun] 将把 $shim 联接至 $target"; return }

# 已有正确定向则跳过
if (Test-Path $shim) {
  $item = Get-Item $shim
  if ($item.LinkType -eq "Junction" -and $item.Target -contains $target) {
    Write-Host "[OK] 联接已正确指向快照，无需修复"
    return
  }
  $bak = "$shim.bak-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
  Move-Item -LiteralPath $shim -Destination $bak -Force
  Write-Host "[MOVE] 旧 shim 已备份: $bak"
}

New-Item -ItemType Junction -Path $shim -Target $target | Out-Null
$check = Get-Item $shim
Write-Host "[OK] 已建立联接: $shim -> $target (LinkType=$($check.LinkType))"
if (-not (Test-Path $exe)) { throw "联接后 exe 仍不可见，修复失败" }
Write-Host "[OK] 联接后 exe 可见: $((Get-Item $exe).Length) B"
