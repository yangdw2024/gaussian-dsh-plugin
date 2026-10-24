"""Gaussian 输出文件（.log/.out）解析器。

从日志中提取：任务信息、收敛状态、最终能量、优化收敛、HOMO-LUMO、
偶极矩、频率与虚频、热力学量、错误信息、用时。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class GaussianOutput:
    """解析结果。"""
    filename: str = ""
    normal_termination: bool = False
    error_message: Optional[str] = None
    method: Optional[str] = None
    basis: Optional[str] = None
    charge: Optional[int] = None
    multiplicity: Optional[int] = None
    atom_count: Optional[int] = None
    basis_functions: Optional[int] = None
    final_energy: Optional[float] = None
    energy_unit: str = "a.u."
    # 优化
    stationary_point: Optional[bool] = None
    opt_converged: Optional[bool] = None
    opt_steps: Optional[int] = None
    max_force: Optional[float] = None
    rms_force: Optional[float] = None
    max_displacement: Optional[float] = None
    rms_displacement: Optional[float] = None
    # 轨道
    homo_energy: Optional[float] = None
    lumo_energy: Optional[float] = None
    homo_lumo_gap: Optional[float] = None
    # 偶极
    dipole_moment: Optional[float] = None
    # 频率
    frequencies: List[float] = field(default_factory=list)
    imaginary_frequencies: List[float] = field(default_factory=list)
    # 热力学
    zero_point_energy: Optional[float] = None
    thermal_enthalpy: Optional[float] = None
    thermal_free_energy: Optional[float] = None
    # 用时
    cpu_time: Optional[str] = None
    wall_time: Optional[str] = None
    # 原始摘要
    warnings: List[str] = field(default_factory=list)


def _safe_float(text: str) -> Optional[float]:
    try:
        return float(text)
    except (ValueError, TypeError):
        return None


def parse_gaussian_log(content: str, filename: str = "") -> GaussianOutput:
    """解析 Gaussian 日志文本。"""
    out = GaussianOutput(filename=filename)

    # 正常结束
    if re.search(r"Normal termination of Gaussian", content):
        out.normal_termination = True

    # 错误终止
    err_match = re.search(r"Error termination via Lnk1e in[^\n]+\n([^\n]+)", content)
    if err_match:
        out.error_message = err_match.group(1).strip()
        out.normal_termination = False
    # 常见错误
    if "Out-of-memory" in content or "out of memory" in content:
        out.error_message = (out.error_message or "") + " | 内存不足 (Out-of-memory)"
    if "Convergence failure" in content or "convergence failure" in content:
        out.error_message = (out.error_message or "") + " | SCF 收敛失败"

    # 方法与基组（从 route 行，去掉 # 后的打印控制字符 p/n/t）
    route_match = re.search(r"^\s*#\s*[pnt]?\s*(.+)$", content, re.MULTILINE)
    if route_match:
        route = route_match.group(1).strip()
        # 方法是第一个 / 之前的最后一个词（去掉 opt/freq 等任务关键词）
        if "/" in route:
            before_basis = route.split("/")[0]
            tokens = before_basis.split()
            # 方法通常是最后一个 token（如 "opt b3lyp" -> b3lyp）
            out.method = tokens[-1] if tokens else before_basis
        else:
            out.method = route.split()[0] if route.split() else None
        basis_match = re.search(r"/(\S+)", route)
        if basis_match:
            out.basis = basis_match.group(1).split()[0]

    # 电荷与自旋（Gaussian 输出格式：Charge =  0 Multiplicity = 1）
    charge_match = re.search(r"Charge\s*=\s*(-?\d+).*?Multiplicity\s*=\s*(\d+)", content, re.DOTALL)
    if charge_match:
        out.charge = int(charge_match.group(1))
        out.multiplicity = int(charge_match.group(2))

    # 原子数与基函数数
    natom_match = re.search(r"NAtoms=\s*(\d+)", content)
    if natom_match:
        out.atom_count = int(natom_match.group(1))
    nbf_match = re.search(r"NBasis=\s*(\d+)", content)
    if nbf_match:
        out.basis_functions = int(nbf_match.group(1))

    # 最终能量（取最后一个 SCF Done / E(Rxxx)）
    energy_matches = re.findall(r"SCF Done:\s+E\(\S+\)\s*=\s*(-?[\d.]+)", content)
    if energy_matches:
        out.final_energy = _safe_float(energy_matches[-1])
    else:
        # 后 HF 能量
        mp2_match = re.findall(r"EUMP2\s*=\s*(-?[\d.]+)", content)
        if mp2_match:
            out.final_energy = _safe_float(mp2_match[-1])

    # 优化收敛
    if "Stationary point found" in content:
        out.stationary_point = True
        out.opt_converged = True
    # 优化步数
    opt_step_matches = re.findall(r"Optimization cycle\s+(\d+)", content)
    if opt_step_matches:
        out.opt_steps = int(opt_step_matches[-1])
    # 收敛判据（逐行格式，取最后一组四行块）
    conv_lines = re.findall(
        r"(Maximum Force|RMS\s+Force|Maximum Displacement|RMS\s+Displacement)\s+([\d.]+)\s+(YES|NO)",
        content,
    )
    if conv_lines:
        # 按顺序每4个一组，取最后一组
        n_blocks = len(conv_lines) // 4
        if n_blocks > 0:
            last_block = conv_lines[(n_blocks-1)*4 : n_blocks*4]
            values = {}
            for name, val, ok in last_block:
                values[name.strip()] = (float(val), ok)
            if "Maximum Force" in values:
                out.max_force = values["Maximum Force"][0]
            if "RMS Force" in values:
                out.rms_force = values["RMS Force"][0]
            if "Maximum Displacement" in values:
                out.max_displacement = values["Maximum Displacement"][0]
            if "RMS Displacement" in values:
                out.rms_displacement = values["RMS Displacement"][0]
            if all(v[1] == "YES" for v in values.values()):
                out.opt_converged = True

    # HOMO-LUMO（遍历所有 occ/virt 组，取 HOMO 最大且 LUMO>HOMO 的合理组）
    occ_matches = re.findall(r"Alpha\s+occ\. eigenvalues --((?:\s+-?[\d.]+)+)", content)
    virt_matches = re.findall(r"Alpha\s+virt\. eigenvalues --((?:\s+-?[\d.]+)+)", content)
    if occ_matches and virt_matches:
        best_homo = None
        best_lumo = None
        n_pairs = min(len(occ_matches), len(virt_matches))
        for i in range(n_pairs):
            occ_vals = [float(x) for x in occ_matches[i].split()]
            virt_vals = [float(x) for x in virt_matches[i].split()]
            if not occ_vals or not virt_vals:
                continue
            h = occ_vals[-1]
            l = virt_vals[0]
            # 合理条件：HOMO < 0，-1 < LUMO < 1.5，LUMO > HOMO，gap < 20
            if h < 0 and -1.0 < l < 1.5 and l > h and (l - h) < 20:
                if best_homo is None or h > best_homo:
                    best_homo = h
                    best_lumo = l
        if best_homo is not None:
            out.homo_energy = best_homo
            out.lumo_energy = best_lumo
            out.homo_lumo_gap = best_lumo - best_homo

    # 偶极矩
    dipole_match = re.search(
        r"Dipole moment.*?Debye.*?X=\s*([-\d.]+)\s+Y=\s*([-\d.]+)\s+Z=\s*([-\d.]+)\s+Tot=\s*([-\d.]+)",
        content, re.DOTALL,
    )
    if dipole_match:
        dip = _safe_float(dipole_match.group(4))
        if dip is not None and 0 <= dip < 100:
            out.dipole_moment = dip

    # 频率
    freq_matches = re.findall(r"Frequencies --((?:\s+-?[\d.]+)+)", content)
    all_freqs = []
    for m in freq_matches:
        all_freqs.extend([float(x) for x in m.split()])
    out.frequencies = all_freqs
    out.imaginary_frequencies = [f for f in all_freqs if f < 0]

    # 热力学量
    zpe_match = re.search(r"Zero-point correction=\s+([\d.]+)", content)
    if zpe_match:
        out.zero_point_energy = _safe_float(zpe_match.group(1))
    enthalpy_match = re.search(r"Thermal correction to Enthalpy=\s+([\d.]+)", content)
    if enthalpy_match:
        out.thermal_enthalpy = _safe_float(enthalpy_match.group(1))
    free_match = re.search(r"Thermal correction to Gibbs Free Energy=\s+([\d.]+)", content)
    if free_match:
        out.thermal_free_energy = _safe_float(free_match.group(1))

    # 用时
    cpu_match = re.search(r"Job cpu time:\s+(.+)$", content, re.MULTILINE)
    if cpu_match:
        out.cpu_time = cpu_match.group(1).strip()
    wall_match = re.search(r"Elapsed time:\s+(.+)$", content, re.MULTILINE)
    if wall_match:
        out.wall_time = wall_match.group(1).strip()

    # 警告
    if out.normal_termination and out.opt_converged is False:
        out.warnings.append("任务正常结束但优化未收敛到驻点。")
    if out.imaginary_frequencies:
        out.warnings.append(f"存在 {len(out.imaginary_frequencies)} 个虚频，结构可能不是极小点。")
    if not out.normal_termination and not out.error_message:
        out.warnings.append("未检测到 Normal termination，日志可能不完整。")

    return out


def output_to_dict(out: GaussianOutput) -> Dict:
    """转为可序列化字典。"""
    return {
        "filename": out.filename,
        "normal_termination": out.normal_termination,
        "error_message": out.error_message,
        "method": out.method,
        "basis": out.basis,
        "charge": out.charge,
        "multiplicity": out.multiplicity,
        "atom_count": out.atom_count,
        "basis_functions": out.basis_functions,
        "final_energy": out.final_energy,
        "energy_unit": out.energy_unit,
        "stationary_point": out.stationary_point,
        "opt_converged": out.opt_converged,
        "opt_steps": out.opt_steps,
        "max_force": out.max_force,
        "rms_force": out.rms_force,
        "max_displacement": out.max_displacement,
        "rms_displacement": out.rms_displacement,
        "homo_energy": out.homo_energy,
        "lumo_energy": out.lumo_energy,
        "homo_lumo_gap": out.homo_lumo_gap,
        "dipole_moment": out.dipole_moment,
        "frequencies": out.frequencies[:20],  # 只返回前20个避免过大
        "frequency_count": len(out.frequencies),
        "imaginary_frequencies": out.imaginary_frequencies,
        "zero_point_energy": out.zero_point_energy,
        "thermal_enthalpy": out.thermal_enthalpy,
        "thermal_free_energy": out.thermal_free_energy,
        "cpu_time": out.cpu_time,
        "wall_time": out.wall_time,
        "warnings": out.warnings,
    }
