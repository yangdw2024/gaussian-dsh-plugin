# Master Engineering Mission 检查点（Phase 6 Completed）

- **当前分支**：`feature/mcp-server`
- **当前已完成阶段**：Phases 0–6（版本已升至 `0.3.0`，Windows `MAX_PATH=260` 已根治）
- **立即下一步（Phase 7）**：
  1. 升级 `skills/gaussian-job-setup/` 与 `skills/gaussian-output-analysis/`，并新增第 3 技能 `skills/gaussian-postprocessing/`（Multiwfn/VMD/FCHK）。
  2. 为每项技能补充纯 Python 标准库独立 CLI 工具（无 MCP 亦可单独使用），修正 `templates/mcp-config.json` 指向 `<PATH_TO_REPO>/mcp_server.py`。
  3. 编写 `scripts/package_agensi_skills.py` 生成 `SKILL.md` 位于 ZIP 根目录的 `dist/agensi/*.zip` 并做结构与脱敏校验；编写 Agensi 商业化定价/上架策略说明。
