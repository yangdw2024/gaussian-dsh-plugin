# -*- coding: utf-8 -*-
# 复现 gaussian_output.py 的 occ/virt 位置归属规则，验证苯任务 LUMO=0.0026 来源。
import re

LOG = r"E:\YDW\ChemDatas\Gjf\c1ccccc1_opt_B3LYP_631Gdp_67f4b8f183fa.log"
content = open(LOG, "r", encoding="utf-8", errors="replace").read()

occ_re = r"Alpha\s+occ\. eigenvalues --((?:\s+-?[\d.Ee+]+)+)"
virt_re = r"Alpha\s+virt\. eigenvalues --((?:\s+-?[\d.Ee+]+)+)"
occ_spans = [(m.start(), m.group(1)) for m in re.finditer(occ_re, content)]
virt_spans = [(m.start(), m.group(1)) for m in re.finditer(virt_re, content)]

print(f"occ 块数: {len(occ_spans)}, virt 块数: {len(virt_spans)}")
last_occ_pos, last_occ = occ_spans[-1]
occ_vals = [float(x) for x in last_occ.split()]
h = occ_vals[-1]
print(f"末 occ 块位置={last_occ_pos}, 轨道数={len(occ_vals)}, HOMO={h}")
print(f"末 occ 块末 5 值: {occ_vals[-5:]}")

following = [(pos, v) for pos, v in virt_spans if pos > last_occ_pos]
print(f"\n末 occ 之后的 virt 块数: {len(following)}")
for i, (pos, v) in enumerate(following):
    vals = [float(x) for x in v.split()]
    print(f"  virt 块 #{i} pos={pos} 首值={vals[0]} 数量={len(vals)} 前3={vals[:3]}")

if following:
    l = float(following[0][1].split()[0])
    gap = l - h
    print(f"\n后端规则 LUMO=following[0] 首值 = {l}")
    print(f"HOMO={h}, gap={gap}")
    print("合理性: LUMO>HOMO:", l > h, " gap<20Ha:", gap < 20)
