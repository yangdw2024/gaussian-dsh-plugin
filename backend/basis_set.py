"""Basis Set Exchange (BSE) 基组获取客户端。

官方 API：https://www.basissetexchange.org/api
- GET /api/metadata/  — 所有基组元数据
- GET /api/basis/{name}/format/{fmt}/?version={v}&elements={el}  — 获取基组
支持格式：gaussian94 / gaussian / nwchem / orca / psi4 / qchem / turbomole / json
"""
from __future__ import annotations

from typing import Dict, List, Optional

import requests

from .config import settings


class BasisSetClient:
    """BSE 基组库客户端。"""

    def __init__(self, base_url: Optional[str] = None) -> None:
        self.base_url = (base_url or settings.bse_api_base).rstrip("/")
        self._metadata_cache: Optional[Dict] = None

    def list_basis_sets(self, family: Optional[str] = None,
                         elements: Optional[List[int]] = None) -> List[Dict]:
        """列出可用基组（可按族/元素过滤）。

        返回精简列表：[{name, display_name, family, description, elements, versions}]
        """
        if self._metadata_cache is None:
            resp = requests.get(f"{self.base_url}/metadata/", timeout=30)
            resp.raise_for_status()
            self._metadata_cache = resp.json()

        results = []
        for name, meta in self._metadata_cache.items():
            if family and meta.get("family", "").lower() != family.lower():
                continue
            # 版本信息
            versions = meta.get("versions", {})
            latest = meta.get("latest_version", "0")
            version_elements = versions.get(str(latest), {}).get("elements", [])
            if elements:
                if not all(str(e) in version_elements for e in elements):
                    continue
            results.append({
                "name": name,
                "display_name": meta.get("display_name", name),
                "family": meta.get("family", ""),
                "description": meta.get("description", ""),
                "role": meta.get("role", ""),
                "function_types": meta.get("function_types", []),
                "latest_version": latest,
                "elements": [int(e) for e in version_elements],
            })
        return sorted(results, key=lambda x: x["name"].lower())

    def get_basis(self, name: str, elements: List[int],
                  fmt: str = "gaussian94", version: Optional[str] = None) -> Dict:
        """获取指定基组内容。

        Args:
            name: 基组名（如 6-31g_st_, def2-svp, cc-pvdz）
            elements: 原子序数列表
            fmt: 输出格式（gaussian94/gaussian/nwchem/orca/psi4/qchem/json）
            version: 版本，默认最新

        Returns:
            {name, format, version, elements, content, citation}
        """
        # BSE API 路径中的 name 需要用 slug（小写+下划线），但 API 也接受常见名
        params = {"elements": ",".join(str(e) for e in elements)}
        if version:
            params["version"] = version

        url = f"{self.base_url}/basis/{name}/format/{fmt}/"
        resp = requests.get(url, params=params, timeout=30)
        if resp.status_code == 404:
            # 尝试用 metadata 中的实际 slug
            return {"ok": False, "error": f"基组 '{name}' 未找到（404）。可用 list_basis_sets 查看准确名称。"}
        resp.raise_for_status()

        content = resp.text
        # 提取引用信息（如果有）
        citation = ""
        cite_match = None  # BSE 在 header 里有引用，但简化处理

        return {
            "ok": True,
            "name": name,
            "format": fmt,
            "version": version or "latest",
            "elements": elements,
            "content": content,
            "citation": citation,
        }

    def search(self, query: str, limit: int = 20) -> List[Dict]:
        """按关键词搜索基组（名称/描述/族模糊匹配）。"""
        all_basis = self.list_basis_sets()
        q = query.lower()
        scored = []
        for b in all_basis:
            score = 0
            if q == b["name"].lower():
                score += 100
            elif q in b["name"].lower():
                score += 50
            if q in b["display_name"].lower():
                score += 30
            if q in b.get("family", "").lower():
                score += 20
            if q in b.get("description", "").lower():
                score += 10
            if score > 0:
                scored.append((score, b))
        scored.sort(key=lambda x: -x[0])
        return [b for _, b in scored[:limit]]


basis_set_client = BasisSetClient()
