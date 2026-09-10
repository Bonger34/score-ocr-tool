
  // ---------- 离线 OCR：内嵌 tesseract.js（需勾选"识别扫描件"才触发，懒加载） ----------
  function b64bytes(b){ var bin=atob(b),u=new Uint8Array(bin.length); for(var i=0;i<bin.length;i++) u[i]=bin.charCodeAt(i); return u; }
  function b64str(b){ return decodeURIComponent(escape(atob(b))); }
  // 注入 worker 前缀：1)拦截 importScripts 把内核 JS 切到内嵌副本；2)拦截 fetch 提供中文模型
  function buildOcrWorkerSrc(a){
    var ov=
      'const __CORE_B64='+JSON.stringify(a.CORE_B64)+';'+
      'const __CHI_B64='+JSON.stringify(a.CHI_B64)+';'+
      'function _b64b(b){var x=atob(b),u=new Uint8Array(x.length);for(var i=0;i<x.length;i++)u[i]=x.charCodeAt(i);return u;}'+
      'function _b64s(b){return decodeURIComponent(escape(atob(b)));}'+
      'const _coreUrl=URL.createObjectURL(new Blob([_b64s(__CORE_B64)],{type:"text/javascript"}));'+
      'const _iis=self.importScripts.bind(self);'+
      'self.importScripts=function(){var a=[].slice.call(arguments).map(function(u){var n=String(u).split("/").pop().split("?")[0];if(n.indexOf("tesseract-core-")===0&&n.indexOf(".wasm.js")>=0)return _coreUrl;return u;});return _iis.apply(self,a);};'+
      'const _of=self.fetch.bind(self);'+
      'self.fetch=function(u,o){var s=String(u);if(s.indexOf("chi_sim.traineddata.gz")>=0){return Promise.resolve(new Response(_b64b(__CHI_B64),{status:200,headers:{"Content-Type":"application/octet-stream"}}));}return _of(u,o);};';
    var src=ov+b64str(a.WORKER_B64);
    return URL.createObjectURL(new Blob([src],{type:'text/javascript'}));
  }
  // ---------- OCR：多 Worker 并行池（替代原单串行队列） ----------
  var ocrWorkers=[], ocrFree=[], ocrTasks=[], ocrBusy=0;
  var OCR_CONC=Math.max(1, Math.min(2, ((typeof navigator!=='undefined'&&navigator.hardwareConcurrency)||2)-1)); // 并行 worker 数，≤2 兼顾速度与内存
  function ocrClaimWorker(){
    if(ocrFree.length) return Promise.resolve(ocrFree.pop());
    if(ocrWorkers.length<OCR_CONC){
      var assets=window.__OCR_ASSETS__;
      return Tesseract.createWorker('chi_sim',1,{
        workerPath:buildOcrWorkerSrc(assets),
        langPath:'offline/languages/',
        gzip:true,
        cacheMethod:'none',
        workerBlobURL:false
      }).then(function(w){ ocrWorkers.push(w); return w; });
    }
    return Promise.reject(new Error('OCR worker 池已满'));
  }
  function ocrRunOne(t){
    ocrClaimWorker().then(function(w){
      return w.recognize(t.canvas).then(function(r){ ocrFree.push(w); return r; },
        function(e){ ocrFree.push(w); throw e; }); // 无论成败都把 worker 归还空闲池
    }).then(function(r){ t.resolve(r); }, function(e){ t.reject(e); })
      .then(function(){ ocrBusy--; ocrPump(); });
  }
  function ocrPump(){
    while(ocrBusy<OCR_CONC&&ocrTasks.length){ var t=ocrTasks.shift(); ocrBusy++; ocrRunOne(t); }
  }
  // v2.1修复：OCR 文本规范化——保留行内空格与行间换行（仅压缩多重空白）。
  // 原实现 replace(/\s+/g,'') 剥掉全部空白，导致 parseOccurrences 按 [\s|｜]+ 分词失效
  // （姓名/学号/分值连成单个 token，整名检索永远无法命中）——这是原版既有缺陷，v2 沿袭。
  function normTxt(s){
    return String(s)
      .replace(/[^\S\r\n]+/g,' ')      // 行内连续空白 → 单个空格
      .replace(/[ \t]*[\r\n]+[ \t]*/g,'\n') // 换行前后空白 → 单个换行
      .replace(/\n{2,}/g,'\n')         // 多重换行 → 单换行
      .trim();
  }
  // 内置 Tesseract 池识别（作为 GPU 的兼容回退）
  function ocrImageTess(canvas){
    return new Promise(function(res,rej){ ocrTasks.push({canvas:canvas,resolve:res,reject:rej}); ocrPump(); })
      .then(function(r){ var t=(r&&r.data&&r.data.text)||''; return normTxt(t); })
      .catch(function(e){ console.warn('内置OCR失败',e); return ''; });
  }