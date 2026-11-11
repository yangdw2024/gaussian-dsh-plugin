"""Basis Set Exchange (BSE) 基组获取客户端。

官方 API：https://www.basissetexchange.org/api
- GET /api/metadata/  — 所有基组元数据
- GET /api/basis/{name}/format/{fmt}/?version={v}&elements={el}  — 获取基组
支持格式：gaussian94 / gaussian / nwchem / orca / psi4 / qchem / turbomole / json
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional

import requests

from .config import settings

logger = logging.getLogger("gaussian-dsh-backend")


class BasisSetClient:
    """BSE 基组库客户端（支持本地文件缓存与离线回退）。"""

    def __init__(self, base_url: Optional[str] = None) -> None:
        self.base_url = (base_url or settings.bse_api_base).rstrip("/")
        self._metadata_cache: Optional[Dict] = None
        self._cache_file: Path = settings.data_dir / "bse_metadata_cache.json"

    def _load_metadata(self) -> Dict:
        """加载元数据：内存 -> 本地磁盘缓存 -> 网络请求 -> 内置离线回退。"""
        if self._metadata_cache is not None:
            return self._metadata_cache

        # 1. 尝试从本地磁盘缓存读取
        if self._cache_file.exists():
            try:
                data = json.loads(self._cache_file.read_text(encoding="utf-8"))
                if isinstance(data, dict) and data:
                    self._metadata_cache = data
                    return self._metadata_cache
            except Exception as e:
                logger.warning(f"Failed to read local BSE cache file {self._cache_file}: {e}")

        # 2. 尝试从 BSE 官方 API 获取
        try:
            resp = requests.get(f"{self.base_url}/metadata/", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, dict):
                    self._metadata_cache = data
                    try:
                        self._cache_file.parent.mkdir(parents=True, exist_ok=True)
                        self._cache_file.write_text(resp.text, encoding="utf-8")
                    except Exception as e:
                        logger.warning(f"Failed to persist BSE cache to disk: {e}")
                    return self._metadata_cache
        except Exception as e:
            logger.warning(f"BSE API online fetch failed: {e}. Falling back to offline basis set list.")

        # 3. 离线内置常见基组回退
        self._metadata_cache = {
            "6-31g": {"display_name": "6-31G", "family": "pople", "description": "Valence double-zeta Pople basis set", "latest_version": "1", "versions": {"1": {"elements": ["1", "6", "7", "8", "9", "15", "16", "17"]}}},
            "6-31g_st_": {"display_name": "6-31G*", "family": "pople", "description": "Pople 6-31G with polarization on heavy atoms", "latest_version": "1", "versions": {"1": {"elements": ["1", "6", "7", "8", "9", "15", "16", "17"]}}},
            "def2-svp": {"display_name": "def2-SVP", "family": "ahlrichs", "description": "Karlsruhe split-valence with polarization", "latest_version": "1", "versions": {"1": {"elements": ["1", "6", "7", "8", "9", "15", "16", "17", "26", "29", "30"]}}},
            "def2-tzvp": {"display_name": "def2-TZVP", "family": "ahlrichs", "description": "Karlsruhe triple-zeta with polarization", "latest_version": "1", "versions": {"1": {"elements": ["1", "6", "7", "8", "9", "15", "16", "17", "26", "29", "30"]}}},
            "cc-pvdz": {"display_name": "cc-pVDZ", "family": "dunning", "description": "Correlation-consistent polarized valence double-zeta", "latest_version": "1", "versions": {"1": {"elements": ["1", "6", "7", "8", "9"]}}},
            "lanl2dz": {"display_name": "LANL2DZ", "family": "lanl", "description": "Los Alamos effective core potential with double-zeta", "latest_version": "1", "versions": {"1": {"elements": ["1", "6", "7", "8", "26", "29", "30", "46", "78", "79"]}}},
        }
        return self._metadata_cache

    def list_basis_sets(self, family: Optional[str] = None,
                         elements: Optional[List[int]] = None) -> List[Dict]:
        """列出可用基组（可按族/元素过滤）。

        返回精简列表：[{name, display_name, family, description, elements, versions}]
        """
        metadata = self._load_metadata()

        results = []
        for name, meta in metadata.items():
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
                "elements": [int(e) for e in version_elements if str(e).isdigit()],
            })
        return sorted(results, key=lambda x: x["name"].lower())

    def get_basis(self, name: str, elements: List[int],
                  fmt: str = "gaussian94", version: Optional[str] = None) -> Dict:
        """获取指定基组内容（支持本地磁盘缓存与离线保护）。

        Args:
            name: 基组名（如 6-31g_st_, def2-svp, cc-pvdz）
            elements: 原子序数列表
            fmt: 输出格式（gaussian94/gaussian/nwchem/orca/psi4/qchem/json）
            version: 版本，默认最新

        Returns:
            {name, format, version, elements, content, citation, cached: bool}
        """
        sorted_elems = sorted(int(e) for e in elements)
        cache_key = f"{name.lower().replace('*', '_st_')}_{fmt}_{version or 'latest'}_{'_'.join(str(e) for e in sorted_elems)}"
        cache_dir_env = os.environ.get("GAUSSIAN_CACHE_DIR")
        basis_cache_dir = Path(cache_dir_env).expanduser().resolve() if cache_dir_env else (settings.data_dir / "basis_cache")
        basis_cache_file = basis_cache_dir / f"{cache_key}.json"

        # 边界校验：确保缓存目标位于显式授权的缓存边界内
        from .security import validate_safe_path
        try:
            safe_cache_file = validate_safe_path(basis_cache_file, mode="cache")
        except Exception:
            safe_cache_file = None

        # 1. 尝试从本地磁盘缓存读取已下载的基组定义
        if safe_cache_file and safe_cache_file.exists():
            try:
                cached_data = json.loads(safe_cache_file.read_text(encoding="utf-8"))
                if isinstance(cached_data, dict) and cached_data.get("ok"):
                    cached_data["cached"] = True
                    return cached_data
            except Exception as e:
                logger.warning(f"Failed to read basis cache {safe_cache_file}: {e}")

        # 2. 尝试从 BSE API 获取
        params = {"elements": ",".join(str(e) for e in sorted_elems)}
        if version:
            params["version"] = version

        url = f"{self.base_url}/basis/{name}/format/{fmt}/"
        try:
            resp = requests.get(url, params=params, timeout=10)
            if resp.status_code == 404:
                return {
                    "ok": False,
                    "error": f"基组 '{name}' 未找到（404）。可用 list_basis_sets 查看准确名称。",
                }
            resp.raise_for_status()
            content = resp.text
            result = {
                "ok": True,
                "name": name,
                "format": fmt,
                "version": version or "latest",
                "elements": sorted_elems,
                "content": content,
                "citation": "",
                "cached": False,
            }
            # 存盘缓存
            try:
                basis_cache_dir.mkdir(parents=True, exist_ok=True)
                basis_cache_file.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
            except Exception as e:
                logger.warning(f"Failed to save basis to disk cache: {e}")
            return result
        except requests.RequestException as exc:
            return {
                "ok": False,
                "error": (
                    f"BSE 网络连接失败且本地离线缓存未命中: {exc}。"
                    f"请注意：基组元数据列表（search_basis_sets）已本地离线缓存，但完整高精基组定义文件（'{name}'）"
                    f"在首次使用前需要网络连接或预置缓存。"
                ),
                "cached": False,
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
