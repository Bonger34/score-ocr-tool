# -*- coding: utf-8 -*-
"""从 v2 交付物内嵌 gpuassets 解出 PPU 引擎源码（base64+gzip），供分析文本拼接行为"""
import base64, gzip, io, os, re, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = os.path.join(BASE, '搜分名单查询工具.html')
OUT = os.path.join(BASE, '.tools', 'ppu_engine_extracted.js')

html = open(HTML, 'r', encoding='utf-8', errors='replace').read()
m = re.search(r'<script type="text/plain" id="gpuassets">(.*?)</script>', html, re.S)
if not m:
    print('gpuassets not found'); sys.exit(1)
body = m.group(1).strip()
parts = [p for p in body.split('|') if p]
print('parts:', len(parts), 'first part len:', len(parts[0]))
# 键值对：键名 | base64序列 | 键名 | ...
# 找出 PPU 键
idx = None
for i, p in enumerate(parts):
    if p == 'PPU':
        idx = i
        break
print('PPU key at', idx)
if idx is not None and idx + 1 < len(parts):
    b64 = parts[idx + 1]
    raw = base64.b64decode(b64)
    print('raw bytes:', len(raw))
    try:
        js = gzip.decompress(raw)
    except Exception as e:
        js = raw
    with open(OUT, 'wb') as f:
        f.write(js)
    print('saved:', OUT, len(js), 'bytes')
