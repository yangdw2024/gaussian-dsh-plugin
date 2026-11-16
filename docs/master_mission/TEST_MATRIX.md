# 测试矩阵 (TEST_MATRIX)

> 记录原则：仅在最后一次代码改动后**实际执行且目睹全部结果**的测试才可标记 `PASS`；未安装环境标记 `NOT_RUN`。

| Test Suite / Check | 所属阶段 | 目标范围 | 运行状态 | 通过/总数 | 退出码 | 日志/说明 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `baseline-py312-unittest` | Phase 0 / 1 | 现有 V5.2 全量 Python 单测 | `PASS` | `79/79` | `0` | 27.225s，`phase1_baseline_tests.log` 干净退出码 0 |
| `v53-preaccept-preflight` | Phase 1 | `h2_sp_preaccept.gjf` SHA-256 与授权拒绝 | `PASS` | `1/1` | `0` | 干跑通过，负向人工令牌校验拦截，真实执行保持 `HUMAN_APPROVAL_REQUIRED` |
| `phase2-mcp-17-and-postprocess` | Phase 2 | 17 核心工具 + Sobko 可选扩展 + 后处理加固 | `PASS` | `89/89` | `0` | 含 `CH3Cl.fchk` 真实 Multiwfn 3.8 + VMD 后处理联调通过 (`mo_levels.svg`, `orbital_0.png`) |
| `phase3-scientific-correctness` | Phase 3 | 10 项计算化学边界与数据契约测试 (`test_scientific_phase3.py` + 全量回归) | `PASS` | `99/99` | `0` | 24.597s 干净通过，验证 SP/Opt/Post-HF/TD-DFT/虚频/Mock 隔离/Link1/BSE/RDKit 边界 |
| `phase4-security-redteam` | Phase 4 | 安全与稳定性红队对抗回归 (`test_security_phase4.py` + 全量回归) | `PASS` | `106/106` | `0` | 34.167s；含真实 Windows `mklink /J`、ADS/UNC、Link0 注入、HTTP `403`/`413`、GC symlink 与 SMILES DoS |
| `phase5-codex-mcp-live` | Phase 5 | Codex CLI 隔离 `CODEX_HOME` 实机协议调用 | `TODO` | - | - | 不改动 `~/.codex/config.toml` |
| `phase5-claude-cursor` | Phase 5 | Claude Code / Cursor 实机测试 | `NOT_RUN` | `0/0` | `N/A` | 宿主机未安装 `claude` 与 `cursor` |
| `phase6-pack-and-maxpath` | Phase 6 | `npm pack` + 隔离安装 + `<260` 路径校验 | `TODO` | - | - | `LongPathsEnabled=0` 下通过 |
| `phase7-agensi-skills-zip` | Phase 7 | Agensi Skills 结构与降级规范校验 | `TODO` | - | - | 产出于 `dist/agensi/` |
| `phase11-full-regression` | Phase 11 | 发布前最终全量回归测试 | `TODO` | - | - | 在全部改动后统一执行 |

### Phase 5 实测基线追加（2026-11-12）
| 检查项 | 命令 / 方式 | 实测结果 | 备注 |
| :--- | :--- | :--- | :--- |
| Full Python Suite (post `backend/mcp_server.py` edit) | `py312 -m unittest discover -s tests -v` | **PASS (`106/106` OK, 29.124s)** | 含 compiled EXE cross-process |
| DSH Local Build & Registration | `node scripts/build.mjs` + Cordis check | **PASS (`19` tools, `1` prompt)** | `all_have_schema_and_output=true` |
| DSH Host Profile Check (Read-only) | `verify_plugin_shape/profile_bundle/installed_runtime.mjs` | **EXIT=1 (Expected)** | 目标目录不存在，仅 `.bak-gd-gp-20261024` |
| Out-of-Repo Direct MCP Launch | `Popen python backend/mcp_server.py` from `C:\Users\Administrator` | **PASS (`RC=0`, `TOOL_COUNT=19`)** | 修复 `ImportError` 后实测 |
| Codex CLI Isolated Live MCP | `OpenAI Codex v0.148.0` (`gpt-5.6-sol`, isolated `CODEX_HOME`) | **PASS (`EXIT=0`, 4 tools)** | `gaussian_status`, `extract_structure_from_file`, `parse_gaussian_output`, `postprocess_capabilities` |
| Claude Desktop / Cursor IDE | — | **NOT_RUN** | 已提供配置模板 `examples/mcp_configs/` |

### Phase 6 实测基线追加（2026-11-12）
| 检查项 | 命令 / 方式 | 实测结果 | 备注 |
| :--- | :--- | :--- | :--- |
| PyInstaller Rebuild & Deploy (`0.3.0`) | `build_backend.ps1` + `deploy_runtime.ps1 -Version 0.3.0` | **PASS (`1064` files, max rel `96` chars)** | `EXE(..., contents_directory=".")` + `b/` |
| EXE Smoke & RDKit `/v1/molecules/from-smiles` | `smoke_test_backend.ps1` + live HTTP test | **PASS (`version=0.3.0`, 0.5s boot)** | `c1ccccc1` 3D 生成正常 |
| Compiled EXE Cross-Process Suite (`0.3.0`) | `py312 -m unittest tests.test_v52_compiled_cross_process -v` | **PASS (`5/5` OK, 13.033s)** | 使用 `b/gaussian-backend.exe` |
| Dual npm Pack (`@yangdw2024/gp` + `@gd/gp`) | `node scripts/build_npm_packages.mjs` | **PASS (`64.7 MB` each, 1158 files)** | 模拟 147 字符 DSH 路径 `243 < 260` |
| Isolated Deep-Path `npm install` + EXE Launch | `PREFIX_LEN=153`, `npm install --offline`, `verify_*`, live EXE | **PASS (`LONGEST=249 < 260`, `EXIT=0`)** | 形状/bundle/sha256/pydantic_core 全 PASS |

### Phase 7 实测基线追加（2026-11-12）
| 检查项 | 命令 / 方式 | 实测结果 | 备注 |
| :--- | :--- | :--- | :--- |
| Agensi ZIP Pack & Audit | `py312 scripts/package_agensi_skills.py` | **PASS (3 ZIPs, 7556B / 6656B / 5643B)** | `SKILL.md` 位于 ZIP 根，零密钥/私人路径 |
| Phase 7 Standalone Skills Tests | `py312 -m unittest tests.test_agensi_skills_phase7 -v` | **PASS (`4/4` OK, 0.242s)** | 实测 `gjf_helper.py`, `log_analyzer.py`, `multiwfn_recipe.py` 与 ZIP 构建 |

### Phases 9–11 最终全量验收基线（2026-11-12）
| 检查项 | 命令 / 方式 | 实测结果 | 备注 |
| :--- | :--- | :--- | :--- |
| Full Release Candidate Assembly | `py312 scripts/assemble_release_candidate.py --version 0.3.0` | **PASS (`9` files, Secret scan `0` hits)** | 双 `.tgz` + `win32-x64.zip` + `mcp-src.zip` + 3 Agensi ZIP + `SHA256SUMS.txt` |
| SHA-256 Independent Verification | Python `hashlib.sha256` check vs `SHA256SUMS.txt` | **PASS (`9/9` matched)** | 全部签名完全吻合 |
| MCP Source ZIP Cleanliness | Inspect `gaussian-mcp-server-0.3.0-src.zip` | **PASS (`47` files, `0` junk/pyc)** | 无 `__pycache__` / `.pyc` / `.bak` |
| **FINAL Full Python Suite (post last code/build edit)** | `py312 -m unittest discover -s tests -v` | **PASS (`110/110` OK, 34.319s)** | 全部测试零失败、零跳过 |
