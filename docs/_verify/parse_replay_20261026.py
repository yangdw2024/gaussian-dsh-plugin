# -*- coding: utf-8 -*-
"""本轮复核：直接调用后端解析器解析三份本会话 log，复现后端返回字段，
并逐块打印苯 log 轨道归属，核对 LUMO 位置归属规则。只读，不起服务器。"""
import os, re, sys, json
sys.path.insert(0, r"E:\YDW\ChemDatas\gaussian-dsh-plugin")

from backend.gaussian_output import parse_gaussian_log, output_to_dict

GJF = r"E:\YDW\ChemDatas\Gjf"
logs = {
    "苯 opt 67f4b8f183fa": os.path.join(GJF, "c1ccccc1_opt_B3LYP_631Gdp_67f4b8f183fa.log"),
    "水 sp 29d5fbd36387": os.path.join(GJF, "water_B3LYP_631Gdp_sp_29d5fbd36387.log"),
    "h2o_test 853cf885352f": os.path.join(GJF, "h2o_test_853cf885352f.log"),
}

for label, path in logs.items():
    content = open(path, "r", encoding="utf-8", errors="replace").read()
    res = parse_gaussian_log(content, filename=os.path.basename(path))
    d = output_to_dict(res)
    keys = ["method", "final_energy", "homo_energy", "lumo_energy", "homo_lumo_gap",
            "normal_termination", "error_termination", "opt_converged",
            "stationary_point", "atom_count", "basis_functions", "dipole_moment"]
    print(f"\n===== {label} =====")
    for k in keys:
        print(f"  {k} = {d.get(k)}")

# 苯 log 轨道块逐块归属复现
print("\n===== 苯 log 轨道块位置归属 =====")
text = logs["苯 opt 67f4b8f183fa"]
content = open(text, "r", encoding="utf-8", errors="replace").read()
occ_re = r"Alpha\s+occ\. eigenvalues --((?:\s+-?[\d.Ee+]+)+)"
virt_re = r"Alpha\s+virt\. eigenvalues --((?:\s+-?[\d.Ee+]+)+)"
occ_spans = [(m.start(), m.group(1)) for m in re.finditer(occ_re, content)]
virt_spans = [(m.start(), m.group(1)) for m in re.finditer(virt_re, content)]
print(f"occ 块数={len(occ_spans)} virt 块数={len(virt_spans)}")
last_occ_pos, last_occ = occ_spans[-1]
print(f"末 occ 块位置={last_occ_pos} 数值={last_occ.split()}")
following = [(pos, vals) for pos, vals in virt_spans if pos > last_occ_pos]
print(f"末 occ 之后 virt 块数={len(following)}")
for i, (pos, vals) in enumerate(following):
    print(f"  following[{i}] pos={pos} 数值={vals.split()}")
if following:
    first = [float(x) for x in following[0][1].split()]
    print(f"LUMO = following[0] 第一根 = {first[0]}")
