# Gaussian MCP 工程演进：问题排查与经验教训 (Issues & Lessons)

本文档客观记录阶段一审计至 V5.1 工程收尾过程中遭遇的实际问题、根本原因分析 (RCA) 与架构级应对策略（所有机密及本机个人目录已脱敏）。

---

## 1. 运行环境与权限沙箱陷阱

### 问题 1.1: 受限 Miniconda 环境触发 `PermissionError: [Errno 13]`
- **现象**：早期审计阶段使用 IDE 沙箱目录下的 Miniconda (`<SANDBOX_MINICONDA>\python.exe`) 运行测试时，多次遭遇临时目录创建失败、无法写入文件，以及 `_ssl` / `_ctypes` DLL 加载异常。
- **根本原因 (RCA)**：该解释器路径处于 IDE 施加了严格 ACL 策略（`Deny DeleteSubdirectoriesAndFiles`）的受限环境中，导致测试临时目录写入及部分标准库加载异常。
- **解决方案与教训**：
  1. 严格区分“受限宿主工具环境”与“干净的系统/用户级 Python 3.12 运行环境”。
  2. 全量开发与自动化验收统一使用独立标准的 Python 3.12 环境 (`<USER_HOME>\AppData\Local\Programs\Python\Python312\python.exe`) 与虚拟环境锁定依赖 (`requirements-mcp.txt`)。

---

## 2. 外部知识库与进程阻塞

### 问题 2.1: `diagnose_gaussian_error` 早期版本耗时超 90 秒导致测试挂起
- **现象**：初版协议测试中，调用 `diagnose_gaussian_error` 长时间无响应并最终超时。
- **根本原因 (RCA)**：`sobko_client.py` 检测到本地配置目录 (`<EXTERNAL_SOBKO_DIR>`) 后试图探测未启动的外部子服务，引发长超时阻塞。
- **解决方案与教训**：
  1. **区分核心确定性能力与可选外部服务**：错误诊断默认走基于 `backend/keywords.py` 的纯本地瞬时匹配（<0.05s 返回），仅在显式请求且外部服务就绪时才查询外部知识库。

---

## 3. 路径安全沙箱：读写、缓存与人工授权隔离

### 问题 3.1: 初版安全校验未区分只读、只写与敏感授权存储区
- **现象**：首版单一白名单若配置不当，可能导致 Agent 通过 `.gjf` 输出覆盖源码仓库文件或读取受保护配置。
- **根本原因 (RCA)**：缺少按操作语义分离的根目录约束与拒绝清单。
- **解决方案与教训**：
  1. 在 `backend/security.py` 中实现 `validate_safe_path(..., mode="read"|"write"|"cache")` 三态沙箱校验。
  2. **只写白名单 (`Write Roots`)** 仅限计算工作目录 (`<GAUSSIAN_WORK_DIR>`)，严禁写入源码根目录、用户主目录及系统目录。
  3. **专用缓存白名单 (`Cache Roots`)** 显式授权 `~/.gaussian-dsh/basis_cache/` 或 `GAUSSIAN_CACHE_DIR`，与科研工作目录解耦管理。
  4. **V5.1 显式拒绝区 (`approvals/`)**：即使环境变量误配包含上层父目录，`validate_safe_path` 亦显式禁止访问 `<GAUSSIAN_DATA_DIR>/approvals/`，确保 `.human_signing_key` 与人工授权凭据完全不可被 MCP 工具读写。
  5. **符号链接 / Junction 防御**：强制通过 `Path.resolve()` 在物理规范化路径上做前缀包含校验。

---

## 4. MCP Stdio Transport 协议纯净性

### 问题 4.1: `print()` 或第三方库警告污染 `stdout`
- **现象**：部分化学库默认向标准输出打印提示，导致 MCP 客户端解析 JSON-RPC 帧报 `Invalid JSON`。
- **根本原因 (RCA)**：MCP stdio 规范要求 `stdout` 专属于 JSON-RPC 2.0 协议帧。
- **解决方案与教训**：
  1. 在 `backend/mcp_server.py` 启动最前端将全局日志流强制重定向至 `sys.stderr`。
  2. 通过 `tests/test_mcp_protocol_stdio.py` 逐行验证真实子进程管道通信。

---

## 5. BSE 外部基组服务高可用性

### 问题 5.1: 外网 BSE API (`basissetexchange.org`) 高延迟或离线失效
- **解决方案**：在 `backend/basis_set.py` 建立多层级加载与容灾链路：`内存缓存 -> 本地磁盘缓存 (~/.gaussian-dsh/bse_metadata_cache.json) -> 在线 BSE API -> 内置离线字典回退`。

---

## 6. 跨进程计算资源并发竞态 (V5.1 修复)

### 问题 6.1: DSH Backend 与 MCP Server 运行在独立 OS 进程，内存锁无法跨进程互斥
- **现象**：V5.0 阶段 `ChemComputeScheduler` 仅使用进程内 `threading.Lock()` 与内存变量 `_lease`。DSH FastAPI 进程与独立启动的 MCP Server (`stdio`) 进程各自维护一份内存状态，存在双端并发突破单任务串行限制、及终止状态互覆的风险。
- **根本原因 (RCA)**：缺少跨 OS 进程的内核排他锁、共享租约状态文件及终态优先级裁决。
- **解决方案与教训 (V5.1)**：
  1. 重构 `backend/resource_scheduler.py`，使用 `msvcrt.locking` (Windows) / `fcntl.flock` (POSIX) 加锁 `<data_dir>/compute_lease.lock`，配合原子写入 `<data_dir>/compute_lease.json` 记录 `holder_pid`、`holder_pid_start_time` 与 `host_client`。
  2. 持锁进程意外崩溃时自动安全回收失效租约；若属于意在保留的运行中 `g16` 子进程（如 `admin_shutdown`），则继续保留租约阻止并发冲突。
  3. `backend/job_manager.py` 在获取跨进程锁后执行 `has_running()` 二次复查，并在 `_finalize_if_dead()` / `get_job()` / `stop_job()` 中优先采纳磁盘终态，防止一端覆盖另一端写入的 `stopped` 状态。

---

## 7. 执行授权混淆与一次性 Nonce 文件名正则缺陷 (V5.1 修复)

### 问题 7.1: 预检文件完整性令牌与人工任务授权界限模糊
- **根本原因 (RCA)**：V5.0 中 `dry_run=True` 自动生成单一 HMAC token，Agent 可自行拿到该 token 并传 `confirmed=True`，与"人工复核"的信任域未隔离。
- **解决方案与教训 (V5.1)**：
  1. 在 `backend/execution_policy.py` 中严格拆分三层独立授权：`Layer 1 (integrity_token)`、`Layer 2 (GAUSSIAN_ALLOW_REAL_EXECUTION)`、`Layer 3 (human_approval_token / 受信任宿主签发凭据)`，域分离签名密钥且禁止将 `integrity_token` 或 `confirmed=True` 冒充人类审批。
  2. 通过独立 CLI (`scripts/approve_gaussian_job.py`) 和受 `_require_admin` 保护的 `POST /v1/admin/jobs/approve` 签发一次性人工凭据，永不暴露为 `@mcp.tool()`。

### 问题 7.2: Raw string 双反斜杠导致 nonce 防重放标记与凭据文件名全变下划线
- **发现过程**：V5.1 自动化测试 (`test_05_mcp_path_sandbox_blocks_approval_secrets_and_grants`) 立即暴露了 `receipt_path` 与期望路径不匹配的问题。
- **根本原因 (RCA)**：`backend/execution_policy.py` 中第 269 行与第 375 行误写 `r'[^\\w.-]'`（raw string 中双反斜杠匹配字面 `\` 和 `w` 而非 `\w`），导致 `preflight_id` 与十六进制 `nonce` 字符被全部替换成 `_`，可能造成不同一次性凭据冲突映射到同一 `.used` 文件。
- **修复**：立即修正为 `r'[^\w.-]'`，并通过多轮授权与重放测试全通验证。
