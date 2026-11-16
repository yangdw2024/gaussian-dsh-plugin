"""从结构/计算文件中识别分子并提取 SMILES。

支持格式（按扩展名分发）：
- 直接读入：.mol .sdf .sd .mol2 .pdb .xyz .cdxml
  （优先 OpenBabel 自动判键转 canonical SMILES；若 OpenBabel 缺失/失败则回退 RDKit）
- Gaussian 输入 .gjf：解析 Cartesian 坐标块 → 临时 xyz → OpenBabel / RDKit 回退
- Gaussian 输出 .out/.log：取最后一段 Standard/Input orientation 坐标 → 临时 xyz → OpenBabel / RDKit 回退

返回 {smiles, source_format, source_file, natoms_guess, extractor, warnings}。
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .config import settings

# obabel 可直接读的格式（扩展名小写）
_DIRECT_EXT = {".mol", ".sdf", ".sd", ".mol2", ".pdb", ".xyz", ".cdxml"}

# 完整周期表 1–118 原子序数到元素符号映射（杜绝未知金属静默映射为碳 "C"）
_ATNUM_MAP: Dict[int, str] = {
    1: "H", 2: "He",
    3: "Li", 4: "Be", 5: "B", 6: "C", 7: "N", 8: "O", 9: "F", 10: "Ne",
    11: "Na", 12: "Mg", 13: "Al", 14: "Si", 15: "P", 16: "S", 17: "Cl", 18: "Ar",
    19: "K", 20: "Ca", 21: "Sc", 22: "Ti", 23: "V", 24: "Cr", 25: "Mn", 26: "Fe",
    27: "Co", 28: "Ni", 29: "Cu", 30: "Zn", 31: "Ga", 32: "Ge", 33: "As", 34: "Se", 35: "Br", 36: "Kr",
    37: "Rb", 38: "Sr", 39: "Y", 40: "Zr", 41: "Nb", 42: "Mo", 43: "Tc", 44: "Ru",
    45: "Rh", 46: "Pd", 47: "Ag", 48: "Cd", 49: "In", 50: "Sn", 51: "Sb", 52: "Te", 53: "I", 54: "Xe",
    55: "Cs", 56: "Ba",
    57: "La", 58: "Ce", 59: "Pr", 60: "Nd", 61: "Pm", 62: "Sm", 63: "Eu", 64: "Gd",
    65: "Tb", 66: "Dy", 67: "Ho", 68: "Er", 69: "Tm", 70: "Yb", 71: "Lu",
    72: "Hf", 73: "Ta", 74: "W", 75: "Re", 76: "Os", 77: "Ir", 78: "Pt", 79: "Au",
    80: "Hg", 81: "Tl", 82: "Pb", 83: "Bi", 84: "Po", 85: "At", 86: "Rn",
    87: "Fr", 88: "Ra",
    89: "Ac", 90: "Th", 91: "Pa", 92: "U", 93: "Np", 94: "Pu", 95: "Am", 96: "Cm",
    97: "Bk", 98: "Cf", 99: "Es", 100: "Fm", 101: "Md", 102: "No", 103: "Lr",
    104: "Rf", 105: "Db", 106: "Sg", 107: "Bh", 108: "Hs", 109: "Mt", 110: "Ds",
    111: "Rg", 112: "Cn", 113: "Nh", 114: "Fl", 115: "Mc", 116: "Lv", 117: "Ts", 118: "Og",
}


def _atnum_to_symbol(atnum: int) -> Optional[str]:
    """将原子序数转换为元素符号。dummy atom(<=0) 返回 None，超界(>118) 抛 ValueError。"""
    if atnum <= 0:
        return None
    sym = _ATNUM_MAP.get(atnum)
    if sym is None:
        raise ValueError(f"Unsupported atomic number in orientation block: {atnum}")
    return sym


def _obabel_to_smiles(input_path: Path) -> Tuple[str, str]:
    """用 obabel 把文件转 canonical smiles。返回 (smiles, stderr_tail)。"""
    exe = settings.obabel_exe
    if not exe or not Path(exe).exists():
        raise FileNotFoundError(
            f"OpenBabel 未找到（已尝试内嵌 thirdparty、环境变量 OBABEL_EXE、本机路径）。"
            f"请安装 OpenBabel 或在 settings.obabel_exe 指定路径。当前配置：{exe}"
        )
    env = dict(os.environ)
    exe_parent = Path(exe).resolve().parent
    env["OBABEL_DATADIR"] = str(exe_parent)
    data_subdir = exe_parent / "data"
    if data_subdir.is_dir():
        env["BABEL_DATADIR"] = str(data_subdir)

    try:
        proc = subprocess.run(
            [str(exe), str(input_path), "-ocan"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            close_fds=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            timeout=60,
            env=env,
        )
    except subprocess.TimeoutExpired:
        return "", "OpenBabel 执行超时（60秒）"

    out = (proc.stdout or "").strip().splitlines()
    smiles = ""
    for line in out:
        line = line.strip()
        if not line:
            continue
        # obabel -ocan 输出形如 "CCO\tethanol"，取 tab 前
        smiles = line.split("\t")[0].split()[0].strip()
        if smiles:
            break
    return smiles, (proc.stderr or "")[-500:]


def _parse_gjf_coords(text: str) -> List[tuple]:
    """从 gjf 文本提取 Cartesian 坐标。返回 [(element, x, y, z), ...]。"""
    lines = text.splitlines()
    coords: List[tuple] = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i].strip()
        # 找电荷自旋行：两个整数，如 "0 1"
        m = re.match(r"^\s*(-?\d+)\s+(\d+)\s*$", line)
        if m and i + 1 < n:
            j = i + 1
            while j < n:
                cl = lines[j].strip()
                if not cl:
                    break
                parts = cl.replace(",", " ").split()
                if len(parts) >= 4:
                    try:
                        x, y, z = float(parts[1]), float(parts[2]), float(parts[3])
                        elem = parts[0]
                        if elem.isdigit():
                            sym = _atnum_to_symbol(int(elem))
                            if sym is None:
                                j += 1
                                continue
                            elem = sym
                        coords.append((elem, x, y, z))
                    except ValueError:
                        break
                j += 1
            if coords:
                return coords
        i += 1
    return coords


def _parse_orientation_block(text: str) -> Tuple[List[tuple], int]:
    """从 Gaussian out/log 取最后一个 Standard/Input orientation 坐标块。返回 (coords, dummy_count)。"""
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
        return [], 0

    idx = max(blocks)
    tail = text[idx:].splitlines()
    coords: List[tuple] = []
    dummy_skipped = 0
    # Gaussian orientation 块结构：第1条 --- 在表头前，第2条 --- 在表头后，第3条 --- 结束坐标区
    dash_count = 0
    for line in tail[1:]:
        if re.match(r"^\s*-{5,}\s*$", line):
            dash_count += 1
            if dash_count >= 3:
                break
            continue
        if dash_count < 2:
            continue
        parts = line.split()
        if len(parts) >= 6:
            try:
                atnum = int(parts[1])
                x, y, z = float(parts[3]), float(parts[4]), float(parts[5])
                sym = _atnum_to_symbol(atnum)
                if sym is None:
                    dummy_skipped += 1
                    continue
                coords.append((sym, x, y, z))
            except ValueError:
                break
    return coords, dummy_skipped


def _coords_to_xyz_text(coords: List[tuple], name: str) -> str:
    lines = [str(len(coords)), name]
    for el, x, y, z in coords:
        lines.append(f"{el} {x:.6f} {y:.6f} {z:.6f}")
    return "\n".join(lines) + "\n"


def _coords_to_xyz(coords: List[tuple], name: str) -> Tuple[Path, Path]:
    """把坐标写成临时 xyz 文件，返回 (tmp_dir, xyz_path)，调用方负责在 finally 删除 tmp_dir。"""
    tmp_dir = Path(tempfile.mkdtemp(prefix="struct_"))
    xyz_path = tmp_dir / "in.xyz"
    xyz_path.write_text(_coords_to_xyz_text(coords, name), encoding="ascii")
    return tmp_dir, xyz_path


def _estimate_natoms_direct(path: Path, ext: str) -> Optional[int]:
    """针对直接输入文件估算原子数。"""
    try:
        if ext == ".xyz":
            first = path.read_text(encoding="utf-8", errors="ignore").splitlines()[0].strip()
            return int(first)
        if ext in (".mol", ".sdf", ".sd"):
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
            if len(lines) >= 4:
                counts_line = lines[3]
                # V2000 counts line has 3-char natoms field at start
                if "V2000" in counts_line:
                    return int(counts_line[:3].strip())
                parts = counts_line.split()
                if parts and parts[0].isdigit():
                    return int(parts[0])
    except Exception:
        pass
    return None


def _rdkit_smiles_from_coords(coords: List[tuple], name: str) -> Tuple[Optional[str], Optional[int], List[str]]:
    """OpenBabel 不可用或失败时，用 RDKit MolFromXYZBlock + rdDetermineBonds 进行兜底提取。"""
    warnings: List[str] = []
    try:
        from rdkit import Chem
        from rdkit.Chem import rdDetermineBonds
    except Exception as exc:
        return None, None, [f"RDKit 键级推导模块不可用: {exc}"]

    xyz_block = _coords_to_xyz_text(coords, name)
    mol = Chem.MolFromXYZBlock(xyz_block)
    if mol is None:
        return None, None, ["RDKit 无法解析 XYZ 坐标块。"]

    try:
        rdDetermineBonds.DetermineBonds(mol, charge=0)
    except Exception as exc:
        try:
            rdDetermineBonds.DetermineConnectivity(mol)
            warnings.append(f"RDKit 仅推导了连接性而未能确定全部键级（{exc}），SMILES 仅供参考。")
        except Exception as exc2:
            return None, None, [f"RDKit 自动判键失败: {exc2}"]

    try:
        smi = Chem.MolToSmiles(Chem.RemoveHs(mol), isomericSmiles=True)
    except Exception:
        smi = Chem.MolToSmiles(mol, isomericSmiles=True)
    return smi, mol.GetNumAtoms(), warnings


def _rdkit_smiles_from_direct(path: Path, ext: str) -> Tuple[Optional[str], Optional[int], List[str]]:
    """对 .mol/.sdf/.sd/.pdb/.xyz 使用 RDKit 兜底解析。"""
    warnings: List[str] = []
    try:
        from rdkit import Chem
    except Exception as exc:
        return None, None, [f"RDKit 不可用: {exc}"]

    mol = None
    if ext in (".mol",):
        mol = Chem.MolFromMolFile(str(path), removeHs=False)
    elif ext in (".sdf", ".sd"):
        sup = Chem.SDMolSupplier(str(path), removeHs=False)
        mol = next((m for m in sup if m is not None), None)
    elif ext == ".pdb":
        mol = Chem.MolFromPDBFile(str(path), removeHs=False)
    elif ext == ".xyz":
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
            n_declared = int(lines[0].strip())
            coords: List[tuple] = []
            for row in lines[2:2 + n_declared]:
                parts = row.split()
                if len(parts) >= 4:
                    coords.append((parts[0], float(parts[1]), float(parts[2]), float(parts[3])))
            if coords:
                return _rdkit_smiles_from_coords(coords, path.stem)
        except Exception as exc:
            return None, None, [f"RDKit XYZ 读取失败: {exc}"]

    if mol is None:
        return None, None, [f"RDKit 不支持或无法读取 {ext} 文件。"]

    natoms = mol.GetNumAtoms()
    try:
        smi = Chem.MolToSmiles(Chem.RemoveHs(mol), isomericSmiles=True)
    except Exception:
        smi = Chem.MolToSmiles(mol, isomericSmiles=True)
    return smi, natoms, warnings


def _smiles_atom_count_with_hs(smiles: str) -> Optional[int]:
    try:
        from rdkit import Chem
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return None
        return Chem.AddHs(mol).GetNumAtoms()
    except Exception:
        return None


def extract_smiles_from_file(path: str) -> Dict:
    """主入口：根据文件扩展名提取 SMILES，并清理所有临时文件。"""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"文件不存在：{path}")
    ext = p.suffix.lower()
    warnings: List[str] = []
    natoms_guess: Optional[int] = None
    extractor = "openbabel"
    smiles = ""
    err = ""

    if ext in _DIRECT_EXT:
        source = ext.lstrip(".")
        natoms_guess = _estimate_natoms_direct(p, ext)
        try:
            smiles, err = _obabel_to_smiles(p)
        except FileNotFoundError as exc:
            err = str(exc)

        if not smiles:
            r_smi, r_natoms, r_warns = _rdkit_smiles_from_direct(p, ext)
            if r_smi:
                smiles = r_smi
                natoms_guess = natoms_guess or r_natoms
                extractor = "rdkit_fallback"
                warnings.append("OpenBabel 不可用或未识别，已使用 RDKit 兜底提取 SMILES。")
                warnings.extend(r_warns)

    elif ext == ".gjf":
        text = p.read_text(encoding="utf-8", errors="ignore")
        coords = _parse_gjf_coords(text)
        if not coords:
            raise ValueError("未能从 gjf 解析出 Cartesian 坐标块")
        natoms_guess = len(coords)
        source = "gjf(cartesian)"
        tmp_dir, xyz_path = _coords_to_xyz(coords, p.stem)
        try:
            try:
                smiles, err = _obabel_to_smiles(xyz_path)
            except FileNotFoundError as exc:
                err = str(exc)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

        if not smiles:
            r_smi, _, r_warns = _rdkit_smiles_from_coords(coords, p.stem)
            if r_smi:
                smiles = r_smi
                extractor = "rdkit_fallback"
                warnings.append("OpenBabel 不可用或未识别，已使用 RDKit 从 gjf 坐标自动判键兜底提取 SMILES。")
                warnings.extend(r_warns)

    elif ext in (".out", ".log"):
        text = p.read_text(encoding="utf-8", errors="ignore")
        coords, dummy_skipped = _parse_orientation_block(text)
        if not coords:
            raise ValueError("未能从 out/log 找到 Standard/Input orientation 坐标块")
        natoms_guess = len(coords)
        source = f"{ext.lstrip('.')}(last_orientation)"
        if dummy_skipped:
            warnings.append(f"已忽略 {dummy_skipped} 个 dummy atom (原子序数<=0)。")
        warnings.append("从最后一帧优化坐标提取；若需初始结构请用 gjf。")
        tmp_dir, xyz_path = _coords_to_xyz(coords, p.stem)
        try:
            try:
                smiles, err = _obabel_to_smiles(xyz_path)
            except FileNotFoundError as exc:
                err = str(exc)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

        if not smiles:
            r_smi, _, r_warns = _rdkit_smiles_from_coords(coords, p.stem)
            if r_smi:
                smiles = r_smi
                extractor = "rdkit_fallback"
                warnings.append("OpenBabel 不可用或未识别，已使用 RDKit 从 orientation 坐标兜底提取 SMILES。")
                warnings.extend(r_warns)
    else:
        raise ValueError(
            f"不支持的扩展名 {ext}。支持：{', '.join(sorted(_DIRECT_EXT))}, .gjf, .out, .log"
        )

    if not smiles:
        raise RuntimeError(f"未能从 {p.name} 识别出分子（可能结构损坏、缺 OpenBabel 或含特殊配位键）。{err}")

    if natoms_guess is None:
        natoms_guess = _smiles_atom_count_with_hs(smiles)

    return {
        "smiles": smiles,
        "source_format": source,
        "source_file": p.name,
        "natoms_guess": natoms_guess,
        "extractor": extractor,
        "warnings": warnings,
    }
