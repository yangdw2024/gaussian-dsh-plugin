# Gaussian AI MCP Server 发布就绪度评估 (Release Readiness V5.1)

本文档对 `feature/mcp-server` 分支在 V5.1 工程收尾阶段的软件质量、安全合规、跨进程调度稳定性及对外发布阻塞项进行客观评估。

---

## 1. 全量 12 个 MCP 工具与授权机制就绪表

| 工具名称 | 类别 | 代码实现与测试状态 | V5.1 加固要点 | Codex 实机验证 |
|---|---|---|---|---|
| `gaussian_status` | 环境就绪 | PASS | 披露 `compute_lease` 跨进程占用者与隔离根目录 | 已验证 (`v5_audit`) |
| `generate_gaussian_input` | 输入构建 | PASS | `<= 300` 原子校验、仅限 Write Roots | 已验证 (`v5_audit`) |
| `parse_gaussian_output` | 结果解析 | PASS | 自动识别仿真标并将仿真能量隔离至 `simulated_energy`，`final_energy=None` | 已验证 (`v5_audit`) |
| `diagnose_gaussian_error` | 错误诊断 | PASS | 默认本地瞬时规则路径，避免外部慢探测超时 | 已验证 (`v5_audit`) |
| `search_gaussian_keywords` | 知识检索 | PASS | 纯内存关键词检索与数量截断 | 已验证 (`v5_1_audit`) |
| `search_basis_sets` | 基组检索 | PASS | 本地缓存 + 无网离线回退 | 已验证 (`v5_1_audit`) |
| `get_basis_set` | 基组获取 | PASS | 受专用 Cache Roots (`~/.gaussian-dsh/basis_cache/`) / Write Roots 隔离 | 已验证 (`v5_1_audit`) |
| `generate_gaussian_input_from_smiles` | 3D 构象 | PASS | 内存守卫 + 跨进程 `rdkit` 锁 + 显式全氢 | 已验证 (`v5_audit`) |
| `submit_gaussian_calculation` | 任务调度 | PASS | 三层授权 (`integrity_token` + 带外 `human_approval_token` + `GAUSSIAN_ALLOW_REAL_EXECUTION`) + 跨进程锁 + `is_simulated` | 已验证 (`v5_audit` + `v5_1_audit` 防绕过) |
| `get_gaussian_job_status` | 进度监控 | PASS | 采纳跨进程磁盘终态、Mock 能量置入 `simulated_energy` (`last_energy=None`) | 已验证 (`v5_audit`) |
| `list_gaussian_jobs` | 队列管理 | PASS | 统一透传仿真标识并严格隔离 `last_energy` | 已验证 (`v5_audit`) |
| `stop_gaussian_calculation` | 进程终止 | PASS | OS 创建时间防 PID 复用误杀、`taskkill /F /T` 树状清理、重复停止拦截与跨进程终态同步 | 已验证 (`v5_1_audit`) |

---

## 2. 发布演练结果 (Dry-Run Only — 未对外发布)

1. **Agensi Standalone Skills ZIP (`dist/agensi/`)**：
   - `dist/agensi/gaussian-job-setup.zip`：包含根目录 `SKILL.md` (YAML frontmatter 完整)、`references/route-keywords-guide.md`、`templates/mcp-config.json`（含通用占位符配置及不随包分发 G16 二进制的合规声明）。
   - `dist/agensi/gaussian-output-analysis.zip`：包含根目录 `SKILL.md`、`references/error-diagnostics-guide.md`、`templates/mcp-config.json`。
   - 原型源文件位于仓库 `skills/` 目录并纳入 Git 版本管理；`dist/` 按构建产物规则保持在 `.gitignore` 外（仅作本地待上传分发包，上传需等产品文案及人工复核授权）。
2. **npm Dry-Run (`npm pack --dry-run`)**：
   - 成功生成测试归档摘要：`gd-gp-0.2.0.tgz`（包体积 `72.2 MB`，解包体积 `162.8 MB`，共 `2153` 个文件）。
3. **Python 依赖锁定 (`requirements-mcp.txt`)**：
   - 已核查全量第三方直接导入模块（含 `mcp`, `rdkit`, `numpy`, `requests`, `pydantic`, `pydantic-core`, `psutil`, `fastapi`, `uvicorn`, `httpx`, `pillow`），均精确锁定版本号。

---

## 3. 已验证达成项 vs 未解决高风险阻塞项 (Release Blockers)

### 已达成项
- [x] **跨进程锁闭环**：DSH Backend 与 MCP Server 间通过 `compute_lease.lock` + `compute_lease.json` + 原子写盘彻底消除并发越界竞态。
- [x] **人工带外授权隔离**：`confirmed=True` 与 `integrity_token` 无法替代人工授权；`.human_signing_key` 位于 `security.py` 显式屏蔽的 `approvals/` 目录内；单次 `nonce` 拦截重放攻击。
- [x] **仿真产物零混用**：`mock_worker` 输出不再可能伪装成真实 `final_energy` / `last_energy`。
- [x] **全量 67 项单元测试 + 烟雾 + DSH 19 工具契约 + Codex 12 工具全实测 PASS**。

### 发布与上线前阻塞项 (Release Blockers — 必须先解决或显式决策)
1. **[BLOCKER-1] 预构建二进制运行时尚未随 V5.1 源码重编**：
   `npm pack --dry-run` 打包的 `runtimes/win32-x64/gaussian-backend/` 为此前版本构建，**尚未重新执行 PyInstaller 打包与 `scripts/smoke_test_backend.ps1` 验证**。发布新版本 DSH npm 包前，必须重新构建运行时二进制并复测通过。
2. **[BLOCKER-2] npm 包名与工作区配置可移植性差异**：
   当前 `package.json` 中的包名为 `@gd/gp@0.2.0`，与背景说明中的 `@yangdw2024/gp` 存在命名差异；同时 `backend/config.py` 默认回退路径与 `tests/test_scientific_correctness.py` 外部参考日志路径仍指向本机特定工作盘，新用户安装需通过环境变量覆盖或进一步泛化默认值。
3. **[BLOCKER-3] 真实物理计算 (`g16.exe`) 与 DSH Desktop 宿主联调尚未放开实跑**：
   遵循本阶段安全边界，`GAUSSIAN_ALLOW_REAL_EXECUTION` 仍保持禁用，真实工作站算例端到端压测与 DSH Desktop live profile 挂载测试 (`verify_installed_runtime.mjs` / `verify_plugin_shape.mjs`) 待生产发布前单独批准执行。
4. **[BLOCKER-4] 对外分发动作尚未授权**：
   尚未执行 `git push`、`npm publish` 或向 Agensi 提交正式商品包；当前仅完成了 `feature/mcp-server` 分支上的本地安全固化与源码级提交。
