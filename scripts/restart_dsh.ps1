param([string]$Exe = 'E:\DSH\DSH Desktop\DSH Desktop.exe')
$ErrorActionPreference = 'Continue'
$log = 'C:\Users\Administrator\AppData\Roaming\dsh-desktop\harness\_restart_dsh.log'
function W($m) {
  $line = "[{0:HH:mm:ss}] {1}" -f (Get-Date), $m
  Write-Host $line
  try { Add-Content -Path $log -Value $line -Encoding UTF8 -ErrorAction Stop } catch {}
}

W "=== restart begin (self=$PID) ==="
$before = @(Get-CimInstance Win32_Process -Filter "Name='DSH Desktop.exe' OR Name='electron.exe'" -ErrorAction SilentlyContinue |
  Where-Object { $_.CommandLine -notlike '*restart_dsh*' })
W "targets to kill: $($before.Count)"
foreach ($p in $before) {
  try {
    Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop
    W "  killed PID $($p.ProcessId) $($p.Name)"
  } catch {
    W "  kill failed PID $($p.ProcessId): $($_.Exception.Message)"
  }
}
Start-Sleep -Seconds 4
$left = @(Get-CimInstance Win32_Process -Filter "Name='DSH Desktop.exe' OR Name='electron.exe'" -ErrorAction SilentlyContinue |
  Where-Object { $_.CommandLine -notlike '*restart_dsh*' })
W "remaining: $($left.Count)"
Get-Process -Name 'gaussian-backend' -ErrorAction SilentlyContinue | ForEach-Object {
  try { Stop-Process -Id $_.Id -Force; W "  killed stale backend $($_.Id)" } catch {}
}
Start-Sleep -Seconds 1

W "launching: $Exe"
Start-Process -FilePath $Exe -WorkingDirectory 'E:\DSH\DSH Desktop'
Start-Sleep -Seconds 20

$now = @(Get-CimInstance Win32_Process -Filter "Name='DSH Desktop.exe'" -ErrorAction SilentlyContinue)
W "DSH Desktop processes now: $($now.Count)"
$port = @(netstat -ano | Select-String ':8765')
if ($port.Count -gt 0) { W ("port 8765: " + $port[0].Line.Trim()) } else { W "port 8765: (not listening yet)" }
try {
  $r = Invoke-WebRequest -Uri 'http://127.0.0.1:8765/v1/status' -TimeoutSec 10 -UseBasicParsing
  W ("backend status " + $r.StatusCode)
  W ("body: " + $r.Content.Substring(0, [Math]::Min(500, $r.Content.Length)))
} catch {
  W ("backend probe failed: " + $_.Exception.Message)
}
W "=== restart end ==="
