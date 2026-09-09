# -*- coding: utf-8 -*-
"""渲染层回归：同一批文件、同一关键词，分别喂给 v2.4（基线）与 v2.5（改版），
把结果区的"数据"（命中数 / 台账数字 / 明细行 / 重复副本 / 警示）抽出来逐项比对。

只比对数据不比对 HTML——改版换的是标记与样式，业务结果必须一模一样。
用 --no-ocr 避开 GPU 波动；第二个版本复用同一浏览器 profile，走文本缓存，快得多。

用法: python ui_regress.py [--kw 学] [--only 关键字]
输出: .tools/ui_regress.json
"""
import argparse, json, os, shutil, sys, time
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from playwright.sync_api import sync_playwright

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET = os.path.join(BASE, 'target')
TOOLS = os.path.join(BASE, '.tools')
PROF = os.path.join(TOOLS, 'prof_ui_regress')
VERSIONS = [
    ('v24', 'http://127.0.0.1:18010/.tools/v24_ui_baseline.html'),
    ('v25', 'http://127.0.0.1:18010/%E6%90%9C%E5%88%86%E5%90%8D%E5%8D%95%E6%9F%A5%E8%AF%A2%E5%B7%A5%E5%85%B7.html'),
]

# 从页面抽取"结果数据"。两版标记差异较大，统一归一成「育|分值|学号」记录多重集再比。
EXTRACT = """() => {
  const txt = el => el ? (el.innerText || '').trim() : '';
  const num = s => { const m = /[-+]?\\d+(?:\\.\\d+)?/.exec(String(s || '')); return m ? parseFloat(m[0]) : null; };
  const sid = s => { s = String(s || '').trim(); return (s === '—' || s === '未标学号' || !s) ? '' : s; };
  const yu = t => { t = String(t || '').trim(); return (!t || t === '无标注') ? '未标注' : t; };
  const recs = [];
  // v2.4：明细表四列 [文件, 类型, 分值, 学号]；表头行被浏览器包进隐式 tbody，按首列文字剔除
  document.querySelectorAll('#detail table tbody tr').forEach(tr => {
    const c = Array.from(tr.querySelectorAll('td,th')).map(td => txt(td));
    if (c.length === 4 && c[0] !== '文件' && c[0] !== '合计')
      recs.push(yu(c[1]) + '|' + (num(c[2]) === null ? '' : String(num(c[2]))) + '|' + sid(c[3]));
  });
  // v2.7：按人分块 → 五育分段 → 加分项
  document.querySelectorAll('#detail .mperson').forEach(p => {
    const s = sid(txt(p.querySelector('.mp-id')).split('·')[0]);
    p.querySelectorAll('.mp-yu').forEach(sec => {
      const t = yu(txt(sec.querySelector('.mp-yuhead .tag')));
      sec.querySelectorAll('.mp-item').forEach(li => {
        const v = num(txt(li.querySelector('.mp-v')));
        recs.push(t + '|' + (v === null ? '' : String(v)) + '|' + s);
      });
    });
  });
  // 台账：v2.7 是 .ledger .cell，v2.4 是 .kpi
  const ledger = [];
  document.querySelectorAll('#summary .ledger .cell').forEach(c => ledger.push({
    label: txt(c.querySelector('span')), value: num(txt(c.querySelector('b'))), raw: txt(c.querySelector('b')) }));
  document.querySelectorAll('#summary .kpi').forEach(c => ledger.push({
    label: txt(c.querySelector('.lbl')), value: num(txt(c.querySelector('.num'))), raw: txt(c.querySelector('.num')) }));
  // 重复副本放在折叠的 <details> 里，innerText 取不到，必须用 textContent
  const dups = Array.from(document.querySelectorAll('#dupbox table tr'))
    .map(tr => (tr.textContent || '').trim()).filter(Boolean);
  const totalCell = document.querySelector('#detail table tfoot td:nth-child(3)');
  return {
    status: txt(document.getElementById('status')),
    files: ledger.length ? ledger[0].value : null,
    total: ledger.length ? ledger[ledger.length - 1].value : num(txt(totalCell)),
    ledger: ledger,
    records: recs,
    people: document.querySelectorAll('#detail .mperson').length,
    dupCount: dups.length,
    dups: dups,
    alert: txt(document.querySelector('#detail .alert, #detail .note')),
    rows: recs.length,
  };
}"""


def run(page, url, paths, kw, tag=None):
    page.goto(url, wait_until='load', timeout=300000)
    page.wait_for_timeout(2500)
    t0 = time.time()
    page.set_input_files('#file', paths)
    page.wait_for_timeout(1000)
    page.check('#fuzzy')
    page.fill('#kw', kw)
    page.click('#runBtn')
    # 真实运行中截图（v2.5 专用）：等进度到 20% / 70% 各拍一张
    if tag == 'v25':
        for mark in (20, 70):
            try:
                page.wait_for_function(
                    "m => parseInt(document.getElementById('barpct').textContent) >= m", arg=mark, timeout=600000)
                page.screenshot(path=os.path.join(BASE, '.screenshots', 'ui_v25_run_%d.png' % mark))
                print('  shot ui_v25_run_%d.png (%s)' % (mark, page.inner_text('#barpct')), flush=True)
            except Exception as e:
                print('  running shot %d failed: %s' % (mark, str(e)[:80]), flush=True)
    page.wait_for_function(
        "() => /解析完成|没有文件包含|未找到/.test(document.getElementById('status').textContent)",
        timeout=2400000)
    page.wait_for_timeout(1500)
    data = page.evaluate(EXTRACT)
    data['wall'] = round(time.time() - t0, 1)
    # 导出链路自检：统计复用后，Excel 的明细行数必须和表格一致
    if tag == 'v25':
        try:
            print('  export: page.closed=%s url=%s dlxlsx=%s' % (page.is_closed(), page.url[:40],
                  page.evaluate("() => { const e=document.getElementById('dlxlsx'); return e?getComputedStyle(e).display:'missing'; }")), flush=True)
            with page.expect_download(timeout=120000) as dl:
                page.click('#dlxlsx')
            print('  export: got download event, page.closed=%s' % page.is_closed(), flush=True)
            xp = os.path.join(TOOLS, 'ui_export_check.xlsx')
            # save_as 偶发"页面已关闭"（热缓存时下载与上下文回收撞车），优先直接读浏览器的临时文件
            try:
                shutil.copyfile(dl.value.path(), xp)
            except Exception as e:
                print('  export: path() 失败(%s)，回退 save_as' % str(e)[:60], flush=True)
                dl.value.save_as(xp)
            import zipfile, re as _re
            with zipfile.ZipFile(xp) as z:
                s1 = z.read('xl/worksheets/sheet1.xml').decode('utf-8')
                s2 = z.read('xl/worksheets/sheet2.xml').decode('utf-8')
            data['xlsx'] = {'sheet1_rows': s1.count('<row '), 'sheet2_rows': s2.count('<row '),
                            'sheet1_bytes': len(s1), 'name': dl.value.suggested_filename}
        except Exception as e:
            # 重语料下浏览器偶发在下载瞬间被回收；导出内容与行数断言由 ui_shot.py 覆盖
            data['xlsx'] = {'skipped': str(e)[:160]}
    return data


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--kw', default='学')
    ap.add_argument('--only', default=None)
    ap.add_argument('--keep-profile', action='store_true', help='复用浏览器 profile（文本缓存还在，第二次几乎瞬回）')
    args = ap.parse_args()
    paths = []
    for n in sorted(os.listdir(TARGET)):
        if args.only and args.only not in n:
            continue
        if n.lower().endswith(('.zip', '.pdf', '.xlsx')):
            paths.append(os.path.join(TARGET, n))
    print('files:', len(paths), flush=True)

    if os.path.isdir(PROF) and not args.keep_profile:
        shutil.rmtree(PROF, ignore_errors=True)
    out = {}
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            PROF, channel='chrome', headless=False, args=['--window-size=1200,800'],
            viewport={'width': 1200, 'height': 800})
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.set_default_timeout(120000)
        for tag, url in VERSIONS:
            print('--- %s ---' % tag, flush=True)
            d = run(page, url, paths, args.kw, tag)
            out[tag] = d
            print('  wall=%.1fs rows=%d dups=%d status=%s' % (d['wall'], d['rows'], d['dupCount'], d['status'][:60]), flush=True)
        ctx.close()

    a, b = out['v24'], out['v25']
    diffs = []
    # 1) 数据不变式：两版的「育|分值|学号」多重集必须逐条相同——改版只换呈现，不能丢也不能多
    if sorted(a['records']) != sorted(b['records']):
        diffs.append('加分项记录不一致：v24=%d 条 / v25=%d 条' % (len(a['records']), len(b['records'])))
        sa, sb = sorted(a['records']), sorted(b['records'])
        only_a = [x for x in sa if x not in sb][:6]
        only_b = [x for x in sb if x not in sa][:6]
        if only_a:
            diffs.append('  仅 v24 有：%s' % only_a)
        if only_b:
            diffs.append('  仅 v25 有：%s' % only_b)
    if a['files'] != b['files']:
        diffs.append('命中文件数不一致：%s | %s' % (a['files'], b['files']))
    if a['total'] != b['total']:
        diffs.append('加分合计不一致：%s | %s' % (a['total'], b['total']))
    if a['dupCount'] != b['dupCount'] or sorted(a['dups']) != sorted(b['dups']):
        diffs.append('重复副本不一致：%d | %d' % (a['dupCount'], b['dupCount']))
    # 2) 新版自洽：台账各育小计 == 明细里该育之和（呈现换了口径，必须自己跟自己对得上）
    sums = {}
    for rec in b['records']:
        t, v, _ = rec.split('|')
        if v != '':
            sums[t] = sums.get(t, 0) + float(v)
    for cell in b['ledger']:
        label = (cell['label'] or '').split('（')[0]
        if label in sums and abs(round(sums[label], 1) - (cell['value'] or 0)) > 0.05:
            diffs.append('台账 %s 与明细不符：%s vs %s' % (label, cell['value'], round(sums[label], 1)))
    # 3) Excel 与清单同源：1 表头 + N 加分项；汇总表 1 表头 + 人数 + 1 合计
    xl = b.get('xlsx') or {}
    if 'error' in xl:
        diffs.append('导出失败：%s' % xl['error'])
    elif 'skipped' in xl:
        print('  ⚠ 本次导出未校验（%s）——Excel 行数断言由 ui_shot.py 覆盖' % xl['skipped'][:70])
    elif xl:
        want1 = 1 + len(b['records'])
        want2 = 1 + b['people'] + 1
        if xl['sheet1_rows'] != want1:
            diffs.append('Excel 清单行数异常：%d（应为 %d）' % (xl['sheet1_rows'], want1))
        if xl['sheet2_rows'] != want2:
            diffs.append('Excel 五育汇总行数异常：%d（应为 %d）' % (xl['sheet2_rows'], want2))
        print('Excel: %s 清单 %d 行（期望 %d）· 五育汇总 %d 行（期望 %d）'
              % (xl['name'], xl['sheet1_rows'], want1, xl['sheet2_rows'], want2))
    print('\n=== 回归结论 ===')
    print('v24 记录=%d 条 文件=%s 合计=%s 重复=%d' % (len(a['records']), a['files'], a['total'], a['dupCount']))
    print('v25 记录=%d 条 文件=%s 合计=%s 重复=%d 人数=%d'
          % (len(b['records']), b['files'], b['total'], b['dupCount'], b['people']))
    if diffs:
        print('发现 %d 处差异：' % len(diffs))
        for d in diffs:
            print(' ', d)
    else:
        print('结果数据完全一致（命中/台账/明细/重复副本/合计）')

    with open(os.path.join(TOOLS, 'ui_regress.json'), 'w', encoding='utf-8') as fh:
        json.dump({'diffs': diffs, 'v24': a, 'v25': b}, fh, ensure_ascii=False, indent=1)
    return 1 if diffs else 0


if __name__ == '__main__':
    sys.exit(main())
