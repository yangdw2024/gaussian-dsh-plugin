// R17 临时取证：复刻 DSH 内置 pwsh 工具的 spawn 链路，验证 0xC0000142 触发条件。
// 不修改任何业务代码；跑完即弃，打包时排除 docs/_verify/。
// 用法：E:\DSH\resources\runtime\primary-runtime\dependencies\node\bin\node.exe repro_spawn_pwsh.js
const { spawnSync } = require("node:child_process");
const path = require("node:path");

const PROFILE = "C:\\Users\\Administrator\\.dsh\\profiles\\desktop";
const POWERSHELL = "C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe";

// 复刻 dsh-subprocess scrubbedParentEnv：剔除凭据形变量与 DSH_ 前缀，其余系统变量保留。
function scrubbedParentEnv() {
  const out = {};
  for (const [k, v] of Object.entries(process.env)) {
    if (v === undefined) continue;
    if (/KEY|PASSWORD|SECRET|TOKEN/i.test(k)) continue;
    if (k.toUpperCase().startsWith("DSH_")) continue;
    out[k] = v;
  }
  return out;
}

function run(label, env, cwd) {
  console.log(`\n===== ${label} =====`);
  console.log(`SystemRoot=${env.SystemRoot ?? "<MISSING>"}  ComSpec=${env.ComSpec ?? "<MISSING>"}  windir=${env.windir ?? "<MISSING>"}`);
  const cmd = "[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false); echo hello-from-pwsh51";
  const r = spawnSync(POWERSHELL, ["-NoLogo", "-NoProfile", "-NonInteractive", "-Command", cmd], {
    cwd,
    env,
    encoding: "utf8",
  });
  console.log(`exitCode=${r.status}  error=${r.error ? r.error.code + " " + r.error.message : "none"}`);
  console.log(`stdout=${JSON.stringify((r.stdout || "").trim())}`);
  if (r.stderr) console.log(`stderr=${JSON.stringify(r.stderr.trim())}`);
}

// 组 1：完整环境（模拟 DSH 正常链路）
const good = { ...scrubbedParentEnv(), NO_COLOR: "1", PAGER: "cat", GIT_PAGER: "cat" };
run("A. full env (DSH normal path)", good, PROFILE);

// 组 2：故意删掉 SystemRoot / ComSpec / windir（反证：环境缺失是否触发 0xC0000142）
const bad = { ...good };
for (const k of ["SystemRoot", "ComSpec", "windir"]) delete bad[k];
run("B. env without SystemRoot/ComSpec/windir", bad, PROFILE);

// 组 3：cwd 指向不存在目录（反证：cwd 问题的错误码表现）
run("C. full env, nonexistent cwd", good, "C:\\nonexistent-dsh-probe-xyz");
