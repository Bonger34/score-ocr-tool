
  function ocrImageTessBatch(canvases){
    return mapLimit(canvases, OCR_CONC, ocrImageTess);
  }
  // 统一 OCR 入口：GPU(自动)优先，失败或用户选"内置"则自动回退内置 Tesseract
  function ocrImage(canvas){
    var wantGpu = !($('eng')&&$('eng').value==='tess') && !!window.__GPU_OCR_ENABLED__;
    if(!wantGpu){ setEngStatus('cpu','CPU · 内置 Tesseract'); return ocrImageTess(canvas); }
    return gpuRecognize(canvas).then(function(t){
      if(t===null||t===''){ setEngStatus('cpu','CPU · 内置 Tesseract'); return ocrImageTess(canvas); }
      return t;
    }).catch(function(){ setEngStatus('cpu','CPU · 内置 Tesseract'); return ocrImageTess(canvas); });
  }
  // 自测钩子：供控制台/自动化验证 GPU 引擎就绪状态与单张识别
  window.__gpuSelfTest = function(){ return gpuInit(); };
  window.__gpuSelfRecognize = function(c){ return gpuRecognize(c); };
  // v2基准钩子：上报实际生效的会话 EP 与识别参数（供 Playwright 断言配置已生效）
  window.__gpuSvcInfo__=function(){ return gpuInit().then(function(s){
    return s? {
      ep:s.options.session && s.options.session.executionProviders,
      det:s.options.detection && {maxSideLength:s.options.detection.maxSideLength, minimumAreaThreshold:s.options.detection.minimumAreaThreshold},
      rec:s.options.recognition && {mainThreadYieldMs:s.options.recognition.mainThreadYieldMs, recBatchSize:s.options.recognition.recBatchSize}
    } : null; });
  };
  // v2基准钩子：分阶段计时统计（renderMs/ocrMs 在 readPdfText 两阶段流水处累加）
  window.__ocrPerf__={renderMs:0, ocrMs:0, pages:0, tessFallbacks:0, gpuFails:0, gpuBatchLimit:6};
