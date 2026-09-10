# -*- coding: utf-8 -*-
"""查 .job-status 规则是否真的生效（computed overflow-wrap/text-wrap 与 CSSOM 对照）。"""
import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from playwright.sync_api import sync_playwright
URL='http://127.0.0.1:18010/%E6%90%9C%E5%88%86%E5%90%8D%E5%8D%95%E6%9F%A5%E8%AF%A2%E5%B7%A5%E5%85%B7.html'
with sync_playwright() as p:
    b=p.chromium.launch(channel='chrome', headless=True)
    pg=b.new_context(viewport={'width':1280,'height':900}).new_page()
    pg.goto(URL, wait_until='load', timeout=300000); pg.wait_for_timeout(2000)
    print('chrome:', pg.evaluate("() => navigator.userAgent.match(/Chrome\/([0-9.]+)/)[1]"))
    print(pg.evaluate("""() => {
      const rules=[];
      for(const sh of document.styleSheets){
        let rs; try{ rs=sh.cssRules; }catch(e){ continue; }
        for(const r of rs){ if(r.selectorText && /job-status|job-fill/.test(r.selectorText)) rules.push(r.cssText); }
      }
      const st=document.getElementById('status'), cs=getComputedStyle(st);
      return {rules, cls: st.className, ow: cs.overflowWrap, tw: cs.textWrap, wb: cs.wordBreak,
              lineHeight: cs.lineHeight, font: cs.fontSize+' '+cs.fontFamily.slice(0,30)};
    }"""))
    b.close()
