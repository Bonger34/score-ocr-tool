# -*- coding: utf-8 -*-
"""解出 gpuassets 里的 ORT 运行时 JS（base64 明文），供检索 WebGPU EP 支持的算子。"""
import base64, gzip, os, re, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = os.path.join(BASE, '搜分名单查询工具.html')
OUT = os.path.join(BASE, '.tools', 'ort_bundle.js')

html = open(HTML, 'r', encoding='utf-8', errors='replace').read()
m = re.search(r'<script type="text/plain" id="gpuassets">(.*?)</script>', html, re.S)
body = m.group(1).strip()
parts = [p for p in body.split('|') if p]
keys = parts[0::2]
print('keys:', keys)
for i, k in enumerate(keys):
    b64 = parts[2 * i + 1]
    raw = base64.b64decode(b64)
    try:
        raw2 = gzip.decompress(raw)
        kind = 'gzip'
    except Exception:
        raw2 = raw
        kind = 'plain'
    print('%-6s b64=%d raw=%d(%s) decoded=%d' % (k, len(b64), len(raw), kind, len(raw2)))
    if k == 'ORT':
        open(OUT, 'wb').write(raw2)
        print('saved', OUT)
