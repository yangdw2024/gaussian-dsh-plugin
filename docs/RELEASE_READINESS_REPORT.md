# Release Readiness Report — gaussian-dsh-plugin v0.2.0

日期：2026-10-22（R16 复核：工具 function schema parameters 编译为 object-root，离线四项全 PASS；R15b 实机启动态 PASS，剩余生命周期与化学链 NOT RUN）｜ 构建机：Windows（AMD Ryzen 7 9700X / RTX 5060 Ti）｜ Python 3.13.13（D 盘 miniconda3）｜ PyInstaller 6.21.0

> 本报告只记录本轮**实际执行过**的验证；未执行的外部程序/实机项一律标 NOT RUN，不写成 PASS。静态代码闭环结论见 `FIX_REPORT_20261020.md`、`LESSONS_LEARNED.md`、`DSH_ARCHITECTURE.md`。

## 1. 总体结论

**READY WITH EXTERNAL SMOKE PENDING**

后端代码、串行 lease、PID 三态状态机、GJF/输出解析与 onedir 运行框架可发布，本机已完成一次真实 Gaussian Normal termination 单点计算并正确解析；R14 补齐 18 个工具 output 三要素声明并通过离线契约自测（18/18 PASS），R14c 系统提示工具列表补齐到 18 个；R15 把状态卡从「浏览器直连后端 8765」改为 host `connection` 同源代理（`/api/gaussian/status`、`/api/gaussian/retry`），并修掉 `runtime.json` BOM 导致包内 exe 自定位失败的离线缺陷。**R16 修复对话内工具 function schema 缺陷**：模型网关报 `Invalid schema for function 'create_postprocess_task': schema must be a JSON Schema of 'type: "object"', got 'type: null'`，根因是自研 `defineTool` 把扁平参数表直接透传、`parameters` 顶层缺 `type:"object"`；工厂内复刻官方编译函数，18 个工具 `parameters` 统一编译为 `{type:"object", properties, required?}`，output 缺省为 annotation-only 任意 JSON，离线契约脚本补 parameters object-root 硬断言与递归子集白名单；重打 lib、覆盖快照哈希一致，四项离线校验全 PASS，后端零改动、不重打 onedir。本轮发布工程实测：onedir exe 在独立端口 8799 实跑 health 7s 就绪、capabilities 三工具探测存在、带 token 受控退出（PASS）；离线 TestClient 回归 6/6 PASS；后端 compileall 0 错；交付包 leak=0。**2026-10-22 完全退出重启 DSH 实机确认：managed spawn→ready 与状态卡同源渲染链路通过**——状态卡显示「可用」、版本 0.2.0、后端地址 127.0.0.1:8765、数据目录、Gaussian 路径/可用、工作目录、默认内存/核数、Sobko 状态、运行中任务全部由 host snapshot + 后端摘要渲染，bundles 未被摘除。剩余 NOT RUN：external reuse、controlled dispose 实机、orphan/dispose race、对话内 18 工具实际调用（R16 schema 修复后需完全退出重启 DSH、新开对话实调一次确认）、Multiwfn/VMD 端到端化学链（程序仅完成探测，真实 spawn 未跑）。

## 2. 构建结果

| 项 | 值 |
|----|----|
| 源码版本 | v0.2.0（`package.json` 与 `backend/app.py` version 一致） |
| 版本控制 | 非 git 仓库；以 acceptance_bundle.zip 为源码基线快照：52 条目、未压缩约 528 KB、zip 约 228 KB（精确字节以 `scripts/make_acceptance_bundle.ps1` 输出为准），leak=0，2026-10-22 R16 schema 修复与文档回填后由该脚本重打；verifier `zip-check-entries` 14/14 必含条目命中、`zip-list` 52 条目无 runtimes/lib/build/dist/node_modules/backups_/_dsh/_verify 泄漏；独立解压显式 UTF-8 回读确认包内 STATUS/RELEASE/LESSONS/PLAN/DIAGNOSIS/ARCHITECTURE/R16 文档均为最新结论 |
| 后端构建命令 | `python -m PyInstaller --clean -y --distpath dist packaging/gaussian-backend.spec`（onedir）；经 `scripts/build_backend.ps1` → `scripts/deploy_runtime.ps1` |
| 构建期处理 | 临时隐藏 pathlib-1.0.1.dist-info，finally 还原，可逆零下载；排除 Qt，收集 conda SSL DLL |
| 产物 exe | `runtimes/win32-x64/gaussian-backend/gaussian-backend.exe`，17,657,746 字节，mtime 2026-10-21 15:12:48，sha256 前 16 位 `0C28301E10C45E95`，含 R11 GJF 空行修复；R15/R16 均未改后端，无需重打 onedir |
| 部署清单 | `runtimes/win32-x64/runtime.json`（SHA256 清单，2055 条）；旧 onedir 已被此前部署覆盖，未混入旧 runtime |
| 是否最新源码 | 是。R16 只改前端工具 schema 编译层，后端未改动；R16 前端 `lib/index.js`（40,108 B）、`lib/client.js`（7,376 B）与源码 lib 一致，profile 快照已覆盖、根目录与快照 SHA256 一致，`node --check` 双文件 0 错 |
| one-file | 未实现（设计如此，非缺陷，不擅自实现） |
| 前端构建 | `node scripts/build.mjs`（esbuild，external 含 `node:url`、`node:crypto`）；`node --check` 快照两个 lib 通过；`docs/_verify/output_contract_check.mjs` 18/18 PASS（R16 起新增 parameters object-root 硬断言 + 递归子集白名单）；R15 包内 `packagedExecutable()` 离线复刻对快照 manifest 校验版本/target/sha256 通过，返回真实 exe 绝对路径且 exists=true |

## 3. Smoke Matrix

| 项 | 结果 | 证据 / 说明 |
|----|------|-------------|
| backend startup (exe) | **PASS（本轮实跑）** | `scripts/smoke_test_backend.ps1` 在独立端口 8799 拉起 onedir exe（PID 23712），7s 内 `/v1/health` 200，service=gaussian-dsh-backend，version=0.2.0，instance_id=0fd909be92b0；带 token `/v1/admin/shutdown` 受控退出，进程已结束、8799 释放，stdout/stderr 无 traceback（临时日志已清理）。8765 本轮保持空闲、未常驻 |
| health / status / jobs | **PASS（本轮离线 TestClient 6/6）** | 临时目录、`GC_ON_STARTUP=0`、不常驻：`/v1/health` 200 ok=True/service/version 齐全；`/v1/status` 200 字段 missing=[]、gaussian_exists=True；`/v1/postprocess/capabilities` 200；`/v1/jobs` 200 返回 jobs 列表；返回结构符合当前 Pydantic v2 / dataclass 模型 |
| admin auth | **PASS** | 离线 TestClient 匿名 POST `/v1/admin/shutdown` 返回 403；exe smoke 带 Bearer token 受控 shutdown 成功；CORS 仅放行回环端口与 `app://` |
| 非法 / 超资源 GJF 拒绝 | **PASS（本轮离线）** | 无坐标块、无电荷/多重度行的 GJF 提交返回 200 + `{ok:false}`，错误「未找到电荷/多重度行（格式：Charge Multiplicity，如 0 1）」，未拉起进程；301 原子上限、非法 mem/nproc fail-closed 此前已隔离验证 |
| status card connection proxy | **PASS（离线 + 2026-10-22 实机）** | R15：host `ctx.inject(["connection"])` 注册 `GET /api/gaussian/status`、`POST /api/gaussian/retry`；client 改走同源相对路径，不再直连 8765；`manager.snapshot()` 透传 host state/version/mode/owned/ready/baseUrl/dataDir/error/backend。重启 DSH 后卡片显示「可用」、版本 0.2.0、后端地址、数据目录、Gaussian 路径/可用、工作目录、默认内存/核数、Sobko 状态、运行中任务全部渲染；retry 按钮实机触发 host 幂等 start 仍待观察 |
| managed spawn（DSH 启动态） | **PASS（2026-10-22 实机）** | 完全退出重启 DSH 后后端由 managed 拉起，8765 可用、health ready、卡片 state=ready；spawn spec（argv 不经 shell、cwd 字符串、stdio inherit、graceMs）静态闭环。owned=true 标记随 ready 快照显示；reuse/dispose 语义见下行 |
| external reuse | **NOT RUN** | 需 DSH 环境；probe 成功 → owned=false、dispose 不关闭外部后端的语义已静态验收 |
| controlled dispose | **NOT RUN（后端侧 PASS）** | 后端 `/v1/admin/shutdown` 受控退出已验证；`waitForExit()===true` 才清 owned 的前端语义已静态验收，未在 DSH 实机观察 |
| orphan / dispose race | **NOT RUN** | 需 DSH 环境；`_waitReady` disposed → `_controlledStop`、不残留 owned=true+handle=null 已静态验收 |
| Gaussian serial lease | **PASS（状态机 + 实机拒绝路径）** | running 时第二个提交被拒绝（`已有 Gaussian 任务在运行`，HTTP 200 + `{ok:false}`，前端按 ok 字段判定）；终态后 lease 释放；R10 `has_running` 复用 `_finalize_if_dead` 三态，PID 复用/不可判定均不释放 |
| Gaussian 真实拉起 | **PASS** | g16.exe 子进程真实启动（H2O 任务 pid 12976，工作目录 `E:\YDW\ChemDatas\Gjf`） |
| Gaussian 正常完成解析 | **PASS** | Job `29d5fbd36387`，B3LYP/6-31G(d,p)，`Normal termination`，Elapsed 1.8s，status=completed；E(RB3LYP)=−76.4196224301 Ha，HOMO −0.29228 Ha(−7.953 eV，B1 轨道5)，LUMO +0.06755 Ha(+1.838 eV)，gap 0.35983 Ha(9.792 eV)，偶极 2.0298 D，1-A1 闭壳层，5 占据轨道 25 基函数；与日志字段一致 |
| stop running job | **NOT RUN** | 实机任务秒级结束，未抓到 stop 窗口；`stop_job` 内存/进程/PID 三态路径已隔离测试 |
| restart / reconcile 实机接管 | **NOT RUN** | reconcile 终态优先级、adopt/finalize、三态语义在内存状态机隔离验证通过；后端进程重启接管仍在运行 Gaussian 的实机路径未跑 |
| recover（pending+recover / recover-only / stale terminal） | **NOT RUN** | 写盘恢复、去重、失败上报在代码层闭环；实机写盘恢复路径未本轮跑 |
| Sobko JSON-RPC | **NOT RUN** | 无 Sobko server；ID 精确匹配、init expected_id、超时重建、50MB 缓冲上限、锁外 kill 已静态验收 |
| Multiwfn 探测 | **PASS（仅探测，本轮 exe smoke 实测）** | capabilities.formchk/multiwfn/vmd.exists 均=True（Multiwfn `D:\Multiwfn\Multiwfn_3.8_bin_Win64\Multiwfn.exe`、VMD `D:\VMD\vmd.exe`、formchk `D:\G16W\formchk.exe`）；版本走 banner probe，未硬编码；真实 spawn 导出 cube NOT RUN |
| cube header | **NOT RUN** | 未产出 cube；第 3/4/5 行首字段取 nx/ny/nz、非法或非正维度直接 raise 的 fail-closed 已静态验收 |
| VMD 探测 | **PASS（仅探测，本轮 exe smoke 实测）** | capabilities.vmd.exists=True；TGA→Pillow 解码路径已封装；真实 cube→PNG NOT RUN |
| DSH bundle 注册 | **PASS（离线 + 2026-10-22 实机）** | profile `dsh.profile.bundles` 已登记 gaussian（base/web-app/gaussian/aifs）；`verify_profile_bundle.mjs`、toolkit `verify_plugin_manifest.mjs` 离线 PASS；重启后复查 bundles 未被崩溃恢复摘除 |
| DSH 工具 output 契约 | **PASS（离线自测）；对话内注册可见性待新开对话调用确认** | R14：18 个工具均满足 `output { schema, render, presentationMeta? }`；`docs/_verify/output_contract_check.mjs` 复用 dsh-tools `assertSupportedJsonSchema` 复刻 register 校验，18/18 CONTRACT PASS；render 默认返回 text 块且可无损序列化。R14c：系统提示工具列表已从 13 补齐到 18 个。2026-10-22 重启后卡片已渲染，工具在对话内注册可见并实际调用尚未观察 |
| DSH 工具 function schema（parameters object root） | **PASS（R16 离线自测）；对话内实调待重启确认** | R16：18/18 工具 `parameters` 编译为 `{type:"object", properties, required?}`（仅 `required===true` 入 required 数组，array items 递归，default/description/enum 注解保留）；`output.schema` 缺省为 annotation-only 任意 JSON；契约脚本硬断言 parameters.type=object、properties 对象、required 键命中并递归子集白名单，18/18 PASS；`schema_inspect.mjs` 样本核对 `create_postprocess_task`（10 字段、required=["kind"]）与 `gaussian_status`（空 properties）结构正确。对话内模型网关是否接受仍需完全退出重启 DSH、新开对话实调一次确认（L4） |
| README / 环境变量文档一致性 | **PASS（离线核对）** | 逐一比对 `backend/config.py`、`src/index.js` 实际 `getenv`/`process.env` 读取集合与 README 配置表：修正误写的 `EXPECTED_MULTIWFN_VERSION`（代码实读 `MULTIWFN_EXPECTED_VERSION`），补齐后端 HOST/DATA_DIR/MANAGED_TOKEN/线程/GC TTL/RSS 阈值/BSE 基址与前端 `GAUSSIAN_BACKEND_MODE/URL/EXE/启动与关闭超时`；安装段改写为 bundles 登记、快照非软链、完全退出重启的实证流程；verifier `text must-contain` 4/4 命中 |

## 4. 新发现问题

- **[Major-环境，已临时收口，待观察复发] profile bundles 曾被 DSH 崩溃恢复批量摘除**：`C:\Users\Administrator\.dsh\profiles\desktop\package.json` 在 2026-10-21 22:20:53 被重写，`dsh.profile.bundles` 仅剩 `@deepseek-ai/dsh-base`、`@deepseek-ai/dsh-web-app`；aifs 与 gaussian 两个第三方包被同时移出（dependencies 保留）。触发前置是 22:19:55 启动期 `net::ERR_CONNECTION_REFUSED` 崩溃（main 与 web-boot 两条日志，本地服务端口拒绝，非 entry 激活失败）。R14 已把 `@gaussian/dsh-plugin-gaussian` 重新追加回 bundles（改前备份 `.bak-20261021-r14`），未改动 aifs/autorest。**影响**：若重启后再次被批量摘除，第三方 bundle 不会加载、内置区无卡片。**建议**：每次重启 DSH 后先读 bundles 列表确认；若再次被摘，需解包 app.asar 回溯崩溃保护/黑名单逻辑；本条不构成后端源码缺陷。
- **[Fixed] R14 工具缺 output 声明**：旧 `defineTool` 只产出 `{ name, description, parameters, timeoutMs, execute }`，被 dsh-tools register 校验拦下（`tool "gaussian_status" must declare output { schema, render, presentationMeta? }`），entry 在第一个工具处中断、18 个工具全部未注册。已在工厂层统一兜底 `output = { schema: {} , render: defaultRenderJson, ...presentationMeta? }`，离线契约 18/18 PASS；2026-10-22 重启后卡片渲染正常，对话内注册可见性待新开对话调用确认。
- **[Fixed-Minor] R14c 系统提示工具列表漏列后处理工具**：`GAUSSIAN_GUIDANCE` 的"工具列表"只列 13 个，漏列 4 个后处理工具（`postprocess_capabilities`/`create_postprocess_task`/`get_postprocess_task`/`list_postprocess_tasks`）；不阻断注册，但模型可能不知道这些工具存在。已补齐到 18 个，仅提示词文本、不动业务逻辑；重打 `lib/index.js`（35,104 B），快照哈希一致，契约自测仍 18/18 PASS。
- **[Fixed-Minor] R14c README 环境变量与安装流程脱节**：配置表把后端实读的 `MULTIWFN_EXPECTED_VERSION` 误写成 `EXPECTED_MULTIWFN_VERSION`，且漏列后端 HOST/DATA_DIR/MANAGED_TOKEN/线程/GC TTL/RSS 阈值/BSE 基址与前端 managed 模式变量（`GAUSSIAN_BACKEND_MODE/URL/EXE/启动与关闭超时`）；安装段未说明 bundles 登记、快照非软链、完全退出重启。已逐一比对 `config.py`/`src/index.js` 真实读取集合后修正补齐，改前备份 `docs/backups_20261021_rework12/README.md.bak_20261021-r14c`；仅改文档、不动业务逻辑。
- **[Minor] `scripts/build_backend.ps1` 中文注释在 pwsh 7 解析失败**：全角引号/特殊字符导致 `Unexpected token 'Building'`；本轮构建以手动等价 PyInstaller 命令完成，产物不受影响。建议脚本转 UTF-8 with BOM 或改英文/ASCII 注释。
- **[Minor] 串行拒绝返回 HTTP 200 + `{ok:false}`**：不是 409/429；前端已按 `ok` 字段判定，外部脚本集成需读响应体 `ok` 而非状态码。
- **[Minor] `scripts/smoke_test_backend.ps1` 日志清理存在句柄时序竞态**：107–108 行在受控 shutdown 后立即 `Remove-Item smoke_stdout.log/smoke_stderr.log`，若子进程句柄尚未释放，删除会静默失败（`-ErrorAction SilentlyContinue`），留下两个空日志；本轮实测日志为空、无 traceback，已手动清理。建议在删除前再 `Start-Sleep -Milliseconds 300` 或改为 `try/finally` 容错重试；不影响 smoke 判定结论。
- **[Fixed-R15] 状态卡 renderer 直连后端端口，未走 host 同源代理**：旧 `src/client.js` 在浏览器直接 `fetch("http://127.0.0.1:8765/v1/status")`，host 未 inject `connection`、未注册 `/api/gaussian/*` 路由；后端未拉起即 `TypeError: Failed to fetch`，且 `dsh-app://app` 不在后端 CORS 内会被拦截，卡片也拿不到 host state/error/owned/orphan 与 retry 能力。已按官方范本 aifs 架构改为 host `connection.fetch.register` 两条同源路由、client 走相对路径 `/api/gaussian/status`、`/api/gaussian/retry`；离线四项校验 PASS，**2026-10-22 重启 DSH 后卡片状态/版本/地址/数据目录/后端摘要实机渲染 PASS**；retry 按钮触发 host 幂等 start 待后续观察。详见 `LESSONS_LEARNED.md` 第 34、35 条、`DSH_ARCHITECTURE.md` 5.4。
- **[Fixed-R15] `runtime.json` UTF-8 BOM 导致 Node `JSON.parse` 失败、包内 exe 自定位被吞成 null**：清单由 PowerShell 写出带 BOM，Python `utf-8-sig` 可读，Node 默认 utf8 不去 BOM，`JSON.parse` 在首字符抛 `Unexpected token '﻿'`；自定位包在 try/catch 内，异常被吞返回 null，环境变量一缺失就误判「未找到 exe」。已在解析前 `.replace(/^\uFEFF/,"")` 剥离 BOM，源码字面 BOM 规范化为显式转义、写回 UTF-8 无 BOM；离线复刻对快照 manifest 解析、版本/target/sha256 三项校验通过。
- **[Fixed-Major-R16] 工具 `parameters` 扁平表被模型网关判为 `type: null`，对话内工具注册/调用被拒**：报错 `Invalid schema for function 'create_postprocess_task': schema must be a JSON Schema of 'type: "object"', got 'type: null'`（request_id `cc9541df-625a-4e11-9154-b82789fee997`）。旧 `defineTool` 把作者侧扁平参数表直接透传，`parameters` 顶层无 `type:"object"`；OpenAI/DeepSeek function 规范强制 parameters 为 object root，网关读取顶层 type 得 undefined 按 null 拒绝；18/18 工具同构，报错只遍历到第一个被点名工具。旧离线契约只校验 `output.schema`、漏检 parameters 结构，故离线 PASS 而对话内失败。**修复**：工厂内复刻官方 `parameterSchemaSpecToJsonSchema` / `valueSchemaSpecToJsonSchema` 最小子集，`compileParameterSchema` 产出 `{type:"object", properties, required?}`，`compileOutputSchema` 缺省为 annotation-only 任意 JSON；契约脚本补 parameters object-root 硬断言与递归子集白名单。重打 `lib/index.js`（40,108 B）、`lib/client.js`（7,376 B），快照覆盖 SHA256 一致，18/18 PASS；后端零改动、不重打 onedir。**遗留边界**：本轮未在 execute 前补前端入参强校验（后端 Pydantic 已做边界校验，属后续增强）；对话内模型网关是否接受需重启 DSH 新开对话实调确认（L4 NOT RUN）。详见 `LESSONS_LEARNED.md` 第 36 条、`docs/R16_SCHEMA_FIX_20261022.md`。
- **[Minor] profile 快照整包复制臃肿**：手动 `file:` 依赖 + 手动复制快照时，gaussian 目录被整包复制（含 backend/build/dist/docs/runtimes/scripts/src），而 aifs/autorest 只复制 lib/assets/runtimes/licenses；属安装方式遗留，不影响激活，后续可在安装脚本里固化白名单复制。
- **[Minor，历史既有，非 R15 引入，本轮不改后端] Multiwfn 版本探测后台读取线程在 UTF-8 模式下刷 `UnicodeDecodeError`**：`backend/postprocess/multiwfn.py:68` 的 `subprocess.run([exe], input="q\n", capture_output=True, text=True)` 未指定 `encoding/errors`；Python 3.13 在 UTF-8 环境下以 UTF-8 解码 Multiwfn 控制台 GBK 字节（0xb9），内置读取线程向 stderr 打 `UnicodeDecodeError` traceback。主调用外层 `except Exception: return None` 不受影响，版本仍可从已读部分提取或回退 None，不阻断 health/status/capabilities 主流程。**影响**：日志噪音；不影响串行 lease 与计算任务。**建议**：后续后端改版时在该 `subprocess.run` 加 `encoding="utf-8", errors="ignore"`，并同步 `_readerthread` 路径；本轮 R15 只改前端与 host Node 侧、不重打 onedir，故不在此轮修复。
- **[说明，非缺陷] 文档占位符审计**：verifier `text placeholder-audit` 对 README.md 命中 0 个占位符（PASS）；STATUS/RELEASE/LESSONS/ARCHITECTURE/PLAN 命中项经逐条核对全部为省略号 `...`（路径缩写、代码省略、`%mem=...` 关键词示例、TS 展开运算符 `...(typeof...)` 与 spread `...presentationMeta?`），无 TODO/TBD/XXX/`<placeholder>` 等未填模板占位符，属审计工具把 `...` 纳入默认正则的误报。

**本轮离线校验汇总（全部 PASS）**：`verify_plugin_shape.mjs` PASS；`verify_profile_bundle.mjs` PASS；`output_contract_check.mjs` 18/18 PASS（R16 起含 parameters object-root 硬断言 + 递归子集白名单）；`schema_inspect.mjs` 18/18 parameters.type=object、output.schema 合法，样本结构人工核对通过；toolkit `verify_plugin_manifest.mjs` PASS；后端 `backend_offline_smoke.py` TestClient 6/6 PASS；`smoke_test_backend.ps1` onedir exe 实跑 PASS；后端 `compileall` 0 错；交付包 leak=0（条目数/精确字节以 `scripts/make_acceptance_bundle.ps1` 输出为准）。

R16 已修复对话内工具 parameters schema 缺陷（见第 4 节 Fixed-Major-R16）；本轮未发现新的后端源码 Blocker/Major。

## 5. 未验证事项（不得隐藏）

- 真实 DSH/Cordis managed 剩余生命周期：external reuse→owned=false、controlled dispose（仅 `waitForExit()===true` 清 ownership）、orphan 保留 handle、dispose/start race 走 controlled stop。spawn→ready 启动态已于 2026-10-22 重启确认 PASS。
- 对话内 18 个工具（`gaussian_status` / `submit_gaussian_job` 等）注册可见并可实际调用、详情页状态轮询与 `/api/gaussian/retry` 按钮触发 host 幂等 start；状态卡同源渲染与 host snapshot 字段显示已于 2026-10-22 重启确认 PASS。R16 已离线修复 parameters object-root schema，模型网关是否接受仍需完全退出重启 DSH、新开对话实调一次确认（L4）。
- 端到端化学链：Gaussian → chk → formchk → fchk → Multiwfn cube → VMD 最终图片；Pillow 真实解码 PNG（Pillow 不可用时按设计允许交付基础检查后的 TGA，不伪装 PNG）。
- Sobko：server 启动、notification 先于 response、timeout、malformed/oversized stdio frame 故障注入。
- backend 重启后对仍在运行 Gaussian 的持久化接管（reconcile/adopt 实机路径）；stop 运行中任务后状态/lease/PID 跟踪。
- recover-only、pending+recover、terminal+stale recover 的实机写盘恢复路径。
- 301 原子以外的边界用例：大网格点数、开壳层、多片段 SMILES、几何优化（opt）任务流。

## 6. 发布动作

- **最终后端产物**：`runtimes/win32-x64/gaussian-backend/`（exe + `_internal`）+ `runtimes/win32-x64/runtime.json`；这是 DSH managed spawn 实际加载的目录，已是本次新构建，旧 runtime 已替换。
- **最终源码交付包**：`acceptance_bundle.zip`（R16 schema 修复与文档回填后由 `scripts/make_acceptance_bundle.ps1` 重打；条目数、未压缩/压缩字节以脚本输出为准，leak=0；verifier `zip-check-entries` 必含条目命中）。打包脚本固化排除规则：排除 `runtimes/`、`lib/`、`build/`、`dist/`、`__pycache__/`、`node_modules/`、`docs/backups_*`、`docs/_dsh*`、`docs/_verify*`、`*.pyc`、`*.recover.json`、zip 自身；纳入 `backend/`、`src/`、`scripts/`、`packaging/`、`docs/*.md` 与根清单文件。包内含最新 `STATUS.md`、`PLAN.md`、本报告、`DSH_ARCHITECTURE.md`、`FIX_REPORT_20261020.md`、`LESSONS_LEARNED.md`、`R15_DIAGNOSIS_20261022.md`、`R16_SCHEMA_FIX_20261022.md`，以及离线校验脚本（`verify_plugin_shape.mjs`、`verify_profile_bundle.mjs`）与打包脚本 `make_acceptance_bundle.ps1`。
- **是否替换旧 runtime**：后端 onedir 无需替换——R15、R16 只改前端与 host Node 侧，后端业务逻辑无改动，现有 exe 含 R11；交付前核对 zip 内不混入旧 onedir。
- **是否可打 tag/release**：建议先打 `v0.2.0-release-candidate`；待 DSH managed smoke（含 R16 修复后对话内工具实调）与化学链端到端在目标机通过后再转正式 `v0.2.0`。
- **必须完成的剩余步骤**：
  1. 完全退出 DSH（托盘退出、确认进程结束）再启动，新开一轮对话，实际调用 `gaussian_status`、`submit_gaussian_job` 等工具，确认 18 个工具注册可见、可调用且不再报 `Invalid schema`；点状态卡「重试启动」按钮，确认触发 host 幂等 start；
  2. 观察剩余生命周期：先手动起一个外部后端再启动插件验证 reuse→owned=false、dispose 不关闭外部后端；在插件设置里关闭插件验证 controlled dispose 仅 `waitForExit()===true` 清 ownership；观察 orphan 与 dispose/start race 分支；
  3. 在装好 G16/Multiwfn/VMD 的环境跑一条正常完成的任务，复核 Normal termination→completed 与 HOMO/LUMO 解析；
  4. 跑通 chk→formchk→Multiwfn cube→VMD PNG 端到端，回填 Multiwfn profile 菜单数字。
