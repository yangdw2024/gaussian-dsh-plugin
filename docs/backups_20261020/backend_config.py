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


class Settings:
    """运行时配置，可用环境变量覆盖。"""

    # Gaussian 可执行文件（Windows g16.exe）
    gaussian_exe: str = os.environ.get("GAUSSIAN_EXE", r"D:\G16W\g16.exe")
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
    # BSE 基组库 API
    bse_api_base: str = os.environ.get("BSE_API_BASE", "https://www.basissetexchange.org/api")
    # 数据目录（任务数据库、日志）
    data_dir: Path = Path(os.environ.get("GAUSSIAN_DATA_DIR", str(Path.home() / ".gaussian-dsh")))

    def __init__(self) -> None:
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "logs").mkdir(parents=True, exist_ok=True)
        (self.data_dir / "jobs").mkdir(parents=True, exist_ok=True)


settings = Settings()
