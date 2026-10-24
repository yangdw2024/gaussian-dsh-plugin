"""Gaussian 工具：formchk（chk → fchk）。"""
from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Optional

from ..config import settings
from ..process_utils import kill_process_tree, spawn_subprocess


def ensure_fchk(chk_path: Path, fchk_path: Optional[Path] = None) -> Path:
    """确保 fchk 文件存在，不存在则用 formchk 转换。

    Args:
        chk_path: Gaussian checkpoint 文件路径
        fchk_path: 输出 fchk 路径（默认同目录同名）

    Returns:
        fchk 文件路径

    Raises:
        FileNotFoundError: chk 或 formchk 不存在
        RuntimeError: formchk 转换失败
    """
    chk_path = Path(chk_path)
    if not chk_path.exists():
        raise FileNotFoundError(f"chk 文件不存在：{chk_path}")

    if fchk_path is None:
        fchk_path = chk_path.with_suffix(".fchk")

    # 如果 fchk 已存在且比 chk 新，直接用
    if fchk_path.exists() and fchk_path.stat().st_mtime > chk_path.stat().st_mtime:
        return fchk_path

    if not settings.formchk_exe or not Path(settings.formchk_exe).exists():
        raise FileNotFoundError(f"formchk.exe 未找到：{settings.formchk_exe}")

    log_path = fchk_path.parent / f"{fchk_path.stem}_formchk.log"

    # formchk 用法：formchk.exe input.chk output.fchk
    cmd = [str(settings.formchk_exe), str(chk_path), str(fchk_path)]

    proc = spawn_subprocess(
        cmd,
        cwd=str(chk_path.parent),
        stdout_file=log_path,
        stderr_file=log_path,
    )

    # 等待完成（formchk 通常很快）
    try:
        proc.wait(timeout=60)
    except subprocess.TimeoutExpired:
        kill_process_tree(proc.pid)
        raise RuntimeError("formchk 转换超时（60秒）")

    if proc.returncode != 0:
        log_text = log_path.read_text(encoding="utf-8", errors="ignore") if log_path.exists() else ""
        raise RuntimeError(f"formchk 转换失败（返回码 {proc.returncode}）：{log_text[-500:]}")

    if not fchk_path.exists():
        raise RuntimeError(f"formchk 执行完成但 fchk 文件未生成：{fchk_path}")

    return fchk_path
