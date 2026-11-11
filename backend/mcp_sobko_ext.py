"""Optional Sobko computational chemistry knowledge base extension for MCP Server.

Designed to degrade gracefully:
- If Sobko is not configured/installed on the user's machine and GAUSSIAN_MCP_ENABLE_SOBKO is
  unset or 'auto', no broken Sobko dependency ever blocks MCP Server startup.
- Set GAUSSIAN_MCP_ENABLE_SOBKO=true to force registration even if the local Sobko repo is absent
  (calls return clean structured errors), or =false to force-disable.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import settings
from .sobko_client import sobko_client

logger = logging.getLogger("gaussian-mcp-server.sobko-ext")

OPTIONAL_EXTENSION_TOOL_NAMES = ("sobko_search", "sobko_fetch")


def should_register_sobko() -> Dict[str, Any]:
    """Determine whether optional Sobko extension tools should be registered."""
    flag = os.environ.get("GAUSSIAN_MCP_ENABLE_SOBKO", "auto").strip().lower()
    avail = sobko_client.is_available()
    configured = bool(avail.get("configured") and avail.get("run_script_exists"))

    if flag in {"0", "false", "no", "off", "disable", "disabled"}:
        return {
            "enabled": False,
            "reason": "explicitly disabled via GAUSSIAN_MCP_ENABLE_SOBKO",
            "configured": configured,
        }
    if flag in {"1", "true", "yes", "on", "enable", "enabled"}:
        return {
            "enabled": True,
            "reason": "explicitly enabled via GAUSSIAN_MCP_ENABLE_SOBKO",
            "configured": configured,
        }
    return {
        "enabled": configured,
        "reason": "auto-detected Sobko knowledge base" if configured else "Sobko directory/script absent; skipped gracefully",
        "configured": configured,
    }


def register_sobko_tools(mcp: Any) -> Dict[str, Any]:
    """Register optional Sobko MCP tools on `mcp` if enabled. Never raises on missing local assets."""
    decision = should_register_sobko()
    if not decision["enabled"]:
        logger.info("Optional Sobko extension skipped: %s", decision["reason"])
        return {
            "registered": False,
            "tools": [],
            **decision,
        }

    @mcp.tool()
    def sobko_search(
        query: str,
        top_k: int = 8,
        software: Optional[List[str]] = None,
        source_types: Optional[List[str]] = None,
        topics: Optional[List[str]] = None,
        authority_at_least: Optional[str] = None,
        include_images: bool = False,
    ) -> Dict[str, Any]:
        """Search the optional local Sobko computational chemistry knowledge base (graceful fallback if unavailable).

        Parameters:
            query: Question or search keywords (e.g. 'B3LYP SCF convergence failure').
            top_k: Number of snippets to return (1-20, default 8).
            software: Optional software filter list (e.g. ['Gaussian', 'Multiwfn']).
            source_types: Optional source type filter list.
            topics: Optional chemistry topic filter list.
            authority_at_least: Optional authority threshold ('A' or 'B').
            include_images: Whether to include image references in retrieved snippets.
        """
        if not query or not query.strip():
            raise ValueError("Parameter 'query' must not be empty.")
        avail = sobko_client.is_available()
        if not avail.get("configured") or not avail.get("run_script_exists"):
            return {
                "ok": False,
                "extension": "sobko",
                "configured": False,
                "results": [],
                "error": (
                    "Sobko local knowledge base is not configured or run_server.py is missing. "
                    "Set SOBKO_PROJECT_DIR or use core Gaussian tools without Sobko."
                ),
            }
        bounded_k = min(max(1, int(top_k)), 20)
        return sobko_client.search(
            query=query.strip(),
            top_k=bounded_k,
            source_types=source_types,
            software=software,
            topics=topics,
            authority_at_least=authority_at_least,
            include_images=include_images,
        )

    @mcp.tool()
    def sobko_fetch(
        chunk_id: Optional[str] = None,
        source_id: Optional[str] = None,
        expand_prev_next: int = 1,
    ) -> Dict[str, Any]:
        """Fetch expanded context around a Sobko search snippet by chunk_id or source_id.

        Parameters:
            chunk_id: Chunk identifier returned by sobko_search.
            source_id: Source identifier returned by sobko_search.
            expand_prev_next: Number of adjacent chunks before/after to include (0-5).
        """
        if not chunk_id and not source_id:
            raise ValueError("At least one of 'chunk_id' or 'source_id' must be provided.")
        avail = sobko_client.is_available()
        if not avail.get("configured") or not avail.get("run_script_exists"):
            return {
                "ok": False,
                "extension": "sobko",
                "configured": False,
                "error": (
                    "Sobko local knowledge base is not configured or run_server.py is missing."
                ),
            }
        bounded_expand = min(max(0, int(expand_prev_next)), 5)
        return sobko_client.fetch(
            chunk_id=chunk_id,
            source_id=source_id,
            expand_prev_next=bounded_expand,
        )

    return {
        "registered": True,
        "tools": list(OPTIONAL_EXTENSION_TOOL_NAMES),
        **decision,
    }
