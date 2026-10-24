# gaussian-dsh-plugin 扩展规划文档

> 创建时间：2026-10-20 ｜ 最后更新：2026-10-22
> 状态：后端 R1–R10 静态闭环、onedir 重打部署、R11–R13 DSH 激活修复落盘、H2O 单点实机通过；R14 补齐 18 个工具 output 契约离线 18/18 PASS、bundles 重新登记；R14c 提示词补齐到 18 个、README 环境变量与安装流程对齐代码；R15 状态卡改 host `connection` 同源代理，2026-10-22 重启实机 managed spawn→ready 与状态卡渲染 PASS；R16 修复工具 parameters object-root schema（离线 18/18 PASS、四项离线校验全绿）；仅剩对话内 18 工具重启实调确认与真实 Multiwfn/VMD 端到端化学链
> 作者：YDW + Doubao

## 一、项目逆推结论

### 现有架构
- **前端**：Cordis 插件（src/index.js），18 个工具，HTTP 调用后端
- **后端**：Python FastAPI（backend/app.py），17 个 REST 端点
- **任务管理**：JobManager 串行提交（running 即拒绝新任务）
- **知识库**：Sobko MCP stdio 子进程（BM25-only）
- **基组库**：BSE REST API 客户端
- **打包**：esbuild 前端 → lib/；后端未打包，直接 python -m backend.app

### M0 级问题（必须先修）
1. **%NoSave/%Chk 顺序错误**：gaussian_input.py 先写 %chk 再写 %nosave，Gaussian 会删除 chk 文件，导致 formchk/Multiwfn 后处理链断裂
2. **backendMode: managed 是空壳**：apply() 只注册工具，不 spawn/health-check/dispose backend
3. **Sobko sys.executable 问题**：PyInstaller 冻结后 sys.executable 指向 exe 自己，不再是 python.exe
4. **mem/nproc 硬编码**：gaussian_input.py 硬编码 "12GB"/8，与 settings.default_mem/default_nproc 两套配置漂移

## 二、目标架构

```
DSH 客户端（Cordis 插件）
  │
  ├── HTTP 工具注册（Cordis）
  │
  ▼
FastAPI 后端（gaussian-backend.exe）
  │
  ├── ChemComputeScheduler（统一计算资源互斥）
  │     ├── Gaussian 16（独占 lease）
  │     ├── Multiwfn（独占 lease）
  │     ├── VMD render（独占 lease）
  │     ├── RDKit 重计算（独占 lease）
  │     └── 轻量任务（无 lease：log 解析、BSE 查询、Sobko、status）
  │
  ├── 现有模块（已稳定）
  │     ├── gaussian_input.py / gaussian_output.py
  │     ├── job_manager.py / basis_set.py
  │     ├── sobko_client.py / keywords.py
  │
  ├── 新增模块
  │     ├── resource_scheduler.py（M0）
  │     ├── process_utils.py（M0）
  │     ├── entrypoint.py（M4）
  │     ├── fchk_reader.py（M2）
  │     ├── smiles/rdkit_builder.py（M1）
  │     └── postprocess/（M2-M3）
  │           ├── manager.py / gaussian_tools.py
  │           ├── multiwfn.py / vmd.py
  │           ├── profiles/multiwfn-3.8.json
  │           └── templates/*.tcl
  │
  └── 外部程序（配置检测，不捆绑）
        ├── Gaussian 16 (D:\G16W)
        ├── Multiwfn 3.8
        ├── VMD
        └── formchk.exe
```

## 三、里程碑

| 里程碑 | 内容 | 验收标准 | 状态 |
|--------|------|----------|------|
| **M0** | 基础修复：%NoSave/%Chk、统一 settings、scheduler、health、process_utils、Sobko frozen fix | checkpoint 能保留；两个 compute job 永远不能同时拿 lease；/v1/health 返回正常 | ✅ 已完成（单元+TestClient 验证） |
| **M1** | RDKit SMILES → Gaussian 输入 | ethanol/ion/radical/stereo/salt/diradical 测试全部符合预期 | ✅ 已完成（6 组测试，冻结 exe 内复跑通过） |
| **M2** | Multiwfn 后处理：formchk、version profile、HOMO/LUMO、ESP、RDG | 小分子 .chk → fchk → cube 全自动 | 🟡 框架完成；capabilities 探测到 Multiwfn 3.8；真实 spawn 跑 cube 未端到端（NOT RUN） |
| **M3** | VMD headless render：orbital/ESP/RDG Tcl、TGA→PNG | 无 GUI 生成稳定图片 | 🟡 框架完成；capabilities 探测到 VMD；真实 cube→PNG 未端到端（NOT RUN） |
| **M4** | PyInstaller：RDKit DLL、templates/profile datas、Sobko frozen fix | 干净 Win11 环境启动 exe 后 /v1/health 正常 | ✅ 已完成（onedir exe 17.66 MB，health/RDKit/shutdown 通过，含 R11 修复） |
| **M5** | Cordis managed lifecycle：spawn/reuse/ownership/shutdown | 启插件自动启动；卸插件关闭 backend；运行中 Gaussian 不受热重载影响 | 🟡 契约静态闭环（probe/reuse/spawn/受控 dispose/waitForExit===true/orphan）；R12/R13 前端激活修复落盘；R14 工具 output 契约离线 18/18 PASS；2026-10-22 重启 DSH 确认 spawn→ready 启动态与状态卡同源渲染 PASS；external reuse、controlled dispose、orphan/race 实机行为待观察 |
| **M6** | 加固：memory guard、artifact GC、timeouts、version checks | 大体系被提前拒绝而非 Windows OOM | ✅ 已完成（hard 拒绝/GC/300 原子 422/版本 fail-fast） |

## 四、关键设计决策

1. **重型计算统一互斥**：Gaussian、Multiwfn、VMD、RDKit 重计算四者互斥，用 ChemComputeScheduler 的 lease 机制保证
2. **Multiwfn 菜单版本化**：不硬编码菜单数字，用 multiwfn-3.8.json profile + banner probe，未知版本 fail-fast
3. **managed shutdown 不杀正在跑的 Gaussian**：DSH 热重载 → Cordis disposer → backend shutdown 时，保留 Gaussian 子进程，下次启动 reconcile
4. **Uvicorn 单 worker**：workers=1，保证 scheduler 单实例
5. **大文件不走 tool JSON**：cube/PNG/长日志用 artifact path + 下载接口，不塞进 tool response（现有 1 MiB guard）
6. **SMILES 化学边界严格**：盐/多片段/过渡金属/多自由基/未指定手性，不包装成"一键可靠结构"

## 五、15 GB 内存约束

| 进程 | 内存上限 |
|------|----------|
| FastAPI idle | < 250 MB |
| FastAPI + RDKit | < 600 MB typical |
| Backend soft warning | ≈ 1.0 GB |
| Backend hard reject | ≈ 1.8 GB |
| Gaussian running | 12 GB（禁止 Multiwfn/VMD 同时跑） |

- POSTPROCESS_MAX_GRID_POINTS = 16_000_000（≈252³）
- Multiwfn threads = 2（不是 16/24）
- RDKit threads = 1
- VMD = 1 process
- Uvicorn = 1 worker

## 六、文件结构（目标）

```
gaussian-dsh-plugin/
├── backend/
│   ├── __init__.py
│   ├── app.py
│   ├── entrypoint.py          # [新增 M4]
│   ├── config.py
│   ├── resource_scheduler.py  # [新增 M0]
│   ├── process_utils.py       # [新增 M0]
│   ├── memory_guard.py        # [新增 M6a] RSS soft/hard 守卫
│   ├── artifact_gc.py        # [新增 M6b] TTL 回收
│   ├── gaussian_input.py
│   ├── gaussian_output.py
│   ├── job_manager.py
│   ├── fchk_reader.py          # [新增 M2]
│   ├── basis_set.py
│   ├── sobko_client.py
│   ├── keywords.py
│   ├── smiles/                 # [新增 M1]
│   │   ├── __init__.py
│   │   ├── models.py
│   │   └── rdkit_builder.py
│   └── postprocess/            # [新增 M2-M3]
│       ├── __init__.py
│       ├── models.py
│       ├── manager.py
│       ├── gaussian_tools.py
│       ├── multiwfn.py
│       ├── vmd.py
│       ├── profiles/
│       │   └── multiwfn-3.8.json
│       └── templates/
│           ├── orbital.tcl
│           ├── esp_surface.tcl
│           └── rdg.tcl
├── packaging/
│   └── gaussian-backend.spec   # [新增 M4]
├── scripts/
│   ├── build.mjs
│   ├── build_backend.ps1      # [新增 M4] 可逆绕过 pathlib backport
│   ├── deploy_runtime.ps1     # [新增 M4] 部署 runtimes + sha256 清单
│   ├── smoke_test_backend.ps1 # [新增 M4]
│   ├── verify_plugin_shape.mjs   # R12 离线校验插件对象 inject/apply/name
│   ├── verify_profile_bundle.mjs  # R13 离线校验 bundles 注册与 manifest 链
│   └── make_acceptance_bundle.ps1 # 发布打包（排除运行时/缓存/备份，自带 leak 复核）
│
├── docs/_verify/                # R14 离线回归脚本（打包时排除，不进交付包）
│   ├── output_contract_check.mjs    # 18 工具 output {schema,render,presentationMeta?} 契约自测
│   └── reconcile_bundles.mjs         # 崩溃恢复摘除后把本包重新追加进 bundles（幂等）
├── runtimes/
│   └── win32-x64/
│       └── gaussian-backend/
│           └── gaussian-backend.exe
├── docs/
│   ├── PLAN.md                 # 本文件
│   ├── STATUS.md               # 项目状态记录
│   ├── LESSONS_LEARNED.md      # 经验文档
│   ├── DSH_ARCHITECTURE.md     # DSH Host/Client/Desktop 架构调研
│   ├── RELEASE_READINESS_REPORT.md  # 发布验收报告
│   └── FIX_REPORT_20261020.md  # R1–R14 修复报告
├── acceptance_bundle.zip       # 源码交付包（不含 runtimes/lib/缓存）
├── src/
│   ├── index.js
│   └── client.js
├── lib/
│   ├── index.js
│   └── client.js
├── package.json
├── cordis.patch.yml
├── README.md
└── start_backend.bat
```

## 七、后续阶段（2026-10-21 收口记录）

### 已完成
- **发布工程**：冻结 v0.2.0 基线，重打 onedir 部署到 `runtimes/win32-x64/gaussian-backend/`，生成 runtime.json SHA256 清单；后端基础 smoke（health/status/jobs/admin 403/301 原子 422）通过。
- **R11 GJF 空行**：写盘前 `rstrip("\n") + "\n\n"`，修掉 `End of file in ZSymb`。
- **R12 前端对象契约**：default 对象带 `inject`；client 模块 id 用完整包名，消除 duplicate factory。
- **R13 bundle 注册**：包进 `dsh.profile.bundles`；清除 profile patch 的 disabled 残留；备份先行。
- **实机单点**：H2O B3LYP/6-31G(d,p) Normal termination，completed，能量/HOMO/LUMO/偶极解析正确。
- **知识沉淀**：`docs/DSH_ARCHITECTURE.md`（DSH 架构调研）；通用 `dsh-plugin-toolkit` Skill（安装/激活/排障/离线校验/骨架模板）。
- **发布收尾**：`scripts/make_acceptance_bundle.ps1` 固化打包排除规则与 leak 复核；一致性校验（4 lib node --check、shape PASS、24 py 编译 0 错、root/快照 manifest equal、zip 50 条目 leak=0 corrupt=0）；系统资产总清单登记本项目与技能。
- **R14 工具 output 契约**：`defineTool` 工厂统一兜底 `output={schema:{},render:defaultRenderJson,...presentationMeta?}`；18 个工具离线契约自测 18/18 PASS；bundles 重新登记 gaussian；413MB 解包临时目录清理，契约结论沉淀进 `DSH_ARCHITECTURE.md` 4.3.1 与 dsh-plugin-toolkit 技能 K8。
- **R14c 提示词对齐**：`GAUSSIAN_GUIDANCE` 工具列表从 13 个补齐到 18 个（补 4 个后处理工具），仅提示词文本、不动业务逻辑；重打 `lib/index.js`（35,104 B），快照哈希一致，契约自测仍 18/18 PASS。
- **R14c 文档对齐**：README 环境变量表逐一比对 `backend/config.py`、`src/index.js` 实读集合，修正 `MULTIWFN_EXPECTED_VERSION` 误写，补齐后端/前端全部 managed 模式变量；安装段改写为 bundles 登记、快照非软链、完全退出重启的实证流程；R14c 提示词一致性经验沉淀进 dsh-plugin-toolkit 技能 K9 与 LESSONS_LEARNED 第 33 条。
- **R15 状态卡同源代理**：client 不再直连后端 8765，host `ctx.inject(["connection"])` 注册 `GET /api/gaussian/status`、`POST /api/gaussian/retry`，renderer 走相对路径；host snapshot 透传 state/version/owned/ready/error 与后端摘要；修掉 `runtime.json` UTF-8 BOM 导致 Node `JSON.parse` 失败、包内 exe 自定位被吞成 null 的离线缺陷。
- **R15b 重启实机（启动态链路 PASS）**：2026-10-22 完全退出重启 DSH，managed spawn→ready、状态卡「可用」、版本/地址/数据目录/Gaussian 路径/工作目录/内存核数/Sobko 字段齐全，bundles 未被摘除；external reuse、controlled dispose、orphan/race 与对话内工具调用未观察，保持 NOT RUN。
- **R16 工具 parameters schema**：模型网关报 `Invalid schema for function ... type:"object", got type:null`；工厂复刻官方参数编译，18 个工具 `parameters` 编译为 `{type:"object", properties, required?}`，离线契约补 object-root 硬断言与递归子集白名单；重打 lib、覆盖快照哈希一致，四项离线校验全 PASS；后端零改动、不重打 onedir；经验沉淀进 LESSONS 第 36 条、架构文档 4.3.2 与技能 K13。
- **R17 运行期排障取证（2026-10-22）**：分清 web profile shell `0xC0000142` 与 desktop gaussian `disabled:true` 两件独立故障；源码链 + 本机实测排除 gaussian 插件因果、环境裁剪、可执行缺失、Job 上限、受限 token、环境变量缺失、cwd 不存在、第三方杀软；确认 disabled 唯一写入路径为 UI 开关、框架不自动禁用；profile 配置与插件完整性取证完成；诊断记录落 `docs/R17_DIAGNOSIS_20261022.md`。**本轮未改源码/后端 exe/profile 配置，R16 终态交付包冻结**；配置修复与 shell 实机复现见剩余路线。

### 剩余路线（按优先级）
1. **R17 配置修复（阻塞 gaussian 可见性，优先）**：故障 B 删除 gaussian `disabled: true` 覆盖条目**已完成**（备份 `.bak-20261022-r17`，按官方 `writePluginEnabled` 规范化结果整条删除，非保留 `disabled: false`）；故障 C 重启后 bundles 被 `selectBundle(false)` 单独摘除，R17c 已备份 `.bak-20261022-r17c` 并把 gaussian 补回 bundles 第三项，JSON 断言与 toolkit manifest 离线校验 PASS，快照 lib/后端 exe 哈希复核为 R16 终态。**剩余**：完全退出 DSH 重启进 desktop profile，先复查 bundles 是否再次只剩官方两条（若再被摘需继续追自动回写路径，见诊断 4.5），再确认内置区卡片与对话工具恢复；aifs/autorest 是否补回 bundles 仍待用户决策。
2. **R17 shell 0xC0000142 实机复现**：本机前置复测已完成——pwsh 7 未安装（DSH 设计内回退 System32 5.1，属预期），系统 `powershell.exe` 5.1 与 `cmd.exe` 绝对路径独立启动 `echo hello` 均 exitCode=0，排除系统 shell 本体损坏。重启后在 desktop 会话先看权限选择器档位，再发一条最简 `echo hello` 观察是否仍退出 `3221225794`；首要候选是 read-only/workspace-write 受限沙箱（官方 `@deepseek-ai/dsh-sandbox-windows-acl` README 机制 + 社区多条 issue 佐证，见诊断 3.3 B1），切 danger-full-access 做对照实验可临时绕开；若复现，按 `docs/R17_DIAGNOSIS_20261022.md` 5.2 分层抓 runner bootstrap 与目标 powershell.exe 证据；属 DSH 内置子系统/系统运行时问题时不改动插件源码。
3. **DSH 对话内工具实调确认**：R15b 已确认状态卡同源渲染与 managed spawn→ready；R16 schema 离线修复后，需完全退出重启桌面端、新开一轮对话，实际调用 `gaussian_status`、`submit_gaussian_job` 等工具，确认 18 个工具注册可见、不再报 `Invalid schema`；复查 bundles 稳定性；再观察 reuse/dispose/orphan/race 与 retry 幂等触发。
4. **化学链端到端**：chk→formchk→fchk→Multiwfn 导出 cube→VMD 渲染 PNG；据真实 Multiwfn 菜单数字回填 `profiles/multiwfn-3.8.json`。
5. **状态机实机路径**：backend 重启接管仍在运行的 Gaussian；stop 运行中任务的状态/lease/PID 跟踪；recover-only 与 terminal+stale recover 实机复核。
6. **Sobko 联调**：server 启动、ID 精确匹配、notification-before-response、timeout、malformed/oversized frame 故障注入。
7. **后续可选**：几何优化工作流、one-file 打包（onedir 稳定后再切）。
