# -*- coding: utf-8 -*-
"""把 ui_progcheck_*.json 的原始采样重新算成统一指标表（早期几轮用的指标口径不同，重算才可比）。

用法: python prog_report.py [tag ...]   不给 tag 就取所有 ui_progcheck_*.json
"""
import glob, json, os, re, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(BASE, '.tools')


def clock(text, label):
    m = re.search(label + r'\s+(\d+):(\d+)(?::(\d+))?', text or '')
    if not m:
        return None
    if m.group(3) is not None:
        return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
    return int(m.group(1)) * 60 + int(m.group(2))


def analyse(path):
    d = json.load(open(path, encoding='utf-8'))
    wall = d['wall']
    live = []
    for s in d['raw']:
        pct = s.get('pct')
        if pct is None:
            continue
        live.append({'t': s['t'], 'pct': pct, 'bar': s.get('bar'),
                     'eta': clock(s['status'], '预计剩余'),
                     'el': clock(s['status'], '已用')})
    if not live:
        return None
    mono = sum(1 for a, b in zip(live, live[1:]) if b['pct'] < a['pct'])
    sync = max([abs(s['bar'] - s['pct']) for s in live if s['bar'] is not None] or [0])

    def runs(key):
        out, i = [], 0
        while i < len(live):
            j = i
            while j + 1 < len(live) and live[j + 1][key] == live[i][key]:
                j += 1
            out.append((live[i][key], live[j]['t'] - live[i]['t']))
            i = j + 1
        return out

    steps = sorted(x for v, x in runs('pct') if v is not None and v < 100)
    stale = max([x for _, x in runs('el')] or [0])
    etas = [(s['t'], s['eta'], wall - s['t']) for s in live
            if s['eta'] is not None and s['t'] > wall * 0.1]
    mae = sum(abs(e - r) for _, e, r in etas) / len(etas) if etas else None
    bias = sum(e - r for _, e, r in etas) / len(etas) if etas else None
    rel = {}
    for frac in (0.5, 0.8):
        s = min(live, key=lambda x: abs(x['t'] - wall * frac))
        if s['eta'] is not None:
            rem = max(0.1, wall - s['t'])
            rel[int(frac * 100)] = round(abs(s['eta'] - rem) / rem, 2)
    return {'tag': d['tag'], 'wall': wall, 'final': live[-1]['pct'], 'mono': mono, 'sync': sync,
            'step_median': steps[len(steps) // 2] if steps else None,
            'step_max': steps[-1] if steps else None, 'stale': stale,
            'eta_mae': None if mae is None else round(mae, 1),
            'eta_bias': None if bias is None else round(bias, 1), 'rel': rel,
            'eta_shown_from': round(etas[0][0], 1) if etas else None}


tags = sys.argv[1:]
paths = [os.path.join(TOOLS, 'ui_progcheck_%s.json' % t) for t in tags] if tags \
    else sorted(glob.glob(os.path.join(TOOLS, 'ui_progcheck_*.json')))
rows = [analyse(p) for p in paths if os.path.exists(p)]
rows = [r for r in rows if r]
cols = ['tag', 'wall', 'final', 'step_median', 'step_max', 'stale', 'eta_mae', 'eta_bias', 'rel50', 'rel80', 'eta_shown_from']
hdr = ['tag', '时长s', '结束%', '走一格中位s', '走一格最长s', '已用冻住s', '倒计时MAEs', '偏差s', '50%误差', '80%误差', '首现倒计时s']
def f1(v):
    return '—' if v is None else (round(v, 1) if isinstance(v, float) else v)


print(''.join(h.ljust(13) for h in hdr))
for r in rows:
    vals = [r['tag'], f1(r['wall']), r['final'], f1(r['step_median']), f1(r['step_max']),
            f1(r['stale']), f1(r['eta_mae']), f1(r['eta_bias']), r['rel'].get(50),
            r['rel'].get(80), f1(r['eta_shown_from'])]
    print(''.join(str(v).ljust(13) for v in vals))
