# -*- coding: utf-8 -*-
# 临时取证：解析 DSH 会话 session.v4.jsonl，统计插件工具注册/调用、shell 退出码与报错。
# 只读会话文件，不写回 DSH；产物打印到 stdout，供 R17 收尾复核取证。
import json, re, sys, collections

PATH = r"E:\YDW\ChemDatas\gaussian-dsh-plugin\docs\_verify\session_b1bc3e92.jsonl"

GAUSSIAN_TOOLS = [
    "gaussian_status", "generate_gaussian_input", "parse_gaussian_output",
    "submit_gaussian_job", "get_gaussian_job", "list_gaussian_jobs", "stop_gaussian_job",
    "search_basis_sets", "get_basis_set", "search_gaussian_keywords",
    "sobko_search", "sobko_fetch", "diagnose_gaussian_error",
    "generate_gaussian_input_from_smiles",
    "postprocess_capabilities", "create_postprocess_task",
    "get_postprocess_task", "list_postprocess_tasks",
]

type_counter = collections.Counter()
defined = set()          # 会话中出现过的 gaussian 工具名（注册/定义/调用都算）
called = collections.Counter()  # 实际工具调用次数
call_errors = []         # 工具调用失败记录
shell_calls = []         # shell 工具调用与退出码
bad_exit = []            # 3221225794 / 0xC0000142
error_lines = []         # 报错关键词
backend_hits = 0
first_ts = last_ts = None

TOOL_NAME_RE = re.compile(r'"(?:name|toolName|tool)"\s*:\s*"([A-Za-z0-9_/]+)"')

def walk(obj, cb):
    if isinstance(obj, dict):
        for k, v in obj.items():
            cb(k, v)
            walk(v, cb)
    elif isinstance(obj, list):
        for v in obj:
            walk(v, cb)

with open(PATH, "r", encoding="utf-8", errors="replace") as f:
    for ln, raw in enumerate(f, 1):
        raw = raw.strip()
        if not raw:
            continue
        try:
            rec = json.loads(raw)
        except Exception:
            error_lines.append((ln, "JSON_PARSE_FAIL", raw[:160]))
            continue
        t = rec.get("type", "?")
        type_counter[t] += 1
        ts = rec.get("time") or rec.get("createdAt")
        if ts:
            first_ts = first_ts or ts
            last_ts = ts
        text = raw
        if "8765" in text:
            backend_hits += 1
        if "3221225794" in text or "0xC0000142" in text:
            bad_exit.append((ln, text[:300]))

        # 收集工具名
        for m in TOOL_NAME_RE.finditer(text):
            name = m.group(1)
            if name in GAUSSIAN_TOOLS:
                defined.add(name)

        # 工具调用记录：常见字段 data.tool / data.name / data.call.name / function.name
        data = rec.get("data", {}) if isinstance(rec.get("data"), dict) else {}
        call_name = None
        for key in ("tool", "name", "toolName"):
            if isinstance(data.get(key), str):
                call_name = data[key]
                break
        if not call_name and isinstance(data.get("call"), dict):
            call_name = data["call"].get("name")
        if not call_name and isinstance(data.get("function"), dict):
            call_name = data["function"].get("name")

        if call_name in GAUSSIAN_TOOLS:
            called[call_name] += 1
            # 结果错误判定
            blob = json.dumps(data, ensure_ascii=False)
            if re.search(r'"ok"\s*:\s*false|error|Error|failed|Traceback', blob):
                call_errors.append((ln, call_name, blob[:240]))

        # shell 工具调用
        if call_name in ("shell", "pwsh", "bash", "terminal", "run_command", "execute_command"):
            shell_calls.append((ln, call_name, json.dumps(data, ensure_ascii=False)[:240]))

        # 报错关键词（排除正常文档性提及）
        for kw in ("did not activate", "import failed", "ERR_MODULE_NOT_FOUND",
                   "Failed to fetch", "Invalid schema", "Traceback", "STATUS_DLL_INIT_FAILED"):
            if kw in text:
                error_lines.append((ln, kw, text[:240]))

print("=== 会话元数据 ===")
print("首条时间:", first_ts, " 末条时间:", last_ts)
print("=== 事件类型 Top 20 ===")
for k, v in type_counter.most_common(20):
    print(f"  {k}: {v}")

print("\n=== 18 个 gaussian 工具在会话中出现情况 ===")
for name in GAUSSIAN_TOOLS:
    mark = "已出现" if name in defined else "未出现"
    print(f"  [{mark}] {name}")

print("\n=== 实际被调用的 gaussian 工具 ===")
for name, n in called.most_common():
    print(f"  {name}: {n} 次")

print("\n=== 工具调用疑似错误记录（前 15） ===")
for ln, name, blob in call_errors[:15]:
    print(f"  L{ln} {name}: {blob}")

print("\n=== shell 工具调用记录数:", len(shell_calls))
for ln, name, blob in shell_calls[:10]:
    print(f"  L{ln} {name}: {blob}")

print("\n=== 3221225794 / 0xC0000142 命中:", len(bad_exit))
for ln, blob in bad_exit[:10]:
    print(f"  L{ln}: {blob}")

print("\n=== 报错关键词命中（前 20） ===")
for ln, kw, blob in error_lines[:20]:
    print(f"  L{ln} [{kw}]: {blob}")

print("\n=== 8765 后端端口出现行数:", backend_hits)
