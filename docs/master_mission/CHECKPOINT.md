# Master Engineering Mission 检查点（Phase 8 Completed）

- **当前分支**：`feature/mcp-server`
- **当前已完成阶段**：Phases 0–8
- **立即下一步（Phases 9–11 最终组装、审计与交付）**：
  1. 编写并运行 `scripts/assemble_release_candidate.py`（组装完整 `dist/release-candidate/`：`.tgz` 双包、`gaussian-backend-0.3.0-win32-x64.zip`、`gaussian-mcp-server-0.3.0-src.zip`、`requirements-mcp.txt`、`agensi/*.zip`、真实 `SHA256SUMS.txt`、发布说明草稿 `RELEASE_NOTES.md`），并执行全仓敏感词/密钥/私人路径扫描。
  2. 运行**最后一轮完整验证**：
     - `py312 -m unittest discover -s tests -v`（全量测试）
     - `node scripts/build_npm_packages.mjs`（含 `node scripts/build.mjs` + `MAX_PATH < 260` 校验 + `.tgz` 打包）
     - `py312 scripts/package_agensi_skills.py`（3 个 Agensi ZIP 校验）
     - 独立校验 `dist/release-candidate/` 全部产物与 `SHA256SUMS.txt`。
  3. 基于上述实测输出，撰写/定稿 `docs/master_mission/{RELEASE_MANIFEST.md,RELEASE_CHECKLIST.md,TEST_MATRIX.md,TASK_BOARD.md,EXECUTION_LOG.md,CHECKPOINT.md,FINAL_REPORT.md}` 并在 `feature/mcp-server` 完成最终清洁提交（`READY_FOR_APPROVAL`）。
