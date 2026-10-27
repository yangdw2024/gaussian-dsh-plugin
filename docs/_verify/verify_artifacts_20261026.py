# -*- coding: utf-8 -*-
"""2026-10-26 R17 收尾复核 — 任务/后处理产物实物 + 日志字段对照。

只读校验，不提交新计算：
A. 三个 Gaussian job JSON 终态与路径实物存在性
B. 三个 postprocess JSON：产物大小一致、PNG 可解码、cube 网格头（标准 cube：L3 原子+原点，L4/L5/L6 首列 nx/ny/nz）
C. 三份本会话 log：终止行、方法、末条 SCF 能量、HOMO/LUMO 位置归属
D. 10-21 串行/recover 历史测试 log 终态扫描（只记录，不宣称本轮复跑）
"""
import json, os, glob, re, struct

JOBS = r"C:\Users\Administrator\.gaussian-dsh\jobs"
PP = r"C:\Users\Administrator\.gaussian-dsh\postprocess"
GJF_DIR = r"E:\YDW\ChemDatas\Gjf"
LIMIT = 16_000_000

fails = []

def check(tag, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {tag} :: {detail}")
    if not ok:
        fails.append(tag)

print("========== A. Gaussian job JSON 终态 ==========")
for jf in sorted(glob.glob(os.path.join(JOBS, "*.json"))):
    m = json.load(open(jf, "r", encoding="utf-8"))
    ok_state = m["status"] == "completed" and m["error"] is None and m["pid"] and m["pid_start_time"]
    check(f"job {m['job_id']} 终态 completed/pid 在位", ok_state,
          f"status={m['status']} pid={m['pid']} start={m['pid_start_time']:.1f}")
    for key in ("gjf_path", "log_path", "chk_path"):
        p = m[key]
        exists = os.path.exists(p)
        size = os.path.getsize(p) if exists else -1
        check(f"  {m['job_id']} {key} 实物存在", exists and size > 0, f"{size} B {os.path.basename(p)}")

print("\n========== B. postprocess 产物 ==========")
for jf in sorted(glob.glob(os.path.join(PP, "*.json"))):
    meta = json.load(open(jf, "r", encoding="utf-8"))
    check(f"task {meta['task_id']} [{meta['kind']}] 终态 completed",
          meta["status"] == "completed" and meta["error"] is None, f"logs={meta['logs']}")
    registered = {a["path"] for a in meta["artifacts"]}
    for art in meta["artifacts"]:
        p = art["path"]
        exists = os.path.exists(p)
        size = os.path.getsize(p) if exists else -1
        check(f"  {meta['task_id']}/{art['name']} 大小一致", exists and size == art["size_bytes"],
              f"记录 {art['size_bytes']} / 实物 {size}")
        if exists and art["kind"] == "image/png":
            try:
                from PIL import Image
                im = Image.open(p); im.verify()
                im2 = Image.open(p)
                check(f"  {meta['task_id']}/{art['name']} PNG 解码", True, f"size={im2.size}")
            except Exception as e:
                check(f"  {meta['task_id']}/{art['name']} PNG 解码", False, str(e))
        if exists and art["kind"] == "chemical/cube":
            with open(p, "rb") as f:
                lines = [next(f) for _ in range(6)]
            nx = int(lines[3].split()[0]); ny = int(lines[4].split()[0]); nz = int(lines[5].split()[0])
            npts = nx * ny * nz
            check(f"  {meta['task_id']}/{art['name']} cube 网格头", npts <= LIMIT,
                  f"{nx} x {ny} x {nz} = {npts} 点 / 上限 {LIMIT}")
    # 未登记中间产物（TGA、Multiwfn/VMD 日志、命令文件）只列报
    dirp = os.path.dirname(jf)
    extra = []
    for f in os.listdir(dirp):
        fp = os.path.join(dirp, f)
        if fp not in registered and os.path.isfile(fp):
            extra.append(f"{f}({os.path.getsize(fp)}B)")
    if extra:
        print(f"  [INFO 未登记中间产物] {meta['task_id']}: {', '.join(extra)}")

print("\n========== C. 三份本会话 log 字段对照 ==========")
log_files = {
    "苯 opt 67f4b8f183fa": os.path.join(GJF_DIR, "c1ccccc1_opt_B3LYP_631Gdp_67f4b8f183fa.log"),
    "水 sp 29d5fbd36387": os.path.join(GJF_DIR, "water_B3LYP_631Gdp_sp_29d5fbd36387.log"),
    "h2o_test 853cf885352f": os.path.join(GJF_DIR, "h2o_test_853cf885352f.log"),
}

for label, path in log_files.items():
    if not os.path.exists(path):
        check(label + " log 存在", False, path); continue
    text = open(path, "r", encoding="utf-8", errors="replace").read()
    lines = text.splitlines()
    scf = [ln for ln in lines if "SCF Done" in ln]
    normal = "Normal termination" in text
    error_term = "Error termination" in text
    check(label + " Normal termination", normal and not error_term,
          "Normal" if normal and not error_term else f"normal={normal} error={error_term}")
    last_scf = scf[-1] if scf else ""
    m = re.search(r"E\([^)]*\)\s*=\s*(-?\d+\.\d+)", last_scf)
    energy = m.group(1) if m else None
    check(label + " 末条 SCF 能量提取", energy is not None, last_scf.strip()[:110])
    # 最后 occ / 第一个 virt 位置归属
    occ_last = []
    virt_first = []
    for ln in lines:
        if "Alpha  occ. eigenvalues" in ln:
            occ_last = ln.split("--", 1)[1].split()
        if "Alpha virt. eigenvalues" in ln and not virt_first:
            virt_first = ln.split("--", 1)[1].split()
    homo = occ_last[-1] if occ_last else None
    lumo = virt_first[0] if virt_first else None
    print(f"    HOMO(末 occ 末值)={homo}  LUMO(末 occ 之后首个 virt 首值)={lumo}")
    # 方法 / 基函数 / 原子数
    route = next((ln for ln in lines if re.match(r"\s*#\s", ln)), "")
    basis_fn = next((ln for ln in lines if "basis functions" in ln.lower()), "")
    print(f"    route: {route.strip()}")
    print(f"    {basis_fn.strip()}")

print("\n========== D. 10-21 串行/recover 历史测试 log 终态（历史证据，非本轮复跑） ==========")
for p in sorted(glob.glob(os.path.join(GJF_DIR, "*.log"))):
    bn = os.path.basename(p)
    if not re.search(r"he_serial|h2o_main|h2o_second|second_when_busy|after_release|probe_95f|h2o_test", bn):
        continue
    t = open(p, "r", encoding="utf-8", errors="replace").read()
    flag = "Normal" if "Normal termination" in t else ("Error" if "Error termination" in t else "UNKNOWN")
    print(f"  {bn}: {flag} ({os.path.getsize(p)} B)")

print("\n========== 汇总 ==========")
print("FAILS:", fails if fails else "无")
