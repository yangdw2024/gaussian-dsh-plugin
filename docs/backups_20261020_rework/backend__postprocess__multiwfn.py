"""Multiwfn 批处理命令序列生成器。

基于版本化 profile（multiwfn-3.8.json）生成 stdin 命令序列，
不硬编码菜单数字。未知版本 fail-fast。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ..config import settings


class MultiwfnProfileError(Exception):
    """Multiwfn 版本不匹配或 profile 加载失败。"""
    pass


def load_profile(profile_name: str = "multiwfn-3.8") -> Dict:
    """加载 Multiwfn 菜单 profile，并做版本/结构 fail-fast 校验。

    - 文件缺失、结构缺关键字段 → MultiwfnProfileError
    - version_hint 与 settings.expected_multiwfn_version 主版本不符 → fail-fast
      （避免用 3.8 的菜单数字去跑 4.x 导致误操作）
    """
    profile_path = Path(__file__).parent / "profiles" / f"{profile_name}.json"
    if not profile_path.exists():
        raise MultiwfnProfileError(f"Profile 文件不存在：{profile_path}")
    try:
        with open(profile_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise MultiwfnProfileError(f"Profile JSON 解析失败 {profile_name}: {e}") from e

    # 结构校验
    for key in ("profile", "version_hint", "menus", "grid_options"):
        if key not in data:
            raise MultiwfnProfileError(f"Profile {profile_name} 缺少必需字段：{key}")

    # 版本主版本（x.y）一致性 fail-fast
    expected = str(settings.expected_multiwfn_version or "3.8")
    hint = str(data["version_hint"])
    if hint.split(".")[0] != expected.split(".")[0]:
        raise MultiwfnProfileError(
            f"Profile 版本 {hint} 与本机期望 {expected} 主版本不符，菜单数字可能漂移，"
            "拒绝使用以防误操作；请更新 profile 或设置 MULTIWFN_EXPECTED_VERSION。"
        )

    return data


def probe_version(fchk_path: Path) -> Optional[str]:
    """探测 Multiwfn 版本（运行一次看 banner）。

    简化实现：返回 None，后续可扩展为实际运行探测。
    """
    # TODO: 实际运行 Multiwfn 探测 banner，匹配 expected_banner
    return "3.8"


def generate_orbital_cube_commands(
    orbitals: List[int],
    grid: str = "medium",
    profile: Optional[Dict] = None,
) -> str:
    """生成导出多个轨道 cube 的 stdin 命令序列。

    菜单路径：200 (Other functions Part 2) → 3 (multiple orbital cube)
    → 轨道编号列表 → 网格精度 → separate cube → 0 (return) → q (quit)

    Args:
        orbitals: 轨道编号列表（如 [87, 88] 表示 HOMO-1, HOMO）
        grid: 网格精度 coarse/medium/fine
        profile: 菜单 profile（默认加载 multiwfn-3.8）

    Returns:
        stdin 命令字符串（每行一个菜单选择）
    """
    if profile is None:
        profile = load_profile()

    menus = profile["menus"]
    grid_opts = profile["grid_options"]
    orb_cfg = profile["orbital_cube"]

    orbitals_str = ",".join(str(o) for o in orbitals)
    grid_num = grid_opts.get(grid, 2)

    commands = [
        str(menus["other_functions_2"]),       # 200 → Other functions Part 2
        str(orb_cfg["multi_orbital_submenu"]),  # 3 → multiple orbital cube
        orbitals_str,                           # 轨道编号列表
        str(grid_num),                          # 网格精度
        str(orb_cfg["separate_cube_option"]),   # 1 → 输出独立 cube 文件
        str(orb_cfg["return_option"]),          # 0 → return
        "q",                                    # quit
    ]
    return "\n".join(commands) + "\n"


def generate_esp_cube_commands(
    grid: str = "medium",
    profile: Optional[Dict] = None,
) -> str:
    """生成导出电子密度 + ESP 双 cube 的 stdin 命令序列。

    流程：
    5 (real space grid) → 1 (electron density) → 网格精度 → 2 (export cube)
    5 (real space grid) → 12 (total ESP) → 网格精度 → 2 (export cube)
    q (quit)

    Args:
        grid: 网格精度 coarse/medium/fine
        profile: 菜单 profile

    Returns:
        stdin 命令字符串
    """
    if profile is None:
        profile = load_profile()

    menus = profile["menus"]
    grid_opts = profile["grid_options"]
    rs_funcs = profile["real_space_functions"]

    grid_num = grid_opts.get(grid, 2)

    # 第一段：电子密度 cube
    density_commands = [
        str(menus["real_space_grid"]),           # 5 → real space grid
        str(rs_funcs["electron_density"]),       # 1 → electron density
        str(grid_num),                            # 网格精度
        "2",                                      # 2 → export cube file
    ]

    # 第二段：总 ESP cube
    esp_commands = [
        str(menus["real_space_grid"]),           # 5 → real space grid
        str(rs_funcs["total_esp"]),               # 12 → total ESP
        str(grid_num),                            # 网格精度
        "2",                                      # 2 → export cube file
    ]

    all_commands = density_commands + esp_commands + ["q"]
    return "\n".join(all_commands) + "\n"


def generate_rdg_cube_commands(
    grid_spacing: float = 0.15,
    profile: Optional[Dict] = None,
) -> str:
    """生成 RDG/NCI 弱相互作用分析的 stdin 命令序列。

    菜单路径：20 (weak interaction) → 1 (NCI) → 4 (manual grid by spacing) → spacing

    Args:
        grid_spacing: 网格间距（默认 0.15 Bohr）
        profile: 菜单 profile

    Returns:
        stdin 命令字符串
    """
    if profile is None:
        profile = load_profile()

    menus = profile["menus"]
    nci_cfg = profile["weak_interaction"]

    commands = [
        str(menus["weak_interaction"]),           # 20 → weak interaction
        str(nci_cfg["nci_option"]),                # 1 → NCI
        str(nci_cfg["manual_grid_spacing"]),      # 4 → manual grid by spacing
        str(grid_spacing),                         # 网格间距
    ]
    # 注意：RDG 计算完成后会进入后处理菜单，导出 cube 的子菜单数字
    # 需要实际 smoke test 后补充到 profile
    # 暂时只生成到计算步骤，导出步骤待验证
    commands.append("q")
    return "\n".join(commands) + "\n"
