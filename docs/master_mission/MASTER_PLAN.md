# Gaussian MCP Master Engineering Mission V1.0 — 总体实施计划 (MASTER_PLAN)

> 状态标识规范：`TODO` | `IN_PROGRESS` | `PASS` | `FAIL` | `BLOCKED` | `NOT_RUN` | `HUMAN_APPROVAL_REQUIRED`
> 事实诚实原则：严格区分 `已实现` / `已测试` / `已验证` / `可发布` / `已发布`。

## 1. 总体交付目标

把 `gaussian-dsh-plugin` 推进为**三栖可独立分发、可安全验收、科学规范严谨**的工程产品：

1. **DeepSeek Harness (DSH) 插件**：保持全部 19 个现有工具契约与桌面端兼容（当前目标版本 `0.3.0`）。
2. **Gaussian MCP Server**：
   - 保留现有 12 个核心工具，补齐 DSH 对齐的 5 个核心工具：`extract_structure_from_file`、`postprocess_capabilities`、`create_postprocess_task`、`get_postprocess_task`、`list_postprocess_tasks` -> 共 **17 个核心常驻工具**。
   - 新增独立可选扩展模块 `backend/mcp_sobko_ext.py`（暴露 `sobko_search` 与 `sobko_fetch`），**未安装/未配置 Sobko 时绝不影响 MCP Server 正常启动**。
   - 修复源码审计暴露的缺陷（`backend/config.py` 重复 `data_dir`、`backend/structure_reader.py` 元素映射/句柄与临时目录清理、`backend/postprocess/manager.py` 缺失 `verify_cube_within_limit()` 调用、`backend/app.py` 后台线程保存 `dict`/`PostprocessTask` 异常、`backend/postprocess/multiwfn.py` 命令序列与子进程参数一致性等）。
3. **Agensi Agent Skills**：将 `gaussian-job-setup`、`gaussian-output-analysis`（及按需新增独立技能包）产品化为符合 Agensi 规范的独立 ZIP 包，确保零绝对路径、零密钥残留、无 MCP 时可降级使用。
4. **Cross-Agent 与 Windows 打包发布工程**：解决 `@yangdw2024/gp` Windows `MAX_PATH = 260` 问题，产出 `dist/release-candidate/` 完整 RC 产物与 GitHub Actions CI/CD 模板。

## 2. 硬性人工与外部发布门禁 (NEVER BYPASS)

| Gate ID | 受控动作 | 当前状态 | 说明 |
| :--- | :--- | :--- | :--- |
| `GATE-G16-REAL` | 真实运行 `D:\G16W\g16.exe` | `HUMAN_APPROVAL_REQUIRED` | 保持 `GAUSSIAN_ALLOW_REAL_EXECUTION=false`；完成所有干跑、文件锁、SHA-256 绑定与前置验证，未获独立人工令牌绝不真实启动 `g16.exe`。 |
| `GATE-GIT-MAIN` | 合并到 `main` / 推送受保护分支 | `HUMAN_APPROVAL_REQUIRED` | 所有开发与提交仅在 `feature/mcp-server` 本地进行。 |
| `GATE-RELEASE-PUB` | 发布 GitHub Release / `npm publish` / Agensi 上架定价 | `HUMAN_APPROVAL_REQUIRED` | 仅本地生成 `dist/release-candidate/` 与 `.tgz`/ZIP 产物并完成本地安装与校验。 |
| `GATE-LIVE-CONFIG` | 修改用户正式 Codex/DSH/Claude/Cursor 配置 | `LOCKED` | 所有联调验证使用临时隔离目录，绝不覆盖 `~/.codex/config.toml` 与 `%APPDATA%\dsh-desktop`。 |

## 3. 分阶段实施路线图

- **Phase 0 (Done)**: 环境盘点、Git 基线核验（`feature/mcp-server @ 27ed1dc5c71c3809755d0e6077ec6d7a33e09485`）、源码深度缺陷扫描。
- **Phase 1**: V5.3 真实计算前置预检验（重跑干净 `79` 项 `py312` 基线测试日志、`g16.exe`/`formchk.exe` 权限检查、`h2_sp_preaccept.gjf` SHA-256 绑定 dry-run 与未授权真实执行拦截）。
- **Phase 2**: 补齐 17 个核心 MCP 工具 + 可选 Sobko 扩展，修复已识别缺陷，完成单测、MCP Stdio 与安全非高斯工具联调（`formchk`/`Multiwfn`/`VMD`）。
- **Phase 3**: 计算化学科学正确性深化（SCF vs Opt、HOMO-LUMO vs 光学激发、单位换算、Post-HF 能量、虚频与收敛/截断日志校验）与基准测试集扩充。
- **Phase 4**: 全链路安全与稳定性审计（21 项清单核查：Junction/Symlink、命令注入、HMAC 重放、CORS、跨进程锁、PID 复用、大日志与 Zip/Cube 限制等）。
- **Phase 5**: 跨 Agent 兼容性测试（DSH、隔离 `CODEX_HOME` 下 Codex CLI 实测；Claude Code / Cursor 诚实标为 `NOT_RUN` 并输出配置模板）。
- **Phase 6**: Windows `MAX_PATH < 260` 打包与 `@yangdw2024/gp` 安装冲突根治 + `0.3.0` 构建验证。
- **Phase 7**: Agensi Skills 独立 ZIP 打包、合规检查、独立降级能力与试点定价策略输出。
- **Phase 8**: GitHub 公开仓库治理与 `.github/workflows/` CI/CD 模板准备。
- **Phase 9–11**: `dist/release-candidate/` 汇总、全量回归测试、发布前静态安全/许可证检查与 `FINAL_REPORT.md` 最终交付。
