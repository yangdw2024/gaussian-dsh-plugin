# Release Readiness Checklist (`v0.3.0`)

## 一、自动化工程门禁（均已实测通过）

- [x] 版本号同步升级至 `0.3.0`（`backend/config.py`, `src/index.js`, `package.json`, `runtime.json`, `scripts/deploy_runtime.ps1`, `tests/test_mcp_batch1.py`）
- [x] 包名正式回归 `@yangdw2024/gp`（同步 `package.json`, `cordis.patch.yml`, `src/client.js`, `scripts/verify_*.mjs`）并提供 `@gd/gp` 兼容构建脚本
- [x] `node scripts/build.mjs` 重建 `lib/index.js`（`41.0kb`）与 `lib/client.js`（`7.2kb`），DSH 19 工具 + 1 Prompt 注册核验通过
- [x] PyInstaller 重建 `runtimes/win32-x64/b/gaussian-backend.exe`（`contents_directory="."` 消除 `_internal/`，文件数 `2150 -> 1064`）
- [x] Windows `MAX_PATH=260` 彻底根治：包内最长相对路径 `96` 字符；隔离 `153` 字符深度 DSH 离线 `npm install` 实测最长全路径 `249 < 260`，且深度启动 EXE 与 RDKit 接口全通
- [x] 全量 Python 自动化套件最终回归：**`110/110` tests OK (`34.319s`, `EXIT=0`)**（含 7 项红队授权攻击测试、5 项编译后 EXE 跨进程锁/取消并发测试、10 项科学计算边界测试、7 项安全四期测试、4 项 Agensi 独立工具与打包测试）
- [x] 多客户端兼容性：Codex CLI `v0.148.0` 隔离 `CODEX_HOME` 实机 `4` 工具调用 `EXIT=0`；`examples/mcp_configs/` 脱敏模板已备；`claude`/`cursor` 诚实标注 `NOT_RUN`
- [x] Agensi 产品化：`3` 份 standalone Skill ZIP（`SKILL.md` 在 ZIP 根目录 + 零依赖 Python CLI）通过全部内容与脱敏核验
- [x] 开源治理：`README.md`、`CHANGELOG.md`、`CONTRIBUTING.md`、`SECURITY.md`、`TROUBLESHOOTING.md`、`THIRD_PARTY_LICENSES.md` 与 `.github/` 模板/CI 就绪
- [x] 安全红线确认：真实 `D:\G16W\g16.exe` 从未触发，用户 `~/.codex/config.toml` 与 `%APPDATA%\dsh-desktop` 保持零改动

## 二、人工审批发布门禁（`HUMAN_APPROVAL_REQUIRED` — 必须由项目所有者确认后手动执行）

- [ ] **合并与推送 Git**：人工复核 `git diff main..feature/mcp-server` 后再执行 `merge` 与 `git push`
- [ ] **发布 npm 包**：`npm publish ./dist/release-candidate/yangdw2024-gp-0.3.0.tgz`（需 OTP / 账号授权）
- [ ] **创建 GitHub Release**：上传 `dist/release-candidate/` 产物与 `SHA256SUMS.txt`，采用 `RELEASE_NOTES.md`
- [ ] **提交 Agensi Marketplace**：访问 `https://www.agensi.io/sell` 手动上传 `dist/agensi/*-v0.3.0.zip` 并设定商业定价
- [ ] **开启真实 Gaussian（若用户本机需跑实算）**：仅当人工显式需要执行实算时，设置 `GAUSSIAN_ALLOW_REAL_EXECUTION=true` 并使用 `scripts/approve_gaussian_job.py` 线下授权单次任务
