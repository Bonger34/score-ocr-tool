# -*- coding: utf-8 -*-
"""给 README 出图：截取合成数据预览页（.tools/demo/ui_demo.html）。

预览页喂的是编造记录，因此产物**不含任何真实姓名/学号**——真实数据的截图不能公开。

用法:
  1) python -m http.server 18010 --bind 127.0.0.1
  2) python .tools/shot_demo.py
输出: docs/截图/结果区-桌面.png、docs/截图/结果区-窄屏.png
"""
import os, sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from playwright.sync_api import sync_playwright

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, 'docs', '截图')
URL = 'http://127.0.0.1:18010/.tools/demo/ui_demo.html'

# (文件名, 视口宽, 视口高)：桌面看完整结果区，窄屏验证重排
SHOTS = [('结果区-桌面.png', 1280, 1200), ('结果区-窄屏.png', 420, 1200)]


def main():
    os.makedirs(OUT, exist_ok=True)
    with sync_playwright() as p:
        b = p.chromium.launch(channel='chrome', headless=True)
        for name, w, h in SHOTS:
            ctx = b.new_context(viewport={'width': w, 'height': h}, device_scale_factor=2)
            pg = ctx.new_page()
            pg.goto(URL, wait_until='load', timeout=120000)
            pg.wait_for_timeout(800)                      # 等字体与排版稳定
            pg.screenshot(path=os.path.join(OUT, name), full_page=True)
            print('已出图: %s' % name)
            ctx.close()
        b.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
