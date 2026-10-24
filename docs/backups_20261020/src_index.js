/**
 * Gaussian DSH Plugin — Cordis 前端插件
 *
 * 基于 AIFS 插件架构（@aifs/dsh-plugin-aifs）开发，辅助 Gaussian 计算：
 * 输入生成、输出解析、任务管理、BSE 基组获取、Sobko 知识库检索、关键词参考、错误诊断。
 *
 * 后端：Python FastAPI（默认 http://127.0.0.1:8765）
 */

// ============ 后端 HTTP 客户端 ============

class GaussianClient {
  constructor(baseUrl, timeoutMs = 30000, maxResponseBytes = 1048576) {
    this.baseUrl = baseUrl.replace(/\/$/, "");
    this.timeoutMs = timeoutMs;
    this.maxResponseBytes = maxResponseBytes;
  }

  async workflow(method, path, body, signal) {
    const url = `${this.baseUrl}${path}`;
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
  const baseUrl = config?.baseUrl || "http://127.0.0.1:8765";
  const client = new GaussianClient(baseUrl, config?.requestTimeoutMs ?? 30000, config?.maxResponseBytes ?? 1048576);

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
  };

  ctx.effect(() => registerTools(ctx, config));
}

export default { name, apply };
