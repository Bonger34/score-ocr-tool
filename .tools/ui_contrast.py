# -*- coding: utf-8 -*-
"""配色对比度自检：从 .tools/src/style.css 读取色值，按 WCAG 2.1 计算对比度。

用法: python ui_contrast.py
"""
import os, re, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSS = open(os.path.join(BASE, '.tools', 'src', 'style.css'), encoding='utf-8').read()
VARS = dict(re.findall(r'--([a-z0-9-]+)\s*:\s*(#[0-9A-Fa-f]{6})', CSS))
LIT = {'#fff': '#FFFFFF', '#F3F6F1': '#F3F6F1', '#F2F5F0': '#F2F5F0', '#F7F9F6': '#F7F9F6',
       '#6B2A22': '#6B2A22', '#C7D4CA': '#C7D4CA', '#174034': '#174034', '#B6C2BA': '#B6C2BA'}


def hex2rgb(h):
    h = h.lstrip('#')
    if len(h) == 3:
        h = ''.join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def lum(rgb):
    def f(c):
        c /= 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = rgb
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def ratio(a, b):
    la, lb = lum(hex2rgb(a)), lum(hex2rgb(b))
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def v(name):
    if name in VARS:
        return VARS[name]
    if name in LIT:
        return LIT[name]
    if name.startswith('#'):
        return name
    raise SystemExit('未知色值: ' + name)


# (说明, 前景, 背景, 字号, 要求)
CASES = [
    ('正文', 'ink', 'sheet', 13.5, 4.5),
    ('次级文字', 'ink-2', 'sheet', 12.5, 4.5),
    ('辅助文字（提示/说明）', 'ink-3', 'sheet', 12, 4.5),
    ('表头文字', 'ink-2', '#F2F5F0', 12, 4.5),
    ('主按钮文字', '#fff', 'brand', 14, 4.5),
    ('主按钮悬停', '#fff', '#174034', 14, 4.5),
    ('禁用按钮文字', 'ink-3', '#E4E9E2', 14, 3.0),   # 禁用态 WCAG 豁免，但仍要求 ≥3
    ('作业条百分比', '#F3F6F1', 'ink', 34, 4.5),
    ('作业条状态小字', '#C7D4CA', 'ink', 12.5, 4.5),
    ('警示条文字', '#6B2A22', 'seal-soft', 12.5, 4.5),
    ('德育标签', 'de', 'sheet', 13, 4.5),
    ('智育标签', 'zhi', 'sheet', 13, 4.5),
    ('体育标签', 'ti', 'sheet', 13, 4.5),
    ('美育标签', 'mei', 'sheet', 13, 4.5),
    ('劳育标签', 'lao', 'sheet', 13, 4.5),
    ('明细加分值', 'ink', '#FFFFFF', 14, 4.5),
    ('明细事由', 'ink', '#FFFFFF', 13, 4.5),
    ('明细来源文件', 'ink-3', '#FFFFFF', 11.5, 4.5),
    ('明细人块表头', 'ink-2', '#F2F5F0', 12.5, 4.5),
    ('明细育段标题', 'ink-2', '#FBFCFA', 12.5, 4.5),
    ('明细育段条数', 'ink-3', '#FBFCFA', 12.5, 4.5),
    ('明细超上限提醒', 'seal', '#FBFCFA', 12.5, 4.5),
    ('重复行文字', '#6B2A22', 'seal-soft', 13, 4.5),
    ('学号缺失占位', 'ink-3', '#FFFFFF', 13, 4.5),
    ('页脚', 'ink-2', 'paper', 12, 4.5),
]

bad = 0
print('%-24s %-9s %-9s %6s %6s  %s' % ('场景', '前景', '背景', '对比度', '要求', '结果'))
for label, fg, bg, size, need in CASES:
    a, b = v(fg), v(bg)
    r = ratio(a, b)
    ok = r >= need
    bad += 0 if ok else 1
    print('%-24s %-9s %-9s %6.2f %6.1f  %s' % (label, a, b, r, need, 'PASS' if ok else 'FAIL  <<<'))
print('\n失败项:', bad)
sys.exit(1 if bad else 0)
