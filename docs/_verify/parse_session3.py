# -*- coding: utf-8 -*-
# 第三轮取证：callId 正确关联，区分受限档(workspace-write)与完全访问档(danger-full-access)。
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

# callId -> (tool, turn, arguments)
calls = {}
pwsh_results = []   # (turn, callId, exitCode, text)
gp_results = []     # (turn, tool, callId, ok, text)
mode_at = []        # (ln, mode)
current_mode = None
mode_lines = []

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
        d = rec.get("data", {}) if isinstance(rec.get("data"), dict) else {}
        turn = d.get("turn")

        if t == "sandbox/mode":
            current_mode = d.get("mode")
            mode_lines.append((ln, current_mode))
        if t == "permission/preset":
            mode_at.append((ln, d.get("preset")))

        if t == "tool/call":
            name = d.get("name")
            cid = d.get("callId")
            calls[cid] = (name, turn, d.get("arguments", ""))

        if t == "tool/result":
            msg = d.get("message", {})
            source = msg.get("source", {})
            cid = source.get("callId")
            content = msg.get("content", [])
            text = "\n".join(c.get("text", "") for c in content if isinstance(c, dict))
            if cid not in calls:
                continue
            name, cturn, args = calls[cid]
            if name == "pwsh":
                m = re.search(r"exit code:\s*(-?\d+)", text)
                code = int(m.group(1)) if m else None
                pwsh_results.append((cturn, cid, code, current_mode, text[:160]))
            elif name in GAUSSIAN:
                is_err = bool(re.search(r"\"ok\"\s*:\s*false|Traceback|TypeError|Error:|0xC0000142|Failed to fetch|无法连接", text))
                gp_results.append((cturn, name, cid, not is_err, text, args))

print("=== 档位切换 ===")
for ln, m in mode_lines:
    print(f"  L{ln}: {m}")
print("  preset:", mode_at)

print("\n=== pwsh 调用结果（按时间顺序） ===")
for turn, cid, code, mode, text in pwsh_results:
    print(f"  turn {turn} [{mode}] exit={code} :: {text[:100]}")

print("\n=== gaussian 工具调用结果（按 turn） ===")
for turn, name, cid, ok, text, args in gp_results:
    print(f"\n--- turn {turn} [{'OK' if ok else 'FAIL'}] {name} ---")
    print("  参数:", args[:180].replace("\n", " "))
    print("  返回:", text[:500].replace("\n", " | "))
