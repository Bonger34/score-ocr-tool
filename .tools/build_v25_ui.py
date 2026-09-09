# -*- coding: utf-8 -*-
"""构建交付物：前端 UI 重构（样式 + 标记 + 渲染层补丁 + v2.6 进度引擎）。

源文件（可单独审阅/迭代）：
  .tools/ui/style.css   —— 新样式（整块替换 <style>）
  .tools/ui/body.html   —— 新页面标记（整块替换 <body> 到首个 <script> 之间）

改动清单（每处锚点必须恰好命中 1 次）：
  1. <style> 整块替换
  2. body 标记整块替换（保留全部原有 id，新增 jobStrip / announce / fileMeta）
  3. setEngStatus：状态色改由 CSS 的 data-kind 决定（原内联色把 err 画成橙色）
  4. fmt() + makeProgress()：v2.6 进度与倒计时引擎（工作量加权 + 实测速度 + 250ms 重绘）
  5. 运行开始/结束/尾部兜底：切换作业条 .running、停表、异常也停表
  6. 空结果：给出下一步，而不是只留一行提示
  7. onFiles：显示"已选 N 个文件（体积）"，新增 clearFiles()
  8. render()：台账 + 明细清单（学号·姓名 → 五育测评 → +分值（事由）），重复副本折叠（源码 .tools/ui/render.js）
  8b. setupDownload：导出改为「加分证明清单 + 五育汇总」两张表（源码 .tools/ui/export.js）
  8c. 材料包：按 学号姓名/五育测评/+分值 (事由) 打包命中的名单原件（源码 .tools/ui/zip.js）
  9. 导出按钮：生成完成后再显示（inline-flex）
 10. readPdfText / extractEntries：按页类型（OCR 页/文本页/文件）分别登记进度权重

用法: python build_v25_ui.py [--dry]
"""
import hashlib, os, re, shutil, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(BASE, '.tools')
UI = os.path.join(TOOLS, 'ui')
HTML = os.path.join(BASE, '搜分名单查询工具.html')
BACKUP = os.path.join(TOOLS, 'v24_ui_baseline.html')
DRY = '--dry' in sys.argv

CSS = open(os.path.join(UI, 'style.css'), encoding='utf-8').read().rstrip('\n')
BODY = open(os.path.join(UI, 'body.html'), encoding='utf-8').read().rstrip('\n')

# ---------------------------------------------------------------- JS 补丁
SET_ENG_OLD = """  function setEngStatus(kind,text){
    var dot=document.getElementById('engDot'), tx=document.getElementById('engText');
    if(!dot||!tx) return;
    var C={gpu:'#22c55e',cpu:'#f59e0b',check:'#3b82f6'};
    var k=(kind in C)?kind:'cpu';
    dot.style.background=C[k];
    tx.textContent=text;
  }"""
SET_ENG_NEW = """  function setEngStatus(kind,text){
    var wrap=document.getElementById('engStatus'), tx=document.getElementById('engText');
    if(!tx) return;
    // v2.5：颜色交给 CSS 按 data-kind 决定。原来内联色表没有 err，GPU 异常会被画成橙色，
    // 和"CPU 模式"看起来一模一样——状态区分不能只靠颜色，更不能靠错的颜色。
    if(wrap) wrap.setAttribute('data-kind',(kind==='gpu'||kind==='cpu'||kind==='check'||kind==='err')?kind:'cpu');
    tx.textContent=text;
  }"""

# v2.6：进度与倒计时引擎。旧版按"单元个数"推进，而一页 OCR 与一张 xlsx 的耗时差上千倍，
# 于是进度条在扫描件上长时间不动、倒计时忽大忽小；新版把每步折算成"预计工作量(毫秒)"，
# 进度=已完成工作量/总工作量，剩余时间=剩余工作量÷实测速度，速度按 1 秒窗口做 EMA。
FMT_OLD = """  function fmt(ms){
    ms=Math.max(0,Math.round(ms));
    var m=Math.floor(ms/60000), s=(ms%60000)/1000|0;
    return m+':'+(s<10?'0':'')+s;
  }"""
FMT_NEW = """  function fmt(ms){
    ms=Math.max(0,Math.round(ms));
    var s=Math.floor(ms/1000), m=Math.floor(s/60), h=Math.floor(m/60);
    var p=function(x){ return (x<10?'0':'')+x; };
    return (h?h+':'+p(m%60):m)+':'+p(s%60);   // v2.6：超过 1 小时显示 1:05:03，不再堆成 65:03
  }
  // ---------- v2.6 进度与倒计时引擎 ----------
  // 旧版按"单元个数"推进：一页 OCR 和一张 xlsx 都算一步，耗时却差上千倍，
  // 于是进度条在扫描件上长时间不动、倒计时也忽大忽小。
  // 新做法把每一步折算成"预计工作量（毫秒）"：进度 = 已完成工作量 / 总工作量，
  // 剩余时间 = 剩余工作量 ÷ 实测速度；速度按 1 秒窗口做 EMA，机器变慢（GPU→CPU）也能跟着收敛。
  // 分母还额外算上"还没打开的文件"按体积外推的墙钟时间（pending）：
  // 否则分母只有已打开的文件，最后一个文件一开头进度条就冲到 98% 不动、倒计时也会假性归零。
  var KMS=1.5;   // 每 KB 的工作量先验（毫秒），由实测校准；zip 内部文件按它折算权重
  function predMs(bytes){ return Math.max(150,(bytes||0)/1024*KMS); }
  function makeProgress(){
    var pri={page:25, file:150, text:12, search:4};
    pri.ocr=window.__GPU_OCR_ENABLED__?1600:8000;  // 单页 OCR 先验：实测 GPU 约 1.6s，CPU 回退约 8s
    var t0=Date.now(), off=0, span=98, totalW=0, doneW=0, totalN=0, doneN=0;
    var lastT=t0, winW=0, winT=t0, speed=1, measured=false, baseT=0, baseW=0;
    var shown=0, head='', timer=null, bucket=-1, pendFn=null;
    function w(kind){ return pri[kind]||pri.file; }
    // 速度以"全程平均"为主、"1 秒窗口 EMA"为辅：页是成批完成的（一批 6 页），
    // 短窗口要么看到 0 页要么看到 6 页，单靠它会严重高估；全程平均则天然把批次抹平，
    // 只留 3 成权重给 EMA，用来跟住"GPU 掉回 CPU"这类速度突变。
    // 起点从"第一个单元完成"算起：首个页面含模型预热/着色器编译，算进去会严重低估速度。
    function effSpeed(now){
      var dT=now-baseT, dW=doneW-baseW;
      var g=(baseT>0&&dT>500)? dW/dT : 0;
      return g>0? g*0.7+speed*0.3 : speed;
    }
    function pendWall(now){ return pendFn? pendFn(now-t0) : 0; }
    function paint(){
      var now=Date.now(), sp=effSpeed(now), pw=pendWall(now);
      var T=totalW+pw*sp;                            // 分母 = 已登记工作量 + 未打开文件折成的工作量
      var done=doneW;
      // 在途工作量按实测速度外推，长页面上进度条也会缓慢前进；一个单元都没完成时不动
      // 两道上限：最多吃剩余工作量的九成（保证不会抢跑到"已完成"），最多外推一批的量
      // （6 页 OCR，防的是"一页卡很久"时外推无限增长把进度条冲到顶）
      if(baseT>0&&T>done) done=doneW+Math.min((T-doneW)*0.98,(now-lastT)*sp,6*pri.ocr);
      var pct=T>0? off+span*(done/T) : off;
      if(pct<shown) pct=shown;                      // 单调：登记新单元让分母变大时不回退
      shown=pct;
      var eta=measured? Math.max(0,(totalW-done)/sp)+pw : -1;
      $('barfill').style.width=Math.max(2,Math.round(pct))+'%';
      $('barpct').textContent=Math.round(pct)+'%';
      $('status').textContent=head+' ·\\u00A0已用 '+fmt(now-t0)+' ·\\u00A0'+(eta<0?'预计剩余 计算中…':'预计剩余 '+fmt(eta));
      // v2.5：进度条补齐无障碍语义；读屏只在每跨 10% 播报一次（逐页更新会刷屏）
      var bar=$('bar'); if(bar) bar.setAttribute('aria-valuenow',String(Math.round(pct)));
      var b=Math.floor(pct/10);
      if(b!==bucket){ bucket=b; var an=$('announce'); if(an) an.textContent='已完成 '+Math.round(pct)+'%'; }
    }
    // 1 秒窗口的实测速度（工作量/墙钟）：窗口太短会被并发批次的脉冲带偏
    function meter(now){
      if(!baseT) return;                             // 第一个单元还没完成，先不测速
      var dT=now-winT;
      if(dT<900) return;
      var dW=doneW-winW;
      if(dW>0){ speed=measured? speed*0.6+(dW/dT)*0.4 : dW/dT; measured=true; }
      winW=doneW; winT=now;
    }
    return {
      // 进入新阶段：off/span 是这一段在总进度条上占的百分比区间
      begin:function(o,s){ off=o; span=s; totalW=0; doneW=0; winW=0; measured=false; lastT=winT=Date.now(); },
      // 登记 n 个待处理单元；n 可以是小数，ms 给定时按 ms 计权（体积预测用），否则按 kind 的先验
      add:function(n,kind,ms){ if(n>0){ totalW+=(ms===undefined? w(kind)*n : ms); totalN+=n; } },
      // 完成一个单元；n 与登记时一致（按文本量分权时 step 也要传同样的 n）
      step:function(kind,n){
        n=(n===undefined||n===null)?1:n;
        if(totalN<=0) totalN=n;                     // 兜底：没登记过也按一个单元算
        doneN=Math.min(doneN+n,totalN);
        var unit=w(kind)*n;
        doneW=Math.min(doneW+unit,totalW>0?totalW:unit);
        lastT=Date.now();
        if(!baseT){                                    // 第一个单元完成：开始计速（含预热的全局平均，偏保守）
          baseT=lastT; baseW=doneW; winT=lastT; winW=doneW;
          speed=(lastT-t0)>0? doneW/(lastT-t0) : 1;
        }
        meter(lastT);
      },
      // 未打开文件的墙钟预估（毫秒），回调参数为已用时
      pending:function(fn){ pendFn=fn; },
      count:function(){ return Math.round(doneN)+'/'+Math.round(totalN); },
      // 收尾：解析可能有个别文件中途失败没走完步进，这里把本阶段直接判满，避免切换阶段时进度条跳一大截
      finish:function(){ doneW=totalW; },
      set:function(h){ head=h; paint(); },
      start:function(){ if(!timer) timer=setInterval(paint,250); }, // 250ms 重绘：长页面上"已用/剩余"也连续跳
      stop:function(){ if(timer){ clearInterval(timer); timer=null; } }
    };
  }"""

RUNSTART_OLD = "    $('runBtn').disabled=true; $('bar').style.display='block'; $('barpct').textContent='0%';"
RUNSTART_NEW = ("    $('runBtn').disabled=true; $('bar').style.display='block'; $('barpct').textContent='0%';\n"
                "    var js0=$('jobStrip'); if(js0) js0.classList.add('running');\n"
                "    try{   // v2.6：无论中途是否抛错，退出时都要停掉进度定时器")

RUNEND_OLD = "    $('bar').style.display='none';"
RUNEND_NEW = ("    $('bar').style.display='none';\n"
              "    prog.stop();   // 先停表，否则定时器会把状态行覆盖回进度文字\n"
              "    var js1=$('jobStrip'); if(js1) js1.classList.remove('running');")

RUNTAIL_OLD = "    $('resultCard').style.display='block';\n    $('runBtn').disabled=false;\n  }"
RUNTAIL_NEW = "    $('resultCard').style.display='block';\n    $('runBtn').disabled=false;\n    } finally { if(prog) prog.stop(); }\n  }"

# ---------- v2.6：解析阶段按页类型分别登记权重 ----------
PAGEADD_OLD = "      if(ctl&&n>1) ctl.add(n-1); // 一个PDF按页数折成多个解析单元，进度更平滑"
PAGEADD_NEW = "      // v2.6：页级权重等下面 ocrIdx 算出来再登记——OCR 页的耗时是文本页的数十倍，必须分开计权"

OCRIDX_OLD = "      var ocrMap={}; ocrIdx.forEach(function(p){ ocrMap[p]=true; });"
OCRIDX_NEW = ("      var ocrMap={}; ocrIdx.forEach(function(p){ ocrMap[p]=true; });\n"
              "      // v2.6：按页类型分别登记进度权重。本 PDF 已被外层预记 1 个单元，\n"
              "      // 从页数多的那组里扣掉，保证总数正好是 n（否则进度条会停在 99%）\n"
              "      if(ctl&&n>1){\n"
              "        var tp=n-ocrIdx.length, op=ocrIdx.length;\n"
              "        if(tp>0) ctl.add(tp-1,'page');\n"
              "        if(op>0) ctl.add(op-(tp>0?0:1),'ocr');\n"
              "      }")

OCRSTEP_OLD = "          done++; if(ctl) ctl.step('第'+chunk[k]+'/'+n+'页·OCR ('+done+'/'+ocrIdx.length+')');"
OCRSTEP_NEW = "          done++; if(ctl) ctl.step('第'+chunk[k]+'/'+n+'页·OCR ('+done+'/'+ocrIdx.length+')','ocr');"

PAGESTEP_OLD = "        if(ctl&&!ocrMap[pg2]) ctl.step('第'+pg2+'/'+n+'页');"
PAGESTEP_NEW = "        if(ctl&&!ocrMap[pg2]) ctl.step('第'+pg2+'/'+n+'页','page');"

ZIPADD_OLD = "      if(ctl&&inner.length>1) ctl.add(inner.length-1); // 该文件从1个单元扩展为内部文件个数"
ZIPADD_NEW = """      if(ctl&&inner.length>1){
        // v2.6：内部文件按各自体积估工作量（zip 中央目录里有 uncompressedSize）。
        // 原来一律按 150ms 记，一个 285MB 的 zip 里大小文件能差几个数量级，进度条会失真
        var innerMs=0;
        inner.forEach(function(it){ innerMs+=predMs(it.size); });
        ctl.add(inner.length-1,'file',innerMs);
      }"""
ZIPSIZE_OLD = "        inner.push({name:n, f:f, e:ext(n)});"
ZIPSIZE_NEW = "        inner.push({name:n, f:f, e:ext(n), size:(f&&f._data&&f._data.uncompressedSize)||0});"

# 解析/检索两段的主循环整段替换（用起止标记定位，避免把整段塞进锚点表）
PROG_START = "    var t0=Date.now(), total=files.length, done=0;"
PROG_END = "      var text=ent.text||'';"
PROG_NEW = """    // ---------- 解析阶段：进度条 0–98% ----------
    var prog=makeProgress();
    prog.add(files.length,'file');                  // 顶层文件先各记 1 个单元，zip/PDF 展开后再追加
    // 还没打开的文件按体积外推一份墙钟时间进分母/倒计时：文件是顺序打开的，
    // 不预留这段，进度条会在最后一个文件开头就冲到 98% 不动，倒计时也会假性归零。
    // 外推口径：已处理 X MB 用了 el 毫秒，剩下的 Y MB 就估 el*Y/X，再乘 1.6 倍的保守系数——
    // 扫描件按体积估耗时天然偏低（同一体积的扫描件和文本件能差一个数量级），宁可估多不可估少
    var opened=[], totalKB=0, pendingKB=0, curFile=-1;
    for(var fi=0;fi<files.length;fi++){ opened.push(false); totalKB+=((files[fi].size||0)/1024); }
    pendingKB=totalKB;
    prog.pending(function(el){
      if(pendingKB<=0) return 0;
      var doneKB=totalKB-pendingKB;
      return doneKB>0? 1.6*el*pendingKB/doneKB : pendingKB*1.5;
    });
    function openFile(i){                            // 文件一旦开始产出单元，就不再按体积估它
      if(i<0||opened[i]) return;
      opened[i]=true; pendingKB-=((files[i].size||0)/1024);
    }
    function line(label){ return '正在解析 '+prog.count()+' ·\\u00A0'+label; }
    prog.set(line('准备中…'));
    prog.start();
    var ctl={
      add:function(n,kind,ms){ openFile(curFile); prog.add(n,kind,ms); prog.set(line('更新任务…')); },
      step:function(label,kind,n){ openFile(curFile); prog.step(kind,n); prog.set(line(label)); }
    };
    matched=[];
    // 展平为文件条目，以便按文件夹树逐条列出
    var entries=[];
    for(var i=0;i<files.length;i++){
      curFile=i;
      var tFile=Date.now();
      try{ var es=await extractEntries(files[i], ctl); entries=entries.concat(es); }
      catch(e){ console.warn('fail',files[i].name,e); ctl.step(files[i].name+'（失败）'); }
      // 用实测校准"每 KB 耗时"，供 zip 内部文件的工作量预估使用
      var kb=((files[i].size||0)/1024), dt=Date.now()-tFile;
      if(kb>0&&dt>300) KMS=Math.max(0.3, KMS*0.5+(dt/kb)*0.5);
      openFile(i);
    }
    curFile=-1;
    // ---------- 检索阶段：进度条 98–100% ----------
    // 检索只是在内存里扫字符串，通常不到 1 秒，所以只占最后 2%：不再让进度条在 85% 处空等。
    // 权重按文本量分配——扫大文件比扫小文件慢，登记与完成都要用同一个权重。
    prog.finish();
    prog.begin(98,2);
    var totalEntries=entries.length||1, done2=0, sw=[];
    for(var q=0;q<entries.length;q++){ var wq=1+((entries[q].text||'').length/50000); sw.push(wq); prog.add(wq,'search'); }
    for(var x=0;x<entries.length;x++){
      var ent=entries[x]; done2++;
      prog.step('search',sw[x]);
      prog.set('正在检索 '+done2+'/'+totalEntries+' ·\\u00A0'+ent.name);
"""

NOMATCH_OLD = "    if(matched.length===0){ $('status').textContent='未找到含 “'+kw+'” 的文件。'; $('runBtn').disabled=false; return; }"
NOMATCH_NEW = """    if(matched.length===0){
      // v2.5：空结果也要指出下一步，而不是只留一行灰字
      $('status').textContent='解析完成：没有命中。';
      $('announce').textContent='没有找到包含该姓名的文件';
      $('resultCard').style.display='block';
      $('summary').innerHTML='<div class="empty"><p class="empty-t">没有文件包含「'+esc(kw)+'」</p>'+
        '<p class="hint">可以试试：勾选「模糊匹配」按字串查找；如果名单是扫描件，勾选「识别扫描件」后重跑。</p></div>';
      $('detail').innerHTML=''; $('dupbox').innerHTML=''; $('dupbox').style.display='none';
      $('dlxlsx').style.display='none'; lastBlob=null;
      $('runBtn').disabled=false; return;
    }"""

DONE_OLD = "    $('status').textContent='解析完成：命中 '+matched.length+' 个文件 · 文本缓存 命中 '+textCache.stats.hit+' / 新解析 '+textCache.stats.miss;"
DONE_NEW = ("    // v2.5：去掉\"文本缓存命中/新解析\"这类黑话，改成一句人话\n"
            "    $('status').textContent='解析完成：命中 '+matched.length+' 个文件'+(textCache.stats.hit?'（'+textCache.stats.hit+' 个用了上次的缓存）':'')+'。';\n"
            "    $('announce').textContent='解析完成，命中 '+matched.length+' 个文件';")

ONFILES_OLD = """  function onFiles(fs){
    uploadedFiles=fs;
    $('runBtn').disabled=false;
    $('status').textContent='已载入 '+fs.length+' 个文件，点击「开始解析」。';
  }"""
ONFILES_NEW = """  function fmtSize(b){
    if(!b) return '';
    var u=['B','KB','MB','GB'], i=0;
    while(b>=1024&&i<u.length-1){ b/=1024; i++; }
    return (i===0?b:Math.round(b*10)/10)+' '+u[i];
  }
  // v2.5：再次选择/拖入时"追加"而不是替换（文案写的是"继续添加文件"，行为必须一致）
  function onFiles(fs, append){
    var list=[];
    if(append&&uploadedFiles) list=[].slice.call(uploadedFiles);
    for(var k=0;k<fs.length;k++){
      var f=fs[k], dup=false;
      for(var j=0;j<list.length;j++){
        if(list[j].name===f.name&&list[j].size===f.size&&list[j].lastModified===f.lastModified){ dup=true; break; }
      }
      if(!dup) list.push(f);
    }
    uploadedFiles=list;
    $('runBtn').disabled=false;
    var n=list.length, bytes=0;
    for(var i=0;i<n;i++) bytes+=(list[i]&&list[i].size)||0;
    // v2.5：选完文件后给出"选了什么"的确认，并提供清空
    var meta=$('fileMeta'), wrap=$('fileMetaWrap');
    if(meta) meta.textContent='已选 '+n+' 个文件'+(bytes?'（'+fmtSize(bytes)+'）':'');
    if(wrap) wrap.style.display='flex';
    var dp=$('drop'); if(dp) dp.classList.add('compact');   // v2.5：已选文件后拖放区收成一条，把纵向空间还给结果
    $('status').textContent='点「开始解析」开始查找。';
    $('announce').textContent='已选 '+n+' 个文件';
  }
  function clearFiles(){
    uploadedFiles=null; matched=[]; lastBlob=null;
    var f=$('file'); if(f) f.value='';
    var wrap=$('fileMetaWrap'); if(wrap) wrap.style.display='none';
    var dp=$('drop'); if(dp) dp.classList.remove('compact');
    $('runBtn').disabled=true;
    $('resultCard').style.display='none';
    $('status').textContent='先放入名单文件，再点「开始解析」。';
    $('announce').textContent='已清空已选文件';
  }"""

# render() 与导出块：源码放 .tools/ui/ 下单独维护（与 style.css / body.html 同规格）
RENDER_NEW = open(os.path.join(UI, 'render.js'), encoding='utf-8').read().rstrip('\n')
EXPORT_NEW = open(os.path.join(UI, 'export.js'), encoding='utf-8').read().rstrip('\n')
ZIP_NEW = open(os.path.join(UI, 'zip.js'), encoding='utf-8').read().rstrip('\n')

# 台账与导出的统计只算一次：原来两处各算一遍，出现异常分值时表里会不一致
STATS_OLD = r"""  function setupDownload(keep,removed,doDedup){
    var sums={},cnts={};
    keep.forEach(function(m){m.records.forEach(function(r){
      if(!r.score)return; var t=parseType(r.score),v=parseFloat(/[-+]?\d+(?:\.\d+)?/.exec(r.score)[0]);
      sums[t]=(sums[t]||0)+v; cnts[t]=(cnts[t]||0)+1;
    });});
    var total=0,cntTotal=0; Object.keys(sums).forEach(function(t){total+=sums[t];cntTotal+=cnts[t];});"""
STATS_NEW = r"""  var lastStats=null;   // 由 render() 写入，导出时复用，保证清单与 Excel 完全一致
  function setupDownload(keep,removed,doDedup){
    var st=lastStats||{}, sums=st.sums||{}, cnts=st.cnts||{};
    var total=st.total||0, cntTotal=st.totalCnt||0;
    var people=st.people||[], kw=st.kw||'';"""

# 状态行分隔符：' · ' 改成 ' ·\u00A0'，让分隔符与后一个字段绑定换行，避免「·」孤零零留在行尾
# （v2.6 起这两行整段由 PROG_NEW 重写，NBSP 直接写在引擎里）

APPEND_OLD = "  $('file').addEventListener('change',function(){ if(this.files.length) onFiles(this.files); });"
APPEND_NEW = "  $('file').addEventListener('change',function(){ if(this.files.length) onFiles(this.files,true); }); // v2.5：追加而非替换"
DROP_OLD = "drop.addEventListener('drop',function(e){e.preventDefault();drop.classList.remove('hover');if(e.dataTransfer.files.length)onFiles(e.dataTransfer.files);});"
DROP_NEW = "drop.addEventListener('drop',function(e){e.preventDefault();drop.classList.remove('hover');if(e.dataTransfer.files.length)onFiles(e.dataTransfer.files,true);}); // v2.5：追加"

DLEXPORT_OLD = "      a.style.display='inline-block';"
DLEXPORT_NEW = "      a.style.display='inline-flex'; // v2.5：按钮改为 inline-flex 排版"

EXPOSE_OLD = "  window.handleRun=handleRun;"
EXPOSE_NEW = "  window.handleRun=handleRun;\n  window.clearFiles=clearFiles;"

FAVICON_OLD = '<title>搜分名单查询工具（单文件离线版）</title>'
FAVICON_NEW = ('<title>搜分名单查询工具（单文件离线版）</title>\n'
               '<!-- 内联 SVG 图标：离线单文件不能外链，顺带消掉 favicon 的 404 -->\n'
               "<link rel=\"icon\" href=\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='7' fill='%231E4D3F'/%3E%3Ctext x='16' y='23' font-family='serif' font-size='19' fill='%23F3F6F1' text-anchor='middle'%3E%E5%88%86%3C/text%3E%3C/svg%3E\">")

# ---------- 隐私：注释里的示例姓名一律匿名化（交付物不得出现任何真实姓名）----------
# 写成"正则 + 幂等替换"而不是精确串：既能在未匿名的基线上命中，也能在已匿名的基线上原样通过。
# 这样构建脚本自身与对外分发的 42MB 基线都不必携带任何示例姓名。
PII_ANCHORS = [
    ('匿名化示例1',
     r'      // 姓名\+括号备注在同一 token（如"[^"]*\(曾用名\)"）时：整名命中、括号后缀放行',
     '      // 姓名+括号备注在同一 token（如"某姓名(曾用名)"）时：整名命中、括号后缀放行'),
    ('匿名化示例2',
     r'      // 续字（如搜"[^"]*"时命中"[^"]*"(?:两块)?，块后紧跟单字"[^"]*"），即 kw 只是更长姓名的一部分',
     '      // 续字（如搜"AB"时命中"AB | C"两块，块后紧跟单字"C"），即 kw 只是更长姓名的一部分'),
    ('匿名化示例3',
     r'      // 备注后缀"（xxx）"以括号开头，也不属续字 -> 放行。兼覆单字[^\n]*。',
     '      // 备注后缀"（xxx）"以括号开头，也不属续字 -> 放行。兼覆单字与多字两种检索词。'),
    ('匿名化示例4',
     r'        // 模糊模式（沿用旧行为）：空白归一后子串包含即命中，可捞"[^"]*"',
     '        // 模糊模式（沿用旧行为）：空白归一后子串包含即命中，可捞"姓氏或名字里含该字"'),
    ('匿名化示例5',
     r'    // pdf\.js 对部分 PDF 会把姓名与分值都拆成独立 token（[^）]* / 美育 \| \+1\.5），',
     '    // pdf.js 对部分 PDF 会把姓名与分值都拆成独立 token（姓 名 字 / 美育 | +1.5），'),
]

# 导出的两个工作表改名，与新的清单口径一致
SHEET_OLD = '<sheets><sheet name="加分明细" sheetId="1" r:id="rId1"/><sheet name="加分汇总" sheetId="2" r:id="rId2"/></sheets>'
SHEET_NEW = '<sheets><sheet name="加分证明清单" sheetId="1" r:id="rId1"/><sheet name="五育汇总" sheetId="2" r:id="rId2"/></sheets>'

# ---------- v2.8：材料包导出需要"来源文件"引用 ----------
# 每条解析结果挂上 {file, zip内路径} 与体积，只记引用不复制字节：
# 若直接持有 JSZip 的 ZipObject，其压缩数据是原包的视图，285MB 的包会被长期驻留。
SRC1_OLD = '      return [{name:nm, text:t}];'
SRC1_NEW = '      return [{name:nm, text:t, src:{file:file}, size:file.size||0}];'
SRC2_OLD = '      return [{name:nm, text:t2}];'
SRC2_NEW = '      return [{name:nm, text:t2, src:{file:file}, size:file.size||0}];'
SRC3_OLD = '          return {name:itN, text:t3};'
SRC3_NEW = ('          return {name:itN, text:t3, src:{file:file, path:item.name}, '
            'size:(item.f&&item.f._data&&item.f._data.uncompressedSize)||0};')
SRC4_OLD = "    return [{name:nm, text:new TextDecoder('utf-8').decode(buf)}];"
SRC4_NEW = "    return [{name:nm, text:new TextDecoder('utf-8').decode(buf), src:{file:file}, size:file.size||0}];"
SRC5_OLD = '      matched.push({name:ent.name, act:activityKey(ent.name), records:recs});'
SRC5_NEW = '      matched.push({name:ent.name, act:activityKey(ent.name), records:recs, src:ent.src, size:ent.size||0});'
# zip.js 插在 exportNow 之前（同一个 IIFE 内，能共用 YU / itemStr / lastStats）
ZIPHOOK_OLD = '  window.exportNow=exportNow; // 供内嵌 onclick="return exportNow()" 调用'
ZIPHOOK_NEW = ZIP_NEW + '\n' + ZIPHOOK_OLD

# ---------- v2.10 / v2.11：file:// 提示里的启动器名同步 ----------
# v2.8 把「直接打开_高性能GPU.cmd」改名为「直接打开页面.cmd」，但基线里这句提示没跟着改，
# 于是直接双击 HTML 的用户会看到一个包里并不存在的文件名（v2.8 / v2.9 的真实缺陷）；
# v2.11 启动器又更名为「打开工具.cmd」，此处一并同步。
LAUNCHNAME_OLD = '想用独显请点 直接打开_高性能GPU.cmd'
LAUNCHNAME_NEW = '想用独显请双击 打开工具.cmd'

ANCHORS = [
    ('file://提示启动器名', LAUNCHNAME_OLD, LAUNCHNAME_NEW),
    ('页签图标', FAVICON_OLD, FAVICON_NEW),
    ('引擎状态色', SET_ENG_OLD, SET_ENG_NEW),
    ('时长格式与进度引擎', FMT_OLD, FMT_NEW),
    ('运行开始', RUNSTART_OLD, RUNSTART_NEW),
    ('运行结束', RUNEND_OLD, RUNEND_NEW),
    ('运行尾部兜底', RUNTAIL_OLD, RUNTAIL_NEW),
    ('空结果', NOMATCH_OLD, NOMATCH_NEW),
    ('完成播报', DONE_OLD, DONE_NEW),
    ('文件选择', ONFILES_OLD, ONFILES_NEW),
    ('PDF页权重登记', PAGEADD_OLD, PAGEADD_NEW),
    ('PDF页权重分组', OCRIDX_OLD, OCRIDX_NEW),
    ('OCR页步进', OCRSTEP_OLD, OCRSTEP_NEW),
    ('文本页步进', PAGESTEP_OLD, PAGESTEP_NEW),
    ('zip展开权重', ZIPADD_OLD, ZIPADD_NEW),
    ('zip内部体积', ZIPSIZE_OLD, ZIPSIZE_NEW),
    ('选择文件改为追加', APPEND_OLD, APPEND_NEW),
    ('拖拽文件改为追加', DROP_OLD, DROP_NEW),
    ('统计复用', STATS_OLD, STATS_NEW),
    ('导出按钮显示', DLEXPORT_OLD, DLEXPORT_NEW),
    ('工作表命名', SHEET_OLD, SHEET_NEW),
    ('来源引用·PDF', SRC1_OLD, SRC1_NEW),
    ('来源引用·xlsx', SRC2_OLD, SRC2_NEW),
    ('来源引用·zip内', SRC3_OLD, SRC3_NEW),
    ('来源引用·文本', SRC4_OLD, SRC4_NEW),
    ('来源引用·命中条目', SRC5_OLD, SRC5_NEW),
    ('材料包导出', ZIPHOOK_OLD, ZIPHOOK_NEW),
    ('清空入口', EXPOSE_OLD, EXPOSE_NEW),
]

# render() 用起止标记定位，避免把整段函数塞进锚点表
RENDER_START = "  function render(keep,removed,doDedup,kw){"
RENDER_END = "\n  function esc(s){"
# 导出块同理：从"Sheet1 明细"注释到 JSZip 打包之前
EXPORT_START = "    // Sheet1 明细"
EXPORT_END = "    var zb=new JSZip();"


def rep(raw, tag, old, new):
    n = raw.count(old)
    if n != 1:
        raise SystemExit('锚点「%s」命中 %d 次（应为 1）' % (tag, n))
    return raw.replace(old, new)


def rep_re(raw, tag, pat, new):
    """正则版锚点：替换文本按字面量写入，避免 new 里的 \\1 之类被当成反向引用"""
    n = len(re.findall(pat, raw))
    if n != 1:
        raise SystemExit('锚点「%s」命中 %d 次（应为 1）' % (tag, n))
    return re.sub(pat, lambda m: new, raw, count=1)


def main():
    # --sanitize-baseline：只把基线里的示例姓名匿名化，不生成成品。
    # 对外分发的 42MB 基线用这个模式产出，别人可以自行复算校验。
    if '--sanitize-baseline' in sys.argv:
        raw = open(BACKUP, encoding='utf-8').read()
        n = 0
        for tag, pat, new in PII_ANCHORS:
            cnt = len(re.findall(pat, raw))
            if cnt != 1:
                raise SystemExit('锚点「%s」命中 %d 次（应为 1）' % (tag, cnt))
            raw, k = re.subn(pat, lambda m: new, raw, count=1)
            n += k
            print('锚点 OK: %s' % tag)
        open(BACKUP, 'w', encoding='utf-8', newline='').write(raw)
        print('基线已匿名化：%s（%d 处）' % (BACKUP, n))
        print('sha256 %s' % hashlib.sha256(raw.encode('utf-8')).hexdigest())
        return 0

    # 始终从基线（v2.4）构建，保证可重复：反复执行不会累积改动
    if not os.path.exists(BACKUP):
        shutil.copy2(HTML, BACKUP)
        print('已备份基线 -> %s' % BACKUP)
    raw = open(BACKUP, encoding='utf-8').read()
    orig = len(raw)
    print('源文件: %s' % BACKUP)

    # ---- 1) 样式 ----
    if raw.count('<style>') != 1 or raw.count('</style>') != 1:
        raise SystemExit('<style> 块数量异常')
    m = re.search(r'<style>(.*?)</style>', raw, re.S)
    raw = raw[:m.start(1)] + '\n' + CSS + '\n' + raw[m.end(1):]
    print('样式替换 OK（%d -> %d 字符）' % (len(m.group(1)), len(CSS)))

    # ---- 2) body 标记 ----
    i0 = raw.find('<header>')
    i1 = raw.find('<script type="text/plain" id="pdfworker">')
    if i0 < 0 or i1 < 0 or i1 < i0:
        raise SystemExit('body 标记定位失败')
    if raw.count('<header>') != 1:
        raise SystemExit('<header> 不唯一')
    raw = raw[:i0] + BODY + '\n\n' + raw[i1:]
    print('标记替换 OK（%d -> %d 字符）' % (i1 - i0, len(BODY) + 2))

    # ---- 3) 其余锚点 ----
    for tag, pat, new in PII_ANCHORS:          # 匿名化锚点先跑，幂等，重复构建不累积
        raw = rep_re(raw, tag, pat, new)
        print('锚点 OK: %s' % tag)
    for tag, old, new in ANCHORS:
        raw = rep(raw, tag, old, new)
        print('锚点 OK: %s' % tag)

    # ---- 4) render() 整段替换 ----
    if raw.count(RENDER_START) != 1 or raw.count(RENDER_END) != 1:
        raise SystemExit('render() 定位标记不唯一')
    a = raw.index(RENDER_START)
    b = raw.index(RENDER_END)
    if b < a:
        raise SystemExit('render() 起止顺序异常')
    print('render() 替换 OK（%d -> %d 字符）' % (b - a, len(RENDER_NEW)))
    raw = raw[:a] + RENDER_NEW + raw[b + 1:]

    # ---- 5) 解析/检索主循环整段替换（v2.6 进度与倒计时）----
    for tag, mark in (('进度起点', PROG_START), ('进度终点', PROG_END)):
        if raw.count(mark) != 1:
            raise SystemExit('%s标记命中 %d 次（应为 1）' % (tag, raw.count(mark)))
    a = raw.index(PROG_START)
    b = raw.index(PROG_END)
    if b < a:
        raise SystemExit('进度起止顺序异常')
    print('进度引擎替换 OK（%d -> %d 字符）' % (b - a, len(PROG_NEW)))
    raw = raw[:a] + PROG_NEW + raw[b:]

    # ---- 6) 导出块整段替换（加分证明清单 + 五育汇总）----
    for tag, mark in (('导出块起点', EXPORT_START), ('导出块终点', EXPORT_END)):
        if raw.count(mark) != 1:
            raise SystemExit('%s标记命中 %d 次（应为 1）' % (tag, raw.count(mark)))
    a = raw.index(EXPORT_START)
    b = raw.index(EXPORT_END)
    if b < a:
        raise SystemExit('导出块起止顺序异常')
    print('导出块替换 OK（%d -> %d 字符）' % (b - a, len(EXPORT_NEW)))
    raw = raw[:a] + EXPORT_NEW + raw[b:]

    if DRY:
        print('dry-run 完成，未写盘'); return 0
    open(HTML, 'w', encoding='utf-8', newline='').write(raw)
    print('written %.1f MB (delta %+d bytes)' % (len(raw) / 1048576.0, len(raw) - orig))
    print('sha256 %s' % hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16])
    return 0


if __name__ == '__main__':
    sys.exit(main())
