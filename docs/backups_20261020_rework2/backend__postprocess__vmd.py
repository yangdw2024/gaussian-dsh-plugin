"""VMD headless 渲染封装。

使用 VMD 的 -dispdev text 模式无 GUI 渲染：
vmd.exe -dispdev text -e script.tcl -args ...

输出 TGA 格式，再用 Pillow 转 PNG。
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional

from ..config import settings
from ..process_utils import kill_process_tree, spawn_subprocess


# 模板目录（包内只读资源）
TEMPLATES_DIR = Path(__file__).parent / "templates"


def _get_template_path(template_name: str) -> Path:
    """获取 Tcl 模板路径。"""
    path = TEMPLATES_DIR / template_name
    if not path.exists():
        raise FileNotFoundError(f"VMD 模板不存在：{path}")
    return path


def _tga_to_png(tga_path: Path, png_path: Path) -> Path:
    """TGA 转 PNG（用 Pillow）。"""
    try:
        from PIL import Image
        with Image.open(tga_path) as img:
            img.verify()
        with Image.open(tga_path) as img:
            img.save(png_path, "PNG")
        return png_path
    except ImportError:
        # Pillow 不可用时，直接复制 TGA（调用方已确认 TGA 真实存在非空）
        shutil.copy2(tga_path, png_path.with_suffix(".tga"))
        return png_path.with_suffix(".tga")


def _require_tga(tga_path: Path, label: str) -> Path:
    """M8: 强制校验 TGA 真实存在、非零大小；不存在/为空直接报错，不返回假 PNG 路径。"""
    if not tga_path.exists():
        raise RuntimeError(f"VMD {label} 未生成预期图像文件：{tga_path}")
    if tga_path.stat().st_size == 0:
        raise RuntimeError(f"VMD {label} 图像文件为空：{tga_path}")
    return tga_path


def render_orbitals(
    cube_paths: List[Path],
    output_dir: Path,
    isovalue: float = 0.02,
    base_name: str = "orbital",
) -> List[Path]:
    """渲染轨道等值面图。

    Args:
        cube_paths: 轨道 cube 文件路径列表
        output_dir: 输出目录
        isovalue: 等值面值
        base_name: 输出文件基础名

    Returns:
        PNG 文件路径列表
    """
    if not settings.vmd_exe or not Path(settings.vmd_exe).exists():
        raise FileNotFoundError(f"VMD 未找到：{settings.vmd_exe}")

    template = _get_template_path("orbital.tcl")
    output_dir.mkdir(parents=True, exist_ok=True)

    png_paths = []
    for i, cube_path in enumerate(cube_paths):
        tga_path = output_dir / f"{base_name}_{i}.tga"
        png_path = output_dir / f"{base_name}_{i}.png"

        cmd = [
            str(settings.vmd_exe),
            "-dispdev", "text",
            "-e", str(template),
            "-args",
            str(cube_path),
            str(tga_path),
            str(isovalue),
        ]

        log_path = output_dir / f"{base_name}_{i}_vmd.log"
        proc = spawn_subprocess(
            cmd,
            cwd=str(output_dir),
            stdout_file=log_path,
            stderr_file=log_path,
        )

        try:
            proc.wait(timeout=120)
        except subprocess.TimeoutExpired:
            kill_process_tree(proc.pid)
            raise RuntimeError(f"VMD 渲染超时（120秒）：{cube_path}")

        if proc.returncode != 0:
            log_text = log_path.read_text(encoding="utf-8", errors="ignore") if log_path.exists() else ""
            raise RuntimeError(f"VMD 渲染失败（返回码 {proc.returncode}）：{log_text[-500:]}")

        # M8: 校验 TGA 存在非零再转 PNG，缺失即报错，不静默少返回图
        _require_tga(tga_path, f"轨道 {cube_path.name}")
        out = _tga_to_png(tga_path, png_path)
        png_paths.append(out)

    return png_paths


def render_esp_surface(
    density_cube: Path,
    esp_cube: Path,
    output_path: Path,
    density_isovalue: float = 0.001,
    esp_min: float = -0.05,
    esp_max: float = 0.05,
) -> Path:
    """渲染电子密度表面映射 ESP 图。

    Args:
        density_cube: 电子密度 cube 文件
        esp_cube: ESP cube 文件
        output_path: 输出 PNG 路径
        density_isovalue: 密度等值面值
        esp_min: ESP 色标最小值
        esp_max: ESP 色标最大值

    Returns:
        PNG 文件路径
    """
    if not settings.vmd_exe or not Path(settings.vmd_exe).exists():
        raise FileNotFoundError(f"VMD 未找到：{settings.vmd_exe}")

    template = _get_template_path("esp_surface.tcl")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tga_path = output_path.with_suffix(".tga")

    cmd = [
        str(settings.vmd_exe),
        "-dispdev", "text",
        "-e", str(template),
        "-args",
        str(density_cube),
        str(esp_cube),
        str(tga_path),
        str(density_isovalue),
        str(esp_min),
        str(esp_max),
    ]

    log_path = output_path.parent / f"{output_path.stem}_vmd.log"
    proc = spawn_subprocess(
        cmd,
        cwd=str(output_path.parent),
        stdout_file=log_path,
        stderr_file=log_path,
    )

    try:
        proc.wait(timeout=180)
    except subprocess.TimeoutExpired:
        kill_process_tree(proc.pid)
        raise RuntimeError("VMD ESP 渲染超时（180秒）")

    if proc.returncode != 0:
        log_text = log_path.read_text(encoding="utf-8", errors="ignore") if log_path.exists() else ""
        raise RuntimeError(f"VMD ESP 渲染失败（返回码 {proc.returncode}）：{log_text[-500:]}")

    _require_tga(tga_path, "ESP 表面")
    return _tga_to_png(tga_path, output_path)


def render_rdg(
    signrho_cube: Path,
    rdg_cube: Path,
    output_path: Path,
) -> Path:
    """渲染 RDG/NCI 弱相互作用图。

    Args:
        signrho_cube: sign(lambda2)rho cube 文件
        rdg_cube: RDG cube 文件
        output_path: 输出 PNG 路径

    Returns:
        PNG 文件路径
    """
    if not settings.vmd_exe or not Path(settings.vmd_exe).exists():
        raise FileNotFoundError(f"VMD 未找到：{settings.vmd_exe}")

    template = _get_template_path("rdg.tcl")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tga_path = output_path.with_suffix(".tga")

    cmd = [
        str(settings.vmd_exe),
        "-dispdev", "text",
        "-e", str(template),
        "-args",
        str(signrho_cube),
        str(rdg_cube),
        str(tga_path),
    ]

    log_path = output_path.parent / f"{output_path.stem}_vmd.log"
    proc = spawn_subprocess(
        cmd,
        cwd=str(output_path.parent),
        stdout_file=log_path,
        stderr_file=log_path,
    )

    try:
        proc.wait(timeout=180)
    except subprocess.TimeoutExpired:
        kill_process_tree(proc.pid)
        raise RuntimeError("VMD RDG 渲染超时（180秒）")

    if proc.returncode != 0:
        log_text = log_path.read_text(encoding="utf-8", errors="ignore") if log_path.exists() else ""
        raise RuntimeError(f"VMD RDG 渲染失败（返回码 {proc.returncode}）：{log_text[-500:]}")

    _require_tga(tga_path, "RDG/NCI")
    return _tga_to_png(tga_path, output_path)
