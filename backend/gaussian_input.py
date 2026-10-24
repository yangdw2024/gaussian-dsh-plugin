"""Gaussian 输入文件（.gjf）生成器。

生成标准 Gaussian 16 输入：Link0 命令 + Route section + Title + 电荷自旋 + 坐标。
支持任务类型：sp / opt / freq / opt+freq / td / irc / scan。
支持常用方法、基组、色散校正、溶剂模型、SCF 控制等关键词组合校验。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


# 常用方法（泛函/后HF），用于校验和提示
KNOWN_METHODS = {
    "hf", "b3lyp", "b3lyp/gd3bj", "wb97xd", "wb97x-d3", "m062x", "m06-2x",
    "pbe0", "pbe1pbe", "cam-b3lyp", "lc-wpbe", "tpssh", "bhandhlyp",
    "mp2", "mp4", "ccsd", "ccsd(t)", "qcisd", "casscf", "caspt2",
}

# 常用基组（内置名，Gaussian 原生支持）
KNOWN_BASES = {
    "sto-3g", "3-21g", "6-31g", "6-31g(d)", "6-31g(d,p)", "6-31+g(d)",
    "6-31+g(d,p)", "6-311g", "6-311g(d,p)", "6-311+g(d,p)", "6-311++g(d,p)",
    "6-311++g(3df,3pd)", "def2svp", "def2-svp", "def2tzvp", "def2-tzvp",
    "def2qzvp", "def2-qzvp", "cc-pvdz", "cc-pvtz", "cc-pvqz", "aug-cc-pvdz",
    "aug-cc-pvtz", "lanl2dz", "lanl2mb", "sdd", "sddall",
}

# 任务类型到 route 关键词的映射
JOB_TYPE_KEYWORDS = {
    "sp": "",
    "opt": "opt",
    "freq": "freq",
    "opt+freq": "opt freq",
    "td": "td",
    "irc": "irc",
    "scan": "scan",
}


@dataclass
class GaussianInputRequest:
    """生成 .gjf 的请求参数。"""
    job_name: str = "gaussian_job"
    job_type: str = "opt"  # sp/opt/freq/opt+freq/td/irc/scan
    method: str = "B3LYP"
    basis: str = "6-31G(d,p)"
    charge: int = 0
    multiplicity: int = 1
    # 坐标：[(元素符号, x, y, z), ...]
    atoms: List[Tuple[str, float, float, float]] = field(default_factory=list)
    # 可选
    mem: Optional[str] = None
    nproc: Optional[int] = None
    chk: Optional[str] = None
    extra_keywords: List[str] = field(default_factory=list)
    title: Optional[str] = None
    # 自定义 route（若提供则覆盖 method/basis/job_type 组合）
    custom_route: Optional[str] = None
    # 附加段（基组/ECP/溶剂分子等，原样追加在坐标后）
    append_text: Optional[str] = None


def _sanitize_name(name: str) -> str:
    """清理文件名，只保留安全字符。"""
    cleaned = re.sub(r"[^\w\-.]", "_", name.strip())
    return cleaned or "gaussian_job"


def _validate_atoms(atoms: List[Tuple]) -> List[str]:
    """校验坐标，返回警告列表。"""
    warnings = []
    if not atoms:
        warnings.append("原子坐标为空，生成的输入需要手动补充坐标。")
        return warnings
    for i, atom in enumerate(atoms):
        if len(atom) != 4:
            warnings.append(f"第 {i+1} 个原子格式应为 (元素, x, y, z)，实际 {len(atom)} 项。")
            continue
        elem, x, y, z = atom
        if not isinstance(elem, str) or not elem.strip():
            warnings.append(f"第 {i+1} 个原子元素符号为空。")
        try:
            float(x); float(y); float(z)
        except (TypeError, ValueError):
            warnings.append(f"第 {i+1} 个原子坐标含非数值。")
    return warnings


def _build_route(req: GaussianInputRequest) -> Tuple[str, List[str]]:
    """构建 route section，返回 (route, warnings)。"""
    warnings = []
    if req.custom_route:
        return req.custom_route.strip().lstrip("#").strip(), warnings

    method_l = req.method.strip().lower()
    basis_l = req.basis.strip().lower()
    job_l = req.job_type.strip().lower()

    if method_l not in KNOWN_METHODS:
        warnings.append(f"方法 '{req.method}' 不在内置常用列表，将原样写入（请确认 Gaussian 支持）。")
    if basis_l not in KNOWN_BASES:
        warnings.append(f"基组 '{req.basis}' 不在内置常用列表，将原样写入；若为自定义基组需在 append_text 中提供。")
    if job_l not in JOB_TYPE_KEYWORDS:
        warnings.append(f"任务类型 '{req.job_type}' 未知，将作为 sp 处理。")
        job_l = "sp"

    # method/basis 组合
    route_core = f"{req.method}/{req.basis}"
    job_kw = JOB_TYPE_KEYWORDS[job_l]

    parts = [route_core]
    if job_kw:
        parts.append(job_kw)

    # 额外关键词去重
    seen = set()
    for kw in req.extra_keywords:
        kw = kw.strip()
        if not kw:
            continue
        key = kw.lower()
        if key in seen:
            continue
        seen.add(key)
        parts.append(kw)

    # 常见组合校验
    route_lower = " ".join(parts).lower()
    if "opt" in route_lower and "calcfc" in route_lower:
        warnings.append("opt=calcfc 会在优化开始时计算解析 Hessian，大体系（>100原子）可能内存爆炸；建议用 opt=calcall 或不加 calcfc。")
    if "freq" in route_lower and "opt" not in route_lower:
        warnings.append("纯 freq 任务要求输入结构已是驻点；若非优化后结构，频率结果无意义。")
    if "td" in route_lower and "opt" in route_lower:
        warnings.append("TDDFT 激发态优化（TD opt）计算量大，建议先基态优化再做 TD 单点。")

    route = " ".join(parts)
    return route, warnings


def generate_gjf(req: GaussianInputRequest) -> dict:
    """生成 Gaussian 输入文件内容。

    返回：
        {
            "content": str,        # .gjf 完整内容
            "filename": str,       # 建议文件名
            "route": str,          # route section（不含 #）
            "warnings": List[str], # 校验警告
            "atom_count": int,
        }
    """
    warnings = []
    warnings.extend(_validate_atoms(req.atoms))

    route, route_warnings = _build_route(req)
    warnings.extend(route_warnings)

    from .config import settings

    job_name = _sanitize_name(req.job_name)
    mem = req.mem or settings.default_mem
    nproc = req.nproc or settings.default_nproc
    chk = req.chk or f"{job_name}.chk"
    title = req.title or f"{req.method}/{req.basis} {req.job_type} for {job_name}"

    lines = []
    # Link 0 — 注意顺序：%nosave 必须在 %chk 之前，否则 Gaussian 会删除 chk 文件
    # %NoSave 会删除其之前命名的 scratch 文件（包括 chk）
    lines.append(f"%mem={mem}")
    lines.append(f"%nprocshared={nproc}")
    lines.append(f"%nosave")
    lines.append(f"%chk={chk}")
    # Route
    lines.append(f"# {route}")
    lines.append("")
    # Title
    lines.append(title)
    lines.append("")
    # Charge & multiplicity
    lines.append(f"{req.charge} {req.multiplicity}")
    # Coordinates
    for atom in req.atoms:
        if len(atom) == 4:
            elem, x, y, z = atom
            lines.append(f" {elem:<3s} {float(x):>14.8f} {float(y):>14.8f} {float(z):>14.8f}")
    lines.append("")
    # 附加段
    if req.append_text:
        lines.append(req.append_text.rstrip())
        lines.append("")
    # 结尾空行（Gaussian 要求）
    lines.append("")

    content = "\n".join(lines)
    return {
        "content": content,
        "filename": f"{job_name}.gjf",
        "route": route,
        "warnings": warnings,
        "atom_count": len(req.atoms),
    }


# Gaussian 64-bit 下 1 word = 8 字节（W/KW/MW/GW/TW 为 word 单位，需换算）
_WORD_BYTES = 8
_WORD_MB = _WORD_BYTES / (1024 * 1024)


def _parse_mem_to_mb(text: str) -> float:
    """N3: 把 %mem 值解析为 MB 数值。

    支持 GB/MB/KB 与 word 单位 W/KW/MW/GW/TW；裸数字按 MB。
    无法识别的单位直接 raise（fail-closed），绝不当 MB 低估放行。
    """
    m = re.search(r"%mem\s*=\s*([\d.]+)\s*([a-zA-Z]+)?", text, re.IGNORECASE)
    if not m:
        raise ValueError(f"%mem 无法解析：{text.strip()}")
    val = float(m.group(1))
    raw_unit = m.group(2)
    unit = raw_unit.upper() if raw_unit else "MB"
    if unit == "GB":
        return val * 1024
    if unit == "MB":
        return val
    if unit == "KB":
        return val / 1024
    if unit == "W":
        return val * _WORD_MB
    if unit == "KW":
        return val * 1024 * _WORD_MB
    if unit == "MW":
        return val * (1024 ** 2) * _WORD_MB
    if unit == "GW":
        return val * (1024 ** 3) * _WORD_MB
    if unit == "TW":
        return val * (1024 ** 4) * _WORD_MB
    raise ValueError(f"%mem 单位 '{raw_unit}' 无法识别，拒绝放行（fail-closed）：{text.strip()}")


def validate_gjf(content: str, max_atoms: int = 300, mem_budget_mb: float = 12288.0,
                 max_nproc: int = 8) -> None:
    """B7: 提交边界校验原始 GJF 文本，防止用户贴入的原文绕过原子数/资源/自旋限制。

    解析失败或越界抛 ValueError（由端点/管理器转成 422 或 ok=false）。
    只做保守硬校验，不阻断合法的自定义基组/附加段。
    """
    if not content or not content.strip():
        raise ValueError("gjf_content 为空")

    lines = content.splitlines()
    link0_mem = None
    nproc = None
    charge = None
    multiplicity = None
    coord_count = 0
    seen_charge_line = False

    # 元素符号集合（用于区分坐标行与电荷多重度行）
    elem_re = re.compile(r"^[A-Za-z]{1,2}$")
    # N3: 坐标行同时接受元素符号（C/He）与原子序数（1-118 的数字）+ 三个坐标值
    coord_re = re.compile(
        r"^\s*(?:[A-Za-z]{1,2}|\d{1,3})\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)"
    )
    cm_re = re.compile(r"^\s*(-?\d+)\s+(\d+)\s*$")

    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        low = line.lower()
        if low.startswith("%mem"):
            # N3: 多段 %mem 取最大值（最保守），而非被后段覆盖；未知单位 fail-closed
            mb = _parse_mem_to_mb(line)
            link0_mem = mb if link0_mem is None else max(link0_mem, mb)
            continue
        if low.startswith("%nprocshared") or low.startswith("%nproc"):
            # R8: 多段 %nprocshared 取最大值（最保守），不被末段合法值覆盖前段超限声明
            nm = re.search(r"=?\s*(\d+)", line)
            if nm:
                val = int(nm.group(1))
                nproc = val if nproc is None else max(nproc, val)
            continue
        if line.startswith("%") or line.startswith("#"):
            continue
        # 电荷多重度行（route/title 之后第一次出现的纯整数对）
        if not seen_charge_line and cm_re.match(line) and not elem_re.match(line.split()[0]):
            charge = int(cm_re.match(line).group(1))
            multiplicity = int(cm_re.match(line).group(2))
            seen_charge_line = True
            continue
        # 坐标行：元素符号 + 三个数值
        if seen_charge_line and coord_re.match(line):
            coord_count += 1
            continue

    if charge is None or multiplicity is None:
        raise ValueError("未找到电荷/多重度行（格式：Charge Multiplicity，如 0 1）")
    # 多重度 = 2S+1，可取 1(单态)/2(双态)/3(三态)...，只要求 ≥1，不要求奇数
    if multiplicity < 1:
        raise ValueError(f"多重度 {multiplicity} 非法：必须为 ≥1 的正整数（2S+1）")
    if abs(charge) > 50:
        raise ValueError(f"电荷 {charge} 异常，请核对")

    if coord_count > max_atoms:
        raise ValueError(f"坐标含 {coord_count} 个原子，超过本机上限 {max_atoms}；请降低体系规模或设置 GAUSSIAN_MAX_ATOMS")

    if link0_mem is not None and link0_mem > mem_budget_mb:
        raise ValueError(
            f"%mem 申请 {link0_mem/1024:.1f}GB 超过本机预算 {mem_budget_mb/1024:.0f}GB，"
            "15.1GB 物理内存下禁止超量申请。"
        )
    if nproc is not None and nproc > max_nproc:
        raise ValueError(f"%nprocshared={nproc} 超过本机上限 {max_nproc}，请降低并行核数")
