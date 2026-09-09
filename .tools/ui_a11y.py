# -*- coding: utf-8 -*-
"""无障碍专项验证：键盘可达性、焦点可见、文件选择器、reduced-motion、语义角色。

用法: python ui_a11y.py
输出: .tools/ui_a11y.json（同时打印结论）
"""
import json, os, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from playwright.sync_api import sync_playwright

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
URL = 'http://127.0.0.1:18010/%E6%90%9C%E5%88%86%E5%90%8D%E5%8D%95%E6%9F%A5%E8%AF%A2%E5%B7%A5%E5%85%B7.html'
out = {}

with sync_playwright() as p:
    b = p.chromium.launch(channel='chrome', headless=True)
    ctx = b.new_context(viewport={'width': 1280, 'height': 900})
    page = ctx.new_page()
    page.goto(URL, wait_until='load', timeout=300000)
    page.wait_for_timeout(2500)

    # 1) 键盘 Tab 顺序：第一个可聚焦元素应是文件输入（拖放区）
    #    注意必须先做这一步——后面的点击测试会触发文件选择器，干扰焦点起点
    page.evaluate("() => document.body.focus()")
    order = []
    for _ in range(8):
        page.keyboard.press('Tab')
        order.append(page.evaluate("() => { const a=document.activeElement; return a ? (a.id || a.tagName) : null; }"))
    out['tab_order'] = order
    out['first_focusable_is_file'] = order[0] == 'file'

    # 2) 聚焦隐藏的 file 输入时，拖放区要出现可见焦点环
    page.focus('#file')
    out['drop_focus_ring'] = page.evaluate(
        "() => getComputedStyle(document.getElementById('drop')).boxShadow")

    # 3) 主按钮键盘焦点环：按钮初始是 disabled（不可聚焦，符合预期），先选文件再测
    page.set_input_files('#file', [os.path.join(BASE, 'target', '晚归打卡公示汇总.pdf')])
    page.wait_for_timeout(600)
    page.evaluate("() => document.body.focus()")
    for _ in range(14):
        if page.evaluate("() => document.activeElement && document.activeElement.id === 'runBtn'"):
            break
        page.keyboard.press('Tab')
    out['runbtn_focused_by_keyboard'] = page.evaluate(
        "() => document.activeElement && document.activeElement.id === 'runBtn'")
    out['runbtn_focus_ring'] = page.evaluate(
        "() => getComputedStyle(document.getElementById('runBtn')).boxShadow")

    # 4) 点击拖放区应弹出文件选择器（label 关联的隐藏 input）
    page.goto(URL, wait_until='load', timeout=300000)
    page.wait_for_timeout(2000)
    try:
        with page.expect_file_chooser(timeout=8000) as fc:
            page.click('#drop')
        out['click_opens_picker'] = True
    except Exception as e:
        out['click_opens_picker'] = 'FAIL: ' + str(e)[:120]

    # 5) 语义角色 / 属性
    out['semantics'] = page.evaluate("""() => ({
        dropRole: document.getElementById('drop').tagName,
        fileInputLabelled: !!document.querySelector('label[for=file]'),
        fileInputHiddenButFocusable: (() => { const f=document.getElementById('file');
            return f && !f.disabled && getComputedStyle(f).display !== 'none'; })(),
        progress: (() => { const b=document.getElementById('bar');
            return b ? {role:b.getAttribute('role'), min:b.getAttribute('aria-valuemin'),
                        max:b.getAttribute('aria-valuemax'), now:b.getAttribute('aria-valuenow'),
                        label:b.getAttribute('aria-label')} : null; })(),
        live: !!document.querySelector('#announce[role=status]'),
        matchHintLinked: document.getElementById('fuzzy').getAttribute('aria-describedby'),
        matchHintExists: !!document.getElementById('matchHint'),
        dlIsButton: document.getElementById('dlxlsx').tagName,
        dlHiddenAtStart: getComputedStyle(document.getElementById('dlxlsx')).display === 'none',
        engStatusKind: document.getElementById('engStatus').getAttribute('data-kind'),
        dotIsDecorative: document.getElementById('engDot').getAttribute('aria-hidden'),
        thScopes: Array.from(document.querySelectorAll('thead th')).map(t => t.getAttribute('scope')),
        captions: document.querySelectorAll('caption').length,
        headings: Array.from(document.querySelectorAll('h1,h2,h3')).map(h => h.tagName + ':' + h.textContent.trim().slice(0, 14)),
    })""")

    # 6) 减少动效：系统偏好 reduce 时动画/过渡应被关掉
    ctx2 = b.new_context(viewport={'width': 1280, 'height': 900}, reduced_motion='reduce')
    pg2 = ctx2.new_page()
    pg2.goto(URL, wait_until='load', timeout=300000)
    pg2.wait_for_timeout(2000)
    out['reduced_motion'] = pg2.evaluate("""() => {
        const j = document.getElementById('jobStrip');
        j.classList.add('running');
        const fill = document.getElementById('barfill');
        const rc = getComputedStyle(document.getElementById('resultCard'));
        return {jobAnim: getComputedStyle(j).transitionDuration,
                fillAnim: getComputedStyle(fill).animationName,
                resultAnim: rc.animationName};
    }""")
    ctx2.close()

    # 7) 颜色不是唯一信息来源：引擎状态同时有文字
    out['engine_text_present'] = page.inner_text('#engText')[:60]

    ctx.close()
    b.close()

with open(os.path.join(BASE, '.tools', 'ui_a11y.json'), 'w', encoding='utf-8') as fh:
    json.dump(out, fh, ensure_ascii=False, indent=1)

checks = [
    ('点击拖放区弹出文件选择器', out['click_opens_picker'] is True),
    ('Tab 首个焦点是文件输入（键盘可上传）', out['first_focusable_is_file'] is True),
    ('拖放区有可见焦点环', out['drop_focus_ring'] not in (None, '', 'none')),
    ('主按钮可被键盘聚焦', out.get('runbtn_focused_by_keyboard') is True),
    ('主按钮有可见焦点环', out['runbtn_focus_ring'] not in (None, '', 'none')),
    ('进度条有 progressbar 语义', (out['semantics']['progress'] or {}).get('role') == 'progressbar'),
    ('状态有 aria-live 播报区', out['semantics']['live'] is True),
    ('匹配说明与复选框关联', bool(out['semantics']['matchHintLinked'] and out['semantics']['matchHintExists'])),
    ('导出是 button 且初始隐藏', out['semantics']['dlIsButton'] == 'BUTTON' and out['semantics']['dlHiddenAtStart'] is True),
    ('状态点仅作装饰（有文字兜底）', out['semantics']['dotIsDecorative'] == 'true'),
    ('reduced-motion 下无动画', out['reduced_motion']['fillAnim'] == 'none' and out['reduced_motion']['resultAnim'] == 'none'),
]
print('=== 无障碍自检 ===')
bad = 0
for name, ok in checks:
    bad += 0 if ok else 1
    print('  %-34s %s' % (name, 'PASS' if ok else 'FAIL  <<<'))
print('Tab 顺序:', out['tab_order'])
print('标题层级:', out['semantics']['headings'])
print('失败项:', bad)
sys.exit(1 if bad else 0)
