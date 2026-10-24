"""Gaussian DSH 插件后端配置。"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional


def _env_bool(name: str, default: bool) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


def _env_path(name: str, default: Optional[str]) -> Optional[Path]:
    val = os.environ.get(name)
    if val is None or val == "":
        return Path(default) if default else None
    return Path(val)


class Settings:
    """运行时配置，可用环境变量覆盖。"""

    # Gaussian 可执行文件（Windows g16.exe）
    gaussian_exe: str = os.environ.get("GAUSSIAN_EXE", r"D:\G16W\g16.exe")
    # formchk 可执行文件（Gaussian 工具，chk → fchk）
    formchk_exe: Optional[Path] = _env_path("FORMCHK_EXE", r"D:\G16W\formchk.exe")
    # 默认工作目录（输入/输出/chk 存放）
    work_dir: Path = Path(os.environ.get("GAUSSIAN_WORK_DIR", r"E:\YDW\ChemDatas\Gjf"))
    # 默认内存与核数（匹配用户硬件：15GB 物理内存、8核16线程）
    default_mem: str = os.environ.get("GAUSSIAN_DEFAULT_MEM", "12GB")
    default_nproc: int = int(os.environ.get("GAUSSIAN_DEFAULT_NPROC", "8"))
    # 后端监听
    host: str = os.environ.get("GAUSSIAN_BACKEND_HOST", "127.0.0.1")
    port: int = int(os.environ.get("GAUSSIAN_BACKEND_PORT", "8765"))
    # Sobko 知识库项目路径（直接 import 检索引擎，不走 MCP 协议）
    sobko_project_dir: Optional[Path] = Path(
        os.environ.get("SOBKO_PROJECT_DIR", r"E:\YDW\Trae_Sob\Sobko_MCP_project-main")
    )
    # Sobko 检索模式：bm25_only（轻量，默认）或 hybrid（需 Ollama embedding + rerank）
    sobko_mode: str = os.environ.get("SOBKO_MODE", "bm25_only")
    # PyInstaller 冻结模式下，运行 Sobko 子进程使用的 Python 解释器
    sobko_python_exe: Optional[Path] = _env_path("SOBKO_PYTHON_EXE", None)
    # BSE 基组库 API
    bse_api_base: str = os.environ.get("BSE_API_BASE", "https://www.basissetexchange.org/api")
    # 数据目录（任务数据库、日志）
    data_dir: Path = Path(os.environ.get("GAUSSIAN_DATA_DIR", str(Path.home() / ".gaussian-dsh")))

    # ===== Multiwfn / VMD 后处理配置 =====
    multiwfn_exe: Optional[Path] = _env_path("MULTIWFN_EXE", r"D:\Multiwfn\Multiwfn_3.8_bin_Win64\Multiwfn.exe")
    vmd_exe: Optional[Path] = _env_path("VMD_EXE", r"D:\VMD\vmd.exe")
    # OpenBabel：用于从 mol/sdf/cdxml/xyz 等文件识别结构并转 SMILES（自动判键）。
    # 优先用插件内嵌 thirdparty/openbabel（便携），找不到再回退环境变量/本机路径。
    obabel_exe: Optional[Path] = None
    multiwfn_threads: int = int(os.environ.get("MULTIWFN_THREADS", "2"))
    postprocess_max_grid_points: int = int(
        os.environ.get("POSTPROCESS_MAX_GRID_POINTS", "16000000")
    )

    # ===== 后端内存监控 =====
    backend_rss_soft_mb: int = int(os.environ.get("BACKEND_RSS_SOFT_MB", "1024"))
    backend_rss_hard_mb: int = int(os.environ.get("BACKEND_RSS_HARD_MB", "1800"))

    # ===== Managed 模式 token（DSH 插件 spawn 时注入） =====
    managed_token: Optional[str] = os.environ.get("GAUSSIAN_MANAGED_TOKEN")

    # ===== M6 加固：大体系预检 =====
    # 原子数硬上限（超过直接拒绝，避免 15GB 物理内存下排队后崩溃）
    max_atoms: int = int(os.environ.get("GAUSSIAN_MAX_ATOMS", "300"))

    # ===== M6 加固：Artifact GC（天） =====
    cube_ttl_days: int = int(os.environ.get("GC_CUBE_TTL_DAYS", "7"))
    image_ttl_days: int = int(os.environ.get("GC_IMAGE_TTL_DAYS", "30"))
    log_ttl_days: int = int(os.environ.get("GC_LOG_TTL_DAYS", "30"))
    gc_on_startup: bool = _env_bool("GC_ON_STARTUP", True)

    # ===== M6 加固：Multiwfn 期望版本（profile fail-fast） =====
    expected_multiwfn_version: str = os.environ.get("MULTIWFN_EXPECTED_VERSION", "3.8")

    def __init__(self) -> None:
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "logs").mkdir(parents=True, exist_ok=True)
        (self.data_dir / "jobs").mkdir(parents=True, exist_ok=True)
        (self.data_dir / "postprocess").mkdir(parents=True, exist_ok=True)
        self._resolve_obabel()

    def _resolve_obabel(self) -> None:
        """定位 obabel.exe：内嵌 thirdparty > 环境变量 > 本机固定路径。"""
        import sys
        candidates = []
        if getattr(sys, "frozen", False):
            # exe: runtimes/win32-x64/gaussian-backend/gaussian-backend.exe
            # 内嵌: runtimes/win32-x64/openbabel/bin/obabel.exe
            exe_dir = Path(sys.executable).resolve().parent
            candidates.append(exe_dir.parent / "openbabel" / "bin" / "obabel.exe")
        else:
            # 开发模式：config.py 在 <root>/backend/config.py → root = parent.parent
            candidates.append(
                Path(__file__).resolve().parent.parent
                / "thirdparty" / "openbabel" / "bin" / "obabel.exe"
            )
        env = os.environ.get("OBABEL_EXE")
        if env:
            candidates.append(Path(env))
        candidates.append(Path(r"E:\openbabel-install-msvc\bin\obabel.exe"))
        for c in candidates:
            if c.exists():
                self.obabel_exe = c
                return
        self.obabel_exe = candidates[-1]


settings = Settings()
