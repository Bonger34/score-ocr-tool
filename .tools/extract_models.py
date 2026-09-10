# -*- coding: utf-8 -*-
"""从交付物 gpuassets 解出 REC/DET/DICT 原始字节，便于离线分析/改造模型。"""
import base64, gzip, os, re, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = os.path.join(BASE, '搜分名单查询工具.html')
OUT = os.path.join(BASE, '.tools')

html = open(HTML, 'r', encoding='utf-8', errors='replace').read()
body = re.search(r'<script type="text/plain" id="gpuassets">(.*?)</script>', html, re.S).group(1).strip()
parts = [p for p in body.split('|') if p]
names = {'REC': 'rec.onnx', 'DET': 'det.onnx', 'DICT': 'dict.txt'}
for i, k in enumerate(parts[0::2]):
    if k not in names:
        continue
    raw = base64.b64decode(parts[2 * i + 1])
    try:
        raw = gzip.decompress(raw)
    except Exception:
        pass
    p = os.path.join(OUT, names[k])
    open(p, 'wb').write(raw)
    print(k, len(raw), p)
