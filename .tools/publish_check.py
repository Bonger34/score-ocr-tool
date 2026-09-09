# -*- coding: utf-8 -*-
"""发布前隐私门禁：确认"将要提交到 GitHub 的文件"里没有真实姓名 / 学号 / 本机路径。

用法:
  python .tools/publish_check.py                  # 扫 git 索引里的文件（= 真正会发布的集合，最权威）
  python .tools/publish_check.py --walk           # 未初始化 git 时按目录遍历（跳过数据目录）
  python .tools/publish_check.py --corpus X.txt   # 指定真值语料（默认 .tools/corpus_text_all.txt）

真值从本机真实语料里抽，语料本身不入库。因此公开仓库里这个脚本只能做"格式类"检查
（本机路径 / 邮箱 / 手机号 / 身份证 / 用户名）；姓名与学号检查需要本地保留语料才生效。
命中即失败（退出码 1）。
"""
import os, re, subprocess, sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_CORPUS = os.path.join(BASE, '.tools', 'corpus_text_all.txt')

# 不参与扫描的目录（真实数据 / 第三方产物 / 版本控制）
SKIP_DIRS = {'.git', 'node_modules', 'target', '.samples', '.screenshots',
             '.archive', '.trae-html-share-packages', 'prof_ui_regress', 'prof_ui_zip'}
SKIP_EXT = {'.pdf', '.jpg', '.jpeg', '.png', '.gif', '.webp', '.ico', '.onnx', '.ort',
            '.zip', '.xlsx', '.xls', '.docx', '.woff', '.woff2', '.ttf', '.exe', '.dll'}
MAX_BYTES = 3 * 1024 * 1024          # 单个文件扫描上限，超出的只登记不扫
# 白名单：GitHub 的 noreply 地址本身就是给公开提交用的，不算隐私
EMAIL_ALLOW = ('@users.noreply.github.com',)
SURNAMES = ('王李张刘陈杨黄赵吴周徐孙马朱胡郭何高林罗郑梁谢宋唐许韩冯邓曹彭曾肖田董袁潘于蒋蔡余杜叶'
            '程苏魏吕丁任沈姚卢姜崔钟谭陆汪范金石廖贾夏韦付方白邹孟熊秦邱江尹薛闫段雷侯龙史陶黎贺顾毛'
            '郝龚邵万钱严覃武戴莫孔向汤')

PATTERNS = [
    ('本机路径/用户名', re.compile(r'[A-Za-z]:[\\/]+Users[\\/]+[A-Za-z0-9_.\-]+')),
    ('本机绝对路径', re.compile(r'[A-Za-z]:\\[^\s"\']{3,}')),
    ('邮箱', re.compile(r'[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,6}')),
    ('18位身份证', re.compile(r'(?<!\d)[1-9]\d{5}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx](?![\dXx])')),
    ('11位手机号', re.compile(r'(?<!\d)1[3-9]\d{9}(?!\d)')),
]


def read_text(path):
    """按 UTF-8 读文本；二进制文件返回 None（用 utf-8 严格解码当二进制判据）"""
    try:
        with open(path, 'rb') as f:
            raw = f.read()
    except OSError:
        return None
    if b'\x00' in raw[:8192]:
        return None
    try:
        return raw.decode('utf-8')
    except UnicodeDecodeError:
        return None


def target_files(use_walk):
    """待检查文件：优先用 git 索引（就是会被提交的集合），否则按目录遍历"""
    if not use_walk:
        try:
            out = subprocess.run(['git', 'ls-files', '-z'], cwd=BASE,
                                 capture_output=True, check=True).stdout
            names = [n for n in out.decode('utf-8').split('\0') if n]
            if names:
                return [os.path.join(BASE, n.replace('/', os.sep)) for n in names], 'git 索引'
        except (OSError, subprocess.CalledProcessError):
            pass
    files = []
    for root, dirs, names in os.walk(BASE):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for n in names:
            files.append(os.path.join(root, n))
    return files, '目录遍历'


def build_truth(corpus):
    """抽真值：学号全量 + 姓名。

    姓名判据 = "紧贴学号出现" 且 "贴学号比例≥0.6"。
    比例用单遍有界计数算：只统计候选串本身（不逐候选扫全文），
    否则在 52MB 语料上跑几十万次 str.count 会慢到不可用。
    """
    text = read_text(corpus) or ''
    serials = set(re.findall(r'(?<!\d)\d{9,13}(?!\d)', text))
    print('  真值: 学号 %d 个' % len(serials))
    adj = {}
    for pat in (r'(?<!\d)\d{9,13}(?!\d)[\s|｜]*([\u4e00-\u9fff]{2,3})',
                r'([\u4e00-\u9fff]{2,3})[\s|｜]*(?<!\d)\d{9,13}(?!\d)'):
        for m in re.finditer(pat, text):
            w = m.group(1)
            adj[w] = adj.get(w, 0) + 1
    cand = {w for w in adj if w[0] in SURNAMES}          # 只留姓氏开头的候选
    print('  真值: 贴学号候选 %d 个（姓氏开头 %d 个）' % (len(adj), len(cand)))
    total = {}
    for run in re.finditer(r'[\u4e00-\u9fff]{2,}', text):  # 单遍滑窗，只数候选串
        s = run.group(0)
        for size in (2, 3):
            for i in range(len(s) - size + 1):
                w = s[i:i + size]
                if w in cand:
                    total[w] = total.get(w, 0) + 1
    names = [w for w in cand if total.get(w) and adj[w] / total[w] >= 0.6]
    print('  真值: 姓名 %d 个' % len(names))
    return sorted(names), sorted(serials)


def load_truth(corpus):
    """真值优先读缓存 .tools/pii_truth.json（含真实姓名，已被 .gitignore 排除）"""
    cache = os.path.join(BASE, '.tools', 'pii_truth.json')
    if os.path.isfile(cache) and (not os.path.isfile(corpus)
                                  or os.path.getmtime(cache) >= os.path.getmtime(corpus)):
        try:
            import json
            with open(cache, encoding='utf-8') as f:
                d = json.load(f)
            return set(d['names']), set(d['serials']), cache
        except (OSError, ValueError, KeyError):
            pass
    if not os.path.isfile(corpus):
        return set(), set(), None
    names, serials = build_truth(corpus)
    try:
        import json
        with open(cache, 'w', encoding='utf-8') as f:
            json.dump({'names': names, 'serials': serials, 'source': os.path.basename(corpus)},
                      f, ensure_ascii=False)
    except OSError:
        pass
    return set(names), set(serials), corpus


def hit_names(text, names):
    """姓名命中：连续汉字窗口（2~4 字）+ 分隔符拆开后的合并窗口（防"姓 名 字"式规避）"""
    found = set()
    for run in re.findall(r'[\u4e00-\u9fff]+', text):
        for size in (2, 3, 4):
            for i in range(len(run) - size + 1):
                w = run[i:i + size]
                if w in names:
                    found.add(w)
    for line in text.splitlines():
        merged = re.sub(r'[^\u4e00-\u9fff]', '', line)
        if merged and merged != line:
            for size in (2, 3, 4):
                for i in range(len(merged) - size + 1):
                    w = merged[i:i + size]
                    if w in names:
                        found.add(w + '（分隔符拆分）')
    return found


def main():
    use_walk = '--walk' in sys.argv
    corpus = DEFAULT_CORPUS
    if '--corpus' in sys.argv:
        corpus = sys.argv[sys.argv.index('--corpus') + 1]
    names, serials, corpus_used = load_truth(corpus)
    files, how = target_files(use_walk)
    print('扫描集合: %s（%d 个文件）' % (how, len(files)))
    print('真值语料: %s' % (('已载入 %s（姓名 %d 个 / 学号 %d 个）' % (corpus_used, len(names), len(serials)))
                          if corpus_used else '缺失——只做格式类检查'))

    problems, skipped, scanned = [], [], 0
    for path in sorted(files):
        rel = os.path.relpath(path, BASE)
        ext = os.path.splitext(path)[1].lower()
        if ext in SKIP_EXT:
            skipped.append(rel)
            continue
        size = os.path.getsize(path) if os.path.exists(path) else 0
        if size > MAX_BYTES:
            skipped.append('%s（%.1f MB 超扫描上限）' % (rel, size / 1048576))
            continue
        text = read_text(path)
        if text is None:
            skipped.append(rel)
            continue
        scanned += 1
        for label, pat in PATTERNS:
            for m in pat.finditer(text):
                val = m.group(0)
                if label == '邮箱' and val.lower().endswith(EMAIL_ALLOW):
                    continue
                problems.append((rel, label, val[:60]))
        if serials:
            for m in re.finditer(r'(?<!\d)\d{9,13}(?!\d)', text):
                if m.group(0) in serials:
                    problems.append((rel, '真实学号', m.group(0)))
        if names:
            for w in sorted(hit_names(text, names)):
                problems.append((rel, '真实姓名', w))

    print('已扫描: %d 个文本文件；跳过: %d 个（二进制/超限）' % (scanned, len(skipped)))
    if problems:
        # 按文件聚合：每行给"命中数 + 类型 + 样例"，避免几百条学号刷屏
        grouped = {}
        for rel, label, val in problems:
            g = grouped.setdefault(rel, {})
            g.setdefault(label, []).append(val)
        print('\n命中 %d 处，涉及 %d 个文件：' % (len(problems), len(grouped)))
        for rel in sorted(grouped):
            parts = []
            for label in sorted(grouped[rel]):
                vals = grouped[rel][label]
                sample = '、'.join(sorted(set(vals))[:4])
                parts.append('%s×%d（%s）' % (label, len(vals), sample))
            print('  %-44s %s' % (rel, '；'.join(parts)))
    print('结论:', 'FAIL' if problems else 'PASS')
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
