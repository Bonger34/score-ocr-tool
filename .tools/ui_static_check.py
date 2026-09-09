# -*- coding: utf-8 -*-
"""最终交付物静态自检：关键改动是否都在（不需要浏览器）。"""
import hashlib, os, re, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = os.path.join(BASE, '搜分名单查询工具.html')
raw = open(HTML, encoding='utf-8').read()
checks = [
    ('样式：进度条无宽度过渡', '.job-fill{height:100%;width:0;border-radius:3px;background:var(--brand);}' in raw),
    ('样式：状态行禁止孤字/孤符', 'text-wrap:pretty' in raw and 'overflow-wrap:anywhere' in raw),
    ('样式：紧凑拖放区', '.drop.compact{' in raw),
    ('样式：reduced-motion', 'prefers-reduced-motion' in raw),
    ('样式：纸/墨/松绿/印泥 token', all(k in raw for k in ('--paper:#EAEDE7', '--ink:#17231F', '--brand:#1E4D3F', '--seal:#9C2B23'))),
    ('标记：拖放区是 label', '<label class="drop" id="drop" for="file">' in raw),
    ('标记：文件输入 sr-only 可聚焦', 'id="file" class="sr-only"' in raw),
    ('标记：进度条语义', 'role="progressbar"' in raw),
    ('标记：播报区', 'id="announce" role="status"' in raw),
    ('标记：导出是 button 且默认隐藏', 'id="dlxlsx"' in raw and '#dlxlsx,#dlzip{display:none;' in raw),
    ('标记：材料包按钮', 'id="dlzip"' in raw and 'exportMaterialZip()' in raw),
    ('JS：材料包目录格式', "'德育':'德育测评'" in raw and "'劳育':'劳育测评'" in raw),
    ('JS：材料包体积上限', 'ZIP_CAP=300*1024*1024' in raw),
    ('JS：来源引用只挂引用不挂字节', 'src:{file:file, path:item.name}' in raw and 'src:ent.src' in raw),
    ('JS：材料包挂到 window', 'window.exportMaterialZip=exportMaterialZip;' in raw),
    ('标记：重复副本表 caption/scope', 'class="sr-only">被判为重复副本的文件' in raw and 'scope="col"' in raw),
    ('标记：明细按人分块', 'class="mperson"' in raw and 'class="mp-item"' in raw),
    ('标记：明细按五育分段', 'class="mp-yuhead"' in raw and 'class="mp-v"' in raw),
    ('JS：五育齐全且按通知顺序', "'德育','智育','体育','美育','劳育'" in raw),
    ('JS：德育25/智育10上限', "'德育':25,'智育':10" in raw and '超出 ' in raw),
    ('标记：重复副本用 details', '<details class="dups">' in raw),
    ('标记：无残留伪 title 属性', 'title="默认开启整名匹配' not in raw),
    ('JS：状态分隔符改为不换行空格', raw.count('·' + chr(0x00A0)) + raw.count('·\\u00A0') >= 4),
    ('JS：选择/拖入改为追加', raw.count('onFiles(this.files,true)') == 1 and raw.count('onFiles(e.dataTransfer.files,true)') == 1),
    ('JS：清空入口', 'window.clearFiles=clearFiles;' in raw),
    ('JS：统计复用', 'var lastStats=null;' in raw),
    ('JS：导出复用清单', 'var people=st.people||[]' in raw and 'kw=st.kw||' in raw),
    ('JS：导出表名同步', '加分证明清单' in raw and '五育汇总' in raw),
    ('JS：引擎状态 data-kind', "setAttribute('data-kind'" in raw),
    ('JS：读屏播报节流', 'aria-valuenow' in raw and 'if(b!==bucket)' in raw),
    ('JS：进度按工作量加权', 'function makeProgress()' in raw and "ctl.add(op-(tp>0?0:1),'ocr')" in raw),
    ('JS：倒计时用实测速度', 'function meter(now)' in raw and 'Math.max(0,(totalW-done)/sp)+pw' in raw),
    ('JS：未打开文件计入分母', 'prog.pending(function(el){' in raw and 'totalW+pw*sp' in raw),
    ('JS：定时重绘', 'setInterval(paint,250)' in raw),
    ('JS：进度单调不回退', 'if(pct<shown) pct=shown;' in raw),
    ('JS：进度定时器一定停', 'prog.stop();' in raw and 'finally { if(prog) prog.stop(); }' in raw),
    ('JS：空结果给出下一步', '没有文件包含「' in raw),
    ('页签图标', 'rel="icon" href="data:image/svg+xml' in raw),
]
bad = 0
for name, ok in checks:
    bad += 0 if ok else 1
    print('  %-32s %s' % (name, 'OK' if ok else 'MISSING  <<<'))
print('失败项:', bad)
print('size=%d sha256=%s' % (len(raw.encode('utf-8')), hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]))
# 资源块未被触碰的旁证
print('gpuassets 长度:', len(re.search(r'id="gpuassets">(.*?)</script>', raw, re.S).group(1)))
sys.exit(1 if bad else 0)
