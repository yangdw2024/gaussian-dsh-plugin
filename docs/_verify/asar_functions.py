# -*- coding: utf-8 -*-
# 临时：dump runner-launch 中 validateSubprocessSpec / targetEnvironment / runnerStdio / childEnv 函数体
import struct, json, re

ASAR = r"E:\DSH\resources\app.asar"
f = open(ASAR, "rb")
f.seek(12)
(hsize,) = struct.unpack("<I", f.read(4))
f.seek(16)
header = json.loads(f.read(hsize))
DS = 16 + hsize

def find(n, p, t):
    for k, c in n.get("files", {}).items():
        q = (p + "/" + k) if p else k
        if q == t: return c
        if "files" in c:
            r = find(c, q, t)
            if r is not None: return r

node = find(header, "", "dsh/node_modules/@deepseek-ai/dsh-subprocess-local/lib/runner-launch-B2zsQ1Dz.js")
f.seek(DS + int(node["offset"]))
txt = f.read(int(node["size"])).decode("utf-8", "replace")

for fn in ["function validateSubprocessSpec", "function targetEnvironment", "function runnerStdio", "function childEnv"]:
    idx = txt.find(fn)
    if idx < 0:
        print("MISSING", fn); continue
    print("=" * 20, fn)
    # 取到下一个顶层 function 之前
    m = re.search(r"\nfunction ", txt[idx + 10:])
    end = idx + 10 + m.start() if m else idx + 2200
    print(txt[idx:end][:2400])
