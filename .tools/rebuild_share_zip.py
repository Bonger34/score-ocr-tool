# -*- coding: utf-8 -*-
"""重打分享包：把交付 HTML + 3 个启动器打成 zip（与旧分享包同名同结构）。"""
import os, sys, zipfile
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 附件名必须是纯 ASCII：GitHub 会把非 ASCII 附件名重置为 default.zip，
# 中文显示名交给 Release 的 label 字段（见 docs/发布流程.md）
OUT = os.path.join(BASE, '.trae-html-share-packages', 'score-ocr-tool.zip')
FILES = ['搜分名单查询工具.html', '启动本地服务.cmd', '直接打开页面.cmd', '本地服务_无Python.ps1']

with zipfile.ZipFile(OUT, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
    for n in FILES:
        p = os.path.join(BASE, n)
        if not os.path.isfile(p):
            print('missing:', n); continue
        z.write(p, n)
        print('  + %-46s %10d' % (n, os.path.getsize(p)))
print('written %s (%d bytes)' % (OUT, os.path.getsize(OUT)))
with zipfile.ZipFile(OUT) as z:
    for i in z.infolist():
        print('  zip: %-46s %10d' % (i.filename, i.file_size))
