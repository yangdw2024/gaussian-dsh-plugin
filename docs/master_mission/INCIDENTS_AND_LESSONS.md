# 工程事件与经验教训 (INCIDENTS_AND_LESSONS)

## INC-001: `backend/config.py` 类属性重复定义导致 `_default_data_dir()` 被静默覆盖
- **发现阶段**: Phase 0 静态审计
- **位置**: `backend/config.py` L42 与 L66
- **问题**: 第 42 行定义为 `_default_data_dir()`，第 66 行又定义了同名 `data_dir` 类字段，覆盖了原有跨平台默认路径逻辑。
- **对策**: 在 Phase 2 收敛为单一 `data_dir` 字段并加单元测试锁定行为。

## INC-002: `backend/postprocess/manager.py` 定义了 Cube 体积限额检查但未在执行前调用
- **发现阶段**: Phase 0 静态审计
- **位置**: `backend/postprocess/manager.py` L111 与 L253–L360
- **问题**: `verify_cube_within_limit()` 存在但未接入 `run_task()` 渲染前链路，大体积 `.cub` 可能耗尽 VMD 内存或引发卡死。
- **对策**: Phase 2 强制在 `run_task()` 生成 VMD 脚本前校验所有输出 cube 文件大小，超限直接拦截失败。

## INC-003: `backend/app.py` 后处理后台线程异常处理属性错误
- **发现阶段**: Phase 0 静态审计
- **位置**: `backend/app.py` L756–L760
- **问题**: `postprocess_manager.get_task(tid)` 返回 `dict`，随后却访问 `t.status` 并调用期望 `PostprocessTask` 的 `_save(t)`，导致异常兜底逻辑自身抛错失效。
- **对策**: 在 Phase 2 改用 `_load(tid)` 并补充失败态兜底单测。

## INC-004: `backend/structure_reader.py` 元素表不完整与临时目录泄漏
- **发现阶段**: Phase 0 静态审计
- **位置**: `backend/structure_reader.py` L37–L42, L127–L144, L186
- **问题**: `_ATNUM_MAP` 仅涵盖 29 个常见元素且未知原子回落为 `"C"`（严重误判过渡金属/配体！）；`_coords_to_xyz()` 泄漏 `mkdtemp` 临时目录；`_obabel_to_smiles()` 缺少 `stdin=DEVNULL, close_fds=True`；`natoms_guess` 固定返回 `None`。
- **对策**: Phase 2 补齐 1–118 周期表映射、清理临时目录、统计真实 `natoms_guess`。

## INC-005: `LongPathsEnabled=0` 下 `runtimes/win32-x64` 子文件深度接近 Windows 极限
- **发现阶段**: Phase 0 实测
- **现象**: 宿主机注册表 `LongPathsEnabled = 0`；包内 `rdkit\Contrib\NIBRSubstructureFilters\...`、`numpy-2.5.0.dist-info\licenses\...` 等路径本身已超 110 字符，嵌套至用户目录 + DSH `.generations\live\<pkg>` 时极易击穿 260 字符限制。
- **对策**: Phase 6 对 PyInstaller 产物裁剪冗余许可证/Contrib 数据并校验安装树最大路径 `< 260`。

## INC-006: Phase 0 外层测试包裹命令返回退出码 1
- **发现阶段**: Phase 0 实测
- **现象**: `py312 -m unittest discover -s tests -v` 打印 `Ran 79 tests in 40.346s — OK`，但组合命令退出码为 1。
- **对策**: Phase 1 使用 `-NoProfile` 与干净进程直接重跑并保存原始日志文件及确切退出码。

## INC-007: `backend/gaussian_output.py` `Alpha occ./virt.` `\s+` 跨行误匹配 `Excited State` 崩溃
- **发现阶段**: Phase 3 科学边界实测
- **现象**: 解析 TD-DFT 日志时，`Alpha virt. eigenvalues --((?:\s+-?[\d.Ee+]+)+)` 因 `\s+` 匹配换行符并吞入下一行 `Excited` 的首字母 `'E'`，导致 `float('E')` 抛出 `ValueError` 崩溃。
- **对策**: 将 `\s+` 严格收敛为单行水平空白 `[ \t]+`，使用严格数字模式 `-?\d+(?:\.\d+)?(?:[Ee][+-]?\d+)?` 并纳入 `test_02_homo_lumo_gap_vs_tddft_excited_states` 回归测试。

## INC-008: 多步 `Link1` 第 1 步完成后第 2 步出错或截断漏判 `incomplete_multistep`
- **发现阶段**: Phase 3 科学边界实测
- **现象**: Step 1 `Normal termination` 后通过 `--Link1--` 进入 Step 2 但发生 `Error termination` 时，日志中若未重复打印 `Entering Link 1`，原判定未置 `incomplete_multistep=True` 与 `route_steps=2`。
- **对策**: 联合统计 `--Link1--`、`Entering Link 1` 与 `#` Route 行定位最后步骤及误差位置，已由 `test_10_incomplete_multistep_link1_and_truncated_log` 验证通过。

## INC-009: Phase 4 HTTP `/v1/gaussian-outputs/parse` 缺 `approvals` 封锁与大日志 OOM 阈值及 `settings.max_log_size_mb` 误假设
- **发现阶段**: Phase 4 安全审计与回归验证
- **现象**: (1) `api_parse_output` 与 `api_extract_structure` 直接读取 `req.file_path`，未封锁 `<data_dir>/approvals` 且无 100MB 体积上限；(2) 初版补丁假定 `Settings` 拥有 `max_log_size_mb` 字段导致 `AttributeError`（实际仅 `mcp_server.py` 硬编码 100MB）。
- **对策**: 改用 `int(os.environ.get("GAUSSIAN_MAX_LOG_SIZE_MB", "100"))` 并抽取 `_guard_http_read_path()`，经 `test_04_http_parse_approvals_blocked_and_oom_size_guard` 实测返回 `403` 与 `413`。
