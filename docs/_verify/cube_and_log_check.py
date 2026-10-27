# -*- coding: utf-8 -*-
# 第六轮：修正 cube header 偏移（第 4 行才是 nx ny nz），提取苯 log 全部 SCF 与轨道能级。
import os, glob, json, re

DATA = r"C:\Users\Administrator\.gaussian-dsh\postprocess"
LOG = r"E:\YDW\ChemDatas\Gjf\c1ccccc1_opt_B3LYP_631Gdp_67f4b8f183fa.log"

print("=== A. cube header 复核（注释2行 + 原子数原点行 + 网格行） ===")
for jf in sorted(glob.glob(os.path.join(DATA, "*.json"))):
    meta = json.load(open(jf, "r", encoding="utf-8"))
    for art in meta["artifacts"]:
        if art["kind"] != "chemical/cube":
            continue
        p = art["path"]
        with open(p, "rb") as f:
            lines = [next(f) for _ in range(6)]
        # 标准 cube: L3=natoms+原点; L4/L5/L6 首列 = nx/ny/nz, 次列=步长
        nx = int(lines[3].split()[0]); ny = int(lines[4].split()[0]); nz = int(lines[5].split()[0])
        npts = nx * ny * nz
        ok = npts <= 16_000_000
        print(f"  {os.path.basename(p)}: {nx} x {ny} x {nz} = {npts} 点, 上限1600万: {'OK' if ok else 'OVER'}")

print("\n=== B. 苯 log SCF Done 全部行（取最后一条） ===")
scf = []
occ_last = []
virt_first = []
with open(LOG, "r", encoding="utf-8", errors="replace") as f:
    for line in f:
        if "SCF Done" in line:
            scf.append(line.strip())
        if "Alpha  occ. eigenvalues" in line:
            occ_last = [x for x in line.split("--", 1)[1].split()]
        if "Alpha virt. eigenvalues" in line and not virt_first:
            virt_first = [x for x in line.split("--", 1)[1].split()]

for i, s in enumerate(scf, 1):
    print(f"  SCF #{i}: {s}")
print(f"\n  最后一条 occ 轨道能级: {occ_last}")
print(f"  第一条 virt 轨道能级: {virt_first[:5]}")
if occ_last:
    print(f"  log 末位 HOMO = {occ_last[-1]}")
if virt_first:
    print(f"  log 首位 LUMO = {virt_first[0]}")

print("\n=== C. 后端 parse_gaussian_output 返回值（会话记录） ===")
print("  final_energy=-232.258201851  homo=-0.24688  lumo=0.0026  gap=0.24948")
