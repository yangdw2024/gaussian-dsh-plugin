# 发布准入检查清单 (RELEASE_CHECKLIST)

| Check ID | 检查项 | 门禁要求 | 当前状态 | 证据 / 备注 |
| :--- | :--- | :--- | :--- | :--- |
| `RC-01` | Git 分支与工作区状态 | 处于 `feature/mcp-server` 且最终全部变动已提交 | `IN_PROGRESS` | 严禁擅自合并或推送到 `main` |
| `RC-02` | V5.3 真实计算审批边界 | `GAUSSIAN_ALLOW_REAL_EXECUTION=false` 保持默认关闭 | `TODO` | 真实计算须人工批准 (`HUMAN_APPROVAL_REQUIRED`) |
| `RC-03` | MCP 工具完整性与降级 | 17 核心工具全部通过契约与测试，可选 Sobko 不阻断启动 | `TODO` | Phase 2 |
| `RC-04` | 科学正确性与 Mock 隔离 | `is_simulated=True` 与 `final_energy=None` 严禁混淆 | `TODO` | Phase 3 |
| `RC-05` | 安全审计与漏洞扫描 | 无路径穿越、Junction 绕过、命令注入或密钥泄露 | `TODO` | Phase 4 & 10 |
| `RC-06` | Windows `MAX_PATH` 与 `@yangdw2024/gp` | 在 `LongPathsEnabled=0` 下完成真实离线安装与启动 | `TODO` | Phase 6 |
| `RC-07` | Agensi Skills 合规 ZIP | 根目录含 `SKILL.md` + `version`，无硬编码路径/密钥 | `TODO` | Phase 7 |
| `RC-08` | 开源治理与第三方许可 | 补全 `CHANGELOG` / `SECURITY` / `THIRD_PARTY_LICENSES` / CI | `TODO` | Phase 8 |
| `RC-09` | RC 候选包与校验和 | `dist/release-candidate/` 完整生成并附 `SHA256SUMS` | `TODO` | Phase 9–10 |
| `RC-10` | 最终全量回归零失败 | 最终代码冻结后所有非外部阻塞测试 100% 通过 | `TODO` | Phase 11 |
