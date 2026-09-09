# -*- coding: utf-8 -*-
"""提取单文件 HTML 里的内联 <script> 块，逐个交给 node --check 做语法自检。
跳过 type="text/plain" 的数据块（pdf.js worker 源码、gpuassets base64 资源）。"""
import os, re, subprocess, sys, tempfile
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = os.path.join(BASE, '搜分名单查询工具.html')

raw = open(HTML, encoding='utf-8').read()
blocks = re.findall(r'<script([^>]*)>(.*?)</script>', raw, re.S)
print('inline script blocks:', len(blocks))
bad = 0
tmpdir = tempfile.mkdtemp(prefix='synchk_')
for i, (attrs, body) in enumerate(blocks):
    if 'text/plain' in attrs or 'src=' in attrs:
        print('  [%d] skipped (attrs=%s, %d chars)' % (i, attrs.strip()[:60], len(body)))
        continue
    fp = os.path.join(tmpdir, 'blk%d.js' % i)
    with open(fp, 'w', encoding='utf-8') as f:
        f.write(body)
    r = subprocess.run(['node', '--check', fp], capture_output=True, text=True, encoding='utf-8', errors='replace')
    ok = r.returncode == 0
    print('  [%d] %s (%d chars) %s' % (i, 'OK' if ok else 'SYNTAX ERROR', len(body),
                                       '' if ok else (r.stderr or '').strip()[:400]))
    if not ok:
        bad += 1
print('bad blocks:', bad)
sys.exit(1 if bad else 0)
