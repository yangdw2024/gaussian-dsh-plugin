# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for gaussian-backend.exe

打包后端为单文件 exe，包含：
- FastAPI + uvicorn
- RDKit（Chem / Geometry / DataStructs / ForceField）
- postprocess 模板和 profile
- 所有 backend 子模块

注意：
- 必须 workers=1（scheduler 是进程内单例）
- Sobko 子进程需要 SOBKO_PYTHON_EXE 环境变量指定 Python
- Gaussian / Multiwfn / VMD 是外部程序，不捆绑
"""
from pathlib import Path
import sys

from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_delvewheel_libs_directory,
    collect_dynamic_libs,
    collect_submodules,
    copy_metadata,
)


SPEC_DIR = Path(SPECPATH).resolve()
PROJECT_ROOT = SPEC_DIR.parent
ENTRYPOINT = PROJECT_ROOT / "backend" / "entrypoint.py"

sys.path.insert(0, str(PROJECT_ROOT))

datas = []
binaries = []
hiddenimports = []

# ----- 本地 backend 包 -----
hiddenimports += collect_submodules(
    "backend",
    on_error="raise",
)

# ----- Uvicorn 动态导入 -----
hiddenimports += collect_submodules(
    "uvicorn",
    on_error="warn once",
)

# ----- RDKit -----
for package in (
    "rdkit.Chem",
    "rdkit.Geometry",
    "rdkit.DataStructs",
    "rdkit.ForceField",
):
    hiddenimports += collect_submodules(
        package,
        on_error="warn once",
    )

datas += collect_data_files(
    "rdkit",
    include_py_files=False,
)

# ----- pydantic_core 必须整套收集（R18 修复） -----
# 现象：onedir 产物里 pydantic_core/ 只有一个 _pydantic_core.cp313-win_amd64.pyd，
# 缺 __init__.py / core_schema.py / _pydantic_core.pyi，启动即
#   ModuleNotFoundError: No module named 'pydantic_core._pydantic_core'
# 原因：conda 版 pydantic_core 的 __init__.py 被 PyInstaller 判为纯模块进 PYZ，
# 而 onedir 的 _internal/pydantic_core/ 只落了二进制，形成「空壳包」把 PYZ 里的
# __init__ 遮蔽掉。显式 collect_submodules + collect_data_files 双管齐下。
hiddenimports += collect_submodules("pydantic_core", on_error="raise")
datas += collect_data_files("pydantic_core", include_py_files=True)
binaries += collect_dynamic_libs("pydantic_core")

binaries += collect_dynamic_libs("rdkit")

# Windows RDKit wheels 可能有 delvewheel .libs 目录
try:
    datas, binaries = collect_delvewheel_libs_directory(
        "rdkit",
        datas=datas,
        binaries=binaries,
    )
except Exception:
    # 不是所有 RDKit 安装都用 delvewheel
    pass

# ----- conda OpenSSL 运行时 DLL（_ssl.pyd 依赖，PyInstaller 默认不收集 Library/bin） -----
# anyio/httpx/urllib3 走 ssl，缺 libcrypto/libssl 会报 "DLL load failed while importing _ssl"。
_conda_root = Path(sys.executable).resolve().parent
_ssl_bin = _conda_root / "Library" / "bin"
if _ssl_bin.exists():
    for _pat in ("libssl-*.dll", "libcrypto-*.dll"):
        for _dll in _ssl_bin.glob(_pat):
            # 跳过 .conda_trash / pdb
            if ".conda_trash" in _dll.name or _dll.suffix == ".pdb":
                continue
            binaries.append((str(_dll), "."))

# ----- 包元数据 -----
for dist in (
    "fastapi",
    "starlette",
    "uvicorn",
    "pydantic",
    "requests",
    "rdkit",
):
    try:
        datas += copy_metadata(dist)
    except Exception:
        pass

# ----- 后端运行时资源（模板 + profile） -----
for src, dest in (
    (
        PROJECT_ROOT / "backend" / "postprocess" / "templates",
        "backend/postprocess/templates",
    ),
    (
        PROJECT_ROOT / "backend" / "postprocess" / "profiles",
        "backend/postprocess/profiles",
    ),
):
    if src.exists():
        datas.append((str(src), dest))

hiddenimports = sorted(set(hiddenimports))

a = Analysis(
    [str(ENTRYPOINT)],
    pathex=[str(PROJECT_ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "pytest",
        "matplotlib",
        "numpy.tests",
        "pandas",
        # 后端不使用任何 Qt 绑定；base 环境同时存在 PyQt5/PyQt6，
        # PyInstaller 禁止收集多个 Qt binding，全部排除。
        "PyQt5",
        "PyQt6",
        "PySide2",
        "PySide6",
        "PySide",
        "qtpy",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

# onedir 模式：exe 启动器 + _internal 目录（DLL/资源外置），便于排查 RDKit DLL 问题，
# 启动也比 one-file 解包快。DLL 全部验证通过后，如需 one-file 再切回内嵌布局。
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="gaussian-backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    # 科学计算 DLL + UPX 兼容性风险大，先不用 UPX
    upx=False,
    # 保留 stdout/stderr 用于日志重定向（managed 模式读 ready record）
    console=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="gaussian-backend",
)
