# -*- coding: utf-8 -*-
import hashlib, os, sys, zipfile
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = os.path.join(BASE, '搜分名单查询工具.html')
ZIP = os.path.join(BASE, '.trae-html-share-packages', 'score-ocr-tool.zip')
def h(b): return hashlib.sha256(b).hexdigest()
a = open(HTML, 'rb').read()
with zipfile.ZipFile(ZIP) as z:
    b = z.read('搜分名单查询工具.html')
    names = z.namelist()
print('workspace html : %d bytes  sha256 %s' % (len(a), h(a)[:16]))
print('inside zip html: %d bytes  sha256 %s' % (len(b), h(b)[:16]))
print('identical:', a == b)
print('zip entries:', names)
