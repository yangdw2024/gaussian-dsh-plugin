"""Sobko 知识库检索客户端（MCP stdio 子进程方式）。

启动 Sobko MCP server 子进程（scripts/run_server.py），通过 stdio JSON-RPC 通信。
子进程懒启动（第一次搜索时），常驻复用。不阻塞后端主进程。
默认 BM25-only 轻量模式（通过环境变量禁用 embedding/reranker）。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

from .config import settings


class SobkoMcpClient:
    """Sobko MCP stdio 客户端（常驻子进程）。"""

    def __init__(self) -> None:
        self._proc: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()
        self._request_id = 0
        self._start_error: Optional[str] = None

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
            self._proc = subprocess.Popen(
                [sys.executable, str(run_script)],
                cwd=str(project_dir),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                bufsize=0,
            )
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

    def _recv_json(self, timeout: float = 120) -> Optional[Dict]:
        if self._proc is None or self._proc.stdout is None:
            return None
        headers = {}
        start = time.time()
        while True:
            if time.time() - start > timeout:
                return None
            line = self._proc.stdout.readline()
            if not line:
                return None
            line = line.decode("utf-8", errors="ignore").strip()
            if not line:
                break
            if ":" in line:
                key, val = line.split(":", 1)
                headers[key.strip().lower()] = val.strip()
        content_length = int(headers.get("content-length", "0"))
        if content_length == 0:
            return {}
        body = self._proc.stdout.read(content_length)
        if not body:
            return None
        try:
            return json.loads(body.decode("utf-8"))
        except Exception:
            return None

    def _call_tool(self, name: str, arguments: Dict, timeout: float = 180) -> Optional[Dict]:
        with self._lock:
            proc = self._ensure_server()
            if proc is None:
                return None
            req_id = self._next_id()
            self._send_json({"jsonrpc": "2.0", "id": req_id, "method": "tools/call",
                             "params": {"name": name, "arguments": arguments}})
            resp = self._recv_json(timeout=timeout)
            if resp is None:
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
        if self._proc is not None:
            try:
                self._proc.kill()
            except Exception:
                pass
            self._proc = None

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
