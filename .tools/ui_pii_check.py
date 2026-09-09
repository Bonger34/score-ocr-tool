# -*- coding: utf-8 -*-
"""交付物隐私自检：HTML 里不得出现真实姓名 / 学号。

用法: python ui_pii_check.py [--html 路径] [--corpus 路径]

姓名来源：语料纯文本（默认 .tools/pick_text.txt；可用 dump_cache_text.py 导出全量语料）。
抽取两条启发式：
  1) 紧跟在 9~12 位学号后面的 2~3 个汉字（名单表格的固定版式，精度最高）；
  2) 「百家姓首字 + 1~2 汉字」的短串。
判定：把 HTML 里所有连续汉字串切成 2~4 字窗口，与上面的姓名集合求交（避免逐条
在 44MB 文本里做子串搜索，几十万候选也只需毫秒级）。
命中即失败（退出码 1）。
"""
import os, re, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = os.path.join(BASE, '搜分名单查询工具.html')
CORPUS = os.path.join(BASE, '.tools', 'pick_text.txt')

SURNAMES = ('王李张刘陈杨黄赵吴周徐孙马朱胡郭何高林罗郑梁谢宋唐许韩冯邓曹彭曾肖田董袁潘于蒋蔡余杜叶'
            '程苏魏吕丁任沈姚卢姜崔钟谭陆汪范金石廖贾夏韦付方白邹孟熊秦邱江尹薛闫段雷侯龙史陶黎贺顾毛'
            '郝龚邵万钱严覃武戴莫孔向汤')

# 常见占位人名：即使是"编的"也不该出现在交付物里
PLACEHOLDERS = ['张三', '李四', '王五', '赵六', '小明', '小张', '小王']


def candidates(text):
    """从语料里抽姓名候选 + 学号候选（只做一遍正则扫描，避免几十万次子串搜索）

    返回 (strong, weak, serials)：
      strong —— 紧贴学号的 2~3 字串，名单版式决定它几乎一定是姓名（判定依据）
      weak   —— 姓氏开头的短串，会把"德育/体育/自动化"这类词也捞进来（只提示，不判失败）
    """
    strong = set()
    for m in re.finditer(r'(?<!\d)\d{9,12}(?!\d)[\s|｜]*([\u4e00-\u9fff]{2,3})', text):  # 学号后紧跟姓名
        strong.add(m.group(1))
    for m in re.finditer(r'([\u4e00-\u9fff]{2,3})[\s|｜]*(?<!\d)\d{9,12}(?!\d)', text):  # 姓名在学号前
        strong.add(m.group(1))
    weak = set()
    for m in re.finditer(r'[\u4e00-\u9fff]{2,3}', text):
        t = m.group(0)
        if t[0] in SURNAMES:
            weak.add(t)
    serials = set(re.findall(r'(?<!\d)\d{9,12}(?!\d)', text))
    return strong, weak, serials


def is_name(text, w):
    """判别一个短串是不是"人名"：人名几乎只出现在学号旁边，词（自动化/德育）则满篇都是。

    判据 = 紧贴学号出现的次数 / 总出现次数 ≥ 0.6。实测：真实姓名 0.67~0.92，
    而"自动化"0.52、"德育"0.008、"金山"0.000，分得开。
    """
    tot = text.count(w)
    if tot <= 0:
        return False
    adj = (len(re.findall(r'(?<!\d)\d{9,12}(?!\d)[\s|｜]*' + re.escape(w), text)) +
           len(re.findall(re.escape(w) + r'[\s|｜]*(?<!\d)\d{9,12}(?!\d)', text)))
    return adj / float(tot) >= 0.6


def main():
    html_path, corpus_paths = HTML, []
    for i, a in enumerate(sys.argv):
        if a == '--html':
            html_path = sys.argv[i + 1]
        if a == '--corpus':
            corpus_paths.append(sys.argv[i + 1])
    if not corpus_paths:
        corpus_paths = [CORPUS]

    html = open(html_path, encoding='utf-8').read()
    text = '\n'.join(open(p, encoding='utf-8', errors='replace').read() for p in corpus_paths)
    strong, weak, serials = candidates(text)
    print('语料候选：强姓名 %d 个，弱候选 %d 个，学号 %d 个（%d 个语料文件，%.1f MB）'
          % (len(strong), len(weak), len(serials), len(corpus_paths), len(text) / 1048576.0), flush=True)

    # 反向求交：先把 HTML 里"像学号"的数字串一次性捞出来，再和语料学号求交集，
    # 避免上万个学号逐个在 44MB 文本里做子串搜索
    html_serials = set(re.findall(r'(?<!\d)\d{9,12}(?!\d)', html))
    hits, weak_hits = [], []
    want = strong | set(PLACEHOLDERS)
    for run in re.findall(r'[\u4e00-\u9fff]{2,}', html):
        for L in (2, 3, 4):
            for i in range(len(run) - L + 1):
                w = run[i:i + L]
                if w in want:
                    hits.append(('姓名', w))
                elif w in weak:
                    weak_hits.append(('弱候选', w))
    for s in (serials & html_serials):
        hits.append(('学号', s))

    # 被空格/竖线拆开的姓名（如"姓 名 字"）：连续汉字窗口抓不到，单独再扫一遍。
    # 只拼接"单字+分隔符+单字"的形态，命中仅提示不判失败——正常词句也可能凑出短姓名。
    hit_names = {h[1] for h in hits}
    split_hits = set()
    for m in re.finditer(r'[\u4e00-\u9fff](?:[\s|｜·、/]{1,2}[\u4e00-\u9fff]){1,3}', html):
        w = re.sub(r'[\s|｜·、/]+', '', m.group(0))
        if w in want and w not in hit_names:
            split_hits.add((w, m.group(0)))
    if split_hits:
        print('分隔符拆分候选 %d 条（逐字窗口抓不到，需人工确认）：' % len(split_hits))
        for w, raw in sorted(split_hits)[:20]:
            idx = html.index(raw)
            ctx = html[max(0, idx - 40):idx + 40].replace('\n', ' ')
            print('  %s  ← "%s"  …%s…' % (w, raw, ctx))
    else:
        print('分隔符拆分候选：无')

    fails, warns = [], []
    for kind, v in sorted(set(hits)):
        (fails if (kind == '学号' or v in PLACEHOLDERS or is_name(text, v)) else warns).append((kind, v))
    weak_hits = sorted(set(weak_hits) - {h[1] for h in fails + warns})
    print('弱候选提示 %d 条（词表噪声，多为"德育/自动化"这类词，仅供人工确认）：%s'
          % (len(weak_hits), '、'.join(w for _, w in weak_hits[:20]) or '无'))
    for tag, items in (('WARN 命中但更像词而非人名', warns), ('FAIL 命中', fails)):
        print('%s %d 条：' % (tag, len(items)))
        for kind, v in items:
            idx = html.index(v)
            ctx = html[max(0, idx - 40):idx + 40].replace('\n', ' ')
            print('  [%s] %s  …%s…' % (kind, v, ctx))

    if fails:
        print('FAIL：HTML 中存在疑似个人隐私')
        return 1
    print('PASS：HTML 中未发现语料里的姓名/学号，也未发现占位人名')
    return 0


if __name__ == '__main__':
    sys.exit(main())
