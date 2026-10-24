"""进程工具函数：子进程启动、日志落盘、进程树管理。

所有子进程统一用参数数组（shell=False），避免路径带空格时手工拼 shell 命令。
长输出全部落文件，不 PIPE 到内存。
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import List, Optional


def is_frozen() -> bool:
    """判断是否在 PyInstaller 冻结模式下运行。"""
    return getattr(sys, "frozen", False)


def get_sobko_python_exe() -> Path:
    """获取 Sobko 子进程使用的 Python 可执行文件路径。

    非冻结模式：直接用 sys.executable（当前 Python）。
    冻结模式：必须通过 SOBKO_PYTHON_EXE 环境变量指定，因为 sys.executable
              此时指向 gaussian-backend.exe 自己，不再是 python.exe。
    """
    if not is_frozen():
        return Path(sys.executable)

    env_val = os.environ.get("SOBKO_PYTHON_EXE", "")
    if not env_val:
        raise RuntimeError(
            "冻结模式下必须设置 SOBKO_PYTHON_EXE 环境变量，"
            "指向用于运行 Sobko MCP server 的 Python 解释器。"
        )
    path = Path(env_val)
    if not path.is_file():
        raise RuntimeError(f"SOBKO_PYTHON_EXE 指定的文件不存在：{path}")
    return path


def spawn_subprocess(
    cmd: List[str],
    cwd: Optional[Path] = None,
    stdout_file: Optional[Path] = None,
    stderr_file: Optional[Path] = None,
    env: Optional[dict] = None,
) -> subprocess.Popen:
    """启动子进程，长输出落文件，不 PIPE 到内存。

    Args:
        cmd: 命令参数数组（不要拼 shell 字符串）
        cwd: 工作目录
        stdout_file: stdout 重定向到的文件路径
        stderr_file: stderr 重定向到的文件路径
        env: 环境变量（默认继承当前进程）

    Returns:
        subprocess.Popen 对象
    """
    stdout_handle: object
    stderr_handle: object

    if stdout_file:
        stdout_file.parent.mkdir(parents=True, exist_ok=True)
        stdout_handle = open(stdout_file, "w", encoding="utf-8", errors="ignore")
    else:
        stdout_handle = subprocess.DEVNULL

    if stderr_file:
        stderr_handle = open(stderr_file, "w", encoding="utf-8", errors="ignore")
    else:
        stderr_handle = subprocess.STDOUT if stdout_file else subprocess.DEVNULL

    creationflags = 0
    if os.name == "nt":
        creationflags = subprocess.CREATE_NO_WINDOW

    return subprocess.Popen(
        cmd,
        cwd=str(cwd) if cwd else None,
        stdout=stdout_handle,
        stderr=stderr_handle,
        env=env or os.environ.copy(),
        creationflags=creationflags,
        shell=False,
    )


def kill_process_tree(pid: int) -> None:
    """终止进程树（包括所有子进程）。

    Windows 用 taskkill /F /T /PID，其他平台用 os.kill。
    """
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                capture_output=True,
                timeout=10,
            )
        except Exception:
            try:
                os.kill(pid, 9)
            except Exception:
                pass
    else:
        try:
            os.kill(pid, 9)
        except Exception:
            pass


def pid_alive(pid: int) -> bool:
    """检查进程是否存活（Windows / POSIX 通用）。

    Windows 下 os.kill(pid, 0) 语义不可靠，用 tasklist 精确查询 PID。
    """
    if not pid or pid <= 0:
        return False
    if os.name == "nt":
        try:
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return str(pid) in result.stdout
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False
