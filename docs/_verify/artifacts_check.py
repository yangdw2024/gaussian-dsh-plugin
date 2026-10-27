# -*- coding: utf-8 -*-
# 第五轮：后处理产物实物核对（存在性/大小/PNG 解码/cube header），报错行工具归属反查。
import json, os, struct, glob, re, io

DATA = r"C:\Users\Administrator\.gaussian-dsh\postprocess"
SESSION = r"E:\YDW\ChemDatas\gaussian-dsh-plugin\docs\_verify\session_b1bc3e92.jsonl"

# ---------- A. 产物核对 ----------
print("=== A. 后处理产物实物核对 ===")
all_ok = True
for jf in sorted(glob.glob(os.path.join(DATA, "*.json"))):
    meta = json.load(open(jf, "r", encoding="utf-8"))
    print(f"\n--- {meta['task_id']} [{meta['kind']}] status={meta['status']} error={meta['error']}")
    for art in meta["artifacts"]:
        p = art["path"]
        exists = os.path.exists(p)
        size = os.path.getsize(p) if exists else -1
        match = (size == art["size_bytes"])
        all_ok &= exists and match
        flag = "OK" if (exists and match) else "MISMATCH"
        print(f"  [{flag}] {art['name']}: 记录 {art['size_bytes']} B / 实物 {size} B")
        if exists and art["kind"] == "image/png" and match:
            try:
                from PIL import Image
                im = Image.open(p); im.verify()
                print(f"        PNG 解码 OK: {im.size if hasattr(im,'size') else ''}")
            except Exception as e:
                all_ok = False
                print(f"        PNG 解码失败: {e}")
        if exists and art["kind"] == "chemical/cube":
            try:
                with open(p, "rb") as f:
                    head = [next(f) for _ in range(6)]
                # cube: 注释两行 + 网格行 (nx ny nz)
                grid = head[2].split()
                nx, ny, nz = int(grid[0]), int(grid[1]), int(grid[2])
                limit = 16_000_000
                ok = nx*ny*nz <= limit
                all_ok &= ok
                print(f"        cube header: {nx} x {ny} x {nz} = {nx*ny*nz} 点 (<= {limit}: {ok})")
            except Exception as e:
                all_ok = False
                print(f"        cube header 读取失败: {e}")
    # 目录内未登记的额外文件（如 TGA 中间产物）
    dirp = os.path.dirname(jf)
    registered = {a["path"] for a in meta["artifacts"]}
    for f in os.listdir(dirp):
        fp = os.path.join(dirp, f)
        if fp not in registered and os.path.isfile(fp):
            print(f"  [未登记] {f}: {os.path.getsize(fp)} B")

print("\n产物核对总体:", "ALL OK" if all_ok else "存在不一致，见上")

# ---------- B. 报错行工具归属 ----------
print("\n=== B. 早期报错行工具归属反查 ===")
calls = {}
with open(SESSION, "r", encoding="utf-8", errors="replace") as f:
    for raw in f:
        raw = raw.strip()
        if not raw:
            continue
        rec = json.loads(raw)
        t = rec.get("type"); d = rec.get("data", {}) if isinstance(rec.get("data"), dict) else {}
        if t == "tool/call":
            calls[d.get("callId")] = (d.get("name"), d.get("arguments", "")[:120])

bad_kw = ["ERR_MODULE_NOT_FOUND", "Failed to fetch", "Invalid schema", "Traceback"]
with open(SESSION, "r", encoding="utf-8", errors="replace") as f:
    for ln, raw in enumerate(f, 1):
        if not any(k in raw for k in bad_kw):
            continue
        rec = json.loads(raw)
        t = rec.get("type"); d = rec.get("data", {}) if isinstance(rec.get("data"), dict) else {}
        if t == "tool/result":
            cid = d.get("message", {}).get("source", {}).get("callId")
            name, args = calls.get(cid, ("(未匹配)", ""))
            m = next((k for k in bad_kw if k in raw), "?")
            snippet = raw[raw.find(m):raw.find(m)+180]
            print(f"  L{ln} turn={d.get('turn')} 工具={name} [{m}] {snippet[:150]}")
        elif t in ("assistant/attempt", "turn/end"):
            blob = json.dumps(d, ensure_ascii=False)
            m = next((k for k in bad_kw if k in blob), "?")
            mm = re.search(r"function '([^']+)'", blob)
            print(f"  L{ln} turn={d.get('turn')} [网关/流 {m}] 函数={mm.group(1) if mm else '?'}")
