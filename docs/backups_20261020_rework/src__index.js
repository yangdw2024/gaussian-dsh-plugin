/**
 * Gaussian DSH Plugin — Cordis 前端插件
 *
 * 基于 AIFS 插件架构（@aifs/dsh-plugin-aifs）开发，辅助 Gaussian 计算：
 * 输入生成、输出解析、任务管理、BSE 基组获取、Sobko 知识库检索、关键词参考、错误诊断。
 *
 * 后端：Python FastAPI（默认 http://127.0.0.1:8765）
 */

// ============ 后端 HTTP 客户端 ============

const SERVICE_NAME = "gaussian-dsh-backend";
const SERVICE_VERSION = "0.2.0";

class GaussianClient {
  /**
   * @param {string|((signal?: AbortSignal) => Promise<string>|string)} baseUrlResolver
   *        固定 URL，或异步解析器（managed 模式等后端就绪后返回 baseUrl）
   */
  constructor(baseUrlResolver, timeoutMs = 30000, maxResponseBytes = 1048576) {
    this.resolveBaseUrl = typeof baseUrlResolver === "function"
      ? baseUrlResolver
      : async () => String(baseUrlResolver ?? "http://127.0.0.1:8765");
    this.timeoutMs = timeoutMs;
    this.maxResponseBytes = maxResponseBytes;
  }

  async workflow(method, path, body, signal) {
    const baseUrl = (await this.resolveBaseUrl(signal)).replace(/\/$/, "");
    const url = `${baseUrl}${path}`;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeoutMs);
    if (signal) signal.addEventListener("abort", () => controller.abort());

    try {
      const init = {
        method,
        headers: { "Content-Type": "application/json" },
        signal: controller.signal,
      };
      if (body !== undefined && body !== null) {
        init.body = JSON.stringify(body);
      }
      const response = await fetch(url, init);
      const text = await response.text();
      if (text.length > this.maxResponseBytes) {
        throw new Error(`Gaussian backend response too large: ${text.length} bytes`);
      }
      let data;
      try {
        data = text ? JSON.parse(text) : null;
      } catch {
        data = { raw: text };
      }
      if (!response.ok) {
        const detail = data?.detail || data?.error || `HTTP ${response.status}`;
        throw new Error(`Gaussian backend ${method} ${path} failed: ${JSON.stringify(detail)}`);
      }
      return data;
    } finally {
      clearTimeout(timer);
    }
  }

  get(path, signal) { return this.workflow("GET", path, undefined, signal); }
  post(path, body, signal) { return this.workflow("POST", path, body, signal); }
}

// ============ Managed 后端生命周期 ============

/**
 * 后端管理器：probe 已有服务 → reuse；managed 模式按需 spawn；
 * disposer 只关闭自己启动（owned）的进程，绝不杀 reuse 进程和正在运行的 Gaussian 子进程。
 */
class BackendManager {
  constructor(config) {
    this.config = config;
    this.owned = false;
    this.baseUrl = config.baseUrl;
    this.managedToken = null;
    this.handle = null;
    this.state = "idle";   // idle / external / reused / starting / ready / failed / stopped
    this.error = null;
    this.startAttempt = null;
  }

  async probe(baseUrl, signal) {
    try {
      const resp = await fetch(`${baseUrl.replace(/\/$/, "")}/v1/health`, {
        signal: AbortSignal.any([signal ?? new AbortController().signal, AbortSignal.timeout(3000)]),
      });
      if (!resp.ok) return null;
      const body = await resp.json();
      // 只认自己的 service 名，避免把端口上的其他进程误当后端
      if (body && body.ok === true && body.service === SERVICE_NAME) return body;
      return null;
    } catch {
      return null;
    }
  }

  /** 返回可用 baseUrl；external 模式直接返回配置 URL。 */
  async getBaseUrl(signal) {
    if (this.config.backendMode === "external") return this.config.baseUrl;
    if (this.state === "ready" && this.baseUrl) return this.baseUrl;
    if (this.startAttempt) await this.startAttempt;
    if (this.state === "ready" && this.baseUrl) return this.baseUrl;
    // 启动未就绪：再探一次（可能用户手动起了后端），失败则抛清晰错误
    const existing = await this.probe(this.config.baseUrl, signal);
    if (existing) {
      this.state = "ready";
      this.owned = false;
      return this.config.baseUrl;
    }
    throw new Error(
      `Gaussian 后端不可用（${this.state}）：${this.error || "后端未启动"}。` +
      `managed 模式请确认 runtimes 目录含 gaussian-backend.exe；` +
      `或用 external 模式配合 start_backend.bat 手动启动。`
    );
  }

  /** 启动（幂等）。subprocessService 来自 ctx.inject(["subprocess"])。 */
  start(subprocessService) {
    if (this.startAttempt) return this.startAttempt;
    this.startAttempt = this._launch(subprocessService).finally(() => {
      this.startAttempt = null;
    });
    return this.startAttempt;
  }

  async _launch(subprocessService) {
    if (this.config.backendMode === "external") {
      this.state = "external";
      return;
    }
    // 已有健康服务 → reuse，owned=false（不关闭别人的进程）
    const existing = await this.probe(this.config.baseUrl);
    if (existing) {
      this.state = "ready";
      this.owned = false;
      this.baseUrl = this.config.baseUrl;
      return;
    }
    // 没有 subprocess 能力或没有 exe：降级为 failed，不崩溃、不杀端口占用
    if (!subprocessService || typeof subprocessService.spawn !== "function") {
      this.state = "failed";
      this.error = "DSH 未提供 subprocess 服务，无法 managed spawn";
      return;
    }
    const exe = this._resolveExecutable();
    if (!exe) {
      this.state = "failed";
      this.error = "未找到 gaussian-backend.exe（runtimes/win32-x64/gaussian-backend/）";
      return;
    }
    try {
      this.state = "starting";
      this.managedToken = this._randomToken();
      const handle = subprocessService.spawn({
        argv: [exe],
        cwd: this.config.dataDir || undefined,
        stdio: { stdin: "pipe", stdout: "pipe", stderr: "pipe" },
        env: {
          GAUSSIAN_MANAGED_TOKEN: this.managedToken,
          GAUSSIAN_BACKEND_PORT: String(this._port()),
        },
        graceMs: 2000,
      });
      this.handle = handle;
      await this._waitReady(handle);
      this.owned = true;
      this.baseUrl = this.config.baseUrl;
      this.state = "ready";
    } catch (err) {
      this.state = "failed";
      this.error = String(err?.message ?? err);
      this._cleanupHandle();
    }
  }

  _port() {
    try { return new URL(this.config.baseUrl).port || 8765; } catch { return 8765; }
  }

  _randomToken() {
    if (typeof crypto !== "undefined" && crypto.randomUUID) return crypto.randomUUID();
    return `managed-${Date.now()}-${Math.floor(Math.random() * 1e9)}`;
  }

  _resolveExecutable() {
    // exe 路径由打包/runtime 约定通过 config.backendExe 注入
    return this.config.backendExe || null;
  }

  async _waitReady(handle) {
    const timeoutMs = this.config.startupTimeoutMs ?? 30000;
    const deadline = Date.now() + timeoutMs;
    let delay = 500;
    while (Date.now() < deadline) {
      await new Promise((r) => setTimeout(r, delay));
      delay = Math.min(delay * 1.5, 3000);
      const body = await this.probe(this.config.baseUrl);
      if (body) return;
      if (handle.done) {
        throw new Error("后端进程在就绪前退出，请查看后端日志");
      }
    }
    throw new Error(`后端启动超时（${timeoutMs}ms）`);
  }

  _cleanupHandle() {
    if (this.handle) {
      try { this.handle.terminate?.(); } catch { /* ignore */ }
      this.handle = null;
    }
  }

  /** disposer：只关闭 owned（自己 spawn）的后端；reuse 不动；Gaussian 子进程始终保留。 */
  async dispose() {
    if (this.owned && this.handle) {
      try {
        // 优先受控 shutdown 端点（后端保留正在跑的 Gaussian 子进程）
        await fetch(`${this.baseUrl}/v1/admin/shutdown`, {
          method: "POST",
          headers: { Authorization: `Bearer ${this.managedToken || ""}` },
          signal: AbortSignal.timeout(3000),
        }).catch(() => {});
      } catch { /* ignore */ }
      try {
        await this.handle.waitForExit?.(AbortSignal.timeout(this.config.shutdownTimeoutMs ?? 5000));
      } catch { /* ignore */ }
      this._cleanupHandle();
    }
    this.owned = false;
    this.handle = null;
    this.state = "stopped";
  }
}

// ============ 工具定义工厂 ============

function defineTool(options) {
  if (!options.name) throw new Error("defineTool: name is required");
  if (!options.description) throw new Error(`defineTool(${options.name}): description is required`);
  if (typeof options.execute !== "function") throw new Error(`defineTool(${options.name}): execute must be a function`);
  const timeoutMs = options.timeoutMs ?? 30000;
  if (!Number.isFinite(timeoutMs) || timeoutMs <= 0) {
    throw new Error(`defineTool(${options.name}): timeoutMs must be a positive finite number`);
  }
  return {
    name: options.name,
    description: options.description,
    parameters: options.parameters ?? {},
    timeoutMs,
    execute: options.execute,
  };
}

// ============ 系统提示 ============

const GAUSSIAN_GUIDANCE = `## Gaussian 计算助手（gaussian-dsh 插件）

本插件辅助 Gaussian 16 计算，后端运行在本机 http://127.0.0.1:8765。

### 工作流
1. **生成输入**：用 generate_gaussian_input 生成 .gjf（自动写入工作目录 E:\\YDW\\ChemDatas\\Gjf）。
2. **提交任务**：用 submit_gaussian_job 提交（自动串行，禁止并行）。
3. **监控状态**：用 get_gaussian_job 查看进度（当前优化步、最新能量、log 尾部）。
4. **解析结果**：任务完成后用 parse_gaussian_output 提取能量、HOMO-LUMO、偶极矩、收敛状态等。

### 硬件约束（用户机器）
- CPU: AMD Ryzen 7 9700X（8核16线程），默认 nprocshared=8
- 内存: 15.1 GB，默认 mem=12GB
- Gaussian 16 Rev A.03，路径 D:\\G16W\\g16.exe
- 严禁并行多任务，必须串行

### 重要提醒
- 大体系（>100原子）不要用 opt=calcfc，会内存爆炸
- 纯 opt 无 freq 不能确认是极小点，需补 freq 验证虚频
- 方法/基组推荐前用 sobko_search 查思想家公社/Multiwfn 知识库证据
- 基组用 get_basis_set 从 BSE 官方库获取（支持 Gaussian94 格式）
- 报错用 diagnose_gaussian_error 诊断，结合内置错误库和 Sobko 解决方案

### 工具列表
gaussian_status, generate_gaussian_input, generate_gaussian_input_from_smiles,
parse_gaussian_output, submit_gaussian_job, get_gaussian_job, list_gaussian_jobs,
stop_gaussian_job, search_basis_sets, get_basis_set, search_gaussian_keywords,
sobko_search, sobko_fetch, diagnose_gaussian_error
`;

// ============ 工具定义 ============

function buildTools(client) {
  const tools = [];

  // 1. 服务状态
  tools.push(defineTool({
    name: "gaussian_status",
    description: "检查 Gaussian 插件后端服务状态：Gaussian 可执行文件是否存在、Sobko 知识库配置、工作目录、默认内存/核数、是否有任务在运行。",
    parameters: {},
    execute: (_args, exec) => client.get("/v1/status", exec.signal),
  }));

  // 2. 生成输入
  tools.push(defineTool({
    name: "generate_gaussian_input",
    description: "生成 Gaussian .gjf 输入文件并写入工作目录。需提供分子坐标（[[元素,x,y,z],...]）、电荷、自旋、方法/泛函、基组、任务类型（sp/opt/freq/opt+freq/td/irc/scan）。后端自动校验方法基组组合，返回内容、文件名、保存路径和警告。大体系不要加 calcfc。",
    parameters: {
      job_name: { type: "string", description: "任务名（用于文件名）", default: "gaussian_job" },
      job_type: { type: "string", description: "任务类型：sp, opt, freq, opt+freq, td, irc, scan", default: "opt" },
      method: { type: "string", description: "方法/泛函，如 B3LYP, wB97XD, M062X, PBE0, CAM-B3LYP, HF, MP2", default: "B3LYP" },
      basis: { type: "string", description: "基组，如 6-31G(d,p), 6-311+G(d,p), def2-SVP, def2-TZVP, cc-pVDZ", default: "6-31G(d,p)" },
      charge: { type: "integer", description: "分子电荷", default: 0 },
      multiplicity: { type: "integer", description: "自旋多重度（闭壳层=1，二重态=2）", default: 1 },
      atoms: { type: "array", description: "原子坐标 [[元素符号, x, y, z], ...]", items: { type: "array" } },
      extra_keywords: { type: "array", description: "额外关键词，如 ['scf=tight','empiricaldispersion=gd3bj','int=ultrafine']", items: { type: "string" } },
      mem: { type: "string", description: "内存，默认 12GB（不要超过物理内存15GB）" },
      nproc: { type: "integer", description: "核数，默认 8" },
    },
    execute: (args, exec) => client.post("/v1/gaussian-inputs", args, exec.signal),
  }));

  // 3. 解析输出
  tools.push(defineTool({
    name: "parse_gaussian_output",
    description: "解析 Gaussian .log/.out 输出文件，提取：正常结束标志、错误信息、方法基组、电荷自旋、原子数/基函数数、最终能量、优化收敛（驻点/力/位移）、HOMO-LUMO 能级和 gap、偶极矩、频率与虚频、热力学量、CPU/墙钟时间。传 file_path 或 content。",
    parameters: {
      file_path: { type: "string", description: "日志文件绝对路径（优先）" },
      content: { type: "string", description: "日志文本内容（若不传 file_path）" },
      filename: { type: "string", description: "文件名（用于显示）" },
    },
    execute: (args, exec) => client.post("/v1/gaussian-outputs/parse", args, exec.signal),
  }));

  // 4. 提交任务
  tools.push(defineTool({
    name: "submit_gaussian_job",
    description: "提交 Gaussian 计算任务（串行执行：若已有任务在运行则拒绝）。传入 gjf_content，后端写入工作目录并启动 g16.exe。返回 job_id 和任务信息。提交前用 generate_gaussian_input 生成内容。",
    parameters: {
      job_name: { type: "string", description: "任务名", default: "gaussian_job" },
      gjf_content: { type: "string", description: "完整的 .gjf 文件内容（来自 generate_gaussian_input 的 content 字段）", required: true },
    },
    execute: (args, exec) => client.post("/v1/jobs", args, exec.signal),
  }));

  // 5. 任务状态
  tools.push(defineTool({
    name: "get_gaussian_job",
    description: "获取单个 Gaussian 任务的实时状态：状态（pending/running/completed/failed/stopped）、当前优化步数、最新能量、log 尾部、PID、输入输出路径。用于轮询监控任务进度。",
    parameters: {
      job_id: { type: "string", description: "任务 ID（来自 submit_gaussian_job）", required: true },
      log_tail_lines: { type: "integer", description: "返回 log 尾部行数", default: 30 },
    },
    execute: (args, exec) => client.get(`/v1/jobs/${encodeURIComponent(args.job_id)}?log_tail_lines=${args.log_tail_lines ?? 30}`, exec.signal),
  }));

  // 6. 列出任务
  tools.push(defineTool({
    name: "list_gaussian_jobs",
    description: "列出所有 Gaussian 历史任务（按时间倒序），返回 job_id、名称、状态、时间等。用于重新打开之前的工作。",
    parameters: {
      limit: { type: "integer", description: "返回数量", default: 50 },
    },
    execute: (args, exec) => client.get(`/v1/jobs?limit=${args.limit ?? 50}`, exec.signal),
  }));

  // 7. 停止任务
  tools.push(defineTool({
    name: "stop_gaussian_job",
    description: "停止正在运行的 Gaussian 任务（终止进程树，包括 l101.exe 等子进程）。仅对 running 状态任务有效。",
    parameters: {
      job_id: { type: "string", description: "任务 ID", required: true },
    },
    execute: (args, exec) => client.post(`/v1/jobs/${encodeURIComponent(args.job_id)}/stop`, {}, exec.signal),
  }));

  // 8. 搜索基组
  tools.push(defineTool({
    name: "search_basis_sets",
    description: "搜索 Basis Set Exchange (BSE) 官方基组库。按名称/描述/族模糊匹配，返回基组名、显示名、族、支持元素、最新版本。BSE 是基组标准来源（basissetexchange.org）。",
    parameters: {
      query: { type: "string", description: "搜索关键词，如 def2, cc-pv, 6-31, lanl2", required: true },
      limit: { type: "integer", description: "返回数量", default: 20 },
    },
    execute: (args, exec) => client.get(`/v1/basis-sets?query=${encodeURIComponent(args.query)}&limit=${args.limit ?? 20}`, exec.signal),
  }));

  // 9. 获取基组
  tools.push(defineTool({
    name: "get_basis_set",
    description: "从 BSE 官方库获取指定基组的完整内容（默认 Gaussian94 格式，可直接嵌入 .gjf 的 gen 段）。需提供基组名（用 search_basis_sets 确认准确名称）和原子序数列表。返回 content 字段为基组文本。",
    parameters: {
      name: { type: "string", description: "基组名（BSE 标准名，如 def2-svp, cc-pvdz, 6-31g_st_）", required: true },
      elements: { type: "string", description: "原子序数逗号分隔，如 6,7,8,16", default: "1,6,7,8" },
      format: { type: "string", description: "输出格式：gaussian94, gaussian, nwchem, orca, psi4, qchem", default: "gaussian94" },
    },
    execute: (args, exec) => client.get(`/v1/basis-sets/${encodeURIComponent(args.name)}?elements=${encodeURIComponent(args.elements)}&fmt=${args.format ?? "gaussian94"}`, exec.signal),
  }));

  // 10. 关键词搜索
  tools.push(defineTool({
    name: "search_gaussian_keywords",
    description: "搜索 Gaussian 关键词参考库（基于 gaussian.com 官方文档整理）。覆盖：任务类型、方法泛函、SCF 控制、色散校正、积分格点、溶剂模型、布居分析、常见错误与解决方案。返回关键词、说明、用法、注意事项。",
    parameters: {
      query: { type: "string", description: "搜索关键词，如 scf, opt, freq, 色散, 溶剂, 收敛失败", required: true },
    },
    execute: (args, exec) => client.get(`/v1/keywords?query=${encodeURIComponent(args.query)}`, exec.signal),
  }));

  // 11. Sobko 检索
  tools.push(defineTool({
    name: "sobko_search",
    description: "检索 Sobko 计算化学知识库（思想家公社学术帖 577篇 + Multiwfn 用户手册 + OPV 有机太阳能电池论文 1108篇）。默认 BM25-only 轻量模式。返回可追溯证据片段（source_id、chunk_id、文本、权威等级）。用于方法选择、错误解决方案、Multiwfn 后处理等的文献证据支持。首次调用需加载索引（约 1-2 分钟）。",
    parameters: {
      query: { type: "string", description: "检索问题，如 'B3LYP 优化 收敛失败 解决'、'Multiwfn 静电势 分析'、'OSC 给体 泛函 选择'", required: true },
      top_k: { type: "integer", description: "返回结果数", default: 8 },
      software: { type: "array", description: "按软件过滤，如 ['Gaussian','Multiwfn','ORCA']", items: { type: "string" } },
      authority_at_least: { type: "string", description: "最低权威等级：A（手册）或 B（帖子/论文）" },
    },
    execute: (args, exec) => client.post("/v1/sobko/search", args, exec.signal),
    timeoutMs: 200000,
  }));

  // 12. Sobko 展开上下文
  tools.push(defineTool({
    name: "sobko_fetch",
    description: "展开 Sobko 知识库中某个 source/chunk 的完整上下文（含相邻 chunk）。用于 sobko_search 返回片段后获取完整内容。",
    parameters: {
      chunk_id: { type: "string", description: "chunk ID（来自 sobko_search）" },
      source_id: { type: "string", description: "source ID（来自 sobko_search）" },
      expand_prev_next: { type: "integer", description: "展开前后各几个 chunk", default: 1 },
    },
    execute: (args, exec) => client.post("/v1/sobko/fetch", args, exec.signal),
  }));

  // 13. 错误诊断
  tools.push(defineTool({
    name: "diagnose_gaussian_error",
    description: "诊断 Gaussian 计算错误：匹配内置错误库（SCF收敛失败、内存不足、优化失败、基组错误等）+ Sobko 知识库检索解决方案。传入错误文本（从 log 中提取的 Error termination 行或报错关键词）。返回诊断结果和文献证据。",
    parameters: {
      error_text: { type: "string", description: "错误文本，如 'Convergence failure'、'Out-of-memory'、'Error termination in l101.exe'", required: true },
    },
    execute: (args, exec) => client.post("/v1/diagnose", args, exec.signal),
    timeoutMs: 200000,
  }));

  // 14. SMILES → Gaussian 输入
  tools.push(defineTool({
    name: "generate_gaussian_input_from_smiles",
    description: "从 SMILES 字符串自动生成 Gaussian .gjf 输入文件。后端用 RDKit ETKDGv3 生成 24 个构象，MMFF94s 优化后选能量最低构象，自动推断电荷和自旋多重度。适合有机小分子快速起步。注意：盐/多片段体系默认拒绝，过渡金属/多自由基需显式指定 multiplicity。",
    parameters: {
      smiles: { type: "string", description: "SMILES 字符串，如 CCO（乙醇）、c1ccccc1（苯）、[NH4+]（铵根）", required: true },
      num_conformers: { type: "integer", description: "生成构象数（默认 24，范围 1-64）", default: 24 },
      multiplicity: { type: "integer", description: "自旋多重度（不填则自动推断：闭壳层=1，单自由基=2）", default: null },
      allow_disconnected: { type: "boolean", description: "是否允许多片段体系（盐/共晶等，默认 false）", default: false },
    },
    execute: (args, exec) => client.post("/v1/gaussian-inputs/from-smiles", args, exec.signal),
    timeoutMs: 60000,
  }));

  return tools;
}

// ============ 注册工具 ============

function registerTools(ctx, config, resolveBaseUrl) {
  // resolveBaseUrl: async (signal) => baseUrl；managed 模式等后端就绪，external 模式直接返回
  const client = new GaussianClient(
    resolveBaseUrl || (async () => config?.baseUrl || "http://127.0.0.1:8765"),
    config?.requestTimeoutMs ?? 30000,
    config?.maxResponseBytes ?? 1048576,
  );

  const disposers = [];
  for (const tool of buildTools(client)) {
    disposers.push(ctx.tools.register(tool));
  }

  // 系统提示注入
  ctx.effect(() => ctx.systemPrompt.section({
    name: "gaussian:guidance",
    order: 85,
    text: GAUSSIAN_GUIDANCE,
  }));

  return () => { for (const d of disposers) d(); };
}

// ============ Cordis 插件入口 ============

export const name = "gaussian-dsh";

export function apply(ctx) {
  const config = {
    backendMode: process.env.GAUSSIAN_BACKEND_MODE ?? "managed",
    baseUrl: process.env.GAUSSIAN_BACKEND_URL ?? "http://127.0.0.1:8765",
    requestTimeoutMs: 30000,
    maxResponseBytes: 1048576,
    startupTimeoutMs: Number(process.env.GAUSSIAN_STARTUP_TIMEOUT_MS ?? 30000),
    shutdownTimeoutMs: Number(process.env.GAUSSIAN_SHUTDOWN_TIMEOUT_MS ?? 5000),
    backendExe: process.env.GAUSSIAN_BACKEND_EXE || null,
    dataDir: process.env.GAUSSIAN_DATA_DIR || null,
  };

  const manager = new BackendManager(config);

  // 工具注册：每次调用时通过 manager 解析 baseUrl（managed 等就绪，external 直连）
  ctx.effect(() => registerTools(ctx, config, (signal) => manager.getBaseUrl(signal)));

  // managed 生命周期：external 模式直连不 spawn；
  // managed 模式注入 subprocess 能力启动后端，disposer 只关 owned 进程。
  if (config.backendMode !== "external") {
    ctx.inject(["subprocess"], (child) => {
      child.effect(() => {
        void manager.start(child.subprocess);
        return async () => {
          await manager.dispose();
        };
      });
    });
  }
}

export default { name, apply };
