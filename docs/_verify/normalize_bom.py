# -*- coding: utf-8 -*-
# R15: 规范化 src/index.js 中两处字面 U+FEFF（注释与正则），改为显式 \uFEFF 转义。
import io

p = r"E:\YDW\ChemDatas\gaussian-dsh-plugin\src\index.js"
raw = open(p, "rb").read()
txt = raw.decode("utf-8-sig")
lines = txt.split("\n")

for i, line in enumerate(lines):
    if "JSON.parse 会在首字符" in line:
        lines[i] = "    // JSON.parse 会在首字符 BOM 处抛错，这里先剥掉 BOM 再解析。"
    elif "readFileSync(manifestPath" in line and "\\ufeff" not in line:
        lines[i] = '    const manifest = JSON.parse(readFileSync(manifestPath, "utf8").replace(/^\\uFEFF/, ""));'

out = "\n".join(lines)
with io.open(p, "w", encoding="utf-8", newline="\n") as f:
    f.write(out)

# 复核：不应再含字面 U+FEFF
check = open(p, "rb").read().decode("utf-8-sig")
print("literal BOM remaining:", "﻿" in check)
for i, l in enumerate(check.split("\n"), 1):
    if "manifestPath" in l and "JSON.parse" in l:
        print(i, l)
