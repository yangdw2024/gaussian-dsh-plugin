# 发布就绪评估报告（RELEASE READINESS — V5.2）

> 评估范围：`feature/mcp-server` 分支在 V5.2 工程加固后的发布就绪状态。  
> 结论：**桌面开发者源码/预编译本地交付就绪（受控 Dry-Run & Mock 模式）；对 npm 公共发布与真实 `g16.exe` 执行仍按规则保持发布门控锁定。**

---

## 1. 发布就绪检查总览

| 维度 | 当前状态 | 说明与证据 |
| :--- | :--- | :--- |
| Windows 编译运行时 (`runtimes/win32-x64`) | **READY** | Python `3.12.10` + PyInstaller `6.22.3` 重建完成；`2150` 项 `runtime.json` SHA-256 `BAD=0`；支持 `--mock-worker` 与 `stdin=DEVNULL` 管道修复；隔离冒烟 `PASS` |
| DSH 后端与 MCP 跨进程一致性 | **READY** | 实测已编译 `gaussian-backend.exe` + `mcp_server.py` 共享锁、并发抢占、优雅停机保租约与停止竞争 `5/5 OK`；`POST /v1/jobs` 与 MCP 共用三层授权门控 |
| 三层执行授权与对抗加固 | **READY（MCP/HTTP 边界）** | `7/7` 对抗测试拦截了密钥读取、Admin API 越权、HMAC 伪造、令牌重放、审批后参数篡改及跨作业劫持；**同账户 OS Shell 威胁须靠独立系统账户/NTFS ACL 防护** |
| 默认配置可移植性 | **READY** | `backend/config.py` 实现 `_default_work_dir()` 回退至 `<data_dir>/gjf`；`src/index.js` `GAUSSIAN_GUIDANCE` 已泛化，无开发机硬件与私人路径硬编码 |
| DSH / npm 包体积与 Windows `MAX_PATH` | **CONDITIONAL** | `@gd/gp@0.2.0` (`npm pack --dry-run`: `2244` 文件，`~73.13 MiB` 压缩包) 在 DSH `.generations/live` 下最深 RDKit DLL 约 `253` 字符（安全 `< 260`）；若强行重命名为 `@yangdw2024/gp` 则会涨至 `~269` 字符（触发 Win10/11 `MAX_PATH` 风险，除非宿主开启 `LongPathsEnabled` 或重构路径布局） |
| Agensi Skills ZIP 资产 | **READY（待人工审核上架）** | `dist/agensi/gaussian-job-setup.zip` (`3,292` B) 与 `dist/agensi/gaussian-output-analysis.zip` (`3,020` B) 已确认在重建后完整保留 |
| 真实 Gaussian (`g16.exe`) 计算通道 | **HOLD（待 V5.3 批准）** | 已备齐 `H2 HF/STO-3G` 预检档案（[H2_REAL_PREACCEPTANCE.md](file:///E:/YDW/ChemDatas/gaussian-dsh-plugin/docs/engineering/H2_REAL_PREACCEPTANCE.md)），V5.2 阶段保持 `GAUSSIAN_ALLOW_REAL_EXECUTION=false` 未拉起真实算例 |

---

## 2. V5.1 至 V5.2 发布阻塞项核销情况

| 阻塞项编号 | 原先阻塞描述 | V5.2 处置状态 | 结论与后续条件 |
| :--- | :--- | :--- | :--- |
| **BLOCKER-1** | `runtimes/win32-x64/gaussian-backend.exe` 为旧版本，缺少跨进程调度与三层授权同步 | **已关闭（CLOSED）** | 已在 Python `3.12.10` 下全量重建；`2150` 文件 SHA-256 校验通过；编译端与 MCP `5/5` 跨进程测试通过 |
| **BLOCKER-2** | 跨机器默认路径与包名作用域 `@gd/gp` vs `@yangdw2024/gp` 及 `MAX_PATH` 风险未澄清 | **工程部分关闭 / 发布策略锁定** | 默认工作目录回退与提示词泛化已完成验证；保留 `@gd/gp` 规避 `269` 字符溢出，公开 npm `@yangdw2024/gp` 需待路径瘦身或要求目标环境启用 `LongPathsEnabled` |
| **BLOCKER-3** | 真实 Gaussian（最小 H2 单点）端到端实测尚未执行 | **保留待批（GATED -> V5.3）** | 已完成只读文件盘点、SHA-256 固化、Dry-Run 预检与参考能量基准对齐（`H2_REAL_PREACCEPTANCE.md`），等待 V5.3 单独授权运行 |
| **BLOCKER-4** | `git push` / `npm publish` / Agensi 市场发布操作 | **保留待批（GATED）** | 严格遵循指令禁止越权推送或发布，仅完成本地 Git 提交与发布前自检 |
