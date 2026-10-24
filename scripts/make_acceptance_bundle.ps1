#Requires -Version 7.0
# 重打 acceptance_bundle.zip：只纳入源码、脚本、骨架模板与正式文档，
# 排除运行时、构建缓存、备份目录与临时产物。规则与 docs/RELEASE_READINESS_REPORT.md 第 6 节一致。
# 用法：pwsh -File scripts/make_acceptance_bundle.ps1
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$out  = Join-Path $root "acceptance_bundle.zip"

# 排除目录（相对路径段匹配，不区分大小写）
$excludeDirNames = @("runtimes", "lib", "build", "dist", "__pycache__", "node_modules")
# docs 下按前缀排除的备份/临时目录
$excludeDocPrefix = @("backups_", "_dsh", "_verify")
# 排除文件后缀与文件名模式
$excludeFileSuffix = @(".pyc")
$excludeFileNames  = @("acceptance_bundle.zip", "_mk_bundle.py")

# 纳入根目录清单
$includeRootFiles = @("package.json", "cordis.patch.yml", "README.md", "start_backend.bat")
# 纳入目录（递归）
$includeDirs = @("backend", "src", "scripts", "packaging")

$files = New-Object System.Collections.Generic.List[System.IO.FileInfo]

# 1) 纳入目录树
foreach ($dir in $includeDirs) {
  $dirPath = Join-Path $root $dir
  if (-not (Test-Path -LiteralPath $dirPath)) { continue }
  Get-ChildItem -LiteralPath $dirPath -Recurse -File -Force | ForEach-Object {
    $rel = $_.FullName.Substring($root.Length + 1)
    $parts = $rel -split "[/\\]"
    if ($parts | Where-Object { $excludeDirNames -contains $_ }) { return }
    if ($excludeFileSuffix -contains $_.Extension.ToLower()) { return }
    if ($excludeFileNames -contains $_.Name) { return }
    $files.Add($_)
  }
}

# 2) 纳入 docs 下正式 md（排除备份目录与临时前缀）
$docsDir = Join-Path $root "docs"
if (Test-Path -LiteralPath $docsDir) {
  Get-ChildItem -LiteralPath $docsDir -File -Force | ForEach-Object {
    if ($_.Extension.ToLower() -eq ".md" -and $excludeFileNames -notcontains $_.Name) { $files.Add($_) }
  }
  Get-ChildItem -LiteralPath $docsDir -Directory -Force | ForEach-Object {
    foreach ($p in $excludeDocPrefix) {
      if ($_.Name.StartsWith($p, [System.StringComparison]::OrdinalIgnoreCase)) { return }
    }
    Get-ChildItem -LiteralPath $_.FullName -Recurse -File -Force | ForEach-Object {
      $rel = $_.FullName.Substring($root.Length + 1)
      if ($excludeFileSuffix -contains $_.Extension.ToLower()) { return }
      $files.Add($_)
    }
  }
}

# 3) 纳入根目录固定文件
foreach ($name in $includeRootFiles) {
  $p = Join-Path $root $name
  if (Test-Path -LiteralPath $p) { $files.Add((Get-Item -LiteralPath $p)) }
}

# 去重（按相对路径）
$seen = @{}
$unique = New-Object System.Collections.Generic.List[System.IO.FileInfo]
foreach ($f in $files) {
  $rel = $f.FullName.Substring($root.Length + 1).Replace("\", "/")
  if (-not $seen.ContainsKey($rel)) { $seen[$rel] = $true; $unique.Add($f) }
}

# 删除旧 zip，避免陈旧条目残留
if (Test-Path -LiteralPath $out) { Remove-Item -LiteralPath $out -Force }

Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip = [System.IO.Compression.ZipFile]::Open($out, [System.IO.Compression.ZipArchiveMode]::Create)
try {
  foreach ($f in $unique) {
    $entryName = $f.FullName.Substring($root.Length + 1).Replace("\", "/")
    [void][System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile($zip, $f.FullName, $entryName, [System.IO.Compression.CompressionLevel]::Optimal)
  }
} finally {
  $zip.Dispose()
}

# 泄漏检查：重新打开 zip，列出命中排除规则的条目
$zip = [System.IO.Compression.ZipFile]::OpenRead($out)
try {
  $leaks = @()
  foreach ($e in $zip.Entries) {
    $parts = $e.FullName -split "/"
    $hit = $false
    if ($parts | Where-Object { $excludeDirNames -contains $_ }) { $hit = $true }
    if ($parts | Where-Object { $excludeDocPrefix -contains $_ }) { $hit = $true }
    if ($excludeFileSuffix -contains ([System.IO.Path]::GetExtension($e.FullName).ToLower())) { $hit = $true }
    if ($excludeFileNames -contains $parts[-1]) { $hit = $true }
    if ($hit) { $leaks += $e.FullName }
  }
  $totalBytes = ($zip.Entries | Measure-Object -Property Length -Sum).Sum
  Write-Output ("entries: {0}" -f $zip.Entries.Count)
  Write-Output ("uncompressed bytes: {0}" -f $totalBytes)
  if ($leaks.Count -gt 0) {
    Write-Output "LEAK:"
    $leaks | ForEach-Object { Write-Output "  - $_" }
  } else {
    Write-Output "leak: none"
  }
} finally {
  $zip.Dispose()
}
Write-Output ("zip: {0} ({1} bytes)" -f $out, (Get-Item -LiteralPath $out).Length)
