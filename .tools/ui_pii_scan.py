# -*- coding: utf-8 -*-
"""交付物里的"非姓名类"隐私排查：本地路径/用户名、邮箱、身份证号、手机号。

只扫我们自己的代码与标记（样式、body、应用脚本块），不扫内嵌的第三方库/模型 base64——
那些是上游产物，且 34MB 连续 base64 上跑正则会被回溯拖死。
用法: python ui_pii_scan.py
"""
import os, re, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = os.path.join(BASE, '搜分名单查询工具.html')
raw = open(HTML, encoding='utf-8').read()

# 只取"我们自己写的"部分：<style>…</style> + <body>…</body> 里的非脚本标记 + 最后一个 <script> 块
parts = []
m = re.search(r'<style>.*?</style>', raw, re.S)
if m:
    parts.append(('style', m.group(0)))
m = re.search(r'<body>(.*?)<script type="text/plain" id="pdfworker">', raw, re.S)
if m:
    parts.append(('markup', m.group(1)))
i = raw.rfind('<script>')
j = raw.rfind('</script>')
if i > 0 and j > i:
    parts.append(('app', raw[i:j]))

PATTERNS = [
    ('本地路径/用户名', re.compile(r'[A-Za-z]:[\\/]+Users[\\/]+[A-Za-z0-9_.\-]+')),
    ('邮箱', re.compile(r'[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,6}')),
    ('18位身份证', re.compile(r'(?<!\d)[1-9]\d{5}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx](?![\dXx])')),
    ('11位手机号', re.compile(r'(?<!\d)1[3-9]\d{9}(?!\d)')),
    ('用户名 Bonger', re.compile(r'Bonger', re.I)),
]

bad = 0
print('扫描范围: %s（合计 %d 字符）' % ('、'.join(n for n, _ in parts), sum(len(t) for _, t in parts)))
for name, pat in PATTERNS:
    hits = []
    for tag, text in parts:
        for mm in pat.finditer(text):
            hits.append((tag, mm.group(0)))
    bad += len(hits)
    print('  %-14s %s' % (name, ('%d 处 -> %s' % (len(hits), hits[:4])) if hits else '0 处'))
print('结论:', 'FAIL' if bad else 'PASS')
sys.exit(1 if bad else 0)
