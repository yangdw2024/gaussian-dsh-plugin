# 返工修复对照报告（第二轮静态验收前）

> 日期：2026-10-20　基线：`acceptance_bundle.zip` 首轮评审结论"需返工"（9 Blocker / 12 Major / 3 Minor）
> 说明：本报告逐条对照首轮问题清单，给出修复位置、做法与本地验证。未实跑真实 Gaussian/Multiwfn/VMD 的项已如实标注为"代码层修复，待端到端 smoke"。

## 一、Blocker（B1–B9）

| 编号 | 问题 | 修复位置 | 做法 | 验证 |
|------|------|----------|------|------|
| **B1** | Gaussian 未取统一 lease，RDKit 入口也未取，并发可同时通过 has_running | `backend/job_manager.py` `submit()`；`backend/app.py` 两个 SMILES 端点；`resource_scheduler.py` | submit 先生成 job_id，再 `chem_scheduler.acquire(job_id,"gaussian")`（scheduler 内部加锁，消除并发同时通过检查）；启动失败/异常路径 `_release_lease`；reconcile 接管存活 PID 时重新 acquire。两个 SMILES 端点对 `smiles_to_3d` 短持 `rdkit` lease（try/finally），ResourceBusyError→409。Gaussian Popen 加 `CREATE_NO_WINDOW \| CREATE_NEW_PROCESS_GROUP(0x200)` 脱离后端控制台组 | 代码走查；scheduler 8 项测试保留；TestClient 回归通过 |
| **B5** | 启动恢复/GC 用未定义的 `app.logger`，异常处理内二次调用会 AttributeError | `backend/app.py` | 引入标准库 `logging.getLogger("gaussian-dsh-backend")`，替换全部 `app.logger.*`；覆盖 adopted job、GC 删除、reconcile 异常三条启动路径 | py_compile；TestClient startup 不报错 |
| **B6** | 管理端点无 token 时匿名可 shutdown/GC，CORS `*`+credentials | `backend/app.py` `_require_admin()`；CORS 中间件 | 统一鉴权：配 token 校验 Bearer；未配 token 仅放行回环 host（127.0.0.1/::1/localhost）。CORS 由 `*`+credentials 收紧为回环白名单、credentials=False、只开放 GET/POST 与必要头 | TestClient：非回环匿名 POST `/v1/admin/gc` → 403 |
| **B7** | `/v1/jobs` 绕过原子数与资源上限，原始 GJF 原样提交 | `backend/gaussian_input.py` 新增 `validate_gjf()`/`_parse_mem_to_mb()`；`job_manager.submit()` 调用 | 提交边界解析原始 GJF：原子数≤max_atoms、`%mem` 换算 MB 不超预算、`%nprocshared`≤上限、电荷/多重度合法（多重度=2S+1，≥1，不要求奇数，双重态=2 合法） | 单测：301 原子拒绝、20GB 拒绝、合法乙醇通过；TestClient ok=false |
| **B8** | MP2 误把 SCF 参考态当相关能；EUMP2 不支持 Fortran 科学计数 | `backend/gaussian_output.py` 能量段 | 按方法选择最终能量：MP2 取 EUMP2，CCSD 取 E(CCSD)，HF/DFT 回退最后 SCF Done；数值正则兼容 `E[+-]dd` 科学计数 | 单测：MP2 final=-76.234567（非 -76.01） |
| **B9** | stop_job 凭 PID、不查返回码，PID 复用误杀/误报 stopped | `backend/job_manager.py` `stop_job()`/`_finalize_if_dead()` | taskkill 后检查返回码，轮询最多 5 秒确认 PID 消失，未确认不落 stopped、不允许提交新任务；统一结束判据 | 代码走查；与 M1 共用终态逻辑 |
| **B2** | managed dispose 可能 terminate 仍在跑的 Gaussian | `src/index.js` `dispose()`；后端独立进程组 | dispose 先受控 POST `/v1/admin/shutdown`，等 waitForExit；仅超时未退才兜底 terminate。配合后端 CREATE_NEW_PROCESS_GROUP，Gaussian 不在后端可清理句柄范围 | 代码走查（真实 DSH 联调待办） |
| **B3** | `if(handle.done)` 把 Promise 当布尔退出状态 | `src/index.js` `_waitReady()` | `handle.done.then(resolve)` 订阅退出，与 health 轮询 `Promise.race`，进程提前退出立即报错而非空等到超时 | esbuild bundle 通过 |
| **B4** | spawn `cwd: dataDir \|\| undefined`，而 SpawnSpec.cwd 是必需字符串 | `src/index.js` `_resolveCwd()` | 解析真实存在的绝对目录（dataDir→exe 所在目录，不存在则 mkdir），拿不到时**省略 cwd 键**而非传 undefined | esbuild bundle 通过 |

## 二、Major（M1–M12）

| 编号 | 问题 | 修复位置 | 做法 | 验证 |
|------|------|----------|------|------|
| **M1** | has_running 见原 PID 退出就无条件标 failed，忽略 Normal termination | `backend/job_manager.py` `_finalize_if_dead()` | 统一终态 reconciliation：读日志 "Normal termination of Gaussian" 落 completed，否则 failed；has_running/get_job/reconcile 复用同一判据 | 代码走查 |
| **M2** | orbitals/esp/rdg 只生成命令却标 completed、返回 ok=true | `backend/postprocess/manager.py` | 三分支标 `prepared`（awaiting_execution），仅命令落盘；mo_levels 校验 SVG 存在非零才 completed；final_status 变量统一落状态 | 代码走查 |
| **M3** | DSH 前端未注册后处理工具 | `src/index.js` 新增 4 个工具 | `postprocess_capabilities`、`create_postprocess_task`、`get_postprocess_task`、`list_postprocess_tasks`，把状态与产物路径映射回工具结果 | esbuild bundle 含新工具名（13 处匹配） |
| **M4** | Multiwfn probe_version 硬返回 "3.8" | `backend/postprocess/multiwfn.py` `probe_version()` | 真启动 exe、input="q\n"、抓 banner 正则 `Multiwfn (V?\d+\.\d+...)`；超时/抓不到返回 None 不伪造 | 代码走查（实机版本探测待 smoke） |
| **M5** | 网格预检用固定三档，未按真实包围盒 | `backend/postprocess/manager.py` | 三档标注为保守上界；新增 `_cube_header_point_count()` 预留生成后读 nx·ny·nz 复核钩子；当前枚举档位最大值 410 万 < 1600 万上限，不会越限 | 代码走查；真实网格复核待执行器接入 |
| **M6** | GC 只扫 data_dir，产物散在 work_dir 不被回收 | `backend/postprocess/manager.py` | 产物目录改 `data_dir/postprocess/<task_id>`，纳入 GC 扫描 | 代码走查 |
| **M7** | `_recv_json` 阻塞 readline 无法超时，stderr=PIPE 未消费 | `backend/sobko_client.py` | 后台 stdout 泵线程写共享字节缓冲，`_recv_json` 轮询缓冲按 Content-Length 取帧，真超时返回；stderr 独立线程消费留最近 20 行；超时退出附 stderr | 单测：卡死子进程 1.51s 返回 None（非永久阻塞）；直接塞缓冲帧解析正确 |
| **M8** | VMD returncode=0 但 TGA 缺失仍返回 PNG 路径 | `backend/postprocess/vmd.py` `_require_tga()` | 三渲染函数强制校验 TGA 存在、非零、可解码（Pillow verify），缺失即 raise；Pillow 缺失显式返回 TGA | 代码走查（实渲染待 smoke） |
| **M9** | 开壳层 MO 图只画 alpha，用 alpha 定义 gap | `backend/fchk_reader.py` `generate_mo_level_svg()` | 闭壳层单栏；开壳层 alpha/beta 两栏并列，各自 HOMO/LUMO 与 gap；缺 beta 通道显式告警 | 单测：开壳层双栏、闭壳层单栏 |
| **M10** | HOMO/LUMO 遍历优化各步取全局最大，非终态 | `backend/gaussian_output.py` | 取【最后一组】occ/virt（终态 SCF），合理性校验后采用 | 单测：最后一对 -0.25/-0.05 |
| **M11** | managed start 以 void 启动，dispose 与启动竞态 | `src/index.js` | 加 `this.disposed` 终态标志；_launch/probe/waitReady 各处检查；卸载后不再把进程置 owned | esbuild bundle 通过 |
| **M12** | stdout/stderr pipe 无消费者，缓冲满反堵 | `src/index.js` spawn stdio | 改用 health 轮询判定就绪，stdio 设 ignore，避免管道堆积 | esbuild bundle 通过 |

## 三、Minor（m1–m3）

| 编号 | 问题 | 修复位置 | 做法 |
|------|------|----------|------|
| **m1** | package.json 0.1.0 与后端 0.2.0 不一致 | `package.json` | version → 0.2.0 |
| **m2** | client.js 硬编码 127.0.0.1:8765 | `src/client.js` | 提 `backendBase()`，优先 `window.GAUSSIAN_BACKEND_URL`，回环兜底，三处替换 |
| **m3** | one-file 开关误导、找不到 exe 仍成功退出 | `scripts/build_backend.ps1` | 未实现 one-file 时直接 throw 拒绝；onedir exe 缺失改为 exit 1 |

## 四、本地验证汇总

- 后端 24 个 `.py` 全部 `py_compile` 通过（FAIL=0）。
- 前端 `src/index.js`、`src/client.js` esbuild bundle 成功；`lib/` 已用现成 esbuild 重打。
- TestClient 综合回归：health(0.2.0) 200、status 200、capabilities 嵌套结构正常、301 原子与 20GB mem 被 ok=false 拒绝、匿名 admin/gc 403。
- 针对性单测：MP2 能量、最后一对轨道、开壳层 MO 双栏、Sobko 真超时、validate_gjf 三场景，均通过。

## 五、仍需端到端 smoke（非代码缺陷，静态验收不判 blocker）

1. 后端源码改动后需用 `scripts/build_backend.ps1` 重新 PyInstaller onedir 打包 + `deploy_runtime.ps1` 重部署（当前 runtimes exe 仍是返工前版本）。
2. 真实 chk→formchk→Multiwfn 实跑 cube→VMD 出 PNG，据真实菜单回填 profile。
3. 真实 DSH 环境联调 managed spawn/dispose 与新注册的后处理工具。

---

## 六、第三轮修复对照（第二轮评审 N1–N12 + 部分闭环补强）

> 基线：第二轮静态评审维持"需返工"，提出 N1–N5 Blocker、N6–N11 Major、N12 Minor，并指出首轮多项仅"部分闭环"。
> 本轮逐条代码层修复并本地回归；未实跑外部化学程序的项如实标注。

### Blocker

| 编号 | 问题 | 修复位置 | 做法 | 验证 |
|------|------|----------|------|------|
| **N1** | spawn stdio 用 DSH 不支持的 `"ignore"`，可能在参数校验失败 | `src/index.js` spawnSpec | stdin 保留 ignore，stdout/stderr 改 `inherit`（DSH 支持枚举），由宿主消费，不再堵管道 | esbuild bundle + node --check 通过 |
| **N2** | lease 两种相反失效：写文件失败泄漏；Popen 成功但 save 失败误释放 | `job_manager.py` `submit()` | 统一事务：Popen 前失败释放 lease 记 failed；`proc_started=True` 后（含 save 失败）**保留 lease**，仅记异常按已启动返回 | 代码走查；TestClient 正常提交路径不变 |
| **N3** | mem 单位漏算 GW/TW/MW/KW/W、未知后缀当 MB；原子序数坐标漏计；多段 mem 被覆盖 | `gaussian_input.py` `_parse_mem_to_mb()`/`validate_gjf()` | 完整识别 GB/MB/KB 与 word（1 word=8B），裸数字按 MB，未知单位 raise fail-closed；坐标同时接受元素符号与 1–3 位原子序数；多段 %mem 取 max | 纯函数：20GW=163840MB、100MW=800MB、20TB 拒绝、301 数字坐标拒绝、合法乙醇通过 |
| **N4** | `%chk=` 区分大小写，%Chk/%CHK 不改写 | `job_manager.py` `_normalize_chk()` | 忽略大小写正则命中任意 `%chk=` 行替换为 chk_path；无该行则插入首个 Link0 前 | 代码走查 |
| **N5** | CCSD 正则缺左括号匹配不到；MP2 D 指数截断；LUMO 错取高能虚轨 | `gaussian_output.py` | 归一 D→E；CCSD 正则 `E\(CCSD\(?T?\)?\)=` 命中 E(CCSD)/E(CCSD(T))，另补 QCISD；occ/virt 按 min 配对取最后一组，LUMO=配对块首根 | 正则：E(CCSD)/CCSD(T)/QCISD 均命中，旧写法空；LUMO 同 SCF 取 0.10 非 0.30 |

### Major / Minor

| 编号 | 问题 | 修复位置 | 做法 | 验证 |
|------|------|----------|------|------|
| **N6** | RDKit 入口未过 hard guard，原子数检查太晚 | `app.py` 两端点；`smiles/rdkit_builder.py` | acquire 前先 `memory_guard.can_accept_compute()`（503）；AddHs 后、Embed 前用 `GetNumAtoms()` 预检上限 | 代码走查 |
| **N7** | owned 到 ready 才置位，启动中卸载留进程；waitForExit 返回值被忽略 | `src/index.js` | spawn 成功即 owned=true；抽 `_shutdownHandle()`（受控 shutdown→waitForExit===true→兜底 terminate）；dispose 先等 startAttempt settle；`_controlledStop` 真正清理 | esbuild + node --check |
| **N8** | taskkill 异常回退引用未赋值 result.stderr → UnboundLocalError | `job_manager.py` stop_job | 初始化统一 `kill_detail`，区分 taskkill/os.kill/存活检查，不再引用未赋值 result | 代码走查 |
| **N9** | Sobko 超时不杀 worker、不按 id 匹配，迟到响应串用 | `sobko_client.py` | `_recv_json(expected_id)` 按 JSON-RPC id 匹配、旧帧丢弃；超时 `_kill()` 重建会话清缓冲；MAX_FRAME_BYTES 上限 | 代码走查 |
| **N10** | stdout/stderr 同路径两个 "w" 句柄互相覆盖 | `process_utils.py` `spawn_subprocess` | 同 resolve 路径只开一次，stderr=STDOUT；父进程关闭副本句柄 | 代码走查 |
| **N11** | log_tail_lines=0 时 `lines[-0:]`=整份 | `job_manager.py` get_job | ≤0 返回空不读文件；>0 用 deque 有界尾读 | 代码走查 |
| **N12** | CORS 精确 origin 不含端口，拦 localhost:3000 | `app.py` | 改 `allow_origin_regex` 放行 localhost/127.0.0.1 任意端口 + app://，不恢复 *+credentials | 代码走查 |

### 首轮部分闭环补强

| 项 | 补强 |
|----|------|
| **B2** | 注释诚实声明 0x200≠BREAKAWAY_FROM_JOB；只对 backend 句柄受控 shutdown/兜底 terminate，不杀进程树 |
| **B4** | `_resolveCwd` 兜底 `os.tmpdir()`/`process.cwd()`，cwd 永远字符串 |
| **B9** | `process_utils.pid_create_time/pid_is_same_instance` best-effort 比对创建时间，疑似复用拒绝终止；取不到放行 |
| **M4** | capabilities 真调 `probe_version()`，抓不到 version=None，给 version_matched，不硬报 3.8 |
| **M5** | 新增 `verify_cube_within_limit()` 公开钩子，执行器产物按 header 点数复核上限、超额拒绝 |
| **M8** | 缺 Pillow 时 TGA 魔数（图像类型 2/3/10/11）粗检后以 .tga 交付，不伪装 PNG |
| **M9** | 以"存在独立 beta 能量通道"决定双栏，非仅 Nα≠Nβ |
| **M1** | reconcile 复用 `_log_normal_termination` 完整串，不再用子串误判 |

### 第三轮本地验证
- 后端 24 个 `.py` `py_compile` FAIL=0；前端 esbuild bundle 成功、`node --check` 两个产物通过。
- TestClient：health 200(0.2.0)、capabilities 200（multiwfn.version=None 不伪造）、匿名 shutdown 403、`20GW` 正确换算 160GB 超限拒绝（不再当 20MB 放行）。
- 纯函数/正则：N3 单位换算与原子序数坐标、N5 CCSD/MP2-D/LUMO 配对均通过。

---

## 七、第四轮修复对照（第三轮评审 R1–R9，P0/P1/P2）

> 基线：第三轮静态评审维持"需返工"，提出 P0（R1/R2/R3）、P1（R4/R5/R6/R7/R8）、P2（R9）。
> 本轮逐条代码层修复并本地隔离回归；未实跑外部化学程序的项如实标注。

### P0 Blocker

| 编号 | 问题 | 修复位置 | 做法 | 验证 |
|------|------|----------|------|------|
| **R1** | 只替换第一处 %chk；无 chk 时插到首条 % 指令前，首行 %nosave 会使 chk 在前被删；多 Link1 第二条 %CHK 保留原路径 | `job_manager.py` `_normalize_chk()` | 忽略大小写替换**全文所有** %chk 行；Link0 稳定重排为 其他指令→%nosave→%chk，保证 nosave 在 chk 前；无 chk 插到最后一个 nosave 之后；插入后重新定位 Link0 边界 | 隔离：首行 nosave 无 chk → nosave<chk；两条 %CHK 均改写为目标路径 |
| **R2** | `min(len)` 全局同下标配对，多 SCF/每步 virt 拆块时错配到前一步高能虚轨 | `gaussian_output.py` | 改 `finditer` 按位置：取最后一个 Alpha occ 块，收集其**之后**的 virt 块，首根=LUMO、末 occ 末值=HOMO；beta 由 fchk_reader 处理 | 隔离：双 SCF，末步 virt 0.10/0.20、前步 0.50/0.60 → LUMO=0.10、HOMO=-0.25 |
| **R3** | cube header 读原点行第二字段（偏移错），标准 cube 返回 None，verify 返回 -1 放行 | `postprocess/manager.py` | 读 6 行，取第 3/4/5 行（0-based）**首字段**为 nx/ny/nz；非法直接 raise（fail-closed），去掉 -1 放行 | 隔离：标准 2×3×4 → 24 点；缺行/非正整数 raise |

### P1 Major

| 编号 | 问题 | 修复位置 | 做法 | 验证 |
|------|------|----------|------|------|
| **R4** | 整份日志含 "Normal termination" 子串即成功，前段 Link1 成功后段 Error 误报 completed | `job_manager.py` `_log_normal_termination()` | deque 尾读 400 行，取最后一个 termination event；Error 位于最后一个 Normal 之后则判 failed | 隔离：前段 Normal+后段 Error → False；干净成功 → True |
| **R5** | Popen 后两次 _save 都失败仍 ok=true，无 JSON → lease 永久 busy/重启丢失 | `job_manager.py` `submit()` | Popen 前先 `_save(pending)` 落盘；running 保存失败也有 pending 记录供 reconcile 按 pid 接管；Popen 成功后仍不释放 lease | 代码走查 |
| **R6** | 仅 ready 发受控 shutdown；terminate 后 waitForExit=false 仍清空 handle 丢引用 | `src/index.js` `_shutdownHandle()` | 有 baseUrl 先 probe 探活，在线即尝试受控 shutdown（不限 ready）；未确认退出保留 handle 标 orphan，仅确认退出才清引用/置 stopped | esbuild + node --check |
| **R7** | expected_id 非空时仍接受无 id 的 progress 通知帧；未成形缓冲无上限 | `sobko_client.py` `_recv_json()` | 仅 `frame.get("id")==expected_id` 返回，无 id 通知/错 id 帧 continue；未成形缓冲超 50MB `_kill()` 重置 | 判定表达式隔离：通知跳过、匹配返回、错 id 丢弃 |
| **R8** | 多段 %nprocshared 被末段覆盖，前段超核数可绕过 | `gaussian_input.py` | 多段 %nprocshared 取 max，任一段超 max_nproc 即拒绝（与 %mem 一致） | 隔离：前段 32/末段 4，上限 16 → 拒绝 |

### P2 Minor

| 编号 | 问题 | 修复位置 | 做法 | 验证 |
|------|------|----------|------|------|
| **R9** | 独立 stderr 文件句柄未纳入 finally 关闭，只关了 stdout | `process_utils.py` `spawn_subprocess()` | 用 `opened_handles` 列表统一收集 stdout+独立 stderr，Popen 后全部关闭副本 | 代码走查 |

### 第四轮本地验证
- 后端 24 个 `.py` `py_compile` FAIL=0；前端 esbuild bundle 成功、`node --check` 通过。
- TestClient：health 200(0.2.0)、capabilities 200、匿名 shutdown 403。
- 隔离：R1 chk 顺序/全量替换、R2 双 SCF LUMO=0.10、R3 2×3×4=24、R4 混合日志判 False、R8 前段超核拒绝、R7 帧过滤均符合预期。

---

## 八、第五轮修复对照（第四轮评审残留 R1/R2/R5/R6 收口）

> 基线：第四轮评审 R3/R4/R7/R8/R9 已闭环，残留 R2（LUMO 取错块）、R5（持久化失败不可恢复）、
> R1（多 Link1 段与其他 scratch 指令语义缺口）、R6（orphan 被错认 reuse）。本轮逐条收口。

| 编号 | 问题 | 修复位置 | 做法 | 验证 |
|------|------|----------|------|------|
| **R2** | `following[-1]` 取最后一个 virt 块，单 SCF virt 拆行时把高能虚轨当 LUMO | `gaussian_output.py` | 末 occ 之后的 virt 块取 `following[0]` 第一块首根为 LUMO，不再取最后一块 | 隔离：occ -0.55/-0.25，virt 0.10/0.20 与 0.30/0.40 → LUMO=0.10、HOMO=-0.25 |
| **R5** | pending(pid=null) 两次 save 失败后 reconcile 只扫 running，接管不了、lease 永久 busy | `job_manager.py` | Popen 成功先 save(running)，失败落最小 `.recover.json`（pid/创建时间/路径）；reconcile 补齐 pending/缺 pid 记录、重建仅存 recover 的孤儿；`has_running` 加内存 Popen 句柄兜底；成功后清 recover | recover 往返读写/清理通过；代码走查 |
| **R1** | 全局重排把 %RWF 等搬到 nosave 前改变保留语义；第二 Link1 段 %Chk→%NoSave 危险顺序未处理 | `job_manager._normalize_chk()` | 按 `--Link1--` 分段，段内只局部移动/插入 %chk，保证 nosave 在 chk 前；%mem/%nproc/%rwf 原位不动；仅主段缺 chk 插入 | 隔离：%RWF 保持 nosave 后；第二段 %Chk→%NoSave 调成 %NoSave→%Chk；无 chk 插 nosave 后 |
| **R6** | orphan handle 被 getBaseUrl/_launch probe 命中后无条件 owned=false，错认 reuse | `src/index.js` | 仅 `!this.handle`（无自有句柄）时 probe 命中才置 owned=false；已有 own/orphan handle 保持所有权 | esbuild + node --check；代码走查 |

### 第五轮本地验证
- 后端 24 个 `.py` `py_compile` FAIL=0；前端 esbuild bundle、`node --check` 通过。
- TestClient：health 200(0.2.0)、capabilities 200、匿名 shutdown 403。
- 隔离：R2 LUMO=0.10、R1 段内局部保序/%RWF 不动/第二段保序、R5 recover 往返均符合预期。
- 已闭环 R3/R4/R7/R8/R9 未改动，保持第四轮结论。

---

## 九、第六轮修复对照（第五轮残留 R5a/R5b/R5c/R7/R6 收口）

> 基线：第五轮评审 R1/R2/R3/R4/R8/R9 闭环，残留 R5 当前进程内终态合流、list_jobs 重复枚举、
> recover 吞异常假报可恢复、R7 锁内 kill 死锁、R6 dispose 提前清 owned。

| 编号 | 问题 | 修复位置 | 做法 | 验证 |
|------|------|----------|------|------|
| **R5a** | running save 失败后磁盘仍 pending/pid=None，Gaussian 结束时 has_running/get_job 读 pending 主记录，_finalize_if_dead 因 status!=running 直接返回，lease 永久 busy、get_job 仍显示 pending | `job_manager.py` | Popen 成功把运行态 job 存内存 `self._running_jobs`；新增 `_reap_ram_jobs()`，对应 Popen `poll()` 已退出时用内存 job 走统一 `_finalize_if_dead()` 落 completed/failed、释放 lease、清 recover、移出内存；`has_running`/`get_job` 开头先 reap，磁盘 pending 时返回内存对象 | 隔离：假已退出进程 → reap 后 status=completed、lease release 被调、内存与 recover 清除 |
| **R5b** | `glob("*.json")` 同时匹配 `<id>.json` 与 `<id>.recover.json`，同 job 重复列出、reconcile 重复 acquire | `job_manager.list_jobs()` | 列表推导排除 `.recover.json` 结尾文件；reconcile 对 recover 独立枚举按 id 去重 | 隔离：主记录+recover 并存时 list_jobs 中该 id 仅出现 1 次 |
| **R5c** | `_write_pid_recover()` 吞所有异常，running save 与 recover 都失败仍声称可恢复 | `job_manager._write_pid_recover()` | 改返回 bool；都失败时 job.error 明确标注"运行状态与恢复凭据均写盘失败，重启后可能无法接管"，不假装可恢复 | 代码走查；返回值在 submit 两条路径均判断 |
| **R7** | `_recv_json` 在 `with _buf_lock`（普通 Lock，非 RLock）内调 `_kill()`，`_kill` 又取同一把锁 → 50MB 触发即确定性死锁 | `sobko_client.py` | 锁内只判断长度并置 `overflow=True`，退出 `with` 后再 `if overflow: self._kill()` | 代码走查；确认锁内不再直接调 `_kill()` |
| **R6** | dispose 先 `this.owned=false` 再 shutdown，返回 false 形成 orphan 后所有权标志已丢 | `src/index.js` dispose | 先 `await _shutdownHandle()`，仅 `exited===true` 后才 `owned=false`；orphan 时保持 `owned=true` 并保留 handle | esbuild + node --check；代码走查 |

### 第六轮本地验证
- 后端 24 个 `.py` `py_compile` FAIL=0；前端 esbuild bundle、`node --check`（src 与 lib）通过。
- TestClient：health 200、capabilities 200、匿名 shutdown 403。
- 隔离：R5a reap 用假已退出进程落 completed/释放 lease/清 recover；R5b list_jobs 同 id 仅 1 条；R7 锁外 kill 不重入；R6 owned 延后。
- 已闭环 R1/R2/R3/R4/R8/R9 未改动，保持上轮结论。

---

## 十、第七轮修复对照（第六轮残留 R5a 状态机 / R2 跨 SCF / Sobko init / R9 / R6）

> 基线：第六轮评审 R5b/R5c/R7锁死/R6主体闭环，残留 R5a stop 与 PID-reuse 合流、R2 无 virt 跨步回退、
> Sobko initialize 未关联 id、R9 try/finally 起始太晚、R6 _controlledStop 未同步 owned。

| 编号 | 问题 | 修复位置 | 做法 | 验证 |
|------|------|----------|------|------|
| **R5a-1** | stop_job 只认磁盘主记录，pending（写盘失败）时拒绝停止；停止成功后未清内存 running，get_job 会用残留内存对象把磁盘 stopped 覆盖回 failed/completed | `job_manager.stop_job()` | load 后若 `_running_jobs` 有该 id 则改用内存 running+pid 对象；停止成功后同步 pop `_running_jobs/_processes`、`_clear_pid_recover` | 代码走查 |
| **R5a-2** | reap 时 Popen 已确认退出，却又让 `_finalize_if_dead` 用裸 pid_alive 否决；PID 复用时 lease 未释放却清掉 recover/内存，永久 busy | `_finalize_if_dead(trust_handle=)`、`_reap_ram_jobs` | reap 以 `trust_handle=True` 信任句柄退出事实、不再裸查 pid_alive；只有 finalize 真正返回 True 才 clear/pop | 代码走查 |
| **R2** | 最终 SCF 无 virt 时 `following[-1]` 回退到前一 SCF 的 virt，把前步 LUMO 配给最终 HOMO | `gaussian_output.py` | following 为空时只设 HOMO，LUMO/gap 保持 None，绝不跨 SCF 拼接 | 隔离：最终 SCF 无 virt → HOMO=-0.25、LUMO=None；正常两行 virt → LUMO=0.10 |
| **Sobko-init** | initialize 是带 id 的 request，却调 `_recv_json(timeout=90)` 不传 expected_id，progress 通知被当成 initialize 响应 | `sobko_client.py` | 取 `init_id=_next_id()`，发送带上，接收传 `expected_id=init_id`，其余帧丢弃 | 代码走查 |
| **R9** | stdout open 成功后 stderr open/mkdir 抛异常时，执行流尚未进入 try/finally，stdout 句柄泄漏 | `process_utils.spawn_subprocess()` | stdout/stderr 的 mkdir/open 与 Popen 包进同一 try/finally；句柄默认 DEVNULL | 隔离：stderr open 模拟失败，已开 stdout 句柄 closed=True |
| **R6** | `_controlledStop` 确认退出清了 handle 却不同步 owned，出现 owned=true/handle=null | `src/index.js` | 返回 true 时同步 `this.owned=false` | esbuild + node --check |

### 第七轮本地验证
- 后端 24 个 `.py` `py_compile` FAIL=0；前端 esbuild bundle、`node --check`（src 与 lib）通过。
- TestClient：health 200、capabilities 200、匿名 shutdown 403。
- 隔离：R2 无 virt → LUMO=None、正常两行 → LUMO=0.10；R9 stderr open 失败时 stdout 句柄关闭。
- 已闭环 R1/R3/R4/R5b/R5c/R7/R8 未改动，保持上轮结论。

---

## 十一、第八轮修复对照（第七轮"有条件交付"收尾：reconcile 终态优先级 + PID 实例校验）

> 基线：第七轮评审"有条件交付"，剩 1 Major（stale recover 复活终态记录、adopt 未做 PID 实例校验）
> 与 1 Minor（_waitReady disposed 分支未复用 _controlledStop）。

| 编号 | 问题 | 修复位置 | 做法 | 验证 |
|------|------|----------|------|------|
| **R8a** | 终态（completed/failed/stopped）主记录 + 残留 recover 时，reconcile 会用 recover 把它改回 running、重新 acquire lease；旧 PID 复用时还会把无关进程当 Gaussian 接管 | `job_manager.reconcile()` | recover 只补 pending 或 running+缺 pid；终态主记录直接清残留 recover、按终态保留，不复活 | 隔离：completed+stale recover+PID 存活 → adopted=0、不 acquire、recover 清除 |
| **R8b** | `_adopt_or_finalize` 只查 PID 存活，未用创建时间校验实例 | `job_manager._adopt_or_finalize()` | 存活时再 `pid_is_same_instance(pid, pid_start_time)`，False（PID 复用）按原进程已结束 finalize，不接管不重占 lease | 隔离：PID 存活但实例不符 → adopted=0、不 acquire、落 failed |
| **R8c** | `_waitReady` 成功后发现 disposed 直接 `_shutdownHandle`，关闭成功清了 handle 却不同步 owned | `src/index.js` | 改用 `_controlledStop(handle)`，确认退出后同步清 owned | esbuild + node --check |

### 第八轮本地验证
- 后端 24 个 `.py` `py_compile` FAIL=0；前端 esbuild bundle、`node --check` 通过。
- TestClient：health 200、匿名 shutdown 403。
- 隔离：R8a 终态不复活、R8b PID 复用不接管，均不 acquire lease。
- 已闭环 R1/R2/R3/R4/R5a/R5b/R5c/R7/R8/R9 未改动，保持上轮结论。

---

## 十二、第九轮修复对照（PID 实例三态语义 + adopted-job 后续轮询实例校验）

> 基线：第八轮"有条件交付"，剩 1 Blocker（None 不可判定被当成 False 不匹配，误杀运行中 Gaussian、
> 放行第二个任务）与 1 Major（adopted job 后续轮询只用裸 pid_alive、不做实例校验）。

| 编号 | 问题 | 修复位置 | 做法 | 验证 |
|------|------|----------|------|------|
| **R9a** | `_adopt_or_finalize` 用 `if alive and same_instance:`，把 `pid_is_same_instance` 返回的 None（创建时间缺失/取不到=不可判定）当成不匹配，落入 finalize，误判运行中 Gaussian 结束、不重占 lease，导致第二个 Gaussian 被放行 | `job_manager._adopt_or_finalize()` | 三态显式：`same_instance is False` 才按复用 finalize；True 正常 adopt；**None 保守视为仍运行**，同样 adopt+acquire 并记 warning | 隔离：alive+None → adopted=1/acquire=True/running；alive+False → finalize/不acquire；alive+True → adopt |
| **R9b** | adopted job（无 Popen handle）在 `_finalize_if_dead` 中只看裸 pid_alive，原 Gaussian 退出后 PID 被复用时，会把无关新进程当成原进程存活，lease 长期不释放 | `job_manager._finalize_if_dead()` | pid_alive 为真时再 `pid_is_same_instance`；明确 False 才落终态释放 lease；True/None 保守 return False 保持 lease | 隔离：inst=None → return False/running；inst=False → return True/落 failed |

### 第九轮本地验证
- 后端 24 个 `.py` `py_compile` FAIL=0。
- TestClient：health 200、匿名 shutdown 403。
- 隔离：R9a 三态（None 保守运行、False 复用结束、True 正常接管）与 R9b 后续轮询实例判定均符合预期。
- 已闭环 R1/R2/R3/R4/R5a/R5b/R5c/R7/R8/R9 未改动，保持上轮结论。

---

## 十三、第十轮修复对照（has_running 复用实例三态）

> 基线：第九轮"有条件交付"，串行安全已闭环，剩 has_running() 用裸 `pid_alive()` 短路、
> PID 复用时永久判 running、队列卡死且与 get_job() 路径状态不一致。

| 编号 | 问题 | 修复位置 | 做法 | 验证 |
|------|------|----------|------|------|
| **R10** | `has_running()` 对持久化 running job 先 `if self._pid_alive(j.pid): return True`，PID 被其他程序复用时根本不进入 `_finalize_if_dead()` 的实例三态判断，永久判 running、lease 不释放，且与 get_job() 落终态不一致 | `job_manager.has_running()` | 删除裸短路，统一调 `self._finalize_if_dead(j)`；它返回 False（仍运行/不可判定）才算占用，明确 PID 复用或已退出则落终态释放 lease、返回 False | 隔离：inst=False → has_running=False/落 completed/release；inst=True → True/running；inst=None → True/保守占用 |

### 第十轮本地验证
- 后端 `job_manager.py` `py_compile` FAIL=0。
- TestClient：health 200、匿名 shutdown 403。
- 隔离：has_running 三态（False 复用落终态、True 正常占用、None 保守占用）符合预期。
- 已闭环 R1/R2/R3/R4/R5a/R5b/R5c/R7/R8/R9/R9a/R9b 未改动，保持上轮结论。

---

## 十四、第十一轮修复对照（GJF 末尾空行边界）

> 实机 smoke 时发现：提交的 GJF 经 `_normalize_chk`（splitlines + join）后末尾空行被吞掉，Gaussian L101 报 `End of file in ZSymb. Error termination`。fail-closed 正确（标 failed 不假报 completed），但化学链跑不通。

| 编号 | 问题 | 修复位置 | 做法 | 验证 |
|------|------|----------|------|------|
| **R11** | `_normalize_chk` 用 `content.splitlines()` 再 `"\n".join()`，吞掉 GJF 末尾空行；Gaussian 要求坐标块后留一个空行结束，否则 ZSymb EOF | `job_manager.submit()` 写盘前 | `content = content.rstrip("\n") + "\n\n"`，规范为坐标行后恰好一个空行；写盘用 `newline="\n"` | 实机：H2O HF/6-31G* 单点 → `Normal termination of Gaussian 16`，HF=-76.0105 Hartree，后端 status=completed |

### 第十一轮本地验证
- `py_compile` FAIL=0。
- 实机 H2O 任务：Normal termination、0.3s 完成、状态正确收敛到 completed。
- onedir runtime 已重打（2055 文件，exe mtime 2026-10-21 15:12）。

---

## 十五、DSH 前端激活修复（R12，Cordis 插件契约）

> 静态后端已交付，插件装入 DSH 后激活失败。本轮解包 DSH 自带 cordis 源码定位真实加载契约，对照可正常工作的 `@aifs/dsh-plugin-aifs` 修正前端入口。

| 编号 | 问题 | 修复位置 | 做法 | 验证 |
|------|------|----------|------|------|
| **R12a** | 激活报 `cannot get property "tools" without inject`。`cordis-plugin-loader.unwrapExports` 优先取 `module.default` 作为插件对象，Cordis 再从该对象读 `plugin.inject`；原 `export default { name, apply }` 缺 inject，仅 named `export const inject` 被忽略，fiber.inject 为空 | `src/index.js` 入口 | `export default { name, inject, apply }`，把 `inject = ["tools","systemPrompt"]` 一并挂进 default 对象；named export 保留 | `scripts/verify_plugin_shape.mjs` 按 DSH 真实加载路径取值，断言 inject 含 tools/systemPrompt、apply 为函数、name 存在，PASS |
| **R12b** | 修 R12a 后 web boot 崩 `duplicate factory registration for "gaussian-dsh"`：index.js 的 `name` 与 client.js 的 `__ModuleLoader__.load({id:"gaussian-dsh"})` 同名撞注册 | `src/client.js` | client 模块 id 改为完整包名 `@gaussian/dsh-plugin-gaussian`（与 aifs 一致），与后端 cordis 短名区分 | 重启后 duplicate 报错消失，client 状态页正常注入 |
| **R12c** | DSH profile 的 `node_modules\@gaussian\dsh-plugin-gaussian` 是 pnpm install 时复制的整份快照（非软链），改 `lib/` 后 DSH 仍读旧副本 | 部署步骤 | 每次重打前端后，把 `lib/index.js`、`lib/client.js` 同步覆盖到该快照目录 | 部署后核对快照内文件含 inject 声明、id 为包名 |

### 第十二轮本地验证
- `node --check lib/index.js` 通过；`verify_plugin_shape.mjs` 断言 PASS。
- 未改动后端 Python 与 onedir runtime；本轮仅前端 `src/index.js`、`src/client.js`。
- 备份：`docs/backups_20261021_rework11/`（修复前 `src/index.js`、`src/client.js`、`lib/index.js`、`lib/client.js`）。

---

## 十六、R13：插件未进 profile bundles，状态卡不进内置区（DSH 装载配置）

> **现象**：R12 修好 tools inject 后，`without inject` 警告与 duplicate factory 崩溃均消失，但 gaussian 开关虽开，内置插件区始终不出现 aifs 那样的中文状态卡，只在“已安装插件”区显示原始包名与英文 description。

### 16.1 根因（解包 DSH 自带 cordis / app-boot 源码实证，不采信自述）

机制链条（`@deepseek-ai/dsh-app-boot/lib/index.js`）：
- 491–497 行注释：profile 树由 **`dsh.profile.bundles` 顺序**逐个应用各包 `dsh.bundle.patch`，再叠加 profile 自身 `cordis.patch.yml`。
- 1016 行：`bundles = manifest.dsh.profile.bundles ?? []`；1020–1034 行只对列表内每个 bundle 解析目录、读 `dsh.bundle`、读其 patch 文件组成 layer；1035–1039 行失败记入 `skippedBundles`。
- 1042 行：profile 自己的 `cordis.patch.yml` 作为 user layer 最后叠加。
- `@deepseek-ai/dsh-client-modules/lib/index.js` 855 行：`entry.fiber === void 0 || entry.disabled` 即跳过，不扫描 client half；bundle 不在列表 → 其 `cordis.patch.yml`（insert `id: gaussian, name: '@gaussian/dsh-plugin-gaussian'`）从未进入 host loader → 后端 entry 不存在 → client-modules 无 entry 可发现 → `lib/client.js` 不进前端图 → 内置区无 `plugins.item` 卡片。

实测 profile 现状（修复前）：
- `profiles/desktop/package.json` 的 `dsh.profile.bundles` 仅含 `dsh-base`、`dsh-web-app`、`@aifs/dsh-plugin-aifs`；`@gaussian/dsh-plugin-gaussian` 只在 `dependencies`、不在 `bundles`（与灰色未激活的 `@autorest/...` 同病）。
- `profiles/desktop/cordis.patch.yml` 残留一条 `- id: gaussian, disabled: true`：即使补进 bundles，这条 user-layer 禁用也会把 entry 关掉。

### 16.2 改动（不改业务逻辑，仅修正 profile 装载配置；改前已备份）

| 编号 | 问题 | 改动位置 | 做法 |
|------|------|----------|------|
| **R13a** | gaussian 未列入 bundles，自带 patch 未进 host loader | `C:\Users\Administrator\.dsh\profiles\desktop\package.json` | `dsh.profile.bundles` 末尾追加 `"@gaussian/dsh-plugin-gaussian"`，与 aifs 并列 |
| **R13b** | user patch 残留 `disabled: true`，会禁用 entry | `C:\Users\Administrator\.dsh\profiles\desktop\cordis.patch.yml` | 删除 `- id: gaussian / disabled: true` 段，保留三条官方 UI 设置覆盖 |

备份（修复前原文件，便于回滚）：`docs/backups_20261021_rework11/profile_package.json.bak_20261021`、`profile_cordis.patch.yml.bak_20261021`。

### 16.3 离线验证（未启动 DSH，复刻 DSH 解析链；aifs 作对照）

- `docs/_verify_chain.mjs`：以 profile `package.json` 为 anchor，用 `createRequire` 复刻 `resolveBundleDir` + `resolveMeta` 路径，逐项断言 package.json 可解析、`dsh.bundle.patch` 文件存在、`dsh.client.platform === "web"`、`exports["./client"]` 与 main 入口文件存在。
- 结果：aifs 与 gaussian 两条链 **ALL PASS**，manifest 字段完全对齐；兼容性 `evaluatePluginCompatibility` 只认 `engines.dsh` / `peerDependencies` 中 `@deepseek-ai/dsh*`，本插件未声明即放行，不会被 skip。
- 快照产物复核：`lib/index.js`（34581 B，default=`{ name, inject, apply }`）、`lib/client.js`（6005 B，模块 id=完整包名，注册 `plugins.item`）、`cordis.patch.yml` 均在位。

### 16.4 待实机确认（本轮无法在不重启 DSH 的前提下完成）

重启 DSH 桌面端后需观察：内置插件区出现“Gaussian 计算助手 / 生成输入、解析输出、管理任务、检索知识库。”中文卡；后端 entry 激活、`gaussian_status` 等工具在新对话可用。若卡片仍不出现，需在渲染进程 DevTools console 或最新 `crash-*-web-boot.log` 取 gaussian 条目报错，按 `client-modules` / `cordis-client-runner` 报告定位（不在本轮静态结论内臆断）。

> 备注：状态卡详情页当前直连 `http://127.0.0.1:8765/v1/status`（aifs 走 host 内 `/api/aifs/*` 代理）。summary 卡片不发起请求，不影响卡片出现；详情页跨域显示问题留待实机出现后再收口，本轮不扩大重构范围。

---

## 十七、R14：工具缺 output 声明导致 entry 激活失败（DSH 新版工具契约）

> **现象**：R13 重启后内置区已出现"Gaussian 计算助手"卡片，但启动期黄条报错 `tool "gaussian_status" must declare output { schema, render, presentationMeta? }`；entry 在第一个工具处中断，按顺序其余 17 个工具也全部未注册。

### 17.1 根因（解包 `@deepseek-ai/dsh-tools` 源码实证）

- 校验位置：`dsh-tools/lib/types/index.js:471–481` 与 `lib/index.js:2977–2982`。`tools.register(definition)` 依次校验：`output` 必须是对象；`output.render` 必须是函数；`output.presentationMeta` 若存在必须是函数；随后 `assertSupportedJsonSchema(output.schema)` 校验结构；`timeoutMs` 若存在必须为正有限数。
- 执行期 `createSuccessResult`（`lib/index.js:3637–3667`）：先 snapshot 工具值 → 按 `output.schema` 做结构校验（违规抛 `ToolOutputError`）→ 调 `output.render(exec.arguments, value)` → snapshot 投影要求返回可无损 JSON；`presentationMeta(args, value)` 可选。
- 旧 `defineTool` 只产出 `{ name, description, parameters, timeoutMs, execute }`，没有 `output`，因此被整条拦下。
- schema 子集（`types/json-schema.js`）：标量 type 仅 `object/array/string/number/integer/boolean/null`，**无 `type:"json"`**；空对象 `schema: {}` 为 annotation-only，等于任意可无损 JSON；允许关键字 type/oneOf/properties/required/additionalProperties/items/enum/const 加注释类；type 与 oneOf 不能并存。

### 17.2 改动（最小改动，不动业务逻辑；改前已备份）

| 编号 | 问题 | 修复位置 | 做法 | 验证 |
|------|------|----------|------|------|
| **R14** | 18 个工具均缺 `output`，register 校验在 `gaussian_status` 处中断、entry 整体未激活 | `src/index.js` `defineTool()` 工厂 | 新增 `defaultRenderJson`（返回 `[{ type:"text", text: JSON.stringify(value) }]`）；统一兜底 `output = { schema: options.output?.schema ?? {}, render: options.output?.render ?? defaultRenderJson, ...(presentationMeta 为函数时带上) }`；18 个工具 options 逐个无需改动，将来要自定义渲染可在 `options.output` 覆盖 | 离线契约自测 18/18 PASS |
| **R14b** | 崩溃恢复后 gaussian 被摘出 `dsh.profile.bundles`，R13a 配置回退 | `profiles/desktop/package.json` | 改前备份 `.bak-20261021-r14`；把 `@gaussian/dsh-plugin-gaussian` 追加回 bundles（base/web-app 在前），不改动 aifs/autorest | `verify_profile_bundle.mjs`、toolkit `verify_plugin_manifest.mjs` 离线 PASS |
| **R14c** | 系统提示 `GAUSSIAN_GUIDANCE` 工具列表只列 13 个，漏列 4 个后处理工具，模型可能不知道后处理工具存在（不阻断注册） | `src/index.js` 提示词文本 | 工具列表补齐到 18 个（补 `postprocess_capabilities`/`create_postprocess_task`/`get_postprocess_task`/`list_postprocess_tasks`）；仅文本对齐，不动业务逻辑；改前备份 `src_index.js.bak_20261021-r14b` | 重打 `lib/index.js`（35,104 B），快照哈希一致，契约自测仍 18/18 PASS |
| **R14c-doc** | README 配置表环境变量名与代码实读集合脱节：误写 `EXPECTED_MULTIWFN_VERSION`（实读 `MULTIWFN_EXPECTED_VERSION`），漏列后端 HOST/DATA_DIR/MANAGED_TOKEN/线程/GC TTL/RSS 阈值/BSE 基址与前端 managed 模式变量；安装段未说明 bundles 登记、快照非软链、完全退出重启 | `README.md` | 逐一比对 `backend/config.py`、`src/index.js` 真实 `getenv`/`process.env` 读取集合后修正变量名、补齐两张配置表、改写安装流程；仅改文档，不动业务逻辑；改前备份 `README.md.bak_20261021-r14c` | verifier `text must-contain` 4/4 命中；打包后解压复核 README 新表与 18 工具齐全、错误变量名已清除 |

备份：`docs/backups_20261021_rework12/`（修复前 `src/index.js`、`src/client.js`、`lib/index.js`、`lib/client.js`）；profile 备份 `package.json.bak-20261021-r14`、`cordis.patch.yml.bak-20261021-r14`。

### 17.3 本地验证（未启动 DSH）

- `node scripts/build.mjs` 重打 `lib/index.js`（R14 契约修复后 35,007 B、R14c 提示词补齐后最终 35,104 B，旧 34,581 B）；`lib/client.js`（6,005 B）本轮未变；两个文件覆盖到 profile 快照，`node --check` exit 0，根目录与快照 SHA256 一致。
- `docs/_verify/output_contract_check.mjs`：设 `GAUSSIAN_BACKEND_MODE=external`，import 打包后 `lib/index.js`，mock `ctx.tools.register/systemPrompt.section/effect/inject`，走真实 `plugin.default.apply(ctx)` 收集 18 个工具，复用解包 dsh-tools 的 `assertSupportedJsonSchema` 复刻 register 校验（output 对象、render 函数、presentationMeta 函数、schema 合法、默认 render 对样例对象可无损序列化、timeoutMs 正数）；结果 18/18 CONTRACT PASS。
- 后端 24 个 `.py` `py_compile` FAIL=0（本轮未改后端，无需重打 onedir exe）；`verify_plugin_shape.mjs` PASS；`verify_profile_bundle.mjs` PASS；toolkit `verify_plugin_manifest.mjs` PASS。

### 17.4 待实机确认（本轮无法在不重启 DSH 的前提下完成）

完全退出 DSH 再启动后观察：启动黄条消失；内置区"Gaussian 计算助手"卡片；新对话内 18 个工具（`gaussian_status`、`submit_gaussian_job` 等）可直接调用；managed 后端自动拉起/受控退出。若 bundles 再次被崩溃恢复批量摘除，按 LESSONS_LEARNED 第 31 条回溯 DSH 崩溃保护逻辑。

