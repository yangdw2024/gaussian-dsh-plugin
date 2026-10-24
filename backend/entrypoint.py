"""PyInstaller 入口点。

打包后的 exe 从这里启动，确保 uvicorn 单 worker 运行。
"""
from __future__ import annotations

from backend.app import main


if __name__ == "__main__":
    main()
