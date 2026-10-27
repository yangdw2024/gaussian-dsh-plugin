# -*- coding: utf-8 -*-
"""R17 收尾复核 — 后端扩展 smoke（2026-10-26）。

独立启动部署路径 gaussian-backend.exe，不提交真实 Gaussian 任务，验证：
  A. 启动 + /v1/health 身份字段
  B. /v1/status 结构与本机探测值
  C. /v1/postprocess/capabilities 结构与 Multiwfn 真实版本
  D. 管理端点鉴权三态（正确 token 200 / 错误 403 / 无 token 403）
  E. 非法超资源 GJF 被拒绝（ok=false）
  F. 非法 body 被 Pydantic 拒绝（HTTP 422）
  G. 只读接口 keywords / sobko/status 结构
  H. data_dir 下 jobs / postprocess / logs 目录自动创建
  I. 受控 shutdown 后进程确认退出、端口释放
  J. stdout/stderr 日志无 Traceback / Fatal / ModuleNotFoundError

临时 data_dir / work_dir 指向本脚本同目录 smoke-20261026，GC_ON_STARTUP=0，
不读写正式目录 C:\\Users\\Administrator\\.gaussian-dsh 与 E:\\YDW\\ChemDatas\\Gjf。
"""
import json
import os
import subprocess
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

HERE = Path(__file__).resolve().parent
SMOKE_DIR = HERE / "smoke-20261026"
SMOKE_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR = SMOKE_DIR / "data"
WORK_DIR = SMOKE_DIR / "work"
DATA_DIR.mkdir(exist_ok=True)
WORK_DIR.mkdir(exist_ok=True)

PROJECT_ROOT = HERE.parent.parent
EXE = PROJECT_ROOT / "runtimes" / "win32-x64" / "gaussian-backend" / "gaussian-backend.exe"
PORT = "8792"
BASE = f"http://127.0.0.1:{PORT}"
TOKEN = "ext_smoke_token"

STDOUT_LOG = SMOKE_DIR / "stdout.log"
STDERR_LOG = SMOKE_DIR / "stderr.log"

results = []


def record(tag, ok, detail=""):
    results.append((tag, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {tag} :: {detail}")


def req(method, path, body=None, token=None, expect_status=None):
    """发起 HTTP 请求，返回 (http_status, parsed_json_or_text)。"""
    url = BASE + path
    data = None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if body is not None:
        data = json.dumps(body).encode("utf-8")
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=10) as resp:
            raw = resp.read().decode("utf-8", "ignore")
            status = resp.status
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "ignore")
        status = e.code
    except urllib.error.URLError as e:
        return None, f"URLError: {e.reason}"
    try:
        parsed = json.loads(raw)
    except Exception:
        parsed = raw
    if expect_status is not None and status != expect_status:
        record(f"{path} HTTP status", False, f"期望 {expect_status} 实际 {status} body={raw[:200]}")
    return status, parsed


# ---------- 1. 启动后端 ----------
env = dict(os.environ)
env.update({
    "GAUSSIAN_BACKEND_PORT": PORT,
    "GAUSSIAN_DATA_DIR": str(DATA_DIR),
    "GAUSSIAN_WORK_DIR": str(WORK_DIR),
    "GC_ON_STARTUP": "0",
    "GAUSSIAN_MANAGED_TOKEN": TOKEN,
})

if not EXE.exists():
    record("exe 存在", False, str(EXE))
    sys.exit(1)

stdout_f = STDOUT_LOG.open("w", encoding="utf-8", errors="ignore")
stderr_f = STDERR_LOG.open("w", encoding="utf-8", errors="ignore")
proc = subprocess.Popen(
    [str(EXE)],
    cwd=str(PROJECT_ROOT),
    env=env,
    stdout=stdout_f,
    stderr=stderr_f,
)

# ---------- 2. 轮询 health ----------
ready = False
health = None
for i in range(30):
    time.sleep(1)
    status, payload = req("GET", "/v1/health")
    if status == 200 and isinstance(payload, dict) and payload.get("ok"):
        ready = True
        health = payload
        break

if not ready:
    record("backend 启动 + health", False, "30s 内未就绪")
    proc.kill()
    stdout_f.close(); stderr_f.close()
    print("\n--- stderr ---")
    print(STDERR_LOG.read_text(encoding="utf-8", errors="ignore")[-2000:])
    sys.exit(1)

record("backend 启动 + health", True,
       f"pid={health.get('pid')} instance={health.get('instance_id')} "
       f"uptime={health.get('uptime_seconds')}s")

# health 字段断言
record("health service/version 身份",
       health.get("service") == "gaussian-dsh-backend" and health.get("version") == "0.2.0",
       f"service={health.get('service')} version={health.get('version')}")
lease = health.get("compute_lease", {})
record("health lease 空闲（无运行任务）", lease.get("held") is False,
       f"lease={lease}")
record("health memory 字段存在", isinstance(health.get("memory"), dict),
       f"memory keys={list(health['memory'].keys()) if isinstance(health.get('memory'), dict) else health.get('memory')}")

# ---------- 3. status ----------
status, st = req("GET", "/v1/status", expect_status=200)
record("/v1/status 200 + status ok", status == 200 and st.get("status") == "ok",
       f"version={st.get('version')}")
record("/v1/status version 0.2.0", st.get("version") == "0.2.0", str(st.get("version")))
record("/v1/status gaussian.exists", isinstance(st.get("gaussian"), dict) and st["gaussian"].get("exists") is True,
       f"path={st['gaussian'].get('exe')}")
record("/v1/status work/data 指向临时目录",
       st.get("work_dir") == str(WORK_DIR) and st.get("data_dir") == str(DATA_DIR),
       f"work={st.get('work_dir')} data={st.get('data_dir')}")
record("/v1/status 默认资源 12GB/8 核",
       st.get("default_mem") == "12GB" and st.get("default_nproc") == 8,
       f"mem={st.get('default_mem')} nproc={st.get('default_nproc')}")
record("/v1/status running_job=false + lease 空闲",
       st.get("running_job") is False and st.get("compute_lease", {}).get("held") is False,
       f"running={st.get('running_job')} lease={st.get('compute_lease')}")
record("/v1/status sobko 结构存在", isinstance(st.get("sobko"), dict),
       f"mode={st['sobko'].get('mode')} configured={st['sobko'].get('configured')}")

# ---------- 4. capabilities ----------
status, cap = req("GET", "/v1/postprocess/capabilities", expect_status=200)
record("capabilities 200", status == 200, "")
for tool in ("formchk", "multiwfn", "vmd"):
    record(f"capabilities {tool}.exists", cap.get(tool, {}).get("exists") is True,
           f"path={cap.get(tool, {}).get('path')}")
record("Multiwfn 真实版本探测（非硬编码）",
       cap["multiwfn"].get("version") == "3.8" and cap["multiwfn"].get("version_matched") is True,
       f"detected={cap['multiwfn'].get('version')} expected={cap['multiwfn'].get('expected_version')} matched={cap['multiwfn'].get('version_matched')}")
record("max_grid_points=16000000", cap.get("max_grid_points") == 16000000,
       str(cap.get("max_grid_points")))

# ---------- 5. 鉴权三态 ----------
status, _ = req("POST", "/v1/admin/gc?dry_run=true", token=TOKEN)
record("管理端点 正确 token → 200", status == 200, f"status={status}")
status, _ = req("POST", "/v1/admin/gc?dry_run=true", token="wrong_token")
record("管理端点 错误 token → 403", status == 403, f"status={status}")
status, _ = req("POST", "/v1/admin/gc?dry_run=true", token=None)
record("管理端点 无 token → 403", status == 403, f"status={status}")

# ---------- 6. 非法 GJF 拒绝 ----------
base_gjf = (
    "%mem=12GB\n%nprocshared=8\n%nosave\n"
    f"%chk={WORK_DIR / 't.chk'}\n"
    "# B3LYP/6-31G(d,p) sp\n\nwater smoke\n\n0 1\n"
    " O       0.00000000     0.00000000     0.11730000\n"
    " H       0.00000000     0.75700000    -0.46920000\n"
    " H       0.00000000    -0.75700000    -0.46920000\n\n"
)
bad_cases = {
    "空内容": "",
    "缺电荷多重度": base_gjf.replace("\n0 1\n", "\n"),
    "nproc=32 超 8 核": base_gjf.replace("%nprocshared=8", "%nprocshared=32"),
    "mem=20GB 超 12GB": base_gjf.replace("%mem=12GB", "%mem=20GB"),
}
for label, gjf in bad_cases.items():
    status, payload = req("POST", "/v1/jobs", body={"job_name": f"smoke_{label}", "gjf_content": gjf})
    rejected = isinstance(payload, dict) and payload.get("ok") is False
    record(f"非法 GJF 拒绝：{label}", rejected,
           f"http={status} error={str(payload.get('error'))[:120] if isinstance(payload, dict) else payload}")

# ---------- 7. 非法 body（缺 gjf_content）→ Pydantic 422 ----------
status, payload = req("POST", "/v1/jobs", body={"job_name": "missing_field"})
record("缺 gjf_content → HTTP 422", status == 422, f"status={status}")

# ---------- 8. 只读接口 ----------
status, kw = req("GET", "/v1/keywords", expect_status=200)
record("/v1/keywords 200 + categories 结构", status == 200 and isinstance(kw.get("categories"), list),
       f"categories={len(kw.get('categories', []))}")
status, sb = req("GET", "/v1/sobko/status", expect_status=200)
record("/v1/sobko/status 200 + 本地 bm25", status == 200 and isinstance(sb, dict),
       f"mode={sb.get('mode')}")

# ---------- 9. 目录创建 ----------
for sub in ("jobs", "postprocess", "logs"):
    record(f"数据目录自动创建：{sub}", (DATA_DIR / sub).is_dir(), str(DATA_DIR / sub))

# ---------- 10. 受控 shutdown + 退出确认 ----------
status, payload = req("POST", "/v1/admin/shutdown", token=TOKEN)
record("受控 shutdown 200", status == 200 and isinstance(payload, dict) and payload.get("ok") is True,
       f"status={status} body={payload}")

exited = True
for _ in range(10):
    if proc.poll() is not None:
        break
    time.sleep(0.5)
else:
    exited = False
record("waitForExit 确认进程退出", exited, f"returncode={proc.returncode}")

# 端口释放
time.sleep(1)
status, _ = req("GET", "/v1/health")
record("shutdown 后端口释放（连接失败）", status is None, f"last={status}")

stdout_f.close(); stderr_f.close()

# ---------- 11. 日志 traceback 扫描 ----------
combined = STDOUT_LOG.read_text(encoding="utf-8", errors="ignore") + "\n" + \
           STDERR_LOG.read_text(encoding="utf-8", errors="ignore")
bad_markers = ["Traceback (most recent call last)", "ModuleNotFoundError",
               "Fatal Python error", "CRITICAL", "Uncaught exception"]
hits = [m for m in bad_markers if m in combined]
record("启动/关闭日志无致命 traceback", len(hits) == 0, f"markers={hits}")

# ---------- 汇总 ----------
fails = [r for r in results if not r[1]]
print("\n========== SMOKE SUMMARY ==========")
print(f"total={len(results)} pass={len(results)-len(fails)} fail={len(fails)}")
if fails:
    print("FAILED:")
    for tag, _, detail in fails:
        print(f"  - {tag}: {detail}")
    sys.exit(2)
print("ALL EXTENDED SMOKE CHECKS PASSED")
