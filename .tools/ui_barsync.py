# -*- coding: utf-8 -*-
"""验证：进度条宽度与百分比数字逐帧一致（过渡已移除），并检查状态行不把分隔符留在行尾。"""
import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from playwright.sync_api import sync_playwright
URL='http://127.0.0.1:18010/%E6%90%9C%E5%88%86%E5%90%8D%E5%8D%95%E6%9F%A5%E8%AF%A2%E5%B7%A5%E5%85%B7.html'
with sync_playwright() as p:
    b=p.chromium.launch(channel='chrome', headless=True)
    pg=b.new_context(viewport={'width':1280,'height':900}).new_page()
    pg.goto(URL, wait_until='load', timeout=300000); pg.wait_for_timeout(2000)
    out=pg.evaluate("""() => {
      const bar=document.getElementById('bar'), fill=document.getElementById('barfill');
      bar.style.display='block';
      const res={};
      [12,37,63,85,100].forEach(w=>{
        fill.style.width=w+'%';
        res[w]=Math.round(fill.getBoundingClientRect().width / bar.getBoundingClientRect().width * 1000)/10;
      });
      const cs=getComputedStyle(fill);
      // 状态行：塞一个超长中文文件名，检查换行后有没有行以分隔符结尾
      const st=document.getElementById('status');
      st.textContent='正在解析 386/519 ·\u00A03月16日-4月17日福建农林大学金山学院（安溪）2026年度团学活动之构图青春打卡活动加分文件(3) (1).pdf ·\u00A0已用 0:00 ·\u00A0预计剩余 0:00';
      const r=st.getBoundingClientRect();
      return {ratio:res, transition:cs.transitionProperty+' '+cs.transitionDuration,
              lines:Math.round(r.height/ (parseFloat(getComputedStyle(st).lineHeight)||18)),
              textWrap:cs.textWrap||cs.textWrapStyle, overflowWrap:cs.overflowWrap};
    }""")
    print(out)
    b.close()
