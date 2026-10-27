# -*- coding: utf-8 -*-
"""2026-10-26 复核：扫描会话 jsonl，核对 19 个 gaussian 工具名注册/清单出现情况，
统计 tool/call 实际调用集合，并列出非 gaussian 工具失败记录归属。"""
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
    "extract_structure_from_file",
}

type_counter = collections.Counter()
called = collections.Counter()
non_gp_fail = []
calls = {}
blob_text = []

with open(PATH, "r", encoding="utf-8", errors="replace") as f:
    for ln, raw in enumerate(f, 1):
        raw = raw.strip()
        if not raw:
            continue
        try:
            rec = json.loads(raw)
        except Exception:
            continue
        t = rec.get("type")
        type_counter[t] += 1
        d = rec.get("data", {}) if isinstance(rec.get("data"), dict) else {}

        if t == "tool/call":
            name = d.get("name")
            called[name] += 1
            calls[d.get("callId")] = (name, d.get("turn"), raw)

        if t == "tool/result":
            msg = d.get("message", {})
            source = msg.get("source", {})
            cid = source.get("callId")
            text = "\n".join(c.get("text", "") for c in msg.get("content", []) if isinstance(c, dict))
            if cid in calls:
                name, turn, _ = calls[cid]
                if name not in GAUSSIAN and re.search(r"Traceback|Error:|3221225794|Failed to fetch|PermissionError|FileNotFoundError|ModuleNotFoundError", text):
                    non_gp_fail.append((turn, name, text[:200].replace("\n", " ")))

        # 收集大文本块用于工具名清单扫描
        if t in ("assistant/attempt", "system/prompt", "turn/start", "tools/snapshot"):
            blob_text.append(raw)

print("=== 记录类型计数 ===")
for k, v in type_counter.most_common():
    print(f"  {k}: {v}")

print("\n=== 实际被调用工具集合（非 gaussian 单列） ===")
for name, n in called.most_common():
    tag = "GP" if name in GAUSSIAN else "其他"
    print(f"  [{tag}] {name}: {n}")

print("\n=== 19 个 gaussian 工具名在会话文本中出现次数 ===")
joined = "\n".join(blob_text)
# 也扫描全部原始行（工具定义可能在任意 type）
all_text = ""
with open(PATH, "r", encoding="utf-8", errors="replace") as f:
    all_text = f.read()
missing = []
for name in sorted(GAUSSIAN):
    cnt = all_text.count(name)
    flag = "OK" if cnt > 0 else "MISSING"
    if cnt == 0:
        missing.append(name)
    print(f"  [{flag}] {name}: {cnt}")
print(f"\n未出现工具: {missing if missing else '无，19/19 全部出现'}")

print("\n=== 非 gaussian 工具失败记录归属 ===")
if not non_gp_fail:
    print("  无")
for turn, name, text in non_gp_fail:
    print(f"  turn {turn} [{name}]: {text[:180]}")
