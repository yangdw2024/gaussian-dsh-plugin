// R16 临时诊断：实跑插件 lib/index.js，逐个打印工具 parameters 与 output.schema 顶层类型。
// 不启动后端、不联网；打包时被 docs/_verify* 排除。
process.env.GAUSSIAN_BACKEND_MODE = "external";

import { fileURLToPath, pathToFileURL } from "node:url";
import { resolve, dirname } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const pluginPath = resolve(here, "../../lib/index.js");
const plugin = await import(pathToFileURL(pluginPath));

const captured = [];
const effects = [];
const ctx = {
  tools: { register(def) { captured.push(def); return () => {}; } },
  systemPrompt: { section() {} },
  effect(fn) { effects.push(fn); },
  inject(_deps, cb) { cb({ subprocess: {}, connection: { fetch: { register() { return () => {}; } } }, effect() {} }); },
};

plugin.default.apply(ctx);
for (const fn of effects) fn();

const TYPES = new Set(["object", "array", "string", "number", "integer", "boolean", "null"]);
console.log(`tools: ${captured.length}\n`);
let badParam = 0, badOutput = 0;
for (const t of captured) {
  const pOk = t.parameters && t.parameters.type === "object" && t.parameters.properties && typeof t.parameters.properties === "object";
  // output.schema：对象即可；显式 type 必须在白名单内；无 type 属 annotation-only 任意 JSON（官方 type:"json" 产物）。
  const o = t.output && t.output.schema;
  const oOk = o && typeof o === "object" && !Array.isArray(o) && (o.type === undefined || TYPES.has(o.type));
  if (!pOk) badParam++;
  if (!oOk) badOutput++;
  const pKeys = pOk ? Object.keys(t.parameters.properties).length : "(flat)";
  const req = t.parameters && Array.isArray(t.parameters.required) ? t.parameters.required.join(",") : "-";
  console.log(`${pOk ? "P" : "X"}/param  ${oOk ? "P" : "X"}/output  ${t.name}  [required: ${req}]`);
  console.log(`        parameters.type=${JSON.stringify(t.parameters && t.parameters.type)}  properties=${pKeys}  output.schema=${JSON.stringify(o)}`);
}
console.log(`\nparameters 非 object root: ${badParam}/${captured.length}; output.schema 非法: ${badOutput}/${captured.length}`);

// 打印一个带参工具与一个无参工具的完整 schema 供人工核对
for (const name of ["create_postprocess_task", "gaussian_status"]) {
  const t = captured.find((x) => x.name === name);
  if (t) {
    console.log("\n==== sample " + name + " ====");
    console.log(JSON.stringify({ parameters: t.parameters, output: { schema: t.output.schema } }, null, 2));
  }
}
