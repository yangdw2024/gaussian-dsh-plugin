"""Behavioral regression test suite for DSH shared modules (backend/gaussian_input.py, backend/basis_set.py).

Verifies that enhancements (such as job_type 'opt freq' alias and BSE local caching/fallback)
do NOT alter the behavioral contract expected by DSH endpoints or client tools.
"""
from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import json
import unittest
from unittest.mock import patch

from backend.config import settings
from backend.gaussian_input import GaussianInputRequest, generate_gjf, JOB_TYPE_KEYWORDS
from backend.basis_set import BasisSetClient


class TestDSHSharedRegression(unittest.TestCase):
    def test_job_type_mapping_backward_compatibility(self):
        """Verify original DSH job_type keys are preserved and produce correct routes."""
        self.assertEqual(JOB_TYPE_KEYWORDS["sp"], "")
        self.assertEqual(JOB_TYPE_KEYWORDS["opt"], "opt")
        self.assertEqual(JOB_TYPE_KEYWORDS["freq"], "freq")
        self.assertEqual(JOB_TYPE_KEYWORDS["opt+freq"], "opt freq")
        # Newly supported alias
        self.assertEqual(JOB_TYPE_KEYWORDS["opt freq"], "opt freq")

        # Test generation with original opt+freq
        req_plus = GaussianInputRequest(
            job_name="h2_plus",
            job_type="opt+freq",
            atoms=[("H", 0, 0, 0), ("H", 0, 0, 0.74)],
        )
        res_plus = generate_gjf(req_plus)
        self.assertIn("# B3LYP/6-31G(d,p) opt freq", res_plus["content"])

        # Test generation with space alias
        req_space = GaussianInputRequest(
            job_name="h2_space",
            job_type="opt freq",
            atoms=[("H", 0, 0, 0), ("H", 0, 0, 0.74)],
        )
        res_space = generate_gjf(req_space)
        self.assertIn("# B3LYP/6-31G(d,p) opt freq", res_space["content"])

    def test_basis_set_client_cache_and_offline_fallback(self):
        """Verify BasisSetClient transparently handles offline fallback and disk cache."""
        client = BasisSetClient(base_url="https://invalid.domain.never.resolves.example.com")
        
        # Test 1: Fallback when cache file does not exist
        fake_cache = settings.data_dir / "non_existent_fake_bse_cache.json"
        client._cache_file = fake_cache
        client._metadata_cache = None

        items = client.list_basis_sets()
        self.assertGreater(len(items), 0)
        names = [b["name"] for b in items]
        self.assertIn("6-31g", names)
        self.assertIn("def2-svp", names)

        # Test 2: Search on fallback items
        res = client.search("def2-svp")
        self.assertGreater(len(res), 0)
        self.assertEqual(res[0]["name"], "def2-svp")

    def test_basis_set_client_corrupted_cache_resilience(self):
        """Verify that a corrupted disk cache does not crash the client."""
        tmp_corrupt = settings.data_dir / "corrupted_bse_cache.json"
        try:
            tmp_corrupt.write_text("NOT A VALID JSON STRING", encoding="utf-8")
            client = BasisSetClient(base_url="https://invalid.domain.never.resolves.example.com")
            client._cache_file = tmp_corrupt
            client._metadata_cache = None

            # Must fall back gracefully without raising json.JSONDecodeError
            items = client.list_basis_sets()
            self.assertGreater(len(items), 0)
        finally:
            if tmp_corrupt.exists():
                tmp_corrupt.unlink()


if __name__ == "__main__":
    unittest.main()
