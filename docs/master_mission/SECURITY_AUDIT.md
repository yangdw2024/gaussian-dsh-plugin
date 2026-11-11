# 安全与稳定性深度审计报告 (SECURITY_AUDIT)

> **当前状态**：`PASS`（Phase 4 全链审计完成，修复 6 类实质隐患并通过对抗回归验证）  
> **验收基线**：`py312 -m unittest discover -s tests -v` -> **106/106 测试全部通过 (`EXIT=0`, 34.167s)**（含 `tests/test_security_phase4.py` 7 项、`tests/test_v52_auth_adversarial.py` 7 项、`tests/test_execution_authorization.py` 8 项、`tests/test_security.py`、`tests/test_cross_process_scheduling.py` 4 项、`tests/test_v52_compiled_cross_process.py` 5 项）。

---

## 一、全链 16 大安全与稳定性控制面核查矩阵

| 序号 | 审计维度 | 核心模块 / 源码证据 | Phase 4 加固措施与实测验证 | 状态 |
| :---: | :--- | :--- | :--- | :---: |
| `1` | 读写/缓存目录隔离与路径穿越 | `backend/security.py` (`validate_safe_path`, `get_allowed_*_roots`) | 仅开放 `work_dir` 可写、`cache` 限 `~/.gaussian-dsh/basis_cache`、`approvals/` 永久禁止读/写 (`test_security.py`) | `PASS` |
| `2` | Windows NTFS Junction / 符号链接逃逸 | `backend/security.py` (`Path.resolve()`) | 在真实 Windows 下用 `cmd /c mklink /J` 创建指向工作区外目录的 NTFS Junction，`validate_safe_path` 成功解析并触发 `PermissionError` (`test_security_phase4::test_01`) | `PASS` |
| `3` | Windows ADS / UNC / DOS 保留设备名防护 | `backend/security.py` (`_check_windows_path_hazards`) | Phase 4 新增拦截 `foo.gjf:hidden` ADS、禁止 `\\server\share` UNC（防 NTLM 凭据泄漏）及 `NUL`/`CON`/`COM1` 等保留设备名 (`test_security_phase4::test_02`) | `PASS` |
| `4` | 子进程调用安全与句柄防泄漏 | `backend/process_utils.py`, `postprocess/multiwfn.py`, `structure_reader.py` | 全仓库静态扫描验证 **0** `shell=True` / `os.system` / `eval` / `exec` / `yaml.load` / `pickle.loads`；Phase 4 为 `taskkill`/`tasklist` 补齐 `CREATE_NO_WINDOW`、`stdin=DEVNULL` 及 `pid > 0` 防 POSIX 负 PID 误杀进程组 (`test_security_phase4::test_07`) | `PASS` |
| `5` | GJF Link0 / Route CRLF 注入与 `%chk` 穿越 | `backend/gaussian_input.py` (`generate_gjf`, `validate_gjf`) | Phase 4 新增拒绝 `mem`/`chk`/`method`/`basis`/`extra_keywords` 换行控制字符、折叠 `title` 换行、禁止 `chk` 含 `..`/`/`/`\` 及 `nproc <= 0` (`test_security_phase4::test_03`) | `PASS` |
| `6` | `GAUSSIAN_ALLOW_REAL_EXECUTION` 默认策略与重放防护 | `backend/execution_policy.py`, `scripts/approve_gaussian_job.py` | 默认 `false`；消费型 `human_approval_token` 与 `nonce` 单次失效，重放与跨任务劫持均被拦截 (`test_v52_auth_adversarial::test_05,07`) | `PASS` |
| `7` | HMAC-SHA256 完整性 vs 人工审批绑定区分 | `backend/execution_policy.py` | `integrity_token` 与 `human_approval_token` 密码学角色严格隔离；任何坐标、`%mem` 或 `nproc` 篡改均触发校验失败 (`test_v52_auth_adversarial::test_06`) | `PASS` |
| `8` | Agent 自签权限禁止替代人工授权 | `backend/mcp_server.py`, `backend/execution_policy.py` | `confirmed=True + integrity_token` 被 `human_authorization` 层明确拒绝；MCP Server 不暴露任何签发或管理员工具 (`test_v52_auth_adversarial::test_02`) | `PASS` |
| `9` | HTTP `/v1/*` 本地回环、CORS 与管理端鉴权 | `backend/app.py` (`CORSMiddleware`, `_require_admin`, `_guard_http_read_path`) | 监听 `127.0.0.1`、`allow_credentials=False` + 本地端口正则；Phase 4 在 `/v1/gaussian-outputs/parse` 与 `/v1/structure/extract` 补齐 `approvals/` 封锁 (`403`) (`test_security_phase4::test_04`) | `PASS` |
| `10` | 跨进程资源调度互斥与竞争条件 | `backend/resource_scheduler.py` | OS 文件锁 (`msvcrt.locking` / `fcntl.flock`) + 全局 lease JSON；PyInstaller 编译 exe 与 MCP stdio 并发突发仅放行 1 个任务 (`test_v52_compiled_cross_process`) | `PASS` |
| `11` | PID 复用检测与任务状态机一致性 | `backend/process_utils.py`, `backend/job_manager.py` | `pid_create_time` 比对防 PID 复用误杀；跨进程撤单保持 `stopped` 终态不可回退 (`test_cross_process_scheduling`) | `PASS` |
| `12` | 大日志 OOM 与正则跨行 ReDoS 防护 | `backend/app.py`, `backend/mcp_server.py`, `backend/gaussian_output.py` | Phase 4 为 HTTP `/v1/gaussian-outputs/parse` 补齐与 MCP 对齐的 100MB 上限校验 (`413`) (`test_security_phase4::test_04`)；Phase 3 已收敛 `[ \t]+` 单行匹配 | `PASS` |
| `13` | 后处理 Cube 体积、文件名消毒与 VMD Tcl 安全 | `backend/postprocess/manager.py`, `backend/postprocess/vmd.py`, `templates/*.tcl` | 审计确认 3 个 `.tcl` 模板全部使用 `[lindex $argv ...]` 且无 `eval`/拼接命令；`verify_cube_within_limit` 全路径生效 | `PASS` |
| `14` | 恶意 SMILES 复杂度与内存阈值限流 | `backend/smiles/rdkit_builder.py`, `backend/memory_guard.py` | Phase 4 在 `Chem.MolFromSmiles` 前增加 2000 字符上限硬拦截 (`test_security_phase4::test_06`)；结合 `max_atoms` 与 RSS Hard Guard 防内存耗尽 | `PASS` |
| `15` | Mock 与真实量化结果强制隔离 | `backend/gaussian_output.py`, `backend/mock_worker.py` | `[MOCK_GAUSSIAN_SIMULATION]` 等 6 项横幅下强制 `is_simulated=True`, `final_energy=None` | `PASS` |
| `16` | Artifact GC 安全与崩溃恢复 (`reconcile`) | `backend/artifact_gc.py`, `backend/job_manager.py` | Phase 4 为 GC 增加 `is_symlink()` 跳过与 `data_dir.resolve()` 归属校验 (`test_security_phase4::test_05`)；优雅停机保留正在运行的仿真子进程 | `PASS` |

---

## 二、Phase 4 静态全量扫描核验记录

- 对 `backend/`, `src/`, `scripts/` 全量 `.py` / `.js` / `.mjs` 执行模式扫描（`shell=True`, `os.system`, `eval(`, `exec(`, `yaml.load`, `pickle.loads`, `0.0.0.0`, `allow_origins`）：
  - **全部命中数为 0**；仅存在安全白名单 `CORSMiddleware(allow_origin_regex=...)`（`127.0.0.1` / `localhost` / `app://`）与显式带 `CREATE_NO_WINDOW` 的子进程调用。
