
  function pdfPageText(page){ return page.getTextContent().then(function(tc){ return tc.items.map(function(it){return it.str||'';}).join(' | '); }); }
  // OCR/预览渲染：OCR 只需文字清晰达可识别即可，超 1600px 的长边会成倍放大识别输入像素，故 cap。
  // canvas 渲染本身很快，瓶颈在把巨画布喂给 PP-OCR；此处按最长边自适应降 scale 保持长宽比。
  var OC_CAP=1600; // v2提速：1800→1600，det 输入随之从 ~1344 降至 ~1216，rec 行图变窄
  function renderPageToCanvas(page,scale){
    scale=scale||2;
    var vp=page.getViewport({scale:scale});
    var ls=Math.max(vp.width,vp.height);
    if(ls>OC_CAP){ scale*=OC_CAP/ls; vp=page.getViewport({scale:scale}); }
    var canvas=document.createElement('canvas'); canvas.width=vp.width; canvas.height=vp.height;
    return page.render({canvasContext:canvas.getContext('2d'),viewport:vp}).promise.then(function(){return canvas;});
  }
  // v2.1修复：纯白/空白页检测（渲染后 9 点小窗采样，任一非白即视为有内容）。
  // 空白页（如"无文本层+无内容"的废弃导出件）直接按空文本处理，不进 OCR——
  // 否则 det 对白图返回空框会被 10-B 误判为"GPU 会话异常"而整体禁用 GPU。
  function canvasIsBlank(c){
    try{
      var g=c.getContext('2d'), W=c.width, H=c.height;
      var pts=[[0.08,0.08],[0.92,0.08],[0.08,0.92],[0.92,0.92],[0.5,0.5],[0.5,0.1],[0.5,0.9],[0.1,0.5],[0.9,0.5]];
      for(var i=0;i<pts.length;i++){
        var x=Math.max(0,Math.floor(W*pts[i][0])), y=Math.max(0,Math.floor(H*pts[i][1]));
        var wx=Math.min(32, W-x), wy=Math.min(32, H-y);
        if(wx<=0||wy<=0) continue;
        var d=g.getImageData(x,y,wx,wy).data;
        for(var j=0;j<d.length;j+=4){
          if(d[j]<240||d[j+1]<240||d[j+2]<240) return false; // 存在非白像素 → 有内容
        }
      }
      return true;
    }catch(e){ return false; } // 采样失败不判空白，交给 OCR
  }

  function readPdfText(buf, ctl){
    return pdfjsLib.getDocument({data:new Uint8Array(buf), disableFontFace:true, useSystemFonts:false}).promise.then(async function(pdf){ // v2.4：只取文本，跳过字体装配
      var n=pdf.numPages;
      // v2.6：页级权重等下面 ocrIdx 算出来再登记——OCR 页的耗时是文本页的数十倍，必须分开计权
      var doOcr=!!($('ocr').checked)&&(!!(window.Tesseract&&window.__OCR_ASSETS__)||!!window.__GPU_OCR_ENABLED__);
      // 多页并行取词：先一次性 getPage 再并行 getTextContent，充分利用 pdf.js worker
      var pgObjs=[];
      for(var a=1;a<=n;a++){ pgObjs.push(pdf.getPage(a)); }
      pgObjs=await Promise.all(pgObjs);
      var outs=new Array(n);
      await Promise.all(pgObjs.map(function(page,idx){
        return pdfPageText(page).then(function(txt){ outs[idx]=txt.trim(); });
      }));
      var out=[];
      // 需要 OCR 的页下标（原本空文本页才识别），v2：渲染/识别两阶段分块流水线
      var ocrIdx=[];
      for(var pg=1;pg<=n;pg++){ if(doOcr&&!outs[pg-1]) ocrIdx.push(pg); }
      var ocrMap={}; ocrIdx.forEach(function(p){ ocrMap[p]=true; });
      // v2.6：按页类型分别登记进度权重。本 PDF 已被外层预记 1 个单元，
      // 从页数多的那组里扣掉，保证总数正好是 n（否则进度条会停在 99%）
      if(ctl&&n>1){
        var tp=n-ocrIdx.length, op=ocrIdx.length;
        if(tp>0) ctl.add(tp-1,'page');
        if(op>0) ctl.add(op-(tp>0?0:1),'ocr');
      }
      // v2提速：先以较高并发批量渲染（CPU 密集，pdf.js 多 worker 并行），
      // 再以较低并发喂 GPU batchRecognize（rec 动态批在单图内合并 6 线；并发 2-3 让 det/rec
      // 在 GPU 队列串行下仍重叠 CPU 侧预处理与张量搬运）。分块控制画布内存峰值。
      // v3加固：真机 4GB 显存（RTX 2050）降并发防 GPU OOM/驱动重置；REC_CONC=1 时 batch 内动态批仍合并 4 线
      var REND_CONC=3, REC_CONC=1, OCR_CHUNK=6;
      var done=0, pf=window.__ocrPerf__||null;
      // v2.2：块大小随 GPU 批上限动态收缩——GPU 降批后小块更易成功、超时风险更低（重活仍由 GPU 扛）
      for(var ci=0; ci<ocrIdx.length; ){
        var chunkN=Math.min(OCR_CHUNK, gpuBatchLimit);
        if(gpuWarmup) chunkN=1; // v2.2：首个批只发 1 页，先让模型编译完并给出首帧反馈
        var chunk=ocrIdx.slice(ci, ci+chunkN);
        ci+=chunkN;
        // 阶段 A：渲染本块（6 并发）
        var tR0=Date.now();
        var canvases=await mapLimit(chunk, REND_CONC, function(pg){
          return renderPageToCanvas(pgObjs[pg-1],2).catch(function(){ return null; }); // 渲染失败继续
        });
        if(pf) pf.renderMs+=Date.now()-tR0;
        var valid=[];
        canvases.forEach(function(c){ if(c&&!canvasIsBlank(c)) valid.push(c); }); // v2.1：空白页不进 OCR（按空文本处理）
        // 阶段 B：批识别（GPU 优先；整体失败则全部走内置池）
        var texts=null;
        var wantGpuB=!($('eng')&&$('eng').value==='tess') && !!window.__GPU_OCR_ENABLED__;
        var tO0=Date.now();
        if(valid.length && wantGpuB){ texts=await gpuRecognizeBatch(valid, REC_CONC); }
        if(valid.length && !texts){ texts=await ocrImageTessBatch(valid); if(pf) pf.tessFallbacks+=valid.length; }
        if(pf) pf.ocrMs+=Date.now()-tO0;
        // 回填文本 + 进度：每页恰一步（含渲染失败页），done 不溢出 total；GPU 空文本/异常项逐个回退内置
        for(var k=0;k<chunk.length;k++){
          var ti=valid.indexOf(canvases[k]);
          var t=(ti>=0&&texts&&texts[ti])?texts[ti]:'';
          if(ti>=0&&(!texts||!texts[ti])){ t=await ocrImageTess(canvases[ti]).catch(function(){ return ''; }); if(pf) pf.tessFallbacks++; }
          outs[chunk[k]-1]=t||'';
          done++; if(ctl) ctl.step('第'+chunk[k]+'/'+n+'页·OCR ('+done+'/'+ocrIdx.length+')','ocr');
        }
        canvases=null; valid=null; // 块尾置空，依赖 GC 释放画布内存
      }
      // 进度：未被 OCR 覆盖的普通文本页，按页 step 补足
      for(var pg2=1;pg2<=n;pg2++){
        var t2=outs[pg2-1]||'';
        out.push(t2);
        if(ctl&&!ocrMap[pg2]) ctl.step('第'+pg2+'/'+n+'页','page');
      }
      return out.join('\n');
    });
  }
  function xlsxText(zip, keyword){
    var keys=Object.keys(zip.files).filter(function(n){return /\.xml$/.test(n)&&n.indexOf('__MACOSX')<0;});
    return Promise.all(keys.map(function(n){return entryBytes(zip.files[n]);}))
      .then(function(arrs){ return arrs.map(function(a){return new TextDecoder('utf-8').decode(a);}).join('\n'); });
  }
