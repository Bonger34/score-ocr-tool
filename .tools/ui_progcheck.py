# -*- coding: utf-8 -*-
"""进度条 / 倒计时准确性验收：跑一次真实任务，每 500ms 采样一次，量化四个指标。

  freeze   —— 进度条冻结（连续 ≥2s 百分比不动）的总时长与最长一段：旧版在扫描件上会长时间卡住
  eta_mae  —— 显示剩余时间与真实剩余时间的平均绝对误差（只统计前 10% 之后的样本）
  eta_rel  —— 跑到 50% / 80% 墙钟时间时的相对误差
  sync     —— 进度条填充宽度与百分比数字是否逐帧一致；百分比是否单调不回退

用法: python ui_progcheck.py --tag v26 [--url ...] [--files 关键词1,关键词2] [--ocr] [--no-ocr]
"""
import json, os, re, shutil, sys, time
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from playwright.sync_api import sync_playwright

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLES = os.path.join(BASE, '.samples')
DEFAULT_URL = 'http://127.0.0.1:18010/%E6%90%9C%E5%88%86%E5%90%8D%E5%8D%95%E6%9F%A5%E8%AF%A2%E5%B7%A5%E5%85%B7.html'
DEFAULT_FILES = ['008__', '000__', '001__', '010__']   # 1 份 24 页扫描件 + 3 份文本 PDF


def pick(keywords):
    out = []
    for kw in keywords:
        if os.path.exists(kw):          # 直接给路径（例如一个测试 zip）
            out.append(os.path.abspath(kw)); continue
        for n in sorted(os.listdir(SAMPLES)):
            if n.startswith(kw):
                out.append(os.path.join(SAMPLES, n)); break
    return out


def parse_clock(text, label):
    """从状态行里取 "label M:SS" 或 "label H:MM:SS"；没显示数字时返回 None"""
    m = re.search(label + r'\s+(\d+):(\d+)(?::(\d+))?', text)
    if not m:
        return None
    if m.group(3) is not None:
        return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
    return int(m.group(1)) * 60 + int(m.group(2))


def parse_eta(text):
    return parse_clock(text, r'预计剩余')


def parse_elapsed(text):
    return parse_clock(text, r'已用')


def main():
    args = sys.argv[1:]
    tag = args[args.index('--tag') + 1] if '--tag' in args else 'v26'
    url = args[args.index('--url') + 1] if '--url' in args else DEFAULT_URL
    kws = (args[args.index('--files') + 1].split(',') if '--files' in args else DEFAULT_FILES)
    use_ocr = '--no-ocr' not in args
    files = pick(kws)
    profile = os.path.join(BASE, '.tools', 'prof_prog_' + tag)
    if os.path.isdir(profile):
        shutil.rmtree(profile, ignore_errors=True)   # 每次冷缓存，两次对比才可比

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            profile, channel='chrome', headless=False,
            args=['--enable-webgpu', '--force_high_performance_gpu', '--window-size=1200,800'],
            viewport={'width': 1200, 'height': 800})
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.set_default_timeout(180000)
        errs = []
        page.on('pageerror', lambda e: errs.append(str(e)[:200]))
        page.goto(url, wait_until='load', timeout=300000)
        page.wait_for_timeout(2500)
        page.set_input_files('#file', files)
        page.wait_for_timeout(600)
        if use_ocr:
            page.check('#ocr')
        page.fill('#kw', '学')
        page.check('#fuzzy')
        if use_ocr:
            try:
                page.wait_for_function(
                    "() => /GPU ·|内置 Tesseract|CPU/.test(document.getElementById('engText').textContent)",
                    timeout=180000)
            except Exception:
                pass
        print('tag=%s files=%s ocr=%s engine=%s'
              % (tag, [os.path.basename(f)[:6] for f in files], use_ocr, page.inner_text('#engText')), flush=True)

        t0 = time.time()
        page.click('#runBtn')
        samples = []
        while time.time() - t0 < 900:
            page.wait_for_timeout(500)
            st = page.inner_text('#status')
            pct = page.inner_text('#barpct')
            bar = page.evaluate("""() => { const f=document.getElementById('barfill'), t=document.getElementById('bar');
                return t.getBoundingClientRect().width
                  ? Math.round(f.getBoundingClientRect().width/t.getBoundingClientRect().width*1000)/10 : null; }""")
            samples.append({'t': round(time.time() - t0, 2),
                            'pct': int(pct.replace('%', '')) if pct.strip('%').isdigit() else None,
                            'bar': bar, 'eta': parse_eta(st), 'elapsed': parse_elapsed(st),
                            'status': st[:90]})
            if '解析完成' in st or '没有命中' in st or '未找到' in st:
                break
        wall = round(time.time() - t0, 1)
        rows = page.eval_on_selector_all('#detail .mp-item', 'els => els.length')
        ctx.close()

    # ---------- 指标 ----------
    live = [s for s in samples if s['pct'] is not None]
    mono = sum(1 for a, b in zip(live, live[1:]) if b['pct'] < a['pct'])
    sync = max([abs(s['bar'] - s['pct']) for s in live if s['bar'] is not None] or [0])

    def runs_of(key):
        """把"同一个值连续出现"的采样段算出来（按段，不是按采样间隔）"""
        out, i = [], 0
        while i < len(live):
            j = i
            while j + 1 < len(live) and live[j + 1][key] == live[i][key]:
                j += 1
            out.append((live[i][key], live[j]['t'] - live[i]['t']))
            i = j + 1
        return out

    # 进度条"走一格"的间隔：旧版按 6 页一批跳，间隔能到 20~30s；新版逐页+在途外推，间隔短得多
    steps = sorted(d for v, d in runs_of('pct') if v < 100)
    step_median = round(steps[len(steps) // 2], 1) if steps else None
    step_max = round(max(steps), 1) if steps else None
    el = [d for _, d in runs_of('elapsed')]
    stale_max = round(max(el) if el else 0, 1)   # "已用"最长多久没变（旧版只在单元完成时刷新）

    etas = [(s['t'], s['eta'], wall - s['t']) for s in live if s['eta'] is not None and s['t'] > wall * 0.1]
    eta_mae = round(sum(abs(e - r) for _, e, r in etas) / len(etas), 1) if etas else None
    eta_bias = round(sum(e - r for _, e, r in etas) / len(etas), 1) if etas else None
    rel = {}
    for frac in (0.5, 0.8):
        if not live:
            continue
        s = min(live, key=lambda x: abs(x['t'] - wall * frac))
        if s['eta'] is not None:
            rem = max(0.1, wall - s['t'])
            rel['rel%d' % int(frac * 100)] = round(abs(s['eta'] - rem) / rem, 2)
    out = {'tag': tag, 'wall': wall, 'rows': rows,
           'final_pct': live[-1]['pct'] if live else None, 'samples': len(samples),
           'mono_violations': mono, 'bar_sync_max': sync,
           'step_median_s': step_median, 'step_max_s': step_max, 'status_stale_max_s': stale_max,
           'eta_samples': len(etas), 'eta_mae_s': eta_mae, 'eta_bias_s': eta_bias, 'eta_rel': rel,
           'errors': errs, 'raw': samples}
    with open(os.path.join(BASE, '.tools', 'ui_progcheck_%s.json' % tag), 'w', encoding='utf-8') as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
    print('wall=%.1fs rows=%d final=%s%% mono_bad=%d sync=%.1f step_median=%ss step_max=%ss '
          'status_stale_max=%.1fs eta_mae=%ss eta_bias=%ss eta_rel=%s errors=%d'
          % (wall, rows, out['final_pct'], mono, sync, step_median, step_max, stale_max,
             eta_mae, eta_bias, rel, len(errs)), flush=True)
    print('轨迹（每 5s 取一条）：', flush=True)
    for s in samples[::10]:
        print('  %6.1fs pct=%-4s bar=%-6s eta=%-6s %s'
              % (s['t'], s['pct'], s['bar'], s['eta'], s['status'][:70]), flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
