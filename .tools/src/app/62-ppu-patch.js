
  function patchPPU(src){
    var n=0;
    function rep(tag,a,b){
      var i=src.indexOf(a);
      if(i<0) throw new Error('PPU 补丁锚点缺失：'+tag);
      if(src.indexOf(a,i+1)>=0) throw new Error('PPU 补丁锚点重复：'+tag);
      src=src.slice(0,i)+b+src.slice(i+a.length); n++;
    }
    function J(arr){ return arr.join('\n'); }
    var ANCHOR_DECODE = '  function decodeLogitsRow(rowData, sequenceLength, numClasses, charactersDictionary, spaceRecovery = false) {';
    var ANCHOR_BATCH = [
      '        let output = await ctx.runInference(inputTensor);',
      '        const [, seqLen, numClasses] = output.dims;',
      '        let data = output.data;',
      '        let rowSize = (seqLen ?? 0) * (numClasses ?? 0);',
      '        chunk.forEach((cropIndex, row) => {',
      '          let widthShare = (prepped[cropIndex]?.tensorWidth ?? maxWidth) / maxWidth;',
      '          let validSeq = Math.max(1, Math.min(seqLen ?? 0, Math.ceil((seqLen ?? 0) * widthShare)));',
      '          results[cropIndex] = decodeLogitsRow(data.subarray(row * rowSize, row * rowSize + validSeq * (numClasses ?? 0)), validSeq, numClasses ?? 0, dict, spaceRecovery);',
      '        });'
    ].join('\n');
    // ① 新增按索引解码（与 ctcGreedyDecode 同语义；spaceRecovery 依赖空格类概率，索引模式下不可用，
    //    该选项默认关闭且本工具未启用）
    rep('decodeIdxRow', ANCHOR_DECODE, J([
      '  function decodeIdxRow(data, offset, sequenceLength, charDict) {',
      '    let dictLen = charDict.length, lastDictIndex = dictLen - 1;',
      '    let emitted = [], lastCharIndex = -1, confidenceSum = 0, confidenceCount = 0, positions = [];',
      '    for (let t = 0; t < sequenceLength; t++) {',
      '      let p = offset + t * 2, maxIndex = data[p] | 0, maxProb = data[p + 1];',
      '      if (maxIndex === BLANK_INDEX || maxIndex === lastCharIndex) { lastCharIndex = maxIndex; continue; }',
      '      if (maxIndex >= 0 && maxIndex < dictLen) {',
      '        let char = charDict[maxIndex] ?? "";',
      '        if (maxIndex === lastDictIndex) {',
      '          if (char !== UNK_TOKEN) { emitted.push(" "); confidenceSum += maxProb; confidenceCount++; positions.push((t + 0.5) / sequenceLength); }',
      '        } else {',
      '          emitted.push(char); confidenceSum += maxProb; confidenceCount++; positions.push((t + 0.5) / sequenceLength);',
      '        }',
      '      }',
      '      lastCharIndex = maxIndex;',
      '    }',
      '    injectGapSpaces(emitted, positions);',
      '    refineDecodedChars(emitted, positions);',
      '    return { text: emitted.join(""), confidence: confidenceCount > 0 ? confidenceSum / confidenceCount : 0, positions };',
      '  }',
      ANCHOR_DECODE
    ]));
    // ② 批解码分支：索引输出走 decodeIdxRow，概率输出保持原路
    rep('batchBranch', ANCHOR_BATCH, J([
      '        let output = await ctx.runInference(inputTensor);',
      '        let odims = output.dims, data = output.data;',
      '        if (odims.length === 3 && odims[2] === 2) {',
      '          let seqLen = odims[1];',
      '          chunk.forEach((cropIndex, row) => {',
      '            let widthShare = (prepped[cropIndex]?.tensorWidth ?? maxWidth) / maxWidth;',
      '            let validSeq = Math.max(1, Math.min(seqLen, Math.ceil(seqLen * widthShare)));',
      '            results[cropIndex] = decodeIdxRow(data, row * seqLen * 2, validSeq, dict);',
      '          });',
      '        } else {',
      '        const [, seqLen, numClasses] = output.dims;',
      '        let rowSize = (seqLen ?? 0) * (numClasses ?? 0);',
      '        chunk.forEach((cropIndex, row) => {',
      '          let widthShare = (prepped[cropIndex]?.tensorWidth ?? maxWidth) / maxWidth;',
      '          let validSeq = Math.max(1, Math.min(seqLen ?? 0, Math.ceil((seqLen ?? 0) * widthShare)));',
      '          results[cropIndex] = decodeLogitsRow(data.subarray(row * rowSize, row * rowSize + validSeq * (numClasses ?? 0)), validSeq, numClasses ?? 0, dict, spaceRecovery);',
      '        });',
      '        }'
    ]));
    // ③ 单张识别入口（cross-line 策略）同样兼容索引输出
    rep('decodeResults', J([
      '  function decodeResults(outputTensor, charactersDictionary, numClassesFromShape, verbose = false, spaceRecovery = false) {',
      '    let outputData = outputTensor.data;',
      '    let outputShape = outputTensor.dims;'
    ]), J([
      '  function decodeResults(outputTensor, charactersDictionary, numClassesFromShape, verbose = false, spaceRecovery = false) {',
      '    let outputData = outputTensor.data;',
      '    let outputShape = outputTensor.dims;',
      '    if (outputShape.length === 3 && outputShape[2] === 2) {',
      '      return decodeIdxRow(outputData, 0, outputShape[1], charactersDictionary);',
      '    }'
    ]));
    return src;
  }
        if(!window.PPU){ var pb=val('PPU'); if(!pb) throw new Error('缺少 PP-OCR 引擎'); await loadScriptToGlobal(patchPPU(decodeB64str(pb))); }
        if(!window.PPU||!window.PPU.PaddleOcrService) throw new Error('PP-OCR 引擎缺失');
        var svc=new PPU.PaddleOcrService({
        model:{detection:detBuf,recognition:recBuf,charactersDictionary:dictBuf},
        session:{executionProviders:['webgpu','wasm']},   // v2提速：EP 必须放 session 键下才会被 _resolveSessionExecutionProviders 读取（顶层键是死配置，原实现实际以 ['cpu'] 建会话）
        detection:{maxSideLength:960, minimumAreaThreshold:12}, // v2提速：det 输入最长边 1800→960；阈值 20→12 补偿小框在 0.51 倍缩放空间下的面积缩水
        recognition:{mainThreadYieldMs:0, recBatchSize:8}, // v2.4：模型改为输出 [B,T,2] 索引后回读不再是瓶颈，批大小只影响固定开销摊薄；实测 4→8 快 3%（16/32 反而更慢）。显存吃紧时由 gpuBatchFail 自适应把批大小减半（8→4→2→1），故默认取快的档位
      });
        // v3加固：初始化（模型加载+首次编译）30s 超时，超时抛错回退内置引擎，防页面永久"无响应"
        gpuMark('init:start');
        await withTimeout(svc.initialize(), 30000, 'GPU初始化');
        gpuMark('init:ok');
        gpu=svc; gpuState=2; gpuInitFails=0;
        setGpuStatus();
        return gpu;
      }catch(e){
        // v2.2：初始化失败（多为重建时显存暂时不足）不立即永久禁用，允许再试一次；
        // 连续 2 次失败才认定 GPU 不可用，避免偶发 OOM 让整场退化成 CPU 跑几小时
        var im=(e&&(e.message||e))?String(e.message||e):'未知错误';
        console.warn('GPU OCR 不可用，已回退内置引擎：',e);
        gpu=null; gpuP=null; gpuInitFails=(gpuInitFails||0)+1; gpuMark('init:fail:'+im.slice(0,40));
        if(gpuInitFails>=2){
          gpuState=3; setEngStatus('cpu','CPU · 内置 Tesseract（GPU 初始化失败：'+im.slice(0,28)+'）');
        }else{
          gpuState=0; setEngStatus('check','GPU 初始化失败，稍后自动重试…');
        }
        return null;
      }
    })();
    return gpuP;
  }
  // v2.2：单张推理与批识别共用同一条串行队列与降级策略（不再"一次异常即永久禁用"）
  function gpuRecognize(canvas){
    return gpuInit().then(function(svc){
      if(!svc) return null;
      var ms=120000; // 单页上限：密集表格页可到 20s，留足余量
      if(gpuState===3) return null;
      // v2.3：gpuQueue 保证排队；超时只影响调用方，底层 run 仍会被串行链等待
      var raw=gpuQueue(function(){
        if(gpuState===3) throw new Error('GPU 已禁用');
        return svc.recognize(canvas);
      });
      return withTimeout(raw, ms, 'GPU识别').then(function(r){
        gpuBatchOk();
        return normTxt((r&&r.text&&String(r.text))||'');
      }).catch(function(e){ return gpuBatchFail(e); });
    });
  }
  // v2提速：批识别入口。batchRecognize 并发 2-3，settle 吸收单项失败；
  // 返回按输入顺序对齐的文本数组（失败项为 null），页映射 1:1。
  function gpuRecognizeBatch(canvases, concurrency){
    return gpuInit().then(function(svc){
      if(!svc) return null;
      // v3加固：首次推理前提示 shader 编译可能耗时（真机首帧可达数秒~数十秒）
      if(!gpuCompiledWarn){ gpuCompiledWarn=true; setEngStatus('check','GPU 首次编译着色器，可能需数秒…'); }
      // v2.2：超时按页数自适应（基线 60s + 每页 60s）。真机密集表格/扫描页单页 15~20s，
      // 固定 90s 会让正常的 6 页批被判超时并永久禁用 GPU——这正是"跑一会就变 CPU"的元凶。
      var ms=60000 + canvases.length*60000;
      if(gpuState===3) return null; // GPU 已失效，短路
      gpuMark('rec:start');
      // v2.2：识别期间每秒刷新状态栏（页数 + 已用时）。模型首次编译可达数十秒，
      // 没有这个心跳，界面会长时间停在"首次编译着色器"上，用户无法区分"在跑"还是"卡死"。
      var tickT0=Date.now(), tick=setInterval(function(){
        if(gpuState===3) return;
        var s=Math.round((Date.now()-tickT0)/1000);
        setEngStatus('check','GPU 识别中（'+canvases.length+' 页 · 已用 '+s+'s'
          +(s>=90?'，本批较慢，超时后会自动降批重试':'')+'）');
      }, 1000);
      // v2.3：入串行队列（调用即占位），底层 run 完成前不会有第二个批进入同一会话
      var raw=gpuQueue(function(){
        if(gpuState===3) throw new Error('GPU 已禁用');
        return svc.batchRecognize(canvases,{concurrency:concurrency,settle:true});
      });
      return withTimeout(raw, ms, 'GPU批识别')
        .then(function(res){
          clearInterval(tick);
          gpuMark('rec:ok');
          // v3加固：批内失败检测——settle 会吞掉 Session already started 等引擎错误，
          // 若不主动检测，工具会继续用状态错乱的会话跑后续每一块（每块全失败+回退内置，页面假死）
          var bad=0, emptyN=0;
          res.forEach(function(it){
            if(!it||it.status!=='fulfilled') bad++;
            else if(!it.value||!it.value.text||!normTxt(it.value.text)) emptyN++;
          });
          if(bad>0){
            var bmsg='批内有 '+bad+'/'+res.length+' 项异常';
            if(bad<res.length){
              // v2.2：部分失败仍保留成功项（失败项由上层逐个回退内置），只降批不重置会话
              console.warn('GPU 批内部分失败：'+bmsg);
              gpuBatchLimit=Math.max(1, Math.floor(gpuBatchLimit/2)); gpuOkStreak=0;
              if(window.__ocrPerf__) window.__ocrPerf__.gpuBatchLimit=gpuBatchLimit;
            }else{
              return gpuBatchFail(new Error(bmsg+'（Session already started 等）'));
            }
          }
          // v2.1：全 fulfilled 空文本（无错误 reason）= 无内容页，属正常，不触发禁用；
          // 仅当连续 2 块空文本率 >70% 时才视为引擎静默空转并降级（原有防御保留）
          if(res.length>=4 && emptyN/res.length>0.7){
            gpuFailStreak++;
            if(gpuFailStreak>=2) return gpuBatchFail(new Error('连续批空文本率过高'));
          }else if(res.length>=4){ gpuFailStreak=0; }
          gpuBatchOk();
          return res.map(function(it){
            if(!it||it.status!=='fulfilled'||!it.value||!it.value.text) return null;
            return normTxt(it.value.text);
          });
        })
        .catch(function(e){ clearInterval(tick); return gpuBatchFail(e); });
    });
  }
  // v2提速：内置 Tesseract 池批识别（GPU 不可用/显式选内置时走此路）