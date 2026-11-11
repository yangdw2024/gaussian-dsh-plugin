"""PyInstaller 入口点。

打包后的 exe 从这里启动，确保 uvicorn 单 worker 运行，并支持冻结模式下子进程唤醒 mock_worker。
"""
from __future__ import annotations

import sys


def _maybe_run_mock_worker() -> None:
    """在 PyInstaller 冻结模式下派发 mock_worker，避免重复拉起 FastAPI 服务。"""
    args = sys.argv[1:]
    if args and args[0] == "--mock-worker":
        sys.argv = [sys.argv[0], *args[1:]]
    elif len(args) >= 2 and args[0] == "-m" and args[1] == "backend.mock_worker":
        sys.argv = [sys.argv[0], *args[2:]]
    else:
        return

    from backend.mock_worker import main as mock_main
    mock_main()
    sys.exit(0)


if __name__ == "__main__":
    _maybe_run_mock_worker()
    from backend.app import main
    main()
