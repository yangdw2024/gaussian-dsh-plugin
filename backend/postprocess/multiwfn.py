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


def probe_version(fchk_path: Optional[Path] = None, timeout: float = 8.0) -> Optional[str]:
    """M4: 实际启动 Multiwfn 抓取首屏 banner 版本号，不再硬编码 "3.8"。

    - 未配置/找不到 exe、超时、抓不到版本 → 返回 None（由调用方按 profile+配置处理），
      绝不伪造一个版本号。
    - 版本号从 banner 中形如 "Multiwfn 3.8" / "Multiwfn 3.8(dev)" 的文本提取。
    """
    import re as _re
    import subprocess
    from ..config import settings

    exe = settings.multiwfn_exe
    if not exe or not Path(exe).exists():
        return None
    try:
        # P1 修复：以二进制方式抓取 banner，不使用 text=True。
        # 中文 Windows 下 Multiwfn banner 含 GBK 字节，text=True 会在后台 reader
        # 线程里触发 UnicodeDecodeError；这里只保留可打印 ASCII 再正则提取版本号。
        proc = subprocess.run(
            [str(exe)],
            input=b"q\n",
            capture_output=True,
            timeout=timeout,
            cwd=str(Path(exe).parent),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        blob = (proc.stdout or b"") + (proc.stderr or b"")
        # 仅保留可打印 ASCII(0x20-0x7E)，其余替换为空格，GBK 中文不会触发解码异常。
        ascii_text = bytes(
            b if 0x20 <= b <= 0x7E else 0x20 for b in blob
        ).decode("ascii", errors="ignore")
        # banner 形如 "Version 3.8, update date: 2026-Jan-7"；只取 Version 后的主版本号，
        # update date / (dev) 标记不参与比较。兼容 "Multiwfn 3.8" 写法。
        m = _re.search(r"Version\s+(\d+\.\d+(?:\.\d+)?)", ascii_text, _re.IGNORECASE)
        if not m:
            m = _re.search(r"Multiwfn\s+V?\s*(\d+\.\d+(?:\.\d+)?)", ascii_text, _re.IGNORECASE)
        if m:
            return m.group(1)
        return None
    except Exception:
        return None


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


# =====================================================================
# P2-1: 真实执行器（spawn Multiwfn，stdin 喂命令序列）
# 已在本机实测：water.fchk 命令序列 200/3/orbitals/grid/1/0/q，
# Multiwfn 在 cwd 下生成 orb%06d.cub（轨道号 1-based）。
# =====================================================================

def run_orbital_cube_batch(
    fchk_path: Path,
    orbitals: List[int],
    grid: str = "medium",
    work_dir: Optional[Path] = None,
    timeout: float = 600.0,
) -> List[Path]:
    """真实调用 Multiwfn 生成指定轨道的 cube 文件。

    Args:
        fchk_path: 已 formchk 的 fchk 文件
        orbitals: 1-based 轨道编号列表（与 fchk_reader 的 HOMO/LUMO 编号一致）
        grid: coarse/medium/fine
        work_dir: 工作目录（cube 生成于此；须与任务产物目录一致，便于 GC）
        timeout: 秒

    Returns:
        生成的 cube 路径列表（顺序与 orbitals 一致）

    Raises:
        FileNotFoundError: exe/fchk 不存在
        RuntimeError: 超时/返回码异常/预期 cube 未生成
    """
    import subprocess
    from ..process_utils import kill_process_tree

    exe = settings.multiwfn_exe
    if not exe or not Path(exe).exists():
        raise FileNotFoundError(f"Multiwfn 未找到：{exe}")
    fchk_path = Path(fchk_path)
    if not fchk_path.exists():
        raise FileNotFoundError(f"fchk 不存在：{fchk_path}")
    work_dir = Path(work_dir) if work_dir else fchk_path.parent
    work_dir.mkdir(parents=True, exist_ok=True)

    commands = generate_orbital_cube_commands(orbitals, grid)
    cmd_file = work_dir / "multiwfn_commands.txt"
    cmd_file.write_text(commands, encoding="utf-8")
    log_file = work_dir / "multiwfn.log"

    log_h = open(log_file, "w", encoding="utf-8", errors="ignore")
    stdin_h = open(cmd_file, "r", encoding="ascii")
    proc = None
    try:
        proc = subprocess.Popen(
            [str(exe), str(fchk_path)],
            cwd=str(work_dir),
            stdin=stdin_h,
            stdout=log_h,
            stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            shell=False,
        )
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            kill_process_tree(proc.pid)
            raise RuntimeError(f"Multiwfn 轨道 cube 生成超时（{timeout:.0f}秒）")
        # 实测正常跑完返回 0；stdin 提前 EOF 时可能为 24，视为未正常完成。
        if proc.returncode != 0:
            log_text = log_file.read_text(encoding="utf-8", errors="ignore") if log_file.exists() else ""
            raise RuntimeError(
                f"Multiwfn 执行异常（返回码 {proc.returncode}）：{log_text[-800:]}"
            )
    finally:
        for h in (log_h, stdin_h):
            try:
                h.close()
            except Exception:
                pass

    # 校验预期 cube 真实生成且非空（orb%06d.cub）
    cubes: List[Path] = []
    for orb in orbitals:
        cube = work_dir / f"orb{int(orb):06d}.cub"
        if not cube.exists() or cube.stat().st_size == 0:
            raise RuntimeError(f"Multiwfn 未生成预期 cube（命令序列可能与版本漂移）：{cube}")
        cubes.append(cube)
    return cubes


def run_esp_cube_batch(
    fchk_path: Path,
    grid: str = "medium",
    work_dir: Optional[Path] = None,
    timeout: float = 600.0,
) -> tuple:
    """真实调用 Multiwfn 生成密度 + 总 ESP 双 cube（用于 ESP 表面着色图）。

    已在本机 water.fchk 实测命令序列：
      5(real-space grid) → 1(electron density) → grid → 2(export cube) → 0(return)
      → 5 → 12(total ESP) → grid → 2(export cube) → 0 → q
    产出 cube 命名规则：{fchkstem}_density.cub、{fchkstem}_totesp.cub。
    两次 grid 用同分子同精度，网格定义一致，可直接叠加着色。

    Returns:
        (density_cube, esp_cube)
    """
    import subprocess
    from ..process_utils import kill_process_tree

    exe = settings.multiwfn_exe
    if not exe or not Path(exe).exists():
        raise FileNotFoundError(f"Multiwfn 未找到：{exe}")
    fchk_path = Path(fchk_path)
    if not fchk_path.exists():
        raise FileNotFoundError(f"fchk 不存在：{fchk_path}")
    work_dir = Path(work_dir) if work_dir else fchk_path.parent
    work_dir.mkdir(parents=True, exist_ok=True)

    profile = load_profile()
    grid_num = profile["grid_options"].get(grid, 2)

    commands = "\n".join([
        "5",          # real-space grid
        "1",          # electron density
        str(grid_num),
        "2",          # export cube
        "0",          # return to main menu
        "5",          # real-space grid again
        "12",         # total ESP
        str(grid_num),
        "2",
        "0",
        "q",
    ]) + "\n"

    cmd_file = work_dir / "multiwfn_esp_commands.txt"
    cmd_file.write_text(commands, encoding="utf-8")
    log_file = work_dir / "multiwfn_esp.log"

    log_h = open(log_file, "w", encoding="utf-8", errors="ignore")
    stdin_h = open(cmd_file, "r", encoding="ascii")
    try:
        proc = subprocess.Popen(
            [str(exe), str(fchk_path)],
            cwd=str(work_dir),
            stdin=stdin_h,
            stdout=log_h,
            stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            shell=False,
        )
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            kill_process_tree(proc.pid)
            raise RuntimeError(f"Multiwfn ESP cube 生成超时（{timeout:.0f}秒）")
        if proc.returncode != 0:
            log_text = log_file.read_text(encoding="utf-8", errors="ignore") if log_file.exists() else ""
            raise RuntimeError(
                f"Multiwfn ESP 执行异常（返回码 {proc.returncode}）：{log_text[-800:]}"
            )
    finally:
        for h in (log_h, stdin_h):
            try:
                h.close()
            except Exception:
                pass

    # Multiwfn 自动命名：{fchkstem}_density.cub / {fchkstem}_totesp.cub
    stem = fchk_path.stem
    density = work_dir / f"{stem}_density.cub"
    esp = work_dir / f"{stem}_totesp.cub"
    for c in (density, esp):
        if not c.exists() or c.stat().st_size == 0:
            raise RuntimeError(f"Multiwfn 未生成预期 ESP cube：{c}")
    return density, esp


def run_rdg_cube_batch(
    fchk_path: Path,
    grid: str = "medium",
    work_dir: Optional[Path] = None,
    timeout: float = 600.0,
) -> tuple:
    """真实调用 Multiwfn NCI/RDG 分析，生成 sign(lambda2)rho + RDG 双 cube。

    已在本机 water.fchk 实测命令序列：
      20(weak interaction) → 1(NCI) → grid → 3(导出 func1/func2 cube) → 0(exit NCI) → 0(return) → q
    产出固定名 func1.cub（sign(lambda2)rho）、func2.cub（RDG），同网格成对。

    Returns:
        (signrho_cube, rdg_cube)
    """
    import subprocess
    from ..process_utils import kill_process_tree

    exe = settings.multiwfn_exe
    if not exe or not Path(exe).exists():
        raise FileNotFoundError(f"Multiwfn 未找到：{exe}")
    fchk_path = Path(fchk_path)
    if not fchk_path.exists():
        raise FileNotFoundError(f"fchk 不存在：{fchk_path}")
    work_dir = Path(work_dir) if work_dir else fchk_path.parent
    work_dir.mkdir(parents=True, exist_ok=True)

    profile = load_profile()
    grid_num = profile["grid_options"].get(grid, 2)

    commands = "\n".join([
        "20",   # weak interaction
        "1",    # NCI/RDG
        str(grid_num),
        "3",    # output func1.cub / func2.cub
        "0",    # exit NCI post-processing
        "0",    # return to main menu
        "q",
    ]) + "\n"

    cmd_file = work_dir / "multiwfn_rdg_commands.txt"
    cmd_file.write_text(commands, encoding="utf-8")
    log_file = work_dir / "multiwfn_rdg.log"

    log_h = open(log_file, "w", encoding="utf-8", errors="ignore")
    stdin_h = open(cmd_file, "r", encoding="ascii")
    try:
        proc = subprocess.Popen(
            [str(exe), str(fchk_path)],
            cwd=str(work_dir),
            stdin=stdin_h,
            stdout=log_h,
            stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            shell=False,
        )
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            kill_process_tree(proc.pid)
            raise RuntimeError(f"Multiwfn RDG cube 生成超时（{timeout:.0f}秒）")
        if proc.returncode != 0:
            log_text = log_file.read_text(encoding="utf-8", errors="ignore") if log_file.exists() else ""
            raise RuntimeError(
                f"Multiwfn RDG 执行异常（返回码 {proc.returncode}）：{log_text[-800:]}"
            )
    finally:
        for h in (log_h, stdin_h):
            try:
                h.close()
            except Exception:
                pass

    signrho = work_dir / "func1.cub"
    rdg = work_dir / "func2.cub"
    for c in (signrho, rdg):
        if not c.exists() or c.stat().st_size == 0:
            raise RuntimeError(f"Multiwfn 未生成预期 RDG cube：{c}")
    return signrho, rdg

