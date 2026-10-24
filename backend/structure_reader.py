"""从结构/计算文件中识别分子并提取 SMILES。

支持格式（按扩展名分发）：
- 直接喂 OpenBabel：.mol .sdf .sd .mol2 .pdb .xyz .cdxml
  （obabel 自动判键、转 canonical SMILES）
- Gaussian 输入 .gjf：解析 Cartesian 坐标块 → 临时 xyz → obabel
- Gaussian 输出 .out/.log：取最后一段 Standard/Input orientation 坐标 → 临时 xyz → obabel

返回 {smiles, source_format, natoms, warnings}。
"""
from __future__ import annotations

import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

from .config import settings

# obabel 可直接读的格式（扩展名小写）
_DIRECT_EXT = {".mol", ".sdf", ".sd", ".mol2", ".pdb", ".xyz", ".cdxml"}


def _obabel_to_smiles(input_path: Path) -> tuple:
    """用 obabel 把文件转 canonical smiles。返回 (smiles, stderr_tail)。"""
    exe = settings.obabel_exe
    if not exe or not Path(exe).exists():
        raise FileNotFoundError(
            f"OpenBabel 未找到（已尝试内嵌 thirdparty、环境变量 OBABEL_EXE、本机路径）。"
            f"请安装 OpenBabel 或在 settings.obabel_exe 指定路径。当前配置：{exe}"
        )
    # obabel 需要在同目录找到 .obf 插件和 data/；设 OBABEL_DATADIR 兜底
    env = dict(os.environ)
    env["OBABEL_DATADIR"] = str(Path(exe).parent)
    proc = subprocess.run(
        [str(exe), str(input_path), "-ocan"],
        capture_output=True, text=True, encoding="utf-8", errors="ignore",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        timeout=60, env=env,
    )
    out = (proc.stdout or "").strip().splitlines()
    # canonical smiles 输出：第一列是 smiles，第二列是标题（可能空）
    smiles = ""
    for line in out:
        line = line.strip()
        if not line:
            continue
        # obabel -ocan 输出形如 "CCO	ethanol"，取 tab 前
        smiles = line.split("\t")[0].strip()
        break
    return smiles, (proc.stderr or "")[-500:]


def _parse_gjf_coords(text: str) -> List[tuple]:
    """从 gjf 文本提取 Cartesian 坐标。返回 [(element,x,y,z), ...]。"""
    lines = text.splitlines()
    coords = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i].strip()
        # 找电荷自旋行：两个整数，如 "0 1"
        m = re.match(r"^\s*(-?\d+)\s+(\d+)\s*$", line)
        if m and i + 1 < n:
            # 下一行开始是坐标，直到空行
            j = i + 1
            while j < n:
                cl = lines[j].strip()
                if not cl:
                    break
                parts = cl.replace(",", " ").split()
                if len(parts) >= 4:
                    try:
                        x, y, z = float(parts[1]), float(parts[2]), float(parts[3])
                        coords.append((parts[0], x, y, z))
                    except ValueError:
                        break
                j += 1
            if coords:
                return coords
        i += 1
    return coords


def _parse_orientation_block(text: str) -> List[tuple]:
    """从 Gaussian out/log 取最后一个 Standard/Input orientation 坐标块。"""
    blocks = []
    for header in ("Standard orientation:", "Input orientation:"):
        start = 0
        while True:
            idx = text.find(header, start)
            if idx < 0:
                break
            blocks.append(idx)
            start = idx + 1
    if not blocks:
        return []
    # 取最后一个块
    idx = blocks[-1]
    tail = text[idx:].splitlines()
    coords = []
    # 头 5 行是标题：Center/Atomic/... 然后是分隔线
    started = False
    for line in tail[5:]:
        if re.match(r"^\s*-+\s*$", line):
            if started:
                break
            started = True
            continue
        if not started:
            continue
        parts = line.split()
        if len(parts) >= 6:
            try:
                # 格式: Center 原子序号 类型 x y z
                atnum = int(parts[1])
                x, y, z = float(parts[3]), float(parts[4]), float(parts[5])
                # 原子序号 → 元素符号（简化映射）
                coords.append((_atnum_to_symbol(atnum), x, y, z))
            except ValueError:
                break
    return coords


_ATNUM_MAP = {1:"H",2:"He",3:"Li",4:"Be",5:"B",6:"C",7:"N",8:"O",9:"F",10:"Ne",
 11:"Na",12:"Mg",13:"Al",14:"Si",15:"P",16:"S",17:"Cl",18:"Ar",19:"K",20:"Ca",
 26:"Fe",29:"Cu",30:"Zn",35:"Br",36:"Kr",47:"Ag",53:"I",79:"Au",80:"Hg"}


def _atnum_to_symbol(atnum: int) -> str:
    return _ATNUM_MAP.get(atnum, "C")


def _coords_to_xyz(coords: List[tuple], name: str) -> Path:
    """把坐标写成临时 xyz 文件，返回路径。"""
    tmp = Path(tempfile.mkdtemp(prefix="struct_")) / "in.xyz"
    lines = [str(len(coords)), name]
    for el, x, y, z in coords:
        lines.append(f"{el} {x:.6f} {y:.6f} {z:.6f}")
    tmp.write_text("\n".join(lines), encoding="ascii")
    return tmp


def extract_smiles_from_file(path: str) -> Dict:
    """主入口：根据文件扩展名提取 SMILES。"""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"文件不存在：{path}")
    ext = p.suffix.lower()
    warnings: List[str] = []

    if ext in _DIRECT_EXT:
        smiles, err = _obabel_to_smiles(p)
        source = ext.lstrip(".")
    elif ext == ".gjf":
        text = p.read_text(encoding="utf-8", errors="ignore")
        coords = _parse_gjf_coords(text)
        if not coords:
            raise ValueError("未能从 gjf 解析出 Cartesian 坐标块")
        xyz = _coords_to_xyz(coords, p.stem)
        smiles, err = _obabel_to_smiles(xyz)
        source = "gjf(cartesian)"
    elif ext in (".out", ".log"):
        text = p.read_text(encoding="utf-8", errors="ignore")
        coords = _parse_orientation_block(text)
        if not coords:
            raise ValueError("未能从 out/log 找到 Standard/Input orientation 坐标块")
        xyz = _coords_to_xyz(coords, p.stem)
        smiles, err = _obabel_to_smiles(xyz)
        source = f"{ext.lstrip('.')}(last_orientation)"
        warnings.append("从最后一帧优化坐标提取；若需初始结构请用 gjf。")
    else:
        raise ValueError(
            f"不支持的扩展名 {ext}。支持：{', '.join(sorted(_DIRECT_EXT))}, .gjf, .out, .log"
        )

    if not smiles:
        raise RuntimeError(f"OpenBabel 未能从 {p.name} 识别出分子（可能结构损坏或含特殊配位键）。{err}")

    return {
        "smiles": smiles,
        "source_format": source,
        "source_file": p.name,
        "natoms_guess": None,
        "warnings": warnings,
    }
