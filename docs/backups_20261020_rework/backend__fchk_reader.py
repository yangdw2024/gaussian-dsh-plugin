"""fchk 文件读取器：提取轨道能量、电子数等信息。

不依赖 Multiwfn，直接读 Gaussian fchk 文本文件。
用于生成 MO 能级图、自动推断 HOMO/LUMO 编号。

fchk 格式说明：
- 单值行：Keyword    Type    Value    如 "Number of alpha electrons    I    13"
- 数组行：Keyword    R    N=    N    如 "Alpha Orbital Energies    R    N=    40"
  后续行是缩进的浮点数，每行多个
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple


@dataclass
class OrbitalInfo:
    """轨道信息。"""
    alpha_energies: List[float]
    beta_energies: List[float]
    n_alpha_electrons: int
    n_beta_electrons: int
    n_basis_functions: int

    @property
    def homo_alpha_index(self) -> int:
        """Alpha HOMO 轨道编号（0-based）。"""
        return self.n_alpha_electrons - 1

    @property
    def lumo_alpha_index(self) -> int:
        """Alpha LUMO 轨道编号（0-based）。"""
        return self.n_alpha_electrons

    @property
    def homo_beta_index(self) -> int:
        """Beta HOMO 轨道编号（0-based）。"""
        return self.n_beta_electrons - 1

    @property
    def lumo_beta_index(self) -> int:
        """Beta LUMO 轨道编号（0-based）。"""
        return self.n_beta_electrons

    @property
    def is_closed_shell(self) -> bool:
        """是否闭壳层（alpha = beta 电子数）。"""
        return self.n_alpha_electrons == self.n_beta_electrons

    @property
    def homo_energy(self) -> Optional[float]:
        """HOMO 能量（闭壳层用 alpha）。"""
        if not self.alpha_energies:
            return None
        idx = self.homo_alpha_index
        if 0 <= idx < len(self.alpha_energies):
            return self.alpha_energies[idx]
        return None

    @property
    def lumo_energy(self) -> Optional[float]:
        """LUMO 能量（闭壳层用 alpha）。"""
        if not self.alpha_energies:
            return None
        idx = self.lumo_alpha_index
        if 0 <= idx < len(self.alpha_energies):
            return self.alpha_energies[idx]
        return None

    @property
    def gap(self) -> Optional[float]:
        """HOMO-LUMO gap（eV）。注意：fchk 中能量单位是 Hartree，需要转换。"""
        h = self.homo_energy
        l = self.lumo_energy
        if h is None or l is None:
            return None
        # 1 Hartree = 27.2114 eV
        return (l - h) * 27.2114


def _parse_fchk_scalar(text: str, keyword: str) -> Optional[float]:
    """从 fchk 文本中提取标量值。

    格式：Keyword    Type    Value
    如：Number of alpha electrons    I    13
    """
    # 匹配关键词行，提取最后一个数字
    pattern = re.compile(
        rf"^{re.escape(keyword)}\s+[IRLBCE]\s+(-?[\d.]+)",
        re.MULTILINE,
    )
    match = pattern.search(text)
    if match:
        return float(match.group(1))
    return None


def _parse_fchk_array(text: str, keyword: str) -> List[float]:
    """从 fchk 文本中提取数组数据。

    格式：
    Keyword    R    N=    N
      num1  num2  num3 ...
      num4  num5  ...
    """
    # 先找关键词行
    header_pattern = re.compile(
        rf"^{re.escape(keyword)}\s+R\s+N=\s+(\d+)\s*$",
        re.MULTILINE,
    )
    header_match = header_pattern.search(text)
    if not header_match:
        return []

    n_values = int(header_match.group(1))

    # 从关键词行之后开始读取数字行
    start_pos = header_match.end()
    remaining = text[start_pos:]

    # 收集所有浮点数，直到遇到下一个关键词行（不以空格开头的行）
    numbers = []
    for line in remaining.splitlines():
        # 如果行不以空格开头，说明是下一个关键词了，停止
        if line and not line[0].isspace():
            break
        # 提取行中的所有浮点数
        for token in line.split():
            try:
                numbers.append(float(token))
            except ValueError:
                continue
        if len(numbers) >= n_values:
            break

    return numbers[:n_values]


def read_fchk_orbital_info(fchk_path: Path) -> OrbitalInfo:
    """读取 fchk 文件中的轨道能量和电子数。

    Args:
        fchk_path: fchk 文件路径

    Returns:
        OrbitalInfo 对象

    Raises:
        FileNotFoundError: fchk 文件不存在
        ValueError: 无法解析关键信息
    """
    fchk_path = Path(fchk_path)
    if not fchk_path.exists():
        raise FileNotFoundError(f"fchk 文件不存在：{fchk_path}")

    text = fchk_path.read_text(encoding="utf-8", errors="ignore")

    # Alpha 轨道能量
    alpha_energies = _parse_fchk_array(text, "Alpha Orbital Energies")
    # Beta 轨道能量（开壳层才有）
    beta_energies = _parse_fchk_array(text, "Beta Orbital Energies")

    # 电子数
    n_alpha = _parse_fchk_scalar(text, "Number of alpha electrons")
    n_beta = _parse_fchk_scalar(text, "Number of beta electrons")

    # 基函数数
    n_basis = _parse_fchk_scalar(text, "Number of basis functions")

    if n_alpha is None:
        raise ValueError("fchk 中未找到 'Number of alpha electrons'")
    if not alpha_energies:
        raise ValueError("fchk 中未找到 'Alpha Orbital Energies'")

    return OrbitalInfo(
        alpha_energies=alpha_energies,
        beta_energies=beta_energies,
        n_alpha_electrons=int(n_alpha),
        n_beta_electrons=int(n_beta) if n_beta is not None else int(n_alpha),
        n_basis_functions=int(n_basis) if n_basis is not None else 0,
    )


def generate_mo_level_svg(orbital_info: OrbitalInfo, n_levels: int = 5) -> str:
    """生成 MO 能级图 SVG。

    显示 HOMO-n ... HOMO ─── gap ─── LUMO ... LUMO+n。
    闭壳层只画一组，开壳层 alpha/beta 并列。

    Args:
        orbital_info: 轨道信息
        n_levels: HOMO 下方和 LUMO 上方各显示几级

    Returns:
        SVG 字符串
    """
    h = orbital_info.homo_energy
    l = orbital_info.lumo_energy
    if h is None or l is None:
        return "<svg xmlns='http://www.w3.org/2000/svg' width='400' height='200'><text x='20' y='100'>无法生成能级图</text></svg>"

    gap_ev = orbital_info.gap
    gap_hartree = l - h

    # 收集能级数据（Hartree）
    levels = []
    homo_idx = orbital_info.homo_alpha_index

    # HOMO-n 到 HOMO
    for i in range(min(n_levels, homo_idx + 1)):
        idx = homo_idx - i
        if 0 <= idx < len(orbital_info.alpha_energies):
            label = "HOMO" if i == 0 else f"HOMO-{i}"
            levels.append((label, orbital_info.alpha_energies[idx], "occupied"))

    # LUMO 到 LUMO+n
    lumo_idx = orbital_info.lumo_alpha_index
    for i in range(min(n_levels, len(orbital_info.alpha_energies) - lumo_idx)):
        idx = lumo_idx + i
        if 0 <= idx < len(orbital_info.alpha_energies):
            label = "LUMO" if i == 0 else f"LUMO+{i}"
            levels.append((label, orbital_info.alpha_energies[idx], "virtual"))

    # SVG 布局
    width = 520
    height = 420
    margin_left = 100
    margin_right = 120
    margin_top = 40
    margin_bottom = 40

    energies = [e for _, e, _ in levels]
    e_min = min(energies) - 0.05
    e_max = max(energies) + 0.05
    e_range = e_max - e_min if e_max > e_min else 1.0

    def y_pos(e: float) -> float:
        return margin_top + (e_max - e) / e_range * (height - margin_top - margin_bottom)

    lines = [
        f"<svg xmlns='http://www.w3.org/2000/svg' width='{width}' height='{height}' font-family='Arial, sans-serif' font-size='12'>",
        f"  <rect width='{width}' height='{height}' fill='white'/>",
    ]

    # 能级线
    for label, energy, kind in levels:
        y = y_pos(energy)
        color = "#2563eb" if kind == "occupied" else "#dc2626"
        lines.append(f"  <line x1='{margin_left}' y1='{y:.1f}' x2='{width - margin_right}' y2='{y:.1f}' stroke='{color}' stroke-width='2'/>")
        lines.append(f"  <text x='{margin_left - 10}' y='{y + 4:.1f}' text-anchor='end' fill='{color}'>{label}</text>")
        lines.append(f"  <text x='{width - margin_right + 10}' y='{y + 4:.1f}' fill='{color}'>{energy:.4f}</text>")

    # Gap 标注
    y_h = y_pos(h)
    y_l = y_pos(l)
    arrow_x = width - margin_right + 50
    lines.append(f"  <defs><marker id='arrow' markerWidth='8' markerHeight='8' refX='4' refY='4' orient='auto'><path d='M0,0 L8,4 L0,8 z' fill='black'/></marker></defs>")
    lines.append(f"  <line x1='{arrow_x}' y1='{y_h:.1f}' x2='{arrow_x}' y2='{y_l:.1f}' stroke='black' stroke-width='1' marker-start='url(#arrow)' marker-end='url(#arrow)'/>")
    lines.append(f"  <text x='{arrow_x + 10}' y='{(y_h + y_l) / 2:.1f}'>gap = {gap_ev:.3f} eV</text>")

    lines.append(f"  <text x='{width / 2}' y='{height - 15}' text-anchor='middle' fill='#666'>MO Energy Diagram (Hartree)</text>")
    lines.append("</svg>")

    return "\n".join(lines)
