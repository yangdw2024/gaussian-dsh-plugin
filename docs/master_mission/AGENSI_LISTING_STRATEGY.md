# Agensi Marketplace 上架与商业化交付说明（Phase 7）

本文档结合 Joeri Brons（`joeri@agensi.io`，2026-11-07 邮件反馈）明确提出的 Agensi 市场技术规范与商业规则，规划本项目的 standalone Agent Skills 上架结构、打包验收标准与定价建议。

## 1. Agensi 平台规范对齐（来自 Joeri Brons 邮件事实）

| 平台条目 | 官方邮件说明 | 本项目对应落实 |
| :--- | :--- | :--- |
| **包结构** | 独立 Skill ZIP，根目录直接放置含有效 YAML frontmatter 的 `SKILL.md`，附带 `scripts/` 与 `references/` | `scripts/package_agensi_skills.py` 生成 3 个 ZIP，`SKILL.md` 均位于 ZIP 根目录 |
| **MCP 策略** | Agensi 不托管用户 MCP Server；MCP 集成留在买家本地，ZIP 内提供配置模板与接入说明 | 所有 Skill 均已升级为 **Mode A（无需 MCP 的纯 Python stdlib 独立可用）+ Mode B（可选对接本地 `mcp_server.py`）** |
| **IP 归属** | 非独占上架（non-exclusive），不转移 IP，GitHub 与 npm 仓库保持原样 | 项目 MIT 协议开源底座、GitHub 与 `@yangdw2024/gp` npm 包保持完全独立 |
| **分成模式** | 免费上架，作者自主定价，创作者分得 **70%**，平台扣除 **30%**（包含 Stripe 手续费，由平台作 Merchant of Record） | 建议定价已预留 30% 渠道扣点测算 |

## 2. 本次产出的 3 个 Agensi 独立 Skill ZIP (`v0.3.0`)

1. `gaussian-job-setup-v0.3.0.zip`
   - 核心价值：`.xyz -> .gjf` 一键生成、Link0 安全与语法防错校验（CRLF/路径遍历/尾空行/电子奇偶自旋守恒校验）、SP / Opt+Freq / TS / IRC / TD-DFT / NMR 路线词模板。
   - 内置零依赖脚本：`scripts/gjf_helper.py`（无需安装 RDKit 或运行 MCP Server 即可开箱使用）。
2. `gaussian-output-analysis-v0.3.0.zip`
   - 核心价值：`.log`/`.out` 结构化解析（SCF 能量、HOMO-LUMO 能隙单位换算、TD-DFT 激发态、虚频数量与驻点判定、`--Link1--` 多步未完检测）与经典 Link 错误（`l9999`, `l502`, `l301`, `l103`, `l913`）诊断修复手册。
   - 内置零依赖脚本：`scripts/log_analyzer.py`。
3. `gaussian-postprocessing-v0.3.0.zip`
   - 核心价值：`formchk -> Multiwfn 3.8 -> .cub -> VMD Tachyon -> .png` 闭环后处理指南，涵盖分子轨道（HOMO/LUMO）、静电势（ESP）与非共价相互作用（RDG/NCI）脚本生成及 `16,000,000` 格点 OOM 防护校验。
   - 内置零依赖脚本：`scripts/multiwfn_recipe.py`。

## 3. 商品化定价与上架漏斗建议

- **基础引流品（Free 或 \$5-\$9）**：`gaussian-job-setup`（降低试错门槛，直接引导买家 Star GitHub 或进一步配置本地 17-tool MCP Server）。
- **高频刚需品（\$12-\$19，70% 净收入约 \$8.4-\$13.3/单）**：`gaussian-output-analysis`（覆盖科研日常最痛点的不收敛与虚频排障场景）。
- **高阶可视化包（\$15-\$25，70% 净收入约 \$10.5-\$17.5/单）**：`gaussian-postprocessing`（面向论文作图 ESP / RDG / MO 的即用批量模板）。
- **上架前待人工操作**：登录 `https://www.agensi.io/sell`，上传 `dist/agensi/*-v0.3.0.zip`（本工程不会自动代为提交上架表单）。
