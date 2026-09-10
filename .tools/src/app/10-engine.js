
  // ---------- pdf.js 离线 worker：安全地从 text/plain 块读取源码，避免内嵌进字符串被破坏 ----------
  var pwEl=document.getElementById('pdfworker');
  if(pwEl&&pwEl.textContent&&window.pdfjsLib){
    try{ pdfjsLib.GlobalWorkerOptions.workerSrc=URL.createObjectURL(new Blob([pwEl.textContent],{type:'application/javascript'})); }
    catch(e){ console.warn('worker init failed',e); }
  }
  // 引擎状态指示：kind ∈ gpu/cpu/check，text 为说明；真实反映当前实际所用识别引擎
  function setEngStatus(kind,text){
    var wrap=document.getElementById('engStatus'), tx=document.getElementById('engText');
    if(!tx) return;
    // v2.5：颜色交给 CSS 按 data-kind 决定。原来内联色表没有 err，GPU 异常会被画成橙色，
    // 和"CPU 模式"看起来一模一样——状态区分不能只靠颜色，更不能靠错的颜色。
    if(wrap) wrap.setAttribute('data-kind',(kind==='gpu'||kind==='cpu'||kind==='check'||kind==='err')?kind:'cpu');
    tx.textContent=text;
  }
  // v2.2：file:// 实测可用（GPU 引擎、IndexedDB 缓存、pdf.js worker 均正常，见报告 7.6），
  // 故文案由原来的"建议本地服务打开"改为中性提示，不再误导用户以为 file:// 不可用
  try{
    if(location.protocol==='file:'&&typeof setEngStatus==='function'){
      setEngStatus('check','file:// 模式（可直接使用；想用独显请双击 打开工具.cmd）');
    }
  }catch(_){}
  // 获取"厂商+型号"的 GPU 名称：优先 WebGPU adapter.info；拿不到 description 时
  // 用 WebGL 的 unmasked 渲染器信息（能回报真实型号，如 "NVIDIA GeForce RTX 30xx"）
  function getGpuName(gadt){
    var n='';
    try{ var inf=gadt&&gadt.info; if(inf&&inf.description) n=inf.description; else if(inf&&inf.device) n=inf.device; }catch(e){}
    if(!n||/^(google|angle|unknown|null)$/i.test(n.trim())){
      try{
        var c=document.createElement('canvas');
        var gl=c.getContext('webgl')||c.getContext('experimental-webgl');
        if(gl){
          var ex=gl.getExtension('WEBGL_debug_renderer_info');
          n=ex?String(gl.getParameter(ex.UNMASKED_RENDERER_WEBGL)||''):String(gl.getParameter(gl.RENDERER)||'');
        }
      }catch(e){}
    }
    // 软件渲染没有独立 GPU 型号，如实标注
    if(/SwiftShader/i.test(n)) return 'SwiftShader·软件渲染';
    // 清洗 GPU 型号字符串。分两种情况：
    // ① Windows Chrome WebGL 返回 "ANGLE (厂商, 型号, OpenGL...)" 格式——真实型号在括号内，
    //    外层 ANGLE 只是封装层名，必须提取括号内容，否则会丢失型号只留下 "ANGLE"。
    // ② 手机/桌面直出格式如 "Adreno (TM) 650"、"NVIDIA, GeForce RTX 30xx"——括号内是商标符，
    //    直接移除括号块即可。
    function cleanGpu(s){
      s=String(s||'').trim();
      // 情况①：以 ANGLE 开头且括号内含逗号（厂商,型号,API...），提取括号内真实型号
      var m=s.match(/^ANGLE\s*\(([^]*)\)$/i);
      if(m){
        var inner=m[1];
        inner=inner.replace(/\(TM\)|\(r\)|\(R\)|™|®/gi,' ');       // 移除商标符
        inner=inner.replace(/,?\s*(OpenGL|Direct3D|Vulkan)[^,)]*/gi,''); // 移除 API 描述段
        var segs=inner.split(',').map(function(x){return x.trim();}).filter(Boolean);
        // 通常格式 "厂商, 型号[, 残留]"，取前两段合并；型号已自带厂商名时不再重复（避免 "Intel Intel …"）
        if(segs.length>=2){
          var a=segs[0], b=segs[1];
          var head=(b.toLowerCase().indexOf(a.toLowerCase())===0)?b:(a+' '+b);
          return head.replace(/\s+/g,' ').trim();
        }
        return (segs[0]||'').replace(/\s+/g,' ').trim();
      }
      // 情况②：移除商标符与括号块，再清理 API 后缀
      s=s.replace(/\(TM\)|\(r\)|\(R\)|™|®/gi,' ')
        .replace(/\([^)]*\)/g,' ')
        .replace(/OpenGL[^A-Za-z]*/gi,'')
        .replace(/[Vv]ulkan.*$/i,'')
        .replace(/Direct(R)?3D.*$/i,'')
        .replace(/\bANGLE\b/gi,' ');  // 移除独立 ANGLE 封装层名
      var segs=s.split(',').map(function(x){return x.trim();}).filter(Boolean);
      return (segs.length>1?segs[0]+' '+segs[1]:(segs[0]||'')).trim();
    }
    n=cleanGpu(n);
    // 清洗后为空（如原始串仅是 "ANGLE" 无括号内容）时，按 vendor → "WebGPU" 逐级 fallback，
    // 不再回退到 raw（raw 可能就是无意义的封装层名）
    if(!n){
      try{
        var v=gadt&&gadt.info&&gadt.info.vendor, cv=cleanGpu(v);
        n=(cv&&!/^(google|angle|unknown|swiftshader)$/i.test(cv))?cv:'';
      }catch(e){ n=''; }
    }
    if(!n) n='WebGPU';
    n=n.replace(/\s+/g,' ').trim();
    if(n.length>48) n=n.slice(0,48)+'…';
    return n;
  }
  // v3加固：全局未捕获拒绝兜底——GPU 相关异常自动禁用 GPU 并回退内置引擎，防真机静默死锁/白屏无提示
  window.addEventListener('unhandledrejection',function(ev){
    var re=ev&&ev.reason, m=(re&&(re.message||String(re)))||'未捕获的异步错误';
    try{
      if(/gpu|webgpu|ort|onnx|session|device|adapter|initialize|recognize/i.test(m)){
        window.__GPU_OCR_ENABLED__=false;
        try{ if(typeof gpuState!=='undefined'&&gpuState<2) gpuState=3; }catch(_){}
        setEngStatus('err','GPU 异常，已自动回退内置引擎：'+String(m).slice(0,44));
      }
    }catch(_){}
  });
  // 真实 GPU 能力探测：requestAdapter() 拿到可用适配器才算支持 WebGPU，而非只看 navigator.gpu 属性是否存在
  window.__GPU_OCR_ENABLED__ = false;
  function syncEngUi(gpuOk){
    var hasGpu=(typeof gpuOk==='boolean')?gpuOk:window.__GPU_OCR_ENABLED__;
    var ocr=$('ocr'), engSel=$('eng'), engWrap=$('engWrap');
    var engVal=engSel?engSel.value:'auto';
    // 用户显式选"内置"时按其意愿确定为 CPU
    if(engVal==='tess') hasGpu=false;
    if(engWrap){ engWrap.style.display=(hasGpu&&ocr&&ocr.checked)?'inline-block':'none'; }
    if(!hasGpu){
      // 无 GPU 时把引擎下拉落到"内置"（用户已选则保留）
      if(engVal!=='tess'&&engSel) engSel.value='tess';
      setEngStatus('cpu','CPU · 内置 Tesseract'); return;
    }
    if(ocr&&ocr.checked){
      setEngStatus('check','正在启用 GPU 加速…');
      gpuInit().then(function(s){ if(!s) setEngStatus('cpu','CPU · 内置 Tesseract'); },
                    function(){ setEngStatus('cpu','CPU · 内置 Tesseract'); });
    }else if(!ocr||!ocr.checked){
      setEngStatus('check','GPU 就绪，等待识别');
    }
  }
  (function(){
    var ocr=$('ocr');
    if(ocr) ocr.addEventListener('change',function(){ syncEngUi(); });
  })();
  var __gpuEl=document.getElementById('gpuassets');
  if(__gpuEl&&typeof navigator!=='undefined'&&navigator.gpu){
    setEngStatus('check','检测 OCR 引擎…');
    navigator.gpu.requestAdapter({powerPreference:'high-performance'})
      .then(function(ad){
        window.__GPU_OCR_ENABLED__=!!ad;
        syncEngUi(!!ad);
      })
      .catch(function(){
        window.__GPU_OCR_ENABLED__=false;
        syncEngUi(false);
      });
  }else{
    syncEngUi(false);
  }
  var SCORE_RE=/(美育|德育|劳育|智育|体育)\s*([＋+\uFF0B-]\s*\d+(?:\.\d+)?)/;
  var uploadedFiles=null, matched=[], lastBlob=null; // lastBlob: 已生成的导出内容，供 exportNow 命中
