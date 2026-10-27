// 终态校验：三份 JSON 可解析、版本一致；runtime.json 剥 BOM 后解析。
const fs = require("fs");
const path = require("path");
const root = "E:/YDW/ChemDatas/gaussian-dsh-plugin";
const web = "C:/Users/Administrator/AppData/Roaming/dsh-desktop/harness/profiles/web";
const BOM = String.fromCharCode(0xfeff);

function readJson(p) {
  const raw = fs.readFileSync(p, "utf8").replace(new RegExp("^" + BOM), "");
  return JSON.parse(raw);
}

const rootPkg = readJson(path.join(root, "package.json"));
const webPkg = readJson(path.join(web, "node_modules/@gd/gp/package.json"));
const rt = readJson(path.join(root, "runtimes/win32-x64/runtime.json"));

console.log("root package.json name=", rootPkg.name, "version=", rootPkg.version);
console.log("web  package.json name=", webPkg.name, "version=", webPkg.version);
console.log("runtime.json version=", rt.version, "target=", rt.target, "files=", rt.files.length, "python=", rt.python);
if (rootPkg.version !== "0.2.0" || webPkg.version !== "0.2.0" || rt.version !== "0.2.0") {
  console.error("FAIL: 版本号不一致");
  process.exit(1);
}
console.log("JSON OK: 三份均可解析，版本均 0.2.0");
