# -*- coding: utf-8 -*-
# 第四轮：切档(L332)前后 pwsh 成败、gaussian 工具失败时间点、后处理任务摘要。
import json, re, collections

PATH = r"E:\YDW\ChemDatas\gaussian-dsh-plugin\docs\_verify\session_b1bc3e92.jsonl"
GAUSSIAN = {
    "gaussian_status", "generate_gaussian_input", "parse_gaussian_output",
    "submit_gaussian_job", "get_gaussian_job", "list_gaussian_jobs", "stop_gaussian_job",
    "search_basis_sets", "get_basis_set", "search_gaussian_keywords",
    "sobko_search", "sobko_fetch", "diagnose_gaussian_error",
    "generate_gaussian_input_from_smiles",
    "postprocess_capabilities", "create_postprocess_task",
    "get_postprocess_task", "list_postprocess_tasks",
}
calls = {}
pwsh_all = []
gp_fail = []
mode = "workspace-write"
switch_ln = None

with open(PATH, "r", encoding="utf-8", errors="replace") as f:
    for ln, raw in enumerate(f, 1):
        raw = raw.strip()
        if not raw:
            continue
        rec = json.loads(raw)
        t = rec.get("type"); d = rec.get("data", {}) if isinstance(rec.get("data"), dict) else {}
        turn = d.get("turn")
        if t == "sandbox/mode":
            mode = d.get("mode")
            if mode == "danger-full-access":
                switch_ln = ln
        if t == "tool/call":
            calls[d.get("callId")] = (d.get("name"), turn, mode, d.get("arguments", ""))
        if t == "tool/result":
            msg = d.get("message", {}); source = msg.get("source", {}); cid = source.get("callId")
            text = "\n".join(c.get("text", "") for c in msg.get("content", []) if isinstance(c, dict))
            if cid not in calls:
                continue
            name, cturn, cmode, args = calls[cid]
            if name == "pwsh":
                m = re.search(r"exit code:\s*(-?\d+)", text)
                pwsh_all.append((cturn, cmode, int(m.group(1)) if m else None, text[:120].replace("\n", " ")))
            elif name in GAUSSIAN:
                if re.search(r"\"ok\"\s*:\s*false|Traceback|TypeError|Error:|0xC0000142|Failed to fetch|无法连接|ERR_MODULE_NOT_FOUND", text):
                    gp_fail.append((cturn, cmode, name, text[:260].replace("\n", " ")))

print(f"=== 切档行号: {switch_ln} ===")
print("\n=== 全部 pwsh 结果（mode 标注） ===")
for turn, cmode, code, text in pwsh_all:
    print(f"  turn {turn} [{cmode}] exit={code} :: {text[:90]}")

print("\n=== gaussian 工具失败记录 ===")
if not gp_fail:
    print("  无")
for turn, cmode, name, text in gp_fail:
    print(f"  turn {turn} [{cmode}] {name}: {text[:220]}")
