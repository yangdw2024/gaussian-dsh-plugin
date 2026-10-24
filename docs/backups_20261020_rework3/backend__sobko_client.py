"""Sobko 知识库检索客户端（MCP stdio 子进程方式）。

启动 Sobko MCP server 子进程（scripts/run_server.py），通过 stdio JSON-RPC 通信。
子进程懒启动（第一次搜索时），常驻复用。不阻塞后端主进程。
默认 BM25-only 轻量模式（通过环境变量禁用 embedding/reranker）。

注意：PyInstaller 冻结模式下，sys.executable 指向 gaussian-backend.exe 自己，
不再是 python.exe。因此子进程使用的 Python 路径通过 process_utils.get_sobko_python_exe()
解析，冻结模式下必须设置 SOBKO_PYTHON_EXE 环境变量。
"""
from __future__ import annotations

import json
import logging
import os
import queue
import subprocess
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any, Dict, Optional

from .config import settings
from .process_utils import get_sobko_python_exe

_sobko_logger = logging.getLogger("gaussian-dsh-backend.sobko")

# N9: 单条 JSON-RPC 帧最大字节，防止畸形 Content-Length 把缓冲撑爆。
MAX_FRAME_BYTES = 10 * 1024 * 1024


class SobkoMcpClient:
    """Sobko MCP stdio 客户端（常驻子进程）。"""

    def __init__(self) -> None:
        self._proc: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()
        self._request_id = 0
        self._start_error: Optional[str] = None
        # M7: 后台读线程维护原始字节缓冲，使 _recv_json 可按超时判断，
        # 不再靠会永久阻塞的 readline()；stderr 单独线程消费，避免管道写满反堵。
        self._buf = bytearray()
        self._buf_lock = threading.Lock()
        self._reader_thread: Optional[threading.Thread] = None
        self._stderr_thread: Optional[threading.Thread] = None
        self._stderr_tail = deque(maxlen=20)

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    def _ensure_server(self) -> Optional[subprocess.Popen]:
        """懒启动 Sobko MCP server 子进程。"""
        if self._proc is not None:
            if self._proc.poll() is None:
                return self._proc
            self._proc = None

        project_dir = settings.sobko_project_dir
        if not project_dir or not Path(project_dir).exists():
            self._start_error = f"Sobko 项目目录不存在：{project_dir}"
            return None

        run_script = Path(project_dir) / "scripts" / "run_server.py"
        if not run_script.exists():
            self._start_error = f"Sobko 启动脚本不存在：{run_script}"
            return None

        env = os.environ.copy()
        env["SOBKO_FORCE_BUILTIN_MCP"] = "1"
        env["SOBKO_DISABLE_LOCAL_RERANKER"] = "1"
        if settings.sobko_mode == "bm25_only":
            env["SOBKO_RAG_USE_EMBEDDING"] = "0"
            env["SOBKO_RAG_USE_RERANKER"] = "0"

        try:
            python_exe = get_sobko_python_exe()
            self._proc = subprocess.Popen(
                [str(python_exe), str(run_script)],
                cwd=str(project_dir),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                bufsize=0,
            )
            self._start_reader_threads()
            self._send_json({"jsonrpc": "2.0", "id": self._next_id(), "method": "initialize",
                             "params": {"protocolVersion": "2024-11-05",
                                        "capabilities": {}, "clientInfo": {"name": "gaussian-dsh", "version": "0.1.0"}}})
            resp = self._recv_json(timeout=90)
            if resp is None:
                self._start_error = "Sobko MCP server 初始化超时（正在加载索引，首次调用可能需要 1-2 分钟，请稍后重试）"
                self._kill()
                return None
            self._send_json({"jsonrpc": "2.0", "method": "notifications/initialized"})
            self._start_error = None
            return self._proc
        except Exception as exc:
            self._start_error = f"Sobko MCP server 启动失败：{exc}"
            self._kill()
            return None

    def _send_json(self, payload: Dict) -> None:
        if self._proc is None or self._proc.stdin is None:
            return
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        header = f"Content-Length: {len(body)}\r\n\r\n".encode("utf-8")
        self._proc.stdin.write(header + body)
        self._proc.stdin.flush()

    def _start_reader_threads(self) -> None:
        """M7: 启动 stdout 泵（写入共享字节缓冲）与 stderr 消费线程。"""
        with self._buf_lock:
            self._buf.clear()
        proc = self._proc
        if proc is None:
            return
        if proc.stdout is not None:
            def _pump_stdout():
                try:
                    while self._proc is proc:
                        chunk = proc.stdout.read(4096)
                        if not chunk:
                            break
                        with self._buf_lock:
                            self._buf.extend(chunk)
                except Exception:
                    pass
            self._reader_thread = threading.Thread(target=_pump_stdout, daemon=True)
            self._reader_thread.start()
        if proc.stderr is not None:
            def _pump_stderr():
                try:
                    while self._proc is proc:
                        line = proc.stderr.readline()
                        if not line:
                            break
                        self._stderr_tail.append(line.decode("utf-8", errors="ignore").rstrip())
                except Exception:
                    pass
            self._stderr_thread = threading.Thread(target=_pump_stderr, daemon=True)
            self._stderr_thread.start()

    def _drain_frame(self) -> Optional[Dict]:
        """从共享缓冲取出一个完整 MCP 帧并删除；帧未就绪返回 None。"""
        with self._buf_lock:
            data = bytes(self._buf)
        sep = data.find(b"\r\n\r\n")
        if sep == -1:
            sep = data.find(b"\n\n")
            if sep == -1:
                return None
            header, body_start = data[:sep], sep + 2
        else:
            header, body_start = data[:sep], sep + 4
        headers = {}
        for raw in header.split(b"\r\n" if b"\r\n" in header else b"\n"):
            if b":" in raw:
                k, v = raw.split(b":", 1)
                headers[k.decode("utf-8", "ignore").strip().lower()] = v.decode("utf-8", "ignore").strip()
        try:
            content_length = int(headers.get("content-length", "0"))
        except ValueError:
            content_length = 0
        # N9: 畸形/超大帧直接丢弃整段缓冲，避免撑爆内存或错位解析
        if content_length > MAX_FRAME_BYTES:
            with self._buf_lock:
                self._buf.clear()
            return None
        if content_length == 0:
            # 无 body 的通知/空帧，直接清掉该头部
            with self._buf_lock:
                del self._buf[:body_start]
            return {}
        body = data[body_start:body_start + content_length]
        if len(body) < content_length:
            return None  # body 未到齐
        with self._buf_lock:
            del self._buf[:body_start + content_length]
        try:
            return json.loads(body.decode("utf-8"))
        except Exception:
            return None

    def _recv_json(self, timeout: float = 120, expected_id: Optional[int] = None) -> Optional[Dict]:
        """M7/N9: 基于后台缓冲轮询，超时可真正返回；子进程卡住不输出时也能按时放弃。

        expected_id 给定后，只接受 id 匹配本请求的响应；通知与迟到的旧响应直接丢弃，
        避免上一请求的结果串用到下一请求。超时/退出返回 None，由调用方重建 worker。
        """
        if self._proc is None:
            return None
        start = time.time()
        while time.time() - start < timeout:
            # 子进程已退出且缓冲已空 → 直接失败，附最近 stderr 便于诊断
            if self._proc.poll() is not None:
                with self._buf_lock:
                    buffered = len(self._buf) > 0
                if not buffered:
                    tail = "\n".join(self._stderr_tail)
                    self._start_error = (
                        f"Sobko 子进程已退出。最近 stderr：{tail[-400:]}" if tail else "Sobko 子进程已退出"
                    )
                    return None
            frame = self._drain_frame()
            if frame is not None:
                # N9: 按 JSON-RPC id 关联；无 id 的通知跳过；id 不匹配的迟到帧丢弃继续等
                if expected_id is not None and "id" in frame and frame.get("id") != expected_id:
                    continue
                return frame
            time.sleep(0.05)
        return None

    def _call_tool(self, name: str, arguments: Dict, timeout: float = 180) -> Optional[Dict]:
        with self._lock:
            proc = self._ensure_server()
            if proc is None:
                return None
            req_id = self._next_id()
            self._send_json({"jsonrpc": "2.0", "id": req_id, "method": "tools/call",
                             "params": {"name": name, "arguments": arguments}})
            resp = self._recv_json(timeout=timeout, expected_id=req_id)
            if resp is None:
                # N9: 超时/子进程退出 → 使本会话失效，杀 worker 并清缓冲，
                # 防止迟到的旧响应被下一请求取到；下次调用由 _ensure_server 重新拉起。
                self._start_error = self._start_error or f"工具 {name} 超时（{timeout}s），已重置会话"
                self._kill()
                return None
            if "error" in resp:
                return {"_error": resp["error"]}
            result = resp.get("result", {})
            if "structuredContent" in result:
                return result["structuredContent"]
            content = result.get("content", [])
            if content and isinstance(content, list):
                for item in content:
                    if item.get("type") == "text":
                        try:
                            return json.loads(item["text"])
                        except Exception:
                            return {"text": item["text"]}
            return result

    def _kill(self) -> None:
        proc = self._proc
        self._proc = None  # 先置 None，让泵线程的 while 条件退出
        if proc is not None:
            try:
                proc.kill()
            except Exception:
                pass
        with self._buf_lock:
            self._buf.clear()
        self._reader_thread = None
        self._stderr_thread = None

    def is_available(self) -> Dict[str, Any]:
        """检查 Sobko 配置（不启动子进程）。"""
        project_dir = settings.sobko_project_dir
        exists = bool(project_dir and Path(project_dir).exists())
        run_script = Path(project_dir) / "scripts" / "run_server.py" if exists else None
        return {
            "configured": exists,
            "project_dir": str(project_dir) if project_dir else None,
            "run_script_exists": bool(run_script and run_script.exists()),
            "mode": settings.sobko_mode,
            "running": self._proc is not None and self._proc.poll() is None,
            "start_error": self._start_error,
        }

    def search(self, query: str, top_k: int = 8, **kwargs) -> Dict[str, Any]:
        arguments = {"query": query, "top_k": top_k}
        for key in ["source_types", "software", "topics", "authority_at_least", "include_images"]:
            if key in kwargs and kwargs[key] is not None:
                arguments[key] = kwargs[key]
        result = self._call_tool("sobko_search", arguments, timeout=180)
        if result is None:
            return {"ok": False, "error": self._start_error or "Sobko 检索超时或失败", "results": []}
        if "_error" in result:
            return {"ok": False, "error": str(result["_error"]), "results": []}
        return {"ok": True, "mode": settings.sobko_mode, "results": result}

    def fetch(self, chunk_id: Optional[str] = None, source_id: Optional[str] = None,
              expand_prev_next: int = 1) -> Dict[str, Any]:
        arguments = {"expand_prev_next": expand_prev_next}
        if chunk_id:
            arguments["chunk_id"] = chunk_id
        if source_id:
            arguments["source_id"] = source_id
        result = self._call_tool("sobko_fetch", arguments, timeout=120)
        if result is None:
            return {"ok": False, "error": self._start_error or "Sobko fetch 失败"}
        if "_error" in result:
            return {"ok": False, "error": str(result["_error"])}
        return {"ok": True, "result": result}

    def trace_source(self, source_id: Optional[str] = None,
                     chunk_id: Optional[str] = None) -> Dict[str, Any]:
        arguments = {}
        if source_id:
            arguments["source_id"] = source_id
        if chunk_id:
            arguments["chunk_id"] = chunk_id
        result = self._call_tool("sobko_trace_source", arguments, timeout=60)
        if result is None:
            return {"ok": False, "error": self._start_error or "Sobko trace 失败"}
        if "_error" in result:
            return {"ok": False, "error": str(result["_error"])}
        return {"ok": True, "result": result}


sobko_client = SobkoMcpClient()
