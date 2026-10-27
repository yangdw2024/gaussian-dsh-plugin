# R17c Release Readiness Report — @gd/gp v0.2.0（2026-10-26 收尾复核）

> 复核日期：2026-10-26（周一）｜ 复核机：Windows 11（AMD Ryzen 7 9700X / RTX 5060 Ti / 15.1 GB 内存）
> DSH 桌面端：`0.12.1`（`E:\DSH\DSH Desktop\resources\app.asar`，369,424,689 B；解包 fallback `resources\app\package.json` name=`dsh-desktop` version=`0.12.1`）
> 复核时刻状态：DSH 未运行；`127.0.0.1:8765` 无监听；无 `gaussian-backend` / `g16` / `Multiwfn` / `vmd` 残留进程。
> 本报告只记录本轮**实际执行过**的验证；未执行的外部程序 / DSH 对话内实机项一律标 **NOT RUN**，不写成 PASS。
> 历史报告：`docs/RELEASE_READINESS_REPORT.md`（R16，2026-10-22）、`docs/R17_DIAGNOSIS_20261022.md`（R17 排障）；本报告为当前最新口径，旧报告保留历史过程不覆盖。

---

## 1. 总体结论

**READY WITH EXTERNAL SMOKE PENDING**

一句话原因：离线契约、后端独立 smoke、产物实物与日志解析本轮全部复跑通过，未发现新的 Blocker/Major；但 DSH 对话内 managed 生命周期全状态机、新布局状态卡浏览器渲染、新一轮化学链端到端属于 L4 实机项，复核时刻 DSH 未运行，本轮未现场观察，需在目标机器完全退出重启 DSH 后补一轮 smoke 才能转 READY。

### 1.1 结论边界（四层证据，禁止跨层顶替）

| 层 | 本轮状态 | 能证明 | 不能证明 |
|----|----------|--------|----------|
| L1 离线契约 | **PASS** | 装载声明链、19 个工具 output/parameters 契约、manifest 解析链、Host 形状合法 | 运行时能否拉起后端、卡片能否渲染、工具能否被模型调用 |
| L2 后端独立 smoke | **PASS** | 部署路径 exe 能独立启动，health/status/capabilities/鉴权/非法输入拒绝/目录创建/受控退出正常 | DSH 能拉起它；前端/卡片链路通不通 |
| L3 历史产物复核 | **PASS** | 10-23/10-24 三个 Gaussian 任务、三个后处理任务的落盘记录、实物大小、PNG 解码、cube 网格头、日志解析字段与后端规则一致 | 本轮新跑一遍化学链；DSH 对话内调用链路 |
| L4 重启 DSH 实机 | **NOT RUN** | — | managed spawn→ready、reuse/dispose/orphan/race、状态卡渲染、对话内工具实调、新一轮化学链端到端 |

---

## 2. 构建结果（基线冻结记录）

### 2.1 源码与版本

| 项 | 值 / 证据 |
|----|-----------|
| 插件包名 | `@gd/gp`（2026-10-24 由旧名 `@gaussian/dsh-plugin-gaussian` 改为短包名，规避 MAX_PATH） |
| 插件 / 后端版本 | `0.2.0`（项目根 `package.json` 与 `backend/app.py` L44/L106/L181/L205 一致） |
| 源码根目录 | `E:\YDW\ChemDatas\gaussian-dsh-plugin\`（**Git 仓库**，分支 `main`；HEAD=`8af984b73b95cc2e8948f53876072b41afb99b95`，2026-10-24 21:46:30，提交信息 "v0.2.0: working end-to-end (benzene opt verified), publish to npm"） |
| Git 工作区状态 | 业务源码 `src/`、`backend/`、`lib/`、`runtimes/`、`package.json`、`cordis.patch.yml` 相对 HEAD **零改动**；本轮未提交改动仅限文档（README、docs/ 七份）与两个离线校验脚本（`verify_plugin_shape.mjs`、`verify_profile_bundle.mjs`），新增取证脚本/备份/本报告位于 `docs\_verify\` 与 `docs\backups_20261026\`；`.gitignore` 排除 `node_modules/`、`build/`、`dist/`、`runtimes/`、`__pycache__/`、`*.log`，`lib/` 入库 |
| 后端源码 | `backend\` 共 25 个 Python 文件（根目录 16 + `postprocess\` 6 + `smiles\` 3，各含 `__init__.py`）；最新修改 `config.py` 2026-10-23 21:37:26、`structure_reader.py` 21:37:11、`app.py` 21:29:34、`postprocess\manager.py` 20:20:24、`postprocess\multiwfn.py` 20:20:07、`postprocess\models.py` 18:37:45、`gaussian_input.py` 18:32:29 |
| 前端源码 | `src\index.js`（Host，19 个工具 + systemPrompt section）、`src\client.js`（浏览器状态卡） |
| 前端构建产物 | `lib\index.js`、`lib\client.js`（esbuild `node scripts/build.mjs`） |
| 后端运行时 | PyInstaller **onedir**（one-file 未实现，设计如此，非缺陷，不擅自实现） |
| 构建命令 | `scripts\build_backend.ps1` → PyInstaller `packaging\gaussian-backend.spec` → `scripts\deploy_runtime.ps1` 部署到 `runtimes\win32-x64\` |
| 构建机 / OS | 本机 Windows 11（AMD Ryzen 7 9700X / RTX 5060 Ti / 15.1 GB 内存）；打包 Python 版本以 `runtime.json` 记录为准 = **3.13.13**（当前复核 shell python=3.13.16，属环境后续补丁，不影响已打包 exe）；PyInstaller 6.21.0 为 10-24 打包时点口径，打包工具本身不进 `_internal`，本轮复核环境未装 PyInstaller、未复现该版本号 |
| 后端数据目录 | `C:\Users\Administrator\.gaussian-dsh\`（jobs / postprocess / logs 子目录，启动自动创建） |
| Gaussian 工作目录 | `E:\YDW\ChemDatas\Gjf\` |

### 2.2 本轮实测哈希与大小（SHA-256 前 16 位，2026-10-26 复核）

| 文件 | 位置 | SHA-256 前 16 | 大小 | mtime | 一致性 |
|------|------|---------------|------|-------|--------|
| `lib\index.js` | 项目根 | `611D011A1C83D986` | 41,072 B | 2026-10-24 20:09:42 | 项目根 = generation shim = web junction，三者一致 |
| `lib\client.js` | 项目根 | `CFA2CEB802FFB9EC` | 7,353 B | 2026-10-24 20:09:42 | **新**（见 §4 Minor-1） |
| `lib\client.js` | generation shim / web junction | `B8A38D8D28F5A97A` | 7,376 B | 2026-10-24 17:06:29 | **旧快照**，与项目根差 1 行（ModuleLoader id 字符串），其余 191 行逐字相同 |
| `gaussian-backend.exe` | 项目根 / shim / junction | `E75FBDC99D263A0B` | 17,670,055 B | 项目根 10-24 19:56:02；shim 10-24 20:10:33 | 三者一致；晚于全部后端 py 修改，含 10-23 P1/P3/P2-1 修复 |
| `runtime.json` | 项目根 / shim | `FFC2899D793A92DC` | 488,726 B | 10-24 19:56:50 | 一致；version `0.2.0`、target `win32-x64`、2,059 条文件清单；记录 exe 全量 SHA-256 `e75fbdc99d263a0baf716b1897ea913568dc2472333093176a566b44cf7f010c`，与实测一致 |

### 2.3 当前生效 DSH 布局（新 harness，2026-10-24 迁移后口径）

| 层 | 路径 | 本轮取证结论 |
|----|------|--------------|
| Harness 根 | `C:\Users\Administrator\AppData\Roaming\dsh-desktop\harness\` | DSH 0.12.1 实际读取位置 |
| 活跃 profile | `profiles\web\` | dependencies 末项 `"@gd/gp": "0.2.0"`；`dsh.profile.bundles` 26 项（`@gd/gp` 居第 10 位，非末位）；`generationProjection.plugins["@gd/gp"].generationId = "@gd+gp+0.2.0"`；`pnpm.overrides["@gd/gp"] = "link:../.generations/live/@gd+gp+0.2.0/node_modules/@gd/gp"` |
| Generation 快照 | `profiles\.generations\live\@gd+gp+0.2.0\` | `generation.json`：`pluginName=@gd/gp`、`version=0.2.0`、`sourceSpec=E:\YDW\ChemDatas\gaussian-dsh-plugin`；内含 `node_modules\@gd\gp\`（shim，DSH 实际读取）与 `source\gaussian+dsh-plugin-gaussian\`（整包源副本） |
| Junction | `profiles\web\node_modules\@gd\gp` | LinkType=Junction，指向 generation shim；`Get-Item` Target 已实测 |
| profile patch | `profiles\web\cordis.patch.yml`（51,917 B，10-24 21:35:42，806 个 LF 换行、无 CRLF） | **无 `gaussian` / `@gd/gp` 条目（全文命中 0）；本插件 entry 未被 `disabled: true` 关闭**。文件内 `disabled: true` 共 **17 处**，归属：`michengai-codex-pet`、`ui-skin-maid-atelier`、wallpaper-engine 系列 8 个槽位、`ui-skin-verdandi`、`tool-subagent-codex`×2、`tool-subagent-claude-code`×2、`workflow-worker-thread`×2，均与本插件无关；另有 `disabled: false` 真实配置 10 处（L33/L35/L388/L392/L396/L414/L685/L689/L693/L716），L385/L682 两行注释文本亦提及 `disabled: false`、非配置项；`permission.defaultPreset = danger-full-access`（L73） |
| Generation 清单 | `profiles\.generations\desired.json` | 18 个 generation，末项 `"@gd+gp+0.2.0"`，与 live 目录一一对应 |
| 宿主全局开关 | `harness\desktop-host-plugins.json`（harness 根，非 web profile 目录） | `{"version":1,"disabled":[]}`，无全局禁用插件 |
| 用户环境变量（User 级，永久） | `GAUSSIAN_BACKEND_MODE=managed`；`GAUSSIAN_BACKEND_EXE=E:\YDW\ChemDatas\gaussian-dsh-plugin\runtimes\win32-x64\gaussian-backend\gaussian-backend.exe`；`GAUSSIAN_BACKEND_URL` 未设（代码回退 `http://127.0.0.1:8765`）；`GAUSSIAN_DATA_DIR` / `GAUSSIAN_WORK_DIR` 未设（回退默认） |

**旧布局（不参与当前运行，仅历史遗留）**：`C:\Users\Administrator\.dsh\profiles\desktop\` 配置文件最后改动停在 2026-10-22（`cordis.yml` 20:24:06、`package.json` 20:09:56、`cordis.patch.yml` 18:21:32；`node_modules` 内 `__pycache__` pyc 为 10-24 后端运行时生成的缓存，非配置/源码改动）；dependencies 为旧包名 `@gaussian/dsh-plugin-gaussian` file: 项目根 + `@aifs` / `@autorest` 两个 tgz，bundles 仅官方 base/web-app + 旧包名；`C:\Users\Administrator\.dsh\profiles\web\`（`package.json` 2026-10-09 20:26:26，空依赖、bundles 仅官方两条）同为遗留快照。新 harness 不读取这两个目录。

### 2.4 产物是否来自当前源码

- `lib\index.js` 项目根与运行快照哈希一致（`611D011A…`），L1 契约自测从项目根 `lib/index.js` 收集 19 个工具全部 PASS。
- 后端 exe 晚于全部后端 py 修改时间，`runtime.json` 记录的 SHA-256 与实测一致；`verify_installed_runtime.mjs` 8 项断言全 PASS（含 pydantic_core 四件套：`__init__.py`、`core_schema.py`、`py.typed`、`_pydantic_core.cp313-win_amd64.pyd`）。
- 唯一不一致：快照 `lib\client.js` 落后项目根 1 行（§4 Minor-1），不影响 Host 装载与工具注册。
- 旧 `acceptance_bundle.zip`（R16，2026-10-22 16:36:33，227,669 B）**不代表当前源码**，10-23/10-24 改动后未重打；本轮未将其计入发布产物（见 §6 发布动作）。

---

## 3. Smoke Matrix

> 口径：**PASS** = 本轮实际执行并通过；**FAIL** = 本轮执行且失败；**NOT RUN** = 复核时刻未执行，不顶替为通过。证据路径见 §3.7。

### 3.1 后端基础 smoke（L2，独立端口 8792、临时目录 `docs\_verify\smoke-20261026\`，不污染正式目录、不提交真实 Gaussian）

| 编号 | 检查项 | 结果 | 证据 / 备注 |
|------|--------|------|-------------|
| B1 | backend 能启动（部署路径 exe） | **PASS** | 3 秒内 health OK；2026-10-26 收尾复跑最新一轮 pid=26472，instance_id=`93ef6f31c3e4`，uptime=0.6s（pid/instance_id 每次进程启动随机生成，仅作本轮启动证据；前几轮复跑 pid=26776/instance=`bd2e31111fd3`/0.6s、pid=24120/instance=`6e3cef531567`/uptime=1.3s、pid=21612/instance=`ee4974aa0837`/uptime=0.6s、pid=452/instance=`fac6215ce7e6`、pid=4436/instance=`5caa01c9b8f2`/uptime=0.4s、pid=25756/instance=`8cafdec71958`） |
| B2 | `/v1/health` 正常 | **PASS** | 顶层 8 字段齐全：`ok=true`、`service=gaussian-dsh-backend`、`version=0.2.0`、`pid`、`instance_id`、`uptime_seconds`、`compute_lease`、`memory`；`compute_lease` 子字段 held/kind/owner_id/held_seconds，`memory` 子字段 rss_mb/peak_mb/soft_mb/hard_mb/level/can_accept_compute；lease held=false |
| B3 | `/v1/status` 正常 | **PASS** | 200、status ok、version 0.2.0；`gaussian.exe=D:\G16W\g16.exe` exists=true；work/data 指向临时目录；default_mem=12GB、default_nproc=8；running_job=false、lease held=false；sobko `configured=true`、`mode=bm25_only` |
| B4 | `/v1/postprocess/capabilities` 正常 | **PASS** | formchk exists=true、multiwfn exists=true、vmd exists=true；Multiwfn 实测版本 `3.8` / expected `3.8` / `version_matched=true`（真实抓 banner，非硬编码）；`max_grid_points=16,000,000` |
| B5 | 管理接口鉴权三态 | **PASS** | 正确 token → 200；错误 token → 403；无 token → 403（`_require_admin`，`app.py` L228–243；未配置 `GAUSSIAN_MANAGED_TOKEN` 时仅放行回环来源） |
| B6 | 非法超资源 GJF 被拒绝 | **PASS** | 空内容 → `{ok:false,error:"GJF 校验未通过：gjf_content 为空"}`；缺电荷多重度 → 对应报错；`%nprocshared=32` 超 8 核 → 拒绝；`%mem=20GB` 超 12GB 预算 → 拒绝。四项均 HTTP 200 + `{ok:false}`（历史既有行为口径，见 §4 Minor-4） |
| B7 | 非法 body 被 Pydantic 拒绝 | **PASS** | 缺 `gjf_content` 字段 → HTTP 422 |
| B8 | 正常 API 返回结构符合 Pydantic v2 模型 | **PASS** | health/status/capabilities/keywords/sobko-status 结构与模型字段一致；`/v1/keywords` 200、categories=7；`/v1/sobko/status` 200、bm25_only |
| B9 | 数据目录 / 任务目录 / 日志目录自动创建 | **PASS** | 临时 data 目录下 `jobs`、`postprocess`、`logs` 三个子目录启动后自动生成 |
| B10 | 启动 / 关闭过程无 traceback | **PASS** | stdout/stderr 日志无 Traceback / ModuleNotFoundError / Fatal / CRITICAL；受控 shutdown 200，`waitForExit` returncode=0，端口释放（连接失败） |
| B11 | 项目自带 `scripts\smoke_test_backend.ps1` | **PASS** | 独立端口 8799、token `smoke_test_token`：2026-10-26 收尾复跑最新一轮 PID=29608、instance=`57583eec4722`，exe 1s 内 health OK、version 0.2.0、capabilities 三工具探测存在（formchk/multiwfn/vmd 全 True）、受控退出 exit=0、端口释放、临时日志已清理（前几轮复跑 PID=26168/instance=`37eb6276b93b`、pid=27412/instance=`1163f0c98e60`、pid=3660/instance=`e9b14b7e751c`、pid=15824/instance=`1d47d658ae15`、pid=22240/instance=`7035f71e1382`、pid=26776/instance=`8f2d97050916`；本轮沿用项目自带脚本，未另造矛盾 smoke） |

### 3.2 DSH managed lifecycle（L4，对话内真实状态机）

| 编号 | 检查项 | 结果 | 备注 |
|------|--------|------|------|
| M1 | managed spawn：无已有 backend → DSH 拉起 → health ready → owned=true；cwd 合法字符串；stdout/stderr=inherit；提前退出可检测；health 成功进 ready | **NOT RUN** | 复核时刻 DSH 未运行；10-22 R15b 曾在旧布局实机观察到 spawn→ready 与状态卡渲染（历史证据，不等同本轮新布局复跑） |
| M2 | external reuse：插件启动前 backend 已存在 → probe 成功 → reuse → owned=false；dispose 后不关闭外部 backend | **NOT RUN** | 需在 DSH 对话内手动先起后端再启动插件观察 |
| M3 | 自己启动的 backend 正常 dispose：先受控 HTTP shutdown → `waitForExit()===true` 才确认退出并清 ownership；不以 Promise/handle 存在当退出状态 | **NOT RUN** | 源码规则在位（`src/index.js` BackendManager dispose 路径），未现场观察 |
| M4 | 未确认退出：shutdown+terminate 后仍不能确认退出 → 保留 handle、保持 owned、标记 orphan，不伪造 stopped | **NOT RUN** | 源码规则在位（R6 闭环），未现场观察 |
| M5 | dispose/start race：backend 刚 ready 时插件同时 dispose；`_waitReady` disposed 分支走受控 stop；不出现 owned=true + handle=null 不一致终态 | **NOT RUN** | 源码规则在位（N7/R6 闭环），未现场观察 |
| M6 | managed 模式不主动杀 Gaussian 进程树；优先受控关闭 | **NOT RUN** | 策略在位；Windows Job Object 强制脱离无法纯静态证明，按既定口径不作为 blocker |

### 3.3 Gaussian 严格串行实机（L4 + 化学链）

| 编号 | 检查项 | 结果 | 备注 |
|------|--------|------|------|
| G1 | 第一任务可提交；running 时第二个 Gaussian 被拒绝/阻塞；第一任务结束 lease 释放；第二任务随后可提交 | **NOT RUN** | 本轮未提交新 Gaussian 任务；10-21 历史测试 log（`he_serial_*`、`h2o_second_*` 等 12 份 Error termination 小文件）为历史排障痕迹，非本轮复跑证据 |
| G2 | completed/failed 状态符合最终 Gaussian termination；stop 运行中任务后状态、lease、PID 跟踪正确 | **NOT RUN** | 本轮未现场 stop；源码三态规则在位（见 §3.6） |
| G3 | backend 重启后 Gaussian 仍运行可经持久化信息重新接管（adopt + acquire） | **NOT RUN** | 源码规则在位（`job_manager.py` L338-358），未现场观察 |
| G4 | PID 身份三态：alive+instance=True → 原任务仍运行；alive+instance=False → 视为已结束，不把复用 PID 当 Gaussian；alive+instance=None → 身份不可判定，保守视为运行、继续占 lease；不因身份不可判定放行第二个 Gaussian | **NOT RUN** | 源码规则在位（`job_manager.py` L170-193、L338-358）；本轮不人为制造系统级 PID 复用实验，实机只验证正常 True 路径的计划未执行 |

### 3.4 重启恢复与 recover 状态机（L4）

| 编号 | 检查项 | 结果 | 备注 |
|------|--------|------|------|
| R1 | running 主记录 + 同实例 → adopt + acquire | **NOT RUN** | 源码在位（L338-352） |
| R2 | pending 主记录 + recover → 补齐 PID 后接管 | **NOT RUN** | 源码在位（R5 闭环） |
| R3 | 仅 recover 极端场景 → 恢复最小 running 信息 | **NOT RUN** | 源码在位（R5 闭环） |
| R4 | terminal 主记录 + stale recover → 保持终态、只清 recover；stale recover 不复活终态任务 | **NOT RUN** | 源码在位（L400 主记录永远优先） |
| R5 | 正常 save 成功后 recover 不长期残留；`has_running()` / `get_job()` / `reconcile()` / `stop_job()` 对同一任务状态一致 | **NOT RUN** | 本轮未重启后端观察持久化层 |

### 3.5 真实化学工具链 smoke（仅当程序真实存在时执行；本轮未现场复跑端到端）

| 编号 | 检查项 | 结果 | 证据 / 备注 |
|------|--------|------|-------------|
| C1 | Gaussian 输出解析：method、final energy、Normal/Error termination、HOMO/LUMO 与测试任务 log 字段对应（只验字段对应，不宣称化学正确性） | **PASS（历史产物复核）** | 直接 import 后端 `parse_gaussian_log` / `output_to_dict` 复现三份本会话 log，数值见 §3.6 |
| C2 | Multiwfn：capabilities 探测到真实版本（3.8）、非硬编码；菜单/profile 与实际安装版本匹配 | **PASS（L2 探测）** | 真实抓 banner 返回 3.8、matched=true；本轮未现场 spawn Multiwfn 跑新任务 |
| C3 | cube：生成后实际读取 header（nx×ny×nz）；超出上限拒绝 | **PASS（历史产物复核）** | 6 个已登记 cube 网格头全部合规，见 §3.6；上限 16,000,000；本轮未新生成 cube |
| C4 | VMD：真实渲染产物存在且非空；Pillow 可用时验证图片实际解码 | **PASS（历史产物复核）** | 4 张 PNG 512×512 经 Pillow 解码 OK；TGA 为 VMD 中间产物不登记、不伪装成 PNG；本轮未新跑 VMD 渲染 |
| C5 | 端到端链：Gaussian → chk → formchk → fchk → Multiwfn → cube/分析产物 → VMD → 最终图片/文件 | **NOT RUN** | 本轮未现场复跑完整链路；10-23 water.fchk 与 10-24 苯任务为历史后端侧实物证据（§3.6） |
| C6 | Sobko 知识库：`/v1/sobko/status` 探测（configured / mode / run_script_exists / running / start_error）；对话内 `sobko_search` / `sobko_fetch` 真实检索与返回 | **状态探测 PASS；在线检索 NOT RUN** | B3/B8 已验 status 200、`configured=true`、`mode=bm25_only`、`running=false`、`start_error=null`；本轮未在 DSH 对话内实调 `sobko_search` / `sobko_fetch`（会话审计两项均未被调用，见 §3.7），不写成检索通过 |

### 3.6 历史产物复核明细（本轮只读复跑，未提交新计算）

**A. 三个 Gaussian 任务记录（`C:\Users\Administrator\.gaussian-dsh\jobs\*.json`，全部 completed、error=null、pid + pid_start_time 在位）**

| Job ID | 体系 / 方法 | gjf | log | chk | 解析复现（后端规则口径） |
|--------|-------------|-----|-----|-----|--------------------------|
| `67f4b8f183fa` | 苯 `c1ccccc1` opt B3LYP/6-31G(d,p) | 766 B | 67,424 B | 1,974,272 B | method=B3LYP；final_energy=`-232.258201851`；HOMO=-0.24688；LUMO=0.0026；gap=0.24948；Normal termination；opt_converged=true；stationary_point=true；12 原子、120 基函数；dipole=0.0（苯对称）；末条 SCF 5 cycles |
| `29d5fbd36387` | 水 sp B3LYP/6-31G(d,p) | 320 B | 12,964 B | 667,648 B | method=B3LYP；final_energy=`-76.4196224301`；HOMO=-0.29228；LUMO=0.06755；gap=0.35983；Normal；3 原子、25 基函数；dipole=2.0298；9 cycles |
| `853cf885352f` | h2o_test HF | 136 B | 21,926 B | 659,456 B | method=HF；final_energy=`-76.0105049953`；HOMO=-0.49788；LUMO=0.21062；gap=0.7085；Normal；3 原子、19 基函数；dipole=2.226；10 cycles |

> LUMO 归属口径：后端 `gaussian_output.py` L173-198 取**最后一个 Alpha occ 块末值为 HOMO**，再取该块**之后**首个 virt 块第一根为 LUMO。苯 log 末 occ 之后 following[0] = `[0.00260, 0.00260, 0.09108, …]`（0.00260 简并），故 LUMO=0.0026；临时脚本若取"全文第一个 virt 块"会得到 0.00296，那是脚本口径错误，非后端缺陷。终态无 virtual 时 LUMO 保持 None，不回退前一步。

**B. 三个后处理任务（`C:\Users\Administrator\.gaussian-dsh\postprocess\*.json`，全部 completed、error=null）**

| Task ID | 类型 | 登记产物 | 大小 / 网格 / 解码复核 |
|---------|------|----------|--------------------------|
| `77192b693136` | orbitals（苯） | `orb000005.cub`、`orb000006.cub`、`orbital_0.png`、`orbital_1.png` | cube 各 7,626,560 B，73×91×80=531,440 点；PNG 30,543 B / 39,593 B，512×512 Pillow 解码 OK |
| `8139f6082f25` | ESP（水） | `water…_density.cub`、`water…_totesp.cub`、`esp_surface.png` | cube 各 7,626,560 B，73×91×80；PNG 45,646 B，512×512 解码 OK；未登记中间产物 `esp_surface.tga`（786,450 B，VMD 中间产物，设计如此） |
| `740be6e61356` | RDG/NCI | `func1.cub`、`func2.cub`、`rdg_nci.png` | cube 各 7,721,844 B，59×114×80=538,080 点；PNG 6,497 B，512×512 解码 OK；未登记 TGA 与 Multiwfn/VMD 日志、commands.txt |

**C. 离线契约（L1，本轮复跑）**

| 检查项 | 结果 | 证据 |
|--------|------|------|
| toolkit manifest 校验（`verify_plugin_manifest.mjs --pkg "@gd/gp" --profile <web> --id gaussian`） | **PASS** | bundles 26 项含 `@gd/gp`（第 10 位）；manifest 解析到 junction 目标；bundle.patch 存在；`dsh.client.platform=web`、inject 两项；main/client 在位；Host shape `name=gaussian-dsh`、`inject=["tools","systemPrompt"]`、`apply=function` |
| installed runtime 8 项（`verify_installed_runtime.mjs`） | **PASS** | runtimes 目录、runtime.json（0.2.0 / win32-x64）、exe 路径长度 148<260、exe 存在、sha256 一致、manifest 条目命中、pydantic_core `__init__.py`/`core_schema.py`/`py.typed` + `_pydantic_core.cp313-win_amd64.pyd` 全 PASS |
| profile bundle 校验（`verify_profile_bundle.mjs`，默认新布局 web，可用 `DSH_PROFILE_DIR` 覆盖） | **PASS** | bundles 26 项含 `@gd/gp`；patch 无 gaussian disabled 残留；manifest bundle.patch / platform=web / inject / client.js / main 全部在位；本轮已把脚本默认 profile 从旧布局 `.dsh\profiles\desktop` 改为新布局 web，备份 `scripts\verify_profile_bundle.mjs.bak_20261026` |
| plugin shape 校验（`verify_plugin_shape.mjs`，本轮已参数化路径） | **PASS** | `plugin.name=gaussian-dsh`、`inject=["tools","systemPrompt"]`、`apply=function` |
| 工具契约自测（`output_contract_check.mjs`） | **PASS 19/19** | 19 个工具全部满足 output `{schema, render, presentationMeta?}` + parameters object-root；无失败工具 |
| 提示词工具清单对齐（K9 差集） | **PASS** | 注册 19 名 = `GAUSSIAN_GUIDANCE` 列出 19 名 = README 工具表 19 名；注册未进提示词：无；提示词多出未注册：无 |
| 两份快照 `lib/index.js`、`lib/client.js` `node --check` | **PASS** | exit=0（项目根 + generation shim 四个 JS 文件全部语法合法）；profile/generation `package.json` JSON.parse 合法；`runtime.json` 带 UTF-8 BOM（EF BB BF，项目根与 shim 一致），裸 `JSON.parse` 会报 BOM 错，加载器 `src/index.js` L37 与 `verify_installed_runtime.mjs` L22 均先 `.replace(/^\uFEFF/, '')` 再解析（R15 已闭环，非新缺陷） |

### 3.7 会话审计（`docs\_verify\session_b1bc3e92.jsonl`，2026-10-24 会话，只读复跑）

- 19 个 GP 工具名在会话文本中 **19/19 全部出现**（注册可见）。
- 会话内模型实际调用 GP 工具 **10/19**：`gaussian_status`×2、`postprocess_capabilities`×2、`search_basis_sets`×1、`generate_gaussian_input_from_smiles`×1、`extract_structure_from_file`×1、`list_gaussian_jobs`×1、`list_postprocess_tasks`×1、`submit_gaussian_job`×1、`get_gaussian_job`×1、`parse_gaussian_output`×1；全部返回 OK、零失败。
- 未被本会话实调的 9 个：`create_postprocess_task`、`diagnose_gaussian_error`、`generate_gaussian_input`、`get_basis_set`、`get_postprocess_task`、`search_gaussian_keywords`、`sobko_fetch`、`sobko_search`、`stop_gaussian_job`。其中三个 postprocess 任务由 10-23 会话提交，不在本 jsonl 内。
- 11 次 `pwsh` 退出码 `3221225794`（0xC0000142）全部发生在 `workspace-write` 受限档位（turn 2/4/5/7/8/9）；L331 切 `danger-full-access`、L332 sandbox mode 切换。其余报错归属内置 `ops_bash` / `read` / `write` / `glob` / `job_output` / `win_bash` / `compress` / `cg` 等 R17 排障临时动作（中文乱码、PermissionError、FileNotFoundError、旧快照 pydantic_core 缺失、rdkit DLL、junction 命令行报错、路径不存在等历史排障痕迹），**不属于 19 个 GP 工具**。

---

## 4. 新发现问题（本轮复核记录）

> 未发现新的 **Blocker** 或 **Major**。以下为 Minor / 历史既有项，按格式记录。

### Minor-1 ｜快照 `lib\client.js` 落后项目根 1 行（旧 ModuleLoader id 残留）

- **位置**：generation shim `node_modules\@gd\gp\lib\client.js`（`B8A38D8D28F5A97A`，7,376 B，10-24 17:06:29）vs 项目根 `lib\client.js`（`CFA2CEB802FFB9EC`，7,353 B，10-24 20:09:42）。
- **问题**：唯一差异为 L4 `__ModuleLoader__.load({ id: … })` 字符串——快照仍用旧包名 `@gaussian/dsh-plugin-gaussian`，项目根已改为 `@gd/gp`；其余 191 行逐字相同。
- **定性（已通读 DSH 框架源码 `@deepseek-ai/dsh-client-modules/lib/index.js` 与 `lib/client.js`）**：host bundle 匹配按 **packageName**（`clientExportOf(packageName, exports)`、多来源按 packageName 去重抛错，L748 / L911–915），与 client.js 内 `__ModuleLoader__.load({id, factory})` 的 id 无关；该 id 仅作浏览器模块 `loadCache` 记忆化键与外部 require 解析键（L435 `rowsById.set(entry.id, entry)`、L445 按名查找）。本插件 client 内只 `require2("react")`，不 require 自身包名；本机无第二个模块使用该旧 id，不存在 R12b 类重复 factory 覆盖。浏览器真正生效的槽位 `id:"gaussian"`（order 75）与 locale namespace `"gaussian.status"` 在两份 client.js 中一致。
- **影响**：无功能阻断、无冲突方；属一致性瑕疵。
- **建议**：下次前端 `node scripts/build.mjs` 后，把项目根 `lib\client.js` 同步覆盖到 generation shim 与 web junction，消除旧字符串；不需要改业务逻辑。

### Minor-2 ｜generation `source\` 副本混入 R16 旧 `acceptance_bundle.zip` 与整包第三方目录

- **位置**：`profiles\.generations\live\@gd+gp+0.2.0\source\gaussian+dsh-plugin-gaussian\`（整包复制快照，含 `acceptance_bundle.zip`、`thirdparty\openbabel\`、`backend\` 等）。
- **问题**：DSH 实际读取 shim `node_modules\@gd\gp\`，`source\` 副本仅作溯源留档；其中旧 zip 为 R16 口径，不代表当前源码。
- **影响**：不参与运行，仅占用磁盘、可能造成"包内是否最新"的误读。
- **建议**：下次重建 generation 时按打包清单排除 `acceptance_bundle.zip`、`docs\_verify*`、`backups_*`、`dist\`、`__pycache__`；本轮不删除历史副本。

### Minor-3 ｜README 安装方式 A/B 描述与本地 `file:` 现状不一致（本轮已闭环）

- **位置**：`README.md` 安装章节（复核前 L52–59）。
- **问题**：复核前方式 A 写"从 DSH 插件市场搜索 `@gd/gp` 安装、后端首次启动自动从 GitHub Release 下载预编译包"，方式 B 写"下载 Releases zip"；当前实际为本地 `file:` / generation link 安装，未发布 npm registry、未建 GitHub Release、后端 exe 随包 onedir 携带，不存在"首次启动自动下载"链路。
- **本轮处理**：README 已回填——方式 A/B 标注"规划中，当前不可用"；新增方式 C 本地目录安装（当前实际形态）与方式 D 源码调试运行；配置表拆成前端插件层（6 个 env）与后端层（18 个 env，含 `OBABEL_EXE`）两张，变量名对齐 `src/index.js` 与 `backend/config.py` 实测；工具表补入 `sobko_search` / `sobko_fetch`，注明共 19 个工具。
- **影响**：文档误导风险已消除；不影响本机运行。
- **建议**：待真正发布 registry / Release 后再回填方式 A/B 实机步骤。

### Minor-4 ｜GJF 校验失败与串行拒绝返回 HTTP 200 + `{ok:false}`（历史既有，非本轮新缺陷）

- **位置**：`backend\job_manager.py` L446–480（内存 hard guard L448–457、has_running 串行拒绝 L460–461、GJF 校验失败 L470–474、lease 忙 L477–480）、`backend\gaussian_input.py` L242–315。
- **问题**：校验失败、lease 忙、内存 hard guard 均返回 HTTP 200 + `{ok:false,error:…}`，未使用 422（参数语义错误）或 409（资源冲突）状态码。
- **影响**：前端按 `ok` 字段判断即可工作；HTTP 语义不够规范，不阻断功能。
- **建议**：后续版本可把参数校验失败映射 422、lease 忙映射 409；本轮不改动已闭环接口契约。

### Minor-5 ｜P2-1 遗留：后处理 PNG 经 client 侧回显用户的方案未闭环

- **位置**：`docs\P1_P3_P2-1_FIX_20261023.md` L58（文件共 58 行，P2-1 遗留条目在末段 L58；L57 为 water.fchk 三者端到端完成记录）。
- **问题**：`create_postprocess_task` 工具已存在，渲染出的 PNG 如何在 DSH 对话内回显给用户（路径访问 / 内嵌 base64 / 卡片渲染）尚未在 client 侧确认。
- **影响**：用户拿到 task_id 后需自行到产物目录看图；不影响后端出图正确性。
- **建议**：L4 实机 smoke 时一并确认回显路径；必要时在 client 状态卡或工具 render 投影中登记产物相对路径。

### Minor-6 ｜ README 后端 env 表未列 8 个内部调优项（文档完整性，非功能缺陷）

- **位置**：`README.md` L101–121 后端层配置表；`backend\config.py` L45–80。
- **问题**：表内 18 个变量名与默认值已与 `config.py` 实测一致（含 `OBABEL_EXE`）；另有 8 个内部调优环境变量未列入：`SOBKO_PYTHON_EXE`（L45，None）、`BSE_API_BASE`（L47，BSE 在线端点）、`MULTIWFN_THREADS`（L57，2）、`BACKEND_RSS_SOFT_MB`（L63，1024）、`BACKEND_RSS_HARD_MB`（L64，1800）、`GC_CUBE_TTL_DAYS`（L74，7）、`GC_IMAGE_TTL_DAYS`（L75，30）、`GC_LOG_TTL_DAYS`（L76，30）。
- **影响**：默认值已内置、本机运行无需配置；不列出只影响高级用户调优可发现性，不阻断功能。
- **建议**：下一版 README 在后端表末尾补一节"内部调优项（一般无需修改）"收录这 8 个变量与默认值；本轮不改 README。

### 历史既有项（勿重复排查，本轮确认仍在位）

- one-file 模式未实现（设计如此，非缺陷，不擅自实现）。
- `scripts\build_backend.ps1` 中文注释在 pwsh 7 解析失败（历史 Minor；本机实际用 System32 PowerShell 5.1 构建）。
- `scripts\smoke_test_backend.ps1` 日志清理句柄存在时序竞态（不影响退出码判定）。
- 后端日志目录 `C:\Users\Administrator\.gaussian-dsh\logs\` 为空属设计行为：managed spawn `stdio: {stdin:"ignore", stdout:"inherit", stderr:"inherit"}`，后端 stdout/stderr 继承挂到 DSH 宿主进程输出；`app.py` logger 无 FileHandler、只走 stderr。
- 本机未装 PowerShell 7（`pwsh` 命令 CommandNotFound 属预期）；DSH 执行器设计内回退 System32 5.1；系统本体健康须用 5.1 / cmd 独立启动 `echo hello` exitCode=0 证明。
- 临时复现脚本必须 `.cjs` / `.py` 后缀（项目 `type:module`）。

---

## 5. 未验证事项（本轮未执行，不得在对外口径中写成 PASS）

### 5.1 DSH 对话内生命周期（L4，需完全退出重启 DSH 后在新对话观察）

1. managed spawn→ready、owned=true、cwd 字符串合法、stdout/stderr=inherit、提前退出检测、ready 状态进入（M1）。
2. external reuse→owned=false、dispose 不关闭外部 backend（M2）。
3. 受控 dispose：`waitForExit()===true` 才清 ownership（M3）。
4. orphan：未确认退出时保留 handle、保持 owned、标记 orphan、不伪造 stopped（M4）。
5. dispose/start race：`_waitReady` disposed 分支受控 stop，无 owned=true + handle=null 终态（M5）。
6. 状态卡在新布局浏览器内真实渲染：标题/描述、host snapshot 字段（state/version/mode/owned/ready/baseUrl/dataDir/error/backend）、retry 按钮、同源 `/api/gaussian/status` 与 `/api/gaussian/retry` 路由。
7. 新开对话内 19 个工具对模型可见并可被主动调用（本轮会话仅实调 10 个，其余 9 个未在本会话触发）。
8. retry 按钮在 host 侧触发幂等 `manager.start(subprocessService)`。

### 5.2 Gaussian 串行 / 状态机 / 恢复（L4 + 持久化层）

1. 双任务串行：第一任务 running 时第二个被拒绝；结束 lease 释放；第二个随后可提交（G1）。
2. stop 运行中任务后的状态、lease、PID 跟踪闭环（G2）。
3. backend 重启后运行中 Gaussian 的 adopt + acquire 接管（G3）。
4. PID 三态实机路径：正常 True 路径；False / None 分支优先用已有隔离测试覆盖，不人为制造系统级 PID 复用实验（G4）。
5. running 主记录 adopt、pending+recover 补齐 PID、仅 recover 最小恢复、terminal+stale recover 保持终态不复活、save 成功后 recover 不残留；`has_running()` / `get_job()` / `reconcile()` / `stop_job()` 同任务状态一致（R1–R5）。

### 5.3 化学工具链新一轮端到端

1. 新任务完整链路：Gaussian → chk → formchk → fchk → Multiwfn → cube / 分析产物 → VMD → 最终 PNG（C5）。
2. 本轮未现场 spawn Multiwfn / VMD 跑新任务；capabilities 探测 exists=true 与历史产物合规不等于新一轮端到端通过。
3. Sobko 在线检索（`sobko_search` / `sobko_fetch`）在 DSH 对话内真实调用与返回（当前仅 `bm25_only` 状态探测 PASS）。

### 5.4 环境与遗留决策项

1. 旧布局目录 `C:\Users\Administrator\.dsh\` 是否清理：当前 DSH 不读取，属历史遗留；`profiles\` 下含 `desktop`、`web`、`acp`、`headless` 四个旧 profile，顶层另有 `aifs`、`attachments`、`cache`、`dsh-runtimes`、`llm-deepseek`、`logs`、`redteam`、`sessions`、`skills`、`storages`；清理前需用户确认，本轮不擅自删除。
2. `%APPDATA%\dsh-desktop\harness\profiles\desktop-safe-mode\` 为 10-24 两次崩溃期间 DSH 自动进入的恢复模式产物（新 harness 内独立 profile，dependencies 为空、bundles 仅官方 `@deepseek-ai/dsh-base`、`@deepseek-ai/dsh-web-app` 两条），与最终态 `web` profile 无关；是否清理待用户决策（它不属于第 1 条的旧 `.dsh` 目录）。
3. 10-24 21:25:07 后端 probe 失败是冷启动时序还是启动失败，待新一轮 L4 实机结合 DSH 宿主日志判定；21:42–21:43 苯任务成功已间接证明后端随后拉起。

---

## 6. 发布动作

### 6.1 最终发布产物口径

- **当前可交付的代码与运行框架**：项目根 `E:\YDW\ChemDatas\gaussian-dsh-plugin\`，含前端 `lib\`、后端 onedir `runtimes\win32-x64\gaussian-backend\` + `runtime.json`、后端 `backend\`、源码 `src\`、配置 `cordis.patch.yml`、`package.json`。
- **DSH 实际加载位置**：`%APPDATA%\dsh-desktop\harness\profiles\.generations\live\@gd+gp+0.2.0\node_modules\@gd\gp\`（经 web profile Junction 联接）；本轮四项离线校验 + 8 项 runtime 校验均从该真实入口取证 PASS。
- **旧 `acceptance_bundle.zip`（R16，2026-10-22）已过期**：10-23 P1/P3/P2-1、10-24 改名 `@gd/gp` 与新布局迁移后未重打，**不得作为当前发布包交付**。

### 6.2 是否需要替换旧 runtime

- 后端 exe 已是 10-24 19:56:02 构建版本（含 10-23 全部修复），`runtime.json` SHA-256 自洽；本轮 L2 smoke 用部署路径 exe 独立启动 34/34 PASS，**无需再替换 runtime**。
- 前端 `lib\client.js` 按 §4 Minor-1 建议下次构建后同步快照即可；`lib\index.js` 快照与项目根已一致。

### 6.3 是否可以打 tag / release

- **当前不建议对外打 tag / 发 Release**：L4 DSH 对话内生命周期、新布局状态卡渲染、新一轮化学链端到端尚未在本轮现场观察（§5）。
- 内部可按 `v0.2.0-local` 口径冻结当前源码；待 §5.1 / §5.2 / §5.3 在目标机器补完 smoke 且无新 Blocker/Major 后，再：
  1. `node scripts/build.mjs` 重打前端 `lib\` 并同步 generation shim；
  2. 按需重打 onedir（本轮后端无改动，可不重打）；
  3. 用 `scripts\make_acceptance_bundle.ps1` 重打交付包，跑 L3 leak 复核 + 解压回读抽查；
  4. 再打 tag / 发 Release。

### 6.4 必须完成的剩余步骤（转 READY 前置条件）

1. 完全退出 DSH（托盘退出、进程结束，不是关窗口），重新打开 `web` profile；先复查 `dsh.profile.bundles` 未被崩溃恢复批量摘除。
2. 新开对话，观察状态卡渲染与 19 个工具可见性；实调至少覆盖 `gaussian_status`、`submit_gaussian_job`、`get_gaussian_job`、`parse_gaussian_output`、`postprocess_capabilities`、`create_postprocess_task`、`get_postprocess_task`、`sobko_search`、`stop_gaussian_job`、`diagnose_gaussian_error` 等本轮未实调项。
3. 跑一个极小合法测试任务（如水 HF/6-31G(d) 单点），观察串行拒绝、lease 释放、stop 路径、重启接管。
4. 跑通一轮真实化学链（Gaussian → formchk → Multiwfn → VMD → PNG），核对产物落位与回显。
5. 补 external reuse / controlled dispose / orphan / race 四项生命周期观察记录，回填本报告 §3.2 / §3.4。

### 6.5 本轮未改动清单（回滚边界）

**未改动（业务与运行态，回滚零风险）：**

- 未改动任何业务源码（`src/`、`backend/`）、构建产物 `lib/`、后端 onedir `runtimes/`、DSH profile 配置与用户环境变量。
- 未提交任何新 Gaussian / Multiwfn / VMD 真实计算任务；本轮两轮 smoke 由校验脚本在独立端口内受控拉起后端、跑测后受控 `waitForExit()` 退出，复核时刻三端口已释放、`gaussian-backend` 无残留进程。

**本轮仅改动文档与校验脚本（备份在 `docs\backups_20261026\`，脚本同目录 `.bak_20261026`）：**

- 校验脚本：`scripts\verify_plugin_shape.mjs`（旧版备份 `scripts\verify_plugin_shape.mjs.bak_20261026`，路径改为 `DSH_PROFILE_DIR` 参数化、默认新布局 web）；`scripts\verify_profile_bundle.mjs`（备份 `scripts\verify_profile_bundle.mjs.bak_20261026`，默认 profile 由旧布局 `.dsh\profiles\desktop` 改为新布局 `%APPDATA%\dsh-desktop\harness\profiles\web`，`DSH_PROFILE_DIR` 可覆盖）；通用技能 `dsh-plugin-toolkit\scripts\verify_plugin_manifest.mjs`（备份同名 `.bak_20261026`，默认 profile 同步改为新布局 web，注释补 `--id` 用法）；`docs\_verify\session_audit_20261026.py`（旧 18 工具口径备份 `.bak-18tool`）。三个 mjs 改后均用系统 `node` 复跑 PASS。
- 项目文档：`README.md`（工具表 19 个、安装方式 A/B/C/D、前后端两张配置表）；`docs\STATUS.md`、`docs\PLAN.md`、`docs\RELEASE_READINESS_REPORT.md`、`docs\DSH_ARCHITECTURE.md`、`docs\R17_DIAGNOSIS_20261022.md` 头部追加 R17c 指针（历史口径保留不覆盖）；`docs\LESSONS_LEARNED.md` 追加第 39–43 条（第 43 条为本轮复核补记的 git 基线取证纪律）；`docs\PLUGIN_AUTHORING_WORKFLOW.md` 修正 client ModuleLoader id 定性与 generationId 口径（备份 `docs\backups_20261026\PLUGIN_AUTHORING_WORKFLOW.md.bak_20261026`；该文件被 git 跟踪，HEAD 亦为回滚点）。
- 通用技能：`.user_skills\dsh-plugin-toolkit\SKILL.md`（新布局三层模型、K1–K17、4.0/4.1/4.5 流程、脚本 `--id` 参数、Scope 版本口径；K17 为 git 基线取证纪律；备份 `SKILL.md.bak_20261026` 与项目 `docs\backups_20261026\dsh-plugin-toolkit.SKILL.md.bak_20261026`）。
- 系统资产清单：`E:\YDW\AI_Study\docs\05-系统环境与工具栈.md`（插件段 R17c 复核结论含 git HEAD 基线、技能段 K1–K17 与新布局路径；备份 `05-系统环境与工具栈.md.bak_20261026_preK17`）。
- 本轮新增取证脚本位于 `docs\_verify\`（`smoke_extended_20261026.py`、`verify_artifacts_20261026.py`、`parse_replay_20261026.py`、`session_audit_20261026.py`、`toolset_audit_20261026.py`、`json_check_20261026.cjs`、`count_readme_env.cjs`、`env_set_diff.cjs`），属复核中间产物，不进交付包。
- 本报告自身修订：r3/r4/r5 备份 `…bak_20261026_r3`、`…r4`、`…r5`（`docs\backups_20261026\`）；终态复跑后把 B1 证据刷新为本轮最新一轮扩展 smoke（pid=26472、instance=`93ef6f31c3e4`、uptime=0.6s）、B11 刷新为本轮项目自带 smoke（PID=29608、instance=`57583eec4722`），旧 pid/instance 归入历史注记；Minor-4 内存 guard/串行拒绝/GJF 校验/lease 忙的行号区间由 `L470–480` 勘误为 `job_manager.py L446–480`；Minor-5 遗留条目行号由 L59 勘误为 L58（文件共 58 行，L57 为 water.fchk 完成记录）；§2.3 `disabled: false` 口径由"12 处"勘误为真实配置 10 处 + 2 行注释提及；§5.4 把 `desktop-safe-mode` 归属由"旧布局"勘误为新 harness `profiles\` 下独立恢复 profile；以上均为文档证据与行号口径更新，未改任何业务源码。终态复跑：四个离线契约脚本、output 契约 19/19、toolset 差集为空、扩展 smoke 34/34、项目自带 smoke PASS、parse_replay 三份 log 口径一致、session_audit 19/19 出现且 GP 实调 10/19、四个 `lib/*.js` `node --check` 全 exit=0、三份 JSON（两份 `package.json` + 剥 BOM 后 `runtime.json`）均可解析。

---

## 附录 A. 本轮复跑脚本与证据索引

| 脚本 / 命令 | 作用 | 结果 |
|-------------|------|------|
| `docs\_verify\output_contract_check.mjs` | 19 工具 output/parameters 契约离线自测 | 19/19 PASS |
| `docs\_verify\smoke_extended_20261026.py` | 独立端口 8792 后端扩展 smoke 34 项 | 34/34 PASS |
| `scripts\smoke_test_backend.ps1` | 项目自带后端 smoke（端口 8799） | PASS |
| `docs\_verify\verify_artifacts_20261026.py` | 3 jobs + 3 postprocess 实物大小 / PNG 解码 / cube 网格头 | 全 PASS，无 FAIL |
| `docs\_verify\parse_replay_20261026.py` | import 后端解析器复现三份 log 字段 | 与 §3.6 数值一致 |
| `docs\_verify\session_audit_20261026.py` | 19 工具名出现 / 实调集合 / 非 GP 失败归属 | 19/19 出现，GP 实调 10/19，无 GP 失败 |
| `docs\_verify\toolset_audit_20261026.py` | 注册集合 vs 提示词集合差集 + 会话出现计数 | 差集为空，19/19 出现 |
| `docs\_verify\json_check_20261026.cjs` | 项目根 / web 两份 `package.json` 与剥 BOM 后 `runtime.json` 解析与版本号一致性 | exit=0，三处版本均 `0.2.0` |
| `…/dsh-plugin-toolkit/scripts/verify_plugin_manifest.mjs` | 通用 manifest 离线校验（默认新布局 web；`--pkg @gd/gp --id gaussian`，entry id ≠ 包名时显式传 `--id`） | PASS |
| `scripts\verify_installed_runtime.mjs` | 从 DSH 真实入口自定位校验 8 项 | PASS，exe sha256 与 runtime.json 记录一致 |
| `scripts\verify_profile_bundle.mjs` | profile bundle + manifest 解析链校验（默认新布局 web，`DSH_PROFILE_DIR` 可覆盖） | PASS |
| `scripts\verify_plugin_shape.mjs` | Host 对象 name/inject/apply 形状校验（`DSH_PROFILE_DIR` 可覆盖） | PASS |
| `docs\_verify\env_set_diff.cjs` + `count_readme_env.cjs` | README 前后端 env 表变量名与 `config.py` 读取项集合对照（辅助参考；脚本正则对合并行 `HOST/PORT` 与特殊默认列 `OBABEL_EXE` 解析有偏差，终值以人工清点为准：后端表 18 项、未列 8 项） | 后端表 18 项一致、未列 8 项，差集已人工复核 |

> `docs\_verify\` 目录内另有 R16/R17 排障遗留旧脚本，本轮取证结论只以上表 7 个脚本为准，旧脚本勿复用：`parse_session.py`、`parse_session2.py`（callId 关联有 bug）、`artifacts_check.py`（第一版 cube 偏移错误）、`cube_and_log_check.py`（已修正版）、`parse_session3.py`、`parse_session4.py`（正确分组解析）、`lumo_trace.py`（轨迹辅助）；其余 `asar_*.py`、`backend_offline_smoke.py`、`normalize_bom.py`、`reconcile_bundles.mjs`、`repro_spawn_pwsh.cjs`、`schema_inspect.mjs` 同属历史排障痕迹。

## 附录 B. 本机工具链探测口径（L2 实测）

| 程序 | 路径 | 探测结果 |
|------|------|----------|
| Gaussian 16 Rev A.03 | `D:\G16W\g16.exe` | exists=true |
| formchk | `D:\G16W\formchk.exe` | exists=true |
| Multiwfn 3.8 | `D:\Multiwfn\Multiwfn_3.8_bin_Win64\Multiwfn.exe` | exists=true，banner 实测版本 3.8，`version_matched=true` |
| VMD 1.9.3 | `D:\VMD\vmd.exe` | exists=true |
| Sobko KB | `E:\YDW\Trae_Sob\Sobko_MCP_project-main` | configured=true，mode=bm25_only，run_script_exists=true，running=false，start_error=null |
| 资源预算 | 默认 mem=12GB、nproc=8、max_atoms=300、max_grid_points=16,000,000 | 与 `backend\config.py` 默认值一致 |
