
  // ---------- GPU OCR 引擎：PaddleOCR / WebGPU，懒初始化，失败自动回退内置 ----------
  function loadScriptToGlobal(jsText){
    return new Promise(function(res,rej){
      try{
        var b=new Blob([jsText],{type:'text/javascript'});
        var u=URL.createObjectURL(b);
        var sc=document.createElement('script');
        sc.src=u;
        sc.onload=function(){ URL.revokeObjectURL(u); res(); };
        sc.onerror=function(){ URL.revokeObjectURL(u); rej(new Error('脚本加载失败')); };
        document.head.appendChild(sc);
      }catch(e){ rej(e); }
    });
  }
  function decodeB64str(b){ return decodeURIComponent(escape(atob(b))); }
  // gzip 解压 base64 为 ArrayBuffer：wasm/模型以 gzip 方式内嵌以压缩文件体积
  function gunzipToBuf(s){
    if(typeof DecompressionStream==='undefined') return Promise.reject(new Error('无 gzip 解压支持'));
    return new Response(new Blob([b64bytes(s)]).stream().pipeThrough(new DecompressionStream('gzip'))).arrayBuffer();
  }
  var gpu=null, gpuState=0, gpuP=null, gpuCompiledWarn=false; // 0未试 1初始化中 2就绪 3不可用
  window.__gpuTimeline__=[]; // v3诊断：GPU 关键节点时间戳，真机异常时便于定位挂起点
  function gpuMark(tag){ try{ window.__gpuTimeline__.push(tag+':'+Date.now()); }catch(_){} }
  // v3加固：全局 GPU 推理互斥链——ORT 会话不允许并发 run()（报 Session already started），
  // 任何时刻至多一个批推理在途；排队期间 GPU 若已失效则短路返回 null
  var gpuChain=Promise.resolve(), gpuFailStreak=0;
  // v2.3修复（关键）：串行队列必须在**调用时同步**推进链头。
  // v2.2 曾把链更新写进 then 回调里，于是同一批微任务里先后进入的多个批都读到同一个旧链头，
  // 结果是 6 个文件的批识别同时冲进同一个 ORT 会话 → 会话错乱、主线程被 wasm 占满、页面假死
  // （真机现象：点开始后卡住、"已用"秒数不再增加）。此处改为：调用即占位，链上等待底层 run 真正 settle。
  function gpuQueue(makeRaw){
    var rawResolve, rawReject;
    var rawP=new Promise(function(res,rej){ rawResolve=res; rawReject=rej; });
    var wait=gpuChain;
    gpuChain=wait.then(function(){
      var p;
      try{ p=makeRaw(); }catch(e){ rawReject(e); return; }
      p.then(rawResolve, rawReject);
      // 链等待底层 run 真正结束（withTimeout 只是调用方放弃等待，并不会取消 ORT 的 run）
      return p.then(function(){}, function(){});
    }, function(){ rawReject(new Error('GPU 队列已失效')); });
    return rawP;
  }
  // v2.2加固：真机"一开始是 GPU，跑一会就退化成 CPU（GPU 批识别失败/超时）"的根因是
  // **固定 90s 硬超时 + 一次失败即永久禁用**：密集表格/扫描页单页可达 15~20s，6 页一批就顶到 90s；
  // 超时后底层 run 仍在占用会话，后续批再撞 "Session already started" 就被误判成引擎损坏。
  // 现改为：超时按页数自适应 + 失败降批重试 + 会话重建，只有连续多次失败才彻底回退内置。
  var gpuBatchLimit=6;   // 动态批上限：失败减半（6→3→1），连续成功 3 批后逐步恢复
  var gpuFailTotal=0;    // 连续失败批数（任一成功即清零）
  var gpuOkStreak=0;     // 连续成功批数（用于恢复批上限）
  var gpuStale=false;    // 会话可能被未结束的 run 污染 → 下次 gpuInit 重建会话
  var gpuInitFails=0;    // 连续初始化失败次数（≥2 才永久回退内置）
  var gpuWarmup=true;    // v2.2：首个 GPU 批只发 1 页（模型首次编译单独摊薄），拿到首帧反馈后再放大批量
  // v2.2：统一的 GPU 批失败处理——降批 + 标记会话待重建；本批先回退内置，不立即永久禁用
  function gpuBatchFail(e){
    var msg=(e&&(e.message||e))?String(e.message||e):'未知错误';
    gpuFailTotal++; gpuOkStreak=0; gpuFailStreak=0;
    gpuBatchLimit=Math.max(1, Math.floor(gpuBatchLimit/2)); // 降批：6→3→1
    // v2.4：显存吃紧（本机 GPU 常被桌面程序占满）时，光降"每批页数"不够——单次 rec run 的
    // 中间张量 [B,T,18385] 才是显存大头，这里同步把 rec 批大小减半（4→2→1）；会话重建后恢复默认
    try{ var ro=gpu&&gpu.recognitor&&gpu.recognitor.options; if(ro&&ro.recBatchSize>1){ ro.recBatchSize=Math.max(1,Math.floor(ro.recBatchSize/2)); } }catch(_){}
    gpuStale=true;                                          // 底层 run 可能仍在跑，下次换新会话
    gpuMark('rec:fail:'+msg.slice(0,60));
    if(window.__ocrPerf__){ window.__ocrPerf__.gpuFails++; window.__ocrPerf__.gpuBatchLimit=gpuBatchLimit; }
    console.warn('GPU 批识别失败（本批回退内置，批上限降至 '+gpuBatchLimit+'）：', e);
    if(gpuFailTotal>=6){
      // 连续 6 批（含重建会话后重试）都失败才认定 GPU 不可用，避免"偶发一批拖垮整场"
      gpuDisable('连续 '+gpuFailTotal+' 批失败：'+msg.slice(0,40));
    }else{
      setEngStatus('check','GPU 本批异常，已降批重试（批'+gpuBatchLimit+'：'+msg.slice(0,30)+'）');
    }
    return null;
  }
  // v2.2：统一 GPU 状态栏文案。双显卡笔记本上浏览器默认把 GPU 进程放在核显上
  // （WebGPU 随之只能用核显），此处显式标注"核显"并把切独显的办法挂到 title 上。
  function setGpuStatus(){
    var n=window.__GPU_DEVICE_NAME__||'WebGPU';
    var ig=(/intel/i.test(n)&&!/\barc\b/i.test(n))||/iris|uhd graphics|radeon\(tm\) graphics|vega \d/i.test(n);
    setEngStatus('gpu','GPU · '+n+(ig?'（核显）':'')+'（WebGPU 加速）');
    try{
      var box=document.getElementById('engStatus');
      if(box) box.title=ig
        ? '当前 WebGPU 跑在核显上。若本机配有独立显卡，请用「启动工具.cmd」打开（自动加 --force_high_performance_gpu），或在 Windows「设置→系统→屏幕→图形」中把浏览器设为“高性能”，可显著提速。'
        : 'WebGPU 当前设备：'+n;
    }catch(_){}
  }
  // v2.2：批成功后清零失败计数；顺带把状态栏从"首次编译/降批提示"切回真实 GPU 状态
  function gpuBatchOk(){
    var wasFail=gpuFailTotal>0;
    gpuFailTotal=0; gpuFailStreak=0; gpuOkStreak++;
    gpuWarmup=false; // v2.2：首个批已成功，之后恢复正常批量
    if(gpuBatchLimit<6 && gpuOkStreak>=3){ gpuBatchLimit++; gpuOkStreak=0; }
    if(window.__ocrPerf__) window.__ocrPerf__.gpuBatchLimit=gpuBatchLimit;
    // gpuCompiledWarn 同时充当"状态栏被临时文案占用"的标记，首个成功批后恢复显示
    if(gpuState===2 && (wasFail || gpuCompiledWarn)){ gpuCompiledWarn=false; setGpuStatus(); }
  }
  function gpuDisable(reason){
    gpuState=3; gpu=null; gpuStale=false; window.__GPU_OCR_ENABLED__=false;
    setEngStatus('cpu','CPU · 内置 Tesseract（'+reason+'）');
    console.warn('已禁用 GPU OCR：'+reason);
  }
  // v3加固：统一超时工具——真机 GPU 驱动挂起时 Promise 永不 settle，必须用 race 兜底
  function withTimeout(p, ms, tag){
    var timer=null;
    return Promise.race([
      p,
      new Promise(function(_, rej){ timer=setTimeout(function(){ rej(new Error((tag||'任务')+'超时('+ms+'ms)')); }, ms); })
    ]).then(function(v){ clearTimeout(timer); return v; }, function(e){ clearTimeout(timer); throw e; });
  }
  function gpuInit(){
    // v2.2：会话被污染（批超时后底层 run 仍占用）时丢弃并重建，避免后续批一直撞 Session already started
    var rebuilding=false;
    if(gpuStale&&gpuState!==1){
      try{ if(gpu&&typeof gpu.dispose==='function') gpu.dispose(); }catch(_){}
      gpu=null; gpuP=null; gpuState=0; gpuStale=false; rebuilding=true; gpuMark('session:rebuild');
    }
    if(gpuState===2&&gpu) return Promise.resolve(gpu);
    if(gpuState===3) return Promise.resolve(null);
    if(gpuState===1&&gpuP) return gpuP;
    gpuState=1;
    gpuP=(async function(){
      try{
        // v2.2：重建会话前先等旧 run 收尾（链上最多 15s 宽限），避免新旧会话同时占显存而初始化 OOM
        if(rebuilding){ try{ await gpuChain; }catch(_){} }
        var el=document.getElementById('gpuassets');
        if(!el||!window.navigator.gpu) throw new Error('当前环境不支持 WebGPU');
        // 真实获取 GPU 适配器；5s 超时防驱动枚举挂起（取不到则视为无 GPU，回退内置引擎）
        var gadt=null;
        try{ gpuMark('adapter:start'); gadt=await withTimeout(navigator.gpu.requestAdapter({powerPreference:'high-performance'}), 5000, 'GPU适配器'); gpuMark('adapter:ok'); }
        catch(e){ console.warn('GPU 适配器获取超时/失败：',e); gadt=null; }
        if(!gadt) throw new Error('未获得可用的 GPU 适配器');
        var gpuName=getGpuName(gadt);
        window.__GPU_DEVICE_NAME__=gpuName;
        var parts=el.textContent.split('|');
        function val(k){ for(var i=0;i+1<parts.length;i+=2){ if(parts[i]===k) return parts[i+1]; } return null; }
        if(!window.ort){ var ob=val('ORT'); if(!ob) throw new Error('缺少 ort 运行时'); await loadScriptToGlobal(decodeB64str(ob)); }
        if(!window.ort) throw new Error('ort 注入失败');
        var wasmUrl=URL.createObjectURL(new Blob([await gunzipToBuf(val('WASM'))],{type:'application/wasm'}));
        var mjsUrl=URL.createObjectURL(new Blob([decodeB64str(val('MJS'))],{type:'text/javascript'}));
        ort.env.wasm.wasmPaths={mjs:mjsUrl,wasm:wasmUrl};
        var detBuf=await gunzipToBuf(val('DET'));
        var recBuf=await gunzipToBuf(val('REC'));
        var dictBuf=b64bytes(val('DICT')).buffer;
          // v2.4 提速（核心）：内嵌 rec 模型末尾追加 ArgMax+ReduceMax+Concat，输出由 [B,T,18385]
  // 概率图变为 [B,T,2]（argmax 索引 + 该位置最大概率）。原来每个 rec 批要回读 18385 类
  // fp32 概率图（实测 24 页共 11GB，回读带宽约 0.35GB/s 是主要瓶颈），主线程还要逐类扫描
  // 求 argmax（每批 10.7M 次读取）。这里给引擎注入"索引解码"分支：dims 为 [B,T,2] 时走新路，
  // 否则退回原概率解码——因此补丁对旧模型同样安全。