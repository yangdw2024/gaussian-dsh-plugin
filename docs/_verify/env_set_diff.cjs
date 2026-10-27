// 临时复核：README 后端表变量名 vs config.py env 读取项集合对照（只读）
const fs = require("fs");
const path = require("path");
const root = path.resolve(__dirname, "..", "..");
const readme = fs.readFileSync(path.join(root, "README.md"), "utf8").split(/\r?\n/);
const cfg = fs.readFileSync(path.join(root, "backend", "config.py"), "utf8");

// config.py 读取的 env 名
const cfgVars = new Set();
for (const m of cfg.matchAll(/os\.environ\.get\(\s*"([A-Z_]+)"|_env_path\(\s*"([A-Z_]+)"|_env_bool\(\s*"([A-Z_]+)"|os\.environ\.get\(\s*"([A-Z_]+)"/g)) {
  const v = m[1] || m[2] || m[3] || m[4];
  if (v) cfgVars.add(v);
}
// OBABEL_EXE 在 _resolve_obabel 内 os.environ.get
for (const m of cfg.matchAll(/os\.environ\.get\(\s*"([A-Z_]+)"/g)) cfgVars.add(m[1]);

// README 后端表（"后端层" 到 "快速测试" 之间）
let inBackend = false;
const readmeVars = new Set();
for (const ln of readme) {
  if (ln.includes("后端层（")) { inBackend = true; continue; }
  if (inBackend && ln.includes("快速测试")) break;
  if (inBackend && ln.startsWith("|") && !ln.includes("环境变量") && !ln.includes("---")) {
    for (const m of ln.matchAll(/`([A-Z_]+)`/g)) readmeVars.add(m[1]);
  }
}

console.log("config.py env 读取项 (" + cfgVars.size + "):");
console.log([...cfgVars].sort().join(", "));
console.log("\nREADME 后端表变量 (" + readmeVars.size + "):");
console.log([...readmeVars].sort().join(", "));
console.log("\nREADME 列出但 config.py 未读:", [...readmeVars].filter((v) => !cfgVars.has(v)).join(", ") || "无");
console.log("config.py 有但 README 未列 (" + [...cfgVars].filter((v) => !readmeVars.has(v)).length + "):");
console.log([...cfgVars].filter((v) => !readmeVars.has(v)).sort().join(", "));
