# -*- coding: utf-8 -*-
"""材料包导出验收：真机点「导出材料包」，校验目录结构/清单/说明，并逐字节比对来源文件。

覆盖两条来源路径：直接选择的文件（File）与 zip 内部条目（JSZip）。
用法: python ui_zipcheck.py [--kw 学]
输出: .tools/ui_zip_check.zip + .tools/ui_zipcheck.json
"""
import argparse, base64, csv as _csv, io, json, os, re, shutil, sys, zipfile
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from playwright.sync_api import sync_playwright

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET = os.path.join(BASE, 'target')
TOOLS = os.path.join(BASE, '.tools')
PROF = os.path.join(TOOLS, 'prof_ui_zip')
URL = 'http://127.0.0.1:18010/%E6%90%9C%E5%88%86%E5%90%8D%E5%8D%95%E6%9F%A5%E8%AF%A2%E5%B7%A5%E5%85%B7.html'
FILES = ['人工智能与自动化学院团委2025-2026学年学生干部考核结果（班级）.xlsx',
         '晚归打卡公示汇总.pdf',
         '5月24日—6月25日金山学院2026青春运动季活动加分补充说明名单.xlsx.pdf',
         '院团组织-1月份加分文件（最终版）.zip']
YU_DIRS = ('德育测评', '智育测评', '体育测评', '美育测评', '劳育测评', '未识别')

# 抓取导出结果：临时替换 a.click() 只取 blob 地址，再 fetch 出字节。
# 这样绕开"浏览器落盘"这一步（本机偶发在下载瞬间回收页面），导出的仍是同一条链路。
CAPTURE = """async () => {
  const orig = HTMLAnchorElement.prototype.click;
  let href = null;
  HTMLAnchorElement.prototype.click = function(){ href = this.href; };
  try { await window.exportMaterialZip(); } finally { HTMLAnchorElement.prototype.click = orig; }
  if(!href) return { error: '未捕获到下载链接' };
  const r = await fetch(href);
  const b = new Uint8Array(await r.arrayBuffer());
  let s = '';
  const CH = 0x8000;
  for (let i = 0; i < b.length; i += CH) s += String.fromCharCode.apply(null, b.subarray(i, i + CH));
  return { b64: btoa(s), status: document.getElementById('status').textContent };
}"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--kw', default='学')
    ap.add_argument('--files', default='small', choices=('small', 'all'),
                    help='small=3 个小文件+1 个小 zip；all=target 全量（用于验证体积上限守卫）')
    ap.add_argument('--expect-cap', action='store_true', help='断言触发体积上限提示且不下载')
    ap.add_argument('--keep-profile', action='store_true', help='复用 profile（文本缓存还在，第二次几乎瞬回）')
    args = ap.parse_args()

    inputs = FILES if args.files == 'small' else [
        n for n in sorted(os.listdir(TARGET)) if n.lower().endswith(('.zip', '.pdf', '.xlsx'))]
    if os.path.isdir(PROF) and not args.keep_profile:
        shutil.rmtree(PROF, ignore_errors=True)
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            PROF, channel='chrome', headless=False, args=['--window-size=1200,800'],
            viewport={'width': 1200, 'height': 800})
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.set_default_timeout(120000)
        page.goto(URL, wait_until='load', timeout=300000)
        page.wait_for_timeout(2500)
        page.set_input_files('#file', [os.path.join(TARGET, n) for n in inputs])
        page.wait_for_timeout(800)
        page.check('#fuzzy')
        page.fill('#kw', args.kw)
        page.click('#runBtn')
        page.wait_for_function(
            "() => /解析完成|没有文件包含|未找到/.test(document.getElementById('status').textContent)",
            timeout=2400000)
        page.wait_for_timeout(1000)
        rows = page.eval_on_selector_all('#detail .mp-item', 'els => els.length')
        btn = page.evaluate("() => { const e=document.getElementById('dlzip'); "
                            "return e ? getComputedStyle(e).display : 'missing'; }")
        if args.expect_cap:
            # flex 容器里的 flex item 会被块化：inline-flex 的计算值就是 flex
            page.click('#dlzip')
            page.wait_for_timeout(2500)
            status = page.inner_text('#status')
            got_dl = False
            try:
                with page.expect_download(timeout=4000):
                    pass
                got_dl = True
            except Exception:
                got_dl = False
            ctx.close()
            ok = ('上限' in status) and not got_dl
            print('=== 体积上限守卫（%s 全量，检索词 %s，%d 条记录）===' % (args.files, args.kw, rows))
            print('  状态行: %s' % status)
            print('  是否仍下载: %s' % ('是' if got_dl else '否'))
            print('  结果: %s' % ('OK' if ok else 'FAIL <<<'))
            return 0 if ok else 1
        out = os.path.join(TOOLS, 'ui_zip_check.zip')
        res = page.evaluate(CAPTURE)
        if not res.get('b64'):
            print('FAIL：未捕获到材料包内容（%s）' % res.get('error'))
            ctx.close()
            return 1
        open(out, 'wb').write(base64.b64decode(res['b64']))
        status = res.get('status', '')
        ctx.close()

    z = zipfile.ZipFile(out)
    names = [n for n in z.namelist() if not n.endswith('/')]
    mats = [n for n in names if n not in ('说明.txt', '清单.csv')]
    checks = []

    def add(name, ok, extra=''):
        checks.append({'name': name, 'ok': bool(ok), 'extra': extra})

    add('按钮可见（flex 容器内块化为 flex）', btn in ('flex', 'inline-flex'), btn)
    add('含 说明.txt 与 清单.csv', '说明.txt' in names and '清单.csv' in names)
    add('目录深度 = 人/育/文件', all(len(n.split('/')) == 3 for n in mats),
        '%d 个材料文件' % len(mats))
    add('五育目录名规范', all(n.split('/')[1] in YU_DIRS for n in mats))
    bad_name = [n for n in mats if not re.match(r'^([+-]?\d+(?:\.\d+)?|未识别分值) [^/]+$', n.split('/')[-1])]
    add('文件名 = 分值 + 原文件名', not bad_name, '不合规：%s' % bad_name[:3])
    add('人目录 = 学号+检索词', all(re.match(r'^(\d{6,12}|未标学号)', n.split('/')[0]) for n in mats))
    add('说明含上限提醒', '25 分' in z.read('说明.txt').decode('utf-8')
        and '10 分' in z.read('说明.txt').decode('utf-8'))

    # ---- 清单与包内容一致 ----
    rows_csv = list(_csv.reader(io.StringIO(z.read('清单.csv').decode('utf-8-sig'))))
    add('清单行数 = 1 表头 + N 材料', len(rows_csv) - 1 == len(mats),
        '清单 %d 行 / 材料 %d 个' % (len(rows_csv) - 1, len(mats)))
    hdr = rows_csv[0]
    add('清单表头齐全', hdr[:5] == ['学号', '姓名', '五育', '加分值', '事由'], str(hdr))
    i_src, i_nm = hdr.index('来源名单文件'), hdr.index('材料文件名')

    # ---- 逐字节比对来源（直接选择的文件 + zip 内部条目） ----
    srcmap = {}
    for n in FILES:
        p = os.path.join(TARGET, n)
        if n.lower().endswith('.zip'):
            with zipfile.ZipFile(p) as sz:
                for inner in sz.namelist():
                    if not inner.endswith('/'):
                        srcmap[inner] = ('zip', p, inner)
        else:
            srcmap[n] = ('file', p, None)
    same, diff, missing = 0, [], []
    for r in rows_csv[1:]:
        src, mat = r[i_src], r[i_nm]
        ent = next((n for n in mats if n.split('/')[-1] == mat), None)
        if ent is None:
            missing.append(mat)
            continue
        kind = srcmap.get(src)
        if not kind:
            diff.append('来源未知 %s' % src)
            continue
        if kind[0] == 'file':
            ref = open(kind[1], 'rb').read()
        else:
            with zipfile.ZipFile(kind[1]) as sz:
                ref = sz.read(kind[2])
        if ref == z.read(ent):
            same += 1
        else:
            diff.append('字节不一致 %s' % ent)
    add('材料字节与来源逐字节一致', same == len(mats) and not diff and not missing,
        '一致 %d/%d%s' % (same, len(mats), (' · ' + '; '.join((diff + missing)[:3])) if (diff or missing) else ''))

    bad = sum(0 if c['ok'] else 1 for c in checks)
    print('=== 材料包验收（检索词 %s，%d 条记录）===' % (args.kw, rows))
    for c in checks:
        print('  %-28s %s%s' % (c['name'], 'OK' if c['ok'] else 'FAIL <<<',
                                ('  ' + c['extra']) if c['extra'] else ''))
    print('失败项: %d' % bad)
    print('状态行: %s' % status)
    print('包内结构（前 8 条）:')
    for n in mats[:8]:
        print('  ' + n)
    with open(os.path.join(TOOLS, 'ui_zipcheck.json'), 'w', encoding='utf-8') as fh:
        json.dump({'kw': args.kw, 'rows': rows, 'checks': checks, 'entries': mats,
                   'zip_bytes': os.path.getsize(out), 'status': status}, fh, ensure_ascii=False, indent=1)
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
