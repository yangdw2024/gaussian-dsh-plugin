# -*- coding: utf-8 -*-
# 第二轮取证：按 turn 分组统计 pwsh 退出码、gaussian 工具调用成败，提取后期成功证据。
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

pwsh_by_turn = collections.defaultdict(list)          # turn -> [(callId, exitCode, snippet)]
calls_by_turn = collections.defaultdict(list)        # turn -> [(tool, ok, snippet)]
preset_modes = []
good_gaussian = collections.Counter()
bad_gaussian = collections.Counter()
key_results = []  # 关键工具返回留档

def turn_of(rec):
    d = rec.get("data", {})
    return d.get("turn") if isinstance(d, dict) else None

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
        turn = turn_of(rec)
        if t in ("permission/preset", "sandbox/mode"):
            preset_modes.append((ln, t, rec.get("data")))

        if t == "tool/call":
            d = rec["data"]
            name = d.get("name")
            if name == "pwsh":
                pwsh_by_turn[turn].append((d.get("callId"), None, d.get("arguments", "")[:120]))
            elif name in GAUSSIAN:
                calls_by_turn[turn].append((name, None, d.get("arguments", "")[:200]))

        if t == "tool/result":
            d = rec["data"]
            msg = d.get("message", {})
            source = msg.get("source", {})
            call_id = source.get("callId")
            content = msg.get("content", [])
            text = "\n".join(c.get("text", "") for c in content if isinstance(c, dict))
            # 反查 callId 对应的工具名
            # 简单：从文本识别退出码 / ok
            m = re.search(r"exit code:\s*(-?\d+)", text)
            if call_id and any(c[0] == call_id for lst in pwsh_by_turn.values() for c in lst):
                code = int(m.group(1)) if m else None
                # 回填对应 turn 的记录
                for tn, lst in pwsh_by_turn.items():
                    for i, c in enumerate(lst):
                        if c[0] == call_id:
                            lst[i] = (c[0], code, text[:120])
            # gaussian 结果归类
            blob = text
            is_err = bool(re.search(r"\"ok\"\s*:\s*false|Traceback|TypeError|Error:|失败|无法|0xC0000142", blob))
            # 找对应调用
            for tn, lst in calls_by_turn.items():
                for i, c in enumerate(lst):
                    if c[0] == call_id:
                        ok = not is_err
                        lst[i] = (c[0], ok, blob[:260])
                        if c[0] in GAUSSIAN:
                            (good_gaussian if ok else bad_gaussian)[c[0]] += 1
                        key_results.append((tn, c[0], ok, blob[:400]))

print("=== 档位变更记录 ===")
for ln, t, d in preset_modes:
    print(f"  L{ln} {t}: {json.dumps(d, ensure_ascii=False)}")

print("\n=== 各 turn pwsh 退出码 ===")
for tn in sorted(x for x in pwsh_by_turn if x is not None):
    codes = [c[1] for c in pwsh_by_turn[tn]]
    print(f"  turn {tn}: {len(codes)} 次, 退出码 {codes}")

print("\n=== 各 turn gaussian 工具调用（成败） ===")
for tn in sorted(x for x in calls_by_turn if x is not None):
    for name, ok, snip in calls_by_turn[tn]:
        tag = "OK" if ok else "FAIL"
        print(f"  turn {tn} [{tag}] {name}")

print("\n=== gaussian 工具 OK/FAIL 汇总 ===")
print("  OK:", dict(good_gaussian))
print("  FAIL:", dict(bad_gaussian))

print("\n=== 关键工具返回留档（前 30 条，按 turn） ===")
for tn, name, ok, blob in key_results[:30]:
    print(f"--- turn {tn} {'OK' if ok else 'FAIL'} {name} ---")
    print("   ", blob.replace("\n", " | ")[:380])
