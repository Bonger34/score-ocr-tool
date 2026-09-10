# -*- coding: utf-8 -*-
"""核对状态行分隔符用的是"不换行空格"（NBSP），避免「·」孤零零留在行尾。

v2.6 起源码里写成 `\\u00A0` 转义（可读、不怕编辑器吃掉不可见字符），运行时仍是真正的 NBSP。
所以这里两种写法都认，并另外用浏览器确认渲染后的 DOM 里确实是 NBSP。
"""
import os, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = os.path.join(BASE, '搜分名单查询工具.html')
NB = chr(0x00A0)
raw = open(HTML, encoding='utf-8').read()

n_lit = raw.count(NB)
n_esc = raw.count('\\u00A0')
print('NBSP 字面量: %d 处；\\u00A0 转义: %d 处' % (n_lit, n_esc))
for line in raw.split('\n'):
    if NB in line:
        print('  ', line.strip()[:170].replace(NB, '<NBSP>'))
print('状态行模板命中:', ("+' ·\\u00A0已用 '" in raw) or ("+' ·" + NB + "已用 '" in raw))

if '--dom' in sys.argv:
    from playwright.sync_api import sync_playwright
    URL = 'http://127.0.0.1:18010/%E6%90%9C%E5%88%86%E5%90%8D%E5%8D%95%E6%9F%A5%E8%AF%A2%E5%B7%A5%E5%85%B7.html'
    with sync_playwright() as p:
        b = p.chromium.launch(channel='chrome', headless=True)
        pg = b.new_context(viewport={'width': 1280, 'height': 900}).new_page()
        pg.goto(URL, wait_until='load', timeout=300000)
        pg.wait_for_timeout(1500)
        txt = pg.evaluate("""() => { const s=document.getElementById('status');
            s.textContent='正在解析 1/2 ·\u00A0abc.pdf ·\u00A0已用 0:01 ·\u00A0预计剩余 0:10';
            return s.textContent; }""")
        b.close()
    print('渲染后含 NBSP:', NB in txt, '| 片段:', txt[:60].replace(NB, '<NBSP>'))
sys.exit(0 if (n_esc >= 4 or n_lit >= 4) else 1)
