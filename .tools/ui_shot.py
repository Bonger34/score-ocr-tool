# -*- coding: utf-8 -*-
"""UI 验收：驱动真实页面走完各状态，截图 + 结构化自检（溢出/字体/语义/下载）。

用法: python ui_shot.py [--tag v25] [--ocr]
输出: .screenshots/ui_<tag>_*.png + .tools/ui_audit_<tag>.json
"""
import argparse, json, os, shutil, sys, time, zipfile
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from playwright.sync_api import sync_playwright

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHOTS = os.path.join(BASE, '.screenshots')
TOOLS = os.path.join(BASE, '.tools')
URL = 'http://127.0.0.1:18010/%E6%90%9C%E5%88%86%E5%90%8D%E5%8D%95%E6%9F%A5%E8%AF%A2%E5%B7%A5%E5%85%B7.html'
SMALL = ['人工智能与自动化学院团委2025-2026学年学生干部考核结果（班级）.xlsx',
         '晚归打卡公示汇总.pdf',
         '5月24日—6月25日金山学院2026青春运动季活动加分补充说明名单.xlsx.pdf']
BIG = '3月16日-4月17日福建农林大学金山学院（安溪）2026年度团学活动之构图青春打卡活动加分文件(3) (1).pdf'

AUDIT = """() => {
  const ids = ['kw','dedup','ocr','fuzzy','eng','engWrap','engStatus','engDot','engText','runBtn',
               'status','drop','file','bar','barfill','barpct','resultCard','summary','dupbox',
               'detail','dlxlsx','jobStrip','announce','fileMeta','fileMetaWrap'];
  const missing = ids.filter(i => !document.getElementById(i));
  const over = [];
  document.querySelectorAll('body *').forEach(el => {
    if (el.scrollWidth > el.clientWidth + 2 && el.clientWidth > 0 &&
        getComputedStyle(el).overflowX !== 'auto' && el.id !== 'kw') {
      over.push((el.tagName + (el.id ? '#' + el.id : '') + '.' + (el.className || '')).slice(0, 60));
    }
  });
  const cs = n => { const el = document.querySelector(n); return el ? getComputedStyle(el) : null; };
  const h1 = cs('.masthead h1'), td = cs('td.num'), job = cs('.job'), btn = cs('.btn');
  return {
    missingIds: missing,
    overflow: over.slice(0, 12),
    hOverflow: document.documentElement.scrollWidth - window.innerWidth,
    serifLoaded: document.fonts.check('700 26px "Noto Serif SC"'),
    h1Family: h1 ? h1.fontFamily : null,
    numAlign: td ? td.textAlign : null,
    jobBg: job ? job.backgroundColor : null,
    btnBg: btn ? btn.backgroundColor : null,
    live: !!document.querySelector('#announce[role=status]'),
    progressRole: (document.getElementById('bar') || {}).getAttribute
        ? document.getElementById('bar').getAttribute('role') : null,
    dropTag: (document.getElementById('drop') || {}).tagName || null,
    dlTag: (document.getElementById('dlxlsx') || {}).tagName || null,
    thScope: Array.from(document.querySelectorAll('thead th')).map(t => t.getAttribute('scope')),
    caption: !!document.querySelector('#dupbox caption'),
    dropFocusable: !!document.querySelector('#file') && !document.getElementById('file').disabled,
    titleAttrs: Array.from(document.querySelectorAll('[title]')).map(e => e.getAttribute('title').slice(0, 40)),
  };
}"""


def shot(page, name):
    p = os.path.join(SHOTS, name)
    page.screenshot(path=p)
    print('  shot', os.path.basename(p), flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--tag', default='v25')
    ap.add_argument('--ocr', action='store_true', help='额外跑一次 OCR（含扫描件），截运行中状态')
    args = ap.parse_args()
    paths = [os.path.join(BASE, 'target', n) for n in SMALL]
    out = {'tag': args.tag, 'errors': [], 'phases': {}}

    with sync_playwright() as p:
        b = p.chromium.launch(channel='chrome', headless=True,
                              args=['--enable-webgpu', '--force_high_performance_gpu'])
        ctx = b.new_context(viewport={'width': 1280, 'height': 900}, accept_downloads=True)
        page = ctx.new_page()
        page.set_default_timeout(60000)
        page.on('pageerror', lambda e: out['errors'].append('pageerror: ' + str(e)[:200]))
        page.on('console', lambda m: out['errors'].append('[%s] %s' % (m.type, m.text[:200]))
               if m.type == 'error' else None)
        page.goto(URL, wait_until='load', timeout=300000)
        page.wait_for_timeout(2500)
        shot(page, 'ui_%s_1_idle.png' % args.tag)
        out['phases']['idle'] = page.evaluate(AUDIT)

        # --- 已选文件 ---
        page.set_input_files('#file', paths)
        page.wait_for_timeout(1200)
        page.fill('#kw', '学')
        page.check('#fuzzy')
        shot(page, 'ui_%s_2_picked.png' % args.tag)
        out['phases']['picked'] = {'fileMeta': page.inner_text('#fileMeta'),
                                   'status': page.inner_text('#status'),
                                   'compactDrop': page.evaluate("() => document.getElementById('drop').classList.contains('compact')")}
        # 追加语义：再选一个文件，已选数量应累加（不是替换）
        page.set_input_files('#file', [os.path.join(BASE, 'target', '加分文件补充.zip')])
        page.wait_for_timeout(900)
        out['phases']['append'] = page.inner_text('#fileMeta')
        # 清空：回到初始态
        page.click('.btn-quiet')
        page.wait_for_timeout(500)
        out['phases']['cleared'] = {'metaVisible': page.is_visible('#fileMetaWrap'),
                                    'runDisabled': page.is_disabled('#runBtn'),
                                    'compact': page.evaluate("() => document.getElementById('drop').classList.contains('compact')")}
        page.set_input_files('#file', paths)
        page.wait_for_timeout(800)

        # --- 空结果 ---
        page.fill('#kw', '查无此人名字')
        page.click('#runBtn')
        page.wait_for_function("() => /没有命中/.test(document.getElementById('status').textContent)", timeout=120000)
        page.wait_for_timeout(400)
        shot(page, 'ui_%s_3_empty.png' % args.tag)
        out['phases']['empty'] = {'status': page.inner_text('#status'),
                                  'summary': page.inner_text('#summary')[:200]}

        # --- 正常结果 ---
        page.fill('#kw', '学')
        page.click('#runBtn')
        page.wait_for_function("() => /解析完成/.test(document.getElementById('status').textContent)", timeout=300000)
        page.wait_for_timeout(600)
        shot(page, 'ui_%s_4_result.png' % args.tag)
        page.screenshot(path=os.path.join(SHOTS, 'ui_%s_4_result_full.png' % args.tag), full_page=True)
        out['phases']['result'] = {
            'status': page.inner_text('#status'),
            'ledger': page.inner_text('#summary').replace('\n', ' | ')[:220],
            'rows': page.eval_on_selector_all('#detail .mp-item', 'els => els.length'),
            'total': page.eval_on_selector_all('#summary .ledger .cell:last-child b', 'els => els.map(e => e.textContent)'),
            'dupShown': page.is_visible('#dupbox'),
            'dupSummary': (page.inner_text('#dupbox')[:120] if page.is_visible('#dupbox') else ''),
            'audit': page.evaluate(AUDIT),
        }
        # 导出按钮可用性
        if page.is_visible('#dlxlsx'):
            with page.expect_download(timeout=60000) as dl:
                page.click('#dlxlsx')
            out['phases']['result']['download'] = dl.value.suggested_filename
            # 顺手校验 Excel 与清单同源（重语料回归里导出偶发被浏览器回收，行数断言放这里更稳）
            try:
                xp = os.path.join(TOOLS, 'ui_export_check.xlsx')
                try:
                    shutil.copyfile(dl.value.path(), xp)
                except Exception:
                    dl.value.save_as(xp)
                with zipfile.ZipFile(xp) as z:
                    s1 = z.read('xl/worksheets/sheet1.xml').decode('utf-8')
                    s2 = z.read('xl/worksheets/sheet2.xml').decode('utf-8')
                out['phases']['result']['xlsx'] = {
                    'sheet1_rows': s1.count('<row '), 'sheet2_rows': s2.count('<row '),
                    'expect_sheet1': 1 + out['phases']['result']['rows']}
            except Exception as e:
                out['phases']['result']['xlsx'] = {'error': str(e)[:140]}
        # 材料包真实下载（小样本下这条落盘路径稳定；重语料场景由 ui_zipcheck.py 抓 blob 验证）
        if page.is_visible('#dlzip'):
            try:
                with page.expect_download(timeout=120000) as dl2:
                    page.click('#dlzip')
                d2 = dl2.value
                xp2 = os.path.join(TOOLS, 'ui_zip_check_shot.zip')
                try:
                    shutil.copyfile(d2.path(), xp2)
                except Exception:
                    d2.save_as(xp2)
                out['phases']['result']['zip'] = {'name': d2.suggested_filename,
                                                  'bytes': os.path.getsize(xp2)}
            except Exception as e:
                out['phases']['result']['zip'] = {'error': str(e)[:140]}
            print('  download ok:', dl.value.suggested_filename, flush=True)
        else:
            out['phases']['result']['download'] = 'BUTTON HIDDEN'

        # --- 窄屏 ---
        page.set_viewport_size({'width': 390, 'height': 844})
        page.wait_for_timeout(600)
        shot(page, 'ui_%s_5_mobile.png' % args.tag)
        page.screenshot(path=os.path.join(SHOTS, 'ui_%s_5_mobile_full.png' % args.tag), full_page=True)
        out['phases']['mobile'] = page.evaluate(AUDIT)
        page.set_viewport_size({'width': 1280, 'height': 900})

        # --- 运行中（OCR）---
        if args.ocr:
            page.reload(wait_until='load', timeout=300000)
            page.wait_for_timeout(2000)
            page.set_input_files('#file', [os.path.join(BASE, 'target', BIG)])
            page.wait_for_timeout(800)
            page.check('#ocr')
            page.fill('#kw', '学')
            page.click('#runBtn')
            # 运行中状态多拍几张：解析/OCR 各阶段占比不同，挑信息最全的那张
            out['phases']['running'] = []
            for k in range(4):
                page.wait_for_timeout(15000)
                shot(page, 'ui_%s_6_running_%d.png' % (args.tag, k + 1))
                out['phases']['running'].append({
                    'status': page.inner_text('#status'),
                    'pct': page.inner_text('#barpct'),
                    'jobBg': page.evaluate("() => getComputedStyle(document.getElementById('jobStrip')).backgroundColor"),
                    'aria': page.get_attribute('#bar', 'aria-valuenow')})
            try:
                page.wait_for_function("() => /解析完成|没有文件包含/.test(document.getElementById('status').textContent)", timeout=900000)
                page.wait_for_timeout(500)
                shot(page, 'ui_%s_7_ocr_result.png' % args.tag)
            except Exception as e:
                out['errors'].append('ocr wait: ' + str(e)[:150])

        ctx.close()
        b.close()

    with open(os.path.join(BASE, '.tools', 'ui_audit_%s.json' % args.tag), 'w', encoding='utf-8') as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
    print('=== audit ===')
    print(json.dumps(out, ensure_ascii=False, indent=1)[:6000])
    return 0


if __name__ == '__main__':
    sys.exit(main())
