# -*- coding: utf-8 -*-
"""启动器编码自检：`.cmd` 必须纯 ASCII，`.ps1` 必须带 UTF-8 BOM。

两条约束都是被真实故障逼出来的，改启动器后务必跑一遍：
  - cmd.exe 按控制台代码页逐行解析批处理；中文字节会被当成双字节字符吞掉行尾换行，
    后面的代码要么被并进注释，要么被当命令执行（实测报 `'xxx' is not recognized`）。
  - Windows PowerShell 5.1 对**无 BOM** 的 .ps1 按系统代码页（中文 Windows 是 GBK）解析，
    UTF-8 中文注释会被拆坏语法，脚本直接 `Unexpected token` 起不来。

用法: python .tools/launcher_check.py
"""
import os, sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOM = b'\xef\xbb\xbf'

bad = 0
for name in sorted(os.listdir(BASE)):
    p = os.path.join(BASE, name)
    if not os.path.isfile(p):
        continue
    ext = os.path.splitext(name)[1].lower()
    if ext not in ('.cmd', '.ps1'):
        continue
    raw = open(p, 'rb').read()
    if ext == '.cmd':
        n = sum(1 for b in raw if b > 127)
        ok, detail = n == 0, '非 ASCII %d 字节' % n
    else:
        ok, detail = raw[:3] == BOM, 'BOM %s' % ('有' if raw[:3] == BOM else '无')
    bad += 0 if ok else 1
    print('  %-28s %-16s %s' % (name, detail, 'OK' if ok else 'FAIL <<<'))

print('失败项: %d' % bad)
sys.exit(1 if bad else 0)
