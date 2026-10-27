# -*- coding: utf-8 -*-
"""2026-10-26 复核：19 个注册工具名 vs 提示词清单差集；会话 jsonl 中 19 名出现统计。"""
import json, re, sys
sys.path.insert(0, r"E:\YDW\ChemDatas\gaussian-dsh-plugin")

# 1) 从项目根 lib/index.js 收集注册工具名（走真实插件入口）
import subprocess, os
node = r"E:\DSH\DSH Desktop\resources\runtime\primary-runtime\dependencies\node\bin\node.exe"
if not os.path.exists(node):
    node = "node"
collector = r"""
process.env.GAUSSIAN_BACKEND_MODE = "external";
const { pathToFileURL } = require("node:url");
const path = require("node:path");
(async () => {
  const mod = await import(pathToFileURL(path.join("E:/YDW/ChemDatas/gaussian-dsh-plugin/lib/index.js")).href);
  const plugin = mod.default ?? mod;
  const captured = []; const effects = [];
  const ctx = { tools: { register(d){ captured.push(d.name); return ()=>{}; } },
    systemPrompt: { section(){} }, effect(fn){ effects.push(fn); }, inject(_,cb){ cb({subprocess:{}, effect(){}}); } };
  plugin.apply(ctx); effects.forEach(f=>f());
  console.log(JSON.stringify(captured));
})();
"""
r = subprocess.run([node, "-e", collector], capture_output=True, text=True, encoding="utf-8")
registered = json.loads(r.stdout.strip().splitlines()[-1])
print(f"=== 注册工具数: {len(registered)} ===")

# 2) 提示词文本工具名（从 src/index.js GAUSSIAN_GUIDANCE 提取）
src = open(r"E:\YDW\ChemDatas\gaussian-dsh-plugin\src\index.js", encoding="utf-8").read()
m = re.search(r"const GAUSSIAN_GUIDANCE = `(.*?)`;", src, re.S)
guidance = m.group(1)
prompt_names = set(re.findall(r"[a-z_]+(?:_[a-z]+)+", guidance))
# 只保留注册集合相关名
prompt_in = sorted(n for n in prompt_names if n in registered)
missing_in_prompt = sorted(set(registered) - set(prompt_in))
extra_in_prompt = sorted(set(prompt_in) - set(registered))
print(f"=== 提示词列出工具数: {len(prompt_in)} ===")
print(f"注册未进提示词: {missing_in_prompt if missing_in_prompt else '无'}")
print(f"提示词多出未注册: {extra_in_prompt if extra_in_prompt else '无'}")

# 3) 会话 jsonl 19 名出现次数
SESSION = r"E:\YDW\ChemDatas\gaussian-dsh-plugin\docs\_verify\session_b1bc3e92.jsonl"
text = open(SESSION, encoding="utf-8", errors="replace").read()
print("\n=== 会话文本出现次数 ===")
for n in registered:
    c = text.count(n)
    flag = "OK" if c > 0 else "MISSING"
    print(f"  [{flag}] {n}: {c}")

# 4) 会话中实际 tool/call 调用集合
calls = {}
for raw in open(SESSION, encoding="utf-8", errors="replace"):
    raw = raw.strip()
    if not raw: continue
    try: rec = json.loads(raw)
    except Exception: continue
    if rec.get("type") == "tool/call":
        d = rec.get("data", {})
        calls[d.get("name")] = calls.get(d.get("name"), 0) + 1
gp_called = sorted(n for n in registered if n in calls)
print(f"\n=== 会话内实际被模型调用的 GP 工具: {len(gp_called)}/19 ===")
for n in gp_called:
    print(f"  {n}: {calls[n]}")
print(f"未被实调: {sorted(set(registered)-set(gp_called))}")
