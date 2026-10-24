// R14 离线契约自测：核对 lib/index.js 产出的每个工具是否满足
// output { schema, render, presentationMeta? } 契约；不启动后端、不访问网络。
// 临时脚本，打包时被 docs/_verify* 排除，不进交付包。
// 优先复用解包到 docs/_dsh_unpack 的官方 dsh-tools 校验器；该目录清理后自动降级为
// 内联 schema 子集校验（复刻 types/json-schema.js 的核心规则），脚本仍可离线自验。

process.env.GAUSSIAN_BACKEND_MODE = "external";

import { fileURLToPath, pathToFileURL } from "node:url";
import { resolve, dirname } from "node:path";
import { existsSync } from "node:fs";

const here = dirname(fileURLToPath(import.meta.url));
const officialValidator = resolve(here, "../../docs/_dsh_unpack/dsh/node_modules/@deepseek-ai/dsh-tools/lib/types/json-schema.js");

// 内联兜底：复刻 dsh-tools 受支持子集（type 枚举、type/oneOf 互斥、关键字白名单、递归校验）。
const TYPES = ["object", "array", "string", "number", "integer", "boolean", "null"];
const CONSTRAINT = new Set(["type", "oneOf", "properties", "required", "additionalProperties", "items", "enum", "const"]);
const ANNOTATION = new Set(["description", "title", "default", "examples"]);
function walk(schema, where) {
  if (schema === undefined || schema === null || typeof schema !== "object" || Array.isArray(schema)) throw new Error(`${where} must be a schema object`);
  for (const key of Object.keys(schema)) {
    if (!CONSTRAINT.has(key) && !ANNOTATION.has(key)) throw new Error(`unsupported keyword "${key}" at ${where}`);
  }
  const hasType = Object.hasOwn(schema, "type");
  const hasOneOf = Object.hasOwn(schema, "oneOf");
  if (hasType && hasOneOf) throw new Error(`type and oneOf must not coexist at ${where}`);
  if (hasType && !TYPES.includes(schema.type)) throw new Error(`unsupported type "${schema.type}" at ${where}`);
  if (schema.properties && typeof schema.properties === "object") {
    for (const [name, sub] of Object.entries(schema.properties)) walk(sub, `${where}.properties.${name}`);
  }
  if (schema.items) walk(schema.items, where + ".items");
  if (Array.isArray(schema.oneOf)) schema.oneOf.forEach((sub, i) => walk(sub, `${where}.oneOf[${i}]`));
}
let assertSupportedJsonSchema = (schema) => walk(schema, "$");

// 优先复用解包的官方校验器；官方副本依赖宿主作用域包（@deepseek-ai/dsh-llm 等），
// 离线环境解析不到时自动降级到上面的内联子集校验，不阻断自测。
if (existsSync(officialValidator)) {
  try {
    ({ assertSupportedJsonSchema } = await import(pathToFileURL(officialValidator)));
  } catch (err) {
    console.warn(`[warn] 官方校验器加载失败，使用内联子集校验：${err.message}`);
  }
}

// R16: 校验 parameters 必须是模型 function 要求的 object-root schema。
// 扁平表 { smiles: {...} } 顶层无 type，会被网关判成 type:null 拒绝注册。
function assertParametersObjectRoot(parameters, toolName, problems) {
  if (!parameters || typeof parameters !== "object" || Array.isArray(parameters)) {
    problems.push("parameters must be an object schema");
    return;
  }
  if (parameters.type !== "object") {
    problems.push(`parameters.type must be "object" (got ${JSON.stringify(parameters.type)})`);
  }
  if (!parameters.properties || typeof parameters.properties !== "object" || Array.isArray(parameters.properties)) {
    problems.push("parameters.properties must be an object map");
    return;
  }
  if (parameters.required !== undefined) {
    if (!Array.isArray(parameters.required) || parameters.required.some((k) => typeof k !== "string")) {
      problems.push("parameters.required must be an array of strings");
    } else {
      for (const key of parameters.required) {
        if (!Object.hasOwn(parameters.properties, key)) {
          problems.push(`parameters.required names "${key}" which is not in properties`);
        }
      }
    }
  }
  for (const [name, sub] of Object.entries(parameters.properties)) {
    try {
      assertSupportedJsonSchema(sub);
    } catch (err) {
      problems.push(`parameters.properties.${name} unsupported: ${err.message}`);
    }
  }
}

const pluginPath = resolve(here, "../../lib/index.js");
const plugin = await import(pathToFileURL(pluginPath));

const captured = [];
const pendingEffects = [];

const ctx = {
  tools: {
    register(def) {
      captured.push(def);
      return () => {};
    },
  },
  systemPrompt: { section() {} },
  effect(fn) {
    pendingEffects.push(fn);
  },
  inject(_deps, cb) {
    cb({ subprocess: {}, effect() {} });
  },
};

// 走真实插件入口，触发 registerTools 收集工具
plugin.default.apply(ctx);
for (const fn of pendingEffects) fn();

// 复刻 dsh-tools register(): types/index.js:471-481 / lib/index.js:2977-2980
const failures = [];
const rows = [];
for (const tool of captured) {
  const problems = [];
  if (!tool.name) problems.push("missing name");
  if (!tool.description) problems.push("missing description");
  if (typeof tool.execute !== "function") problems.push("execute must be function");

  const output = tool.output;
  if (output === undefined || typeof output !== "object" || output === null) {
    problems.push("output must be an object { schema, render, presentationMeta? }");
  } else {
    if (typeof output.render !== "function") problems.push("output.render must be a function");
    if (output.presentationMeta !== undefined && typeof output.presentationMeta !== "function") {
      problems.push("output.presentationMeta must be a function when declared");
    }
    try {
      assertSupportedJsonSchema(output.schema);
    } catch (err) {
      problems.push(`output.schema unsupported: ${err.message}`);
    }
    // render 必须返回可无损 JSON 序列化值；用一个样例对象实跑一次
    try {
      const sample = { ok: true, code: 0, text: "sample" };
      const rendered = output.render({}, sample);
      JSON.stringify(rendered);
    } catch (err) {
      problems.push(`output.render threw on sample: ${err.message}`);
    }
  }

  // R16: parameters 必须为 object-root schema（模型 function 调用强制要求）。
  try {
    assertParametersObjectRoot(tool.parameters, tool.name, problems);
  } catch (err) {
    problems.push(`parameters check threw: ${err.message}`);
  }

  if (tool.timeoutMs !== undefined && (!Number.isFinite(tool.timeoutMs) || tool.timeoutMs <= 0)) {
    problems.push("timeoutMs must be a positive finite number");
  }

  rows.push({ name: tool.name, problems });
  if (problems.length > 0) failures.push({ name: tool.name, problems });
}

console.log(`registered tools: ${captured.length}`);
for (const row of rows) {
  const mark = row.problems.length === 0 ? "PASS" : "FAIL";
  console.log(`  [${mark}] ${row.name}${row.problems.length ? " -> " + row.problems.join("; ") : ""}`);
}

if (failures.length > 0) {
  console.error(`\nCONTRACT FAIL: ${failures.length} tool(s) rejected by dsh-tools register().`);
  process.exit(1);
}
console.log("\nCONTRACT PASS: every tool satisfies output { schema, render, presentationMeta? }.");
