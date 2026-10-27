// 临时复核：统计 README 后端配置表变量名数量（只读，不进交付包）
const fs = require("fs");
const path = require("path");
const root = path.resolve(__dirname, "..", "..");
const lines = fs.readFileSync(path.join(root, "README.md"), "utf8").split(/\r?\n/);
let inBackend = false;
const vars = [];
for (const ln of lines) {
  if (ln.includes("后端层（")) { inBackend = true; continue; }
  if (inBackend && ln.startsWith("### 前端")) break;
  if (inBackend && ln.startsWith("|") && ln.includes("`") && !ln.includes("环境变量")) {
    const m = ln.match(/`([A-Z_/]+)`/g) || [];
    m.forEach((x) => vars.push(x.replace(/`/g, "")));
  }
}
console.log("README 后端表变量名 (" + vars.length + "):");
vars.forEach((v, i) => console.log("  " + (i + 1) + ". " + v));

// 前端表
let inFront = false; const fvars = [];
for (const ln of lines) {
  if (ln.includes("前端插件层（")) { inFront = true; continue; }
  if (inFront && ln.startsWith("### 后端")) break;
  if (inFront && ln.startsWith("|") && ln.includes("`") && !ln.includes("环境变量")) {
    const m = ln.match(/`([A-Z_/]+)`/g) || [];
    m.forEach((x) => fvars.push(x.replace(/`/g, "")));
  }
}
console.log("\nREADME 前端表变量名 (" + fvars.length + "):");
fvars.forEach((v, i) => console.log("  " + (i + 1) + ". " + v));
