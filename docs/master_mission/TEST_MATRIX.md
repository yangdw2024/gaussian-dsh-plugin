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
