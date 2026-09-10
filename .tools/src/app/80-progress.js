
  // ---------- 主流程 ----------
  function fmt(ms){
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
      $('status').textContent=head+' ·\u00A0已用 '+fmt(now-t0)+' ·\u00A0'+(eta<0?'预计剩余 计算中…':'预计剩余 '+fmt(eta));
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
  }
  async function handleRun(){
    if(!uploadedFiles) return;
    // 不再内置默认姓名：留空时明确提示
    var kw=$('kw').value.trim();
    if(!kw){ $('status').textContent='请先输入要检索的姓名。'; return; }
    var doDedup=$('dedup').checked;
    var fuzzy=$('fuzzy').checked; // 默认整名匹配；勾选后模糊（子串包含）
    var files=[].slice.call(uploadedFiles);
    $('runBtn').disabled=true; $('bar').style.display='block'; $('barpct').textContent='0%';
    var js0=$('jobStrip'); if(js0) js0.classList.add('running');
    try{   // v2.6：无论中途是否抛错，退出时都要停掉进度定时器
    textCache.stats.hit=0; textCache.stats.miss=0; // 本次运行的缓存统计
    // ---------- 解析阶段：进度条 0–98% ----------
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
    function line(label){ return '正在解析 '+prog.count()+' ·\u00A0'+label; }
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
      prog.set('正在检索 '+done2+'/'+totalEntries+' ·\u00A0'+ent.name);
      var text=ent.text||'';
      var recs;
      if(fuzzy){
        // 模糊模式（沿用旧行为）：空白归一后子串包含即命中，可捞"姓氏或名字里含该字"
        if(text.replace(/[\s|｜　]/g,'').indexOf(kw)<0) continue;
        recs=parseOccurrences(text,kw,fuzzy);
      }else{
        // 整名匹配：仅当文本中存在与输入词相等的完整姓名才命中，避免检索单字/姓氏误中大量文件
        recs=parseOccurrences(text,kw);
        if(recs.length===0) continue;
      }
      if(recs.length===0) recs=[{score:null,serial:null}];
      matched.push({name:ent.name, act:activityKey(ent.name), records:recs, src:ent.src, size:ent.size||0});
    }
    $('bar').style.display='none';
    prog.stop();   // 先停表，否则定时器会把状态行覆盖回进度文字
    var js1=$('jobStrip'); if(js1) js1.classList.remove('running');
    if(matched.length===0){
      // v2.5：空结果也要指出下一步，而不是只留一行灰字
      $('status').textContent='解析完成：没有命中。';
      $('announce').textContent='没有找到包含该姓名的文件';
      $('resultCard').style.display='block';
      $('summary').innerHTML='<div class="empty"><p class="empty-t">没有文件包含「'+esc(kw)+'」</p>'+
        '<p class="hint">可以试试：勾选「模糊匹配」按字串查找；如果名单是扫描件，勾选「识别扫描件」后重跑。</p></div>';
      $('detail').innerHTML=''; $('dupbox').innerHTML=''; $('dupbox').style.display='none';
      $('dlxlsx').style.display='none'; lastBlob=null;
      $('runBtn').disabled=false; return;
    }
    // v2.5：去掉"文本缓存命中/新解析"这类黑话，改成一句人话
    $('status').textContent='解析完成：命中 '+matched.length+' 个文件'+(textCache.stats.hit?'（'+textCache.stats.hit+' 个用了上次的缓存）':'')+'。';
    $('announce').textContent='解析完成，命中 '+matched.length+' 个文件';
    var res=doDedup?dedupe(matched):{keep:matched,removed:[]};
    render(res.keep,res.removed,doDedup,kw);
    $('resultCard').style.display='block';
    $('runBtn').disabled=false;
    } finally { if(prog) prog.stop(); }
  }

  function dedupe(matched){
    var fmap={}, order=[];
    matched.forEach(function(m){ if(!(m.name in fmap)){fmap[m.name]=m;order.push(m.name);} });
    var sigFiles={};
    order.forEach(function(fn){
      var act=fmap[fn].act||'';
      fmap[fn].records.forEach(function(r){
        if(r.serial===null) return;  // 无学号则无法可靠判重，跳过避免误并
        var key=act+'\t'+r.score+'\t'+r.serial; // 三键：活动 + 加分值 + 学号
        (sigFiles[key]=sigFiles[key]||new Set()).add(fn);
      });
    });
    var removed=new Set();
    Object.keys(sigFiles).forEach(function(key){
      var set=sigFiles[key];
      if(set.size<=1) return;
      var keep=[...set].sort(function(a,b){return a<b?-1:1;})[0];
      set.forEach(function(fn){ if(fn!==keep) removed.add(fn); });
    });
    var keep=order.filter(function(fn){return !removed.has(fn);}).map(function(fn){return fmap[fn];});
    var rem=order.filter(function(fn){return removed.has(fn);}).map(function(fn){return fmap[fn];});
    return {keep:keep, removed:rem};
  }

  function parseType(score){
    if(!score) return '';
    var m=/^([^\d+\-＋]+)/.exec(score);
    return m?m[1]:score;
  }
