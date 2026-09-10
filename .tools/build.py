# -*- coding: utf-8 -*-
"""唯一构建入口:模板 + 资产 + 源码 → 单文件 HTML。

纯字节拼接,不做任何「查找旧文本再替换」的锚点补丁——
只要 SOURCES 顺序与槽位内容不变,产物就逐字节可复现。
"""

import hashlib
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(BASE, '.tools')
HTML = os.path.join(BASE, '搜分名单查询工具.html')

# 期望产物:字节等价是本次重构的验收标准
# 见 docs/specs/2026-09-10-构建链重构-design.md §3
EXPECT_SHA = '55ad8f466eaa62d45d0e3446bb6b4b2617f387e0a87167ade879ec8e8d3c6db8'

# 应用块 = 下列文件按顺序拼接。顺序即 IIFE 内部顺序,不可调整。
SOURCES = [
    '00-boot.js', '10-engine.js', '20-cache.js', '30-files.js', '40-parse.js',
    '50-ocr-worker.js', '60-gpu.js', '62-ppu-patch.js', '65-ocr-image.js', '70-pdf.js',
    '75-concurrency.js', '80-progress.js', '85-render.js', '90-export.js', '95-material.js',
    '99-tail.js',
]

# 槽位 → 源文件(相对 .tools)
SLOTS = {
    'style': 'src/style.css',
    'body': 'src/body.html',
    'pdfworker': 'assets/pdfworker.js',
    'jszip': 'assets/jszip.min.js',
    'pdfjs': 'assets/pdf.js',
    'tesseract': 'assets/tesseract.min.js',
    'ocrAssets': 'assets/ocr-assets.js',
    'gpuAssets': 'assets/gpuassets.txt',
}

# 成品里 style / body 被「前后各包一个换行」,源文件末尾换行由构建器统一去掉
# (与旧构建器 CSS = read().rstrip('\n') 语义一致);编辑器加删末尾空行不会改变产物
STRIP_TAIL = {'style', 'body'}


def read(rel):
    """按字节读取 .tools 下的文件。"""
    with open(os.path.join(TOOLS, rel), 'rb') as f:
        return f.read()


def assemble():
    """拼出成品字节(不写盘),供构建与自检共用。"""
    out = read('src/template.html')
    blocks = {}
    for name, rel in SLOTS.items():
        data = read(rel)
        if name in STRIP_TAIL:
            data = data.rstrip(b'\n')
        blocks[name] = data
    blocks['app'] = b''.join(read('src/app/' + name) for name in SOURCES)

    # 逐个替换槽位;每个槽位必须恰好出现一次,否则说明模板与清单不同步
    for name, data in blocks.items():
        token = ('@@SLOT:%s@@' % name).encode('utf-8')
        count = out.count(token)
        if count != 1:
            raise SystemExit('槽位 %s 在模板中出现 %d 次(应为 1)' % (name, count))
        out = out.replace(token, data)

    if b'@@SLOT:' in out:
        raise SystemExit('产物中仍有未替换的槽位')
    return out


def main():
    out = assemble()
    sha = hashlib.sha256(out).hexdigest()
    print('size   %d' % len(out))
    print('sha256 %s' % sha)

    if '--no-assert' not in sys.argv and sha != EXPECT_SHA:
        raise SystemExit('sha256 与期望不符,已中止:\n  期望 %s\n  实际 %s' % (EXPECT_SHA, sha))

    with open(HTML, 'wb') as f:
        f.write(out)
    print('已写出 %s' % HTML)


if __name__ == '__main__':
    main()
