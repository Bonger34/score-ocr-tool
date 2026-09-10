# -*- coding: utf-8 -*-
"""最终版 OCR 路径验收：一份多页密集扫描件（自备，默认取 .samples/008__*）走 GPU OCR，
确认新版界面下 OCR 全程可用、进度条/状态/结果渲染正常。

用法: python ui_ocrcheck.py
"""
import glob, json, os, sys, time
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from playwright.sync_api import sync_playwright

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 需自备一个多页扫描件：设 SAMPLE_PDF 环境变量，或把文件放到 .samples/ 并以 008__ 开头
_cands = sorted(glob.glob(os.path.join(BASE, '.samples', '008__*.pdf')))
PDF = os.environ.get('SAMPLE_PDF') or (_cands[0] if _cands else '')
URL = 'http://127.0.0.1:18010/%E6%90%9C%E5%88%86%E5%90%8D%E5%8D%95%E6%9F%A5%E8%AF%A2%E5%B7%A5%E5%85%B7.html'

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(
        os.path.join(BASE, '.tools', 'prof_ui_ocr'), channel='chrome', headless=False,
        args=['--enable-webgpu', '--force_high_performance_gpu', '--window-size=1200,800'],
        viewport={'width': 1200, 'height': 800})
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.set_default_timeout(120000)
    errs = []
    page.on('pageerror', lambda e: errs.append(str(e)[:200]))
    page.goto(URL, wait_until='load', timeout=300000)
    page.wait_for_timeout(2500)
    page.set_input_files('#file', [PDF])
    page.wait_for_timeout(800)
    page.check('#ocr')
    page.fill('#kw', '学')
    page.check('#fuzzy')
    try:
        page.wait_for_function("() => /GPU ·|内置 Tesseract/.test(document.getElementById('engText').textContent)", timeout=180000)
    except Exception as e:
        print('engine wait:', str(e)[:100])
    print('engine:', page.inner_text('#engText'), flush=True)
    t0 = time.time()
    page.click('#runBtn')
    samples = []
    while time.time() - t0 < 900:
        page.wait_for_timeout(5000)
        st = page.inner_text('#status')
        pct = page.inner_text('#barpct')
        bar = page.evaluate("""() => { const f=document.getElementById('barfill'), t=document.getElementById('bar');
            return t.getBoundingClientRect().width ? Math.round(f.getBoundingClientRect().width/t.getBoundingClientRect().width*100) : null; }""")
        samples.append({'t': round(time.time() - t0), 'pct': pct, 'bar': bar, 'status': st[:70]})
        print('[%4ds] %-6s bar=%-4s %s' % (time.time() - t0, pct, bar, st[:70]), flush=True)
        if '解析完成' in st or '没有命中' in st:
            break
    out = {
        'wall': round(time.time() - t0, 1),
        'engine': page.inner_text('#engText'),
        'status': page.inner_text('#status'),
        'rows': page.eval_on_selector_all('#detail .mp-item', 'els => els.length'),
        'ledger': page.inner_text('#summary').replace('\n', ' | ')[:200],
        'perf': page.evaluate("() => window.__ocrPerf__ ? JSON.stringify(window.__ocrPerf__).slice(0,600) : null"),
        'samples': samples[-6:],
        'errors': errs,
    }
    page.screenshot(path=os.path.join(BASE, '.screenshots', 'ui_v25final_6_ocr.png'))
    ctx.close()

with open(os.path.join(BASE, '.tools', 'ui_ocrcheck.json'), 'w', encoding='utf-8') as fh:
    json.dump(out, fh, ensure_ascii=False, indent=1)
print(json.dumps(out, ensure_ascii=False, indent=1)[:2000])
