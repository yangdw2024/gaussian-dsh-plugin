# -*- coding: utf-8 -*-
# R15 后端离线基础 smoke：不常驻、不占端口、不写真实数据目录。
# 覆盖：health / status / postprocess capabilities / admin 匿名 403 / 非法 GJF 校验拒绝。
# 运行：python docs/_verify/backend_offline_smoke.py
import os, sys, tempfile, json, traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

# 必须在导入 backend.app 之前设置，settings 在导入时读取环境变量。
_tmp = Path(tempfile.mkdtemp(prefix="gaussian_smoke_"))
os.environ["GAUSSIAN_DATA_DIR"] = str(_tmp / "data")
os.environ["GAUSSIAN_WORK_DIR"] = str(_tmp / "work")
os.environ["GC_ON_STARTUP"] = "0"
os.environ.pop("GAUSSIAN_MANAGED_TOKEN", None)

results = []
def check(name, ok, detail=""):
    results.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))

try:
    from fastapi.testclient import TestClient
    from backend.app import app

    with TestClient(app) as client:
        # 1. health
        r = client.get("/v1/health")
        h = r.json()
        check("health 200 + service/version",
              r.status_code == 200 and h.get("ok") is True
              and h.get("service") == "gaussian-dsh-backend" and h.get("version") == "0.2.0",
              f"status={r.status_code} service={h.get('service')} version={h.get('version')}")

        # 2. status 字段齐全
        r = client.get("/v1/status")
        s = r.json()
        need = ["status", "version", "gaussian", "work_dir", "data_dir",
                "default_mem", "default_nproc", "sobko", "running_job", "compute_lease"]
        missing = [k for k in need if k not in s]
        check("status 200 + 字段齐全", r.status_code == 200 and not missing,
              f"status={r.status_code} missing={missing} gaussian_exists={s.get('gaussian',{}).get('exists')}")

        # 3. postprocess capabilities
        r = client.get("/v1/postprocess/capabilities")
        c = r.json()
        check("postprocess capabilities 200", r.status_code == 200 and isinstance(c, dict),
              f"status={r.status_code} keys={list(c.keys())[:6]}")

        # 4. admin shutdown 匿名 403（未配置 token，testserver 不在回环白名单）
        r = client.post("/v1/admin/shutdown")
        check("admin shutdown 匿名 403", r.status_code == 403, f"status={r.status_code}")

        # 5. 非法 GJF 提交被校验拒绝（200 + ok=False，不拉起进程）
        bad_gjf = "%mem=12GB\n%nproc=8\n# B3LYP/6-31G(d,p) SP\n\nBad mol\n\n"  # 无坐标块
        r = client.post("/v1/jobs", json={"job_name": "smoke_bad", "gjf_content": bad_gjf})
        j = r.json()
        check("非法 GJF 被拒绝(ok=False)", r.status_code == 200 and j.get("ok") is False,
              f"status={r.status_code} ok={j.get('ok')} err={str(j.get('error'))[:60]}")

        # 6. 任务列表可枚举（空或仅本次拒绝记录，不报错）
        r = client.get("/v1/jobs")
        check("jobs 列表 200", r.status_code == 200 and "jobs" in r.json(), f"status={r.status_code}")

except Exception:
    check("后端导入与启动无 traceback", False, traceback.format_exc().splitlines()[-1])

failed = [n for n, ok, _ in results if not ok]
print("\n===== 汇总 =====")
print(f"通过 {len(results)-len(failed)}/{len(results)}")
if failed:
    print("失败项:", failed)
    sys.exit(1)
print("BACKEND OFFLINE SMOKE PASS")
