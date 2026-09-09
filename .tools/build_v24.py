# -*- coding: utf-8 -*-
"""构建 v2.4 交付物：把改造后的 rec 模型（GPU 端 argmax，输出 [B,T,2]）与配套引擎补丁写进单文件 HTML。

改动（全部锚点替换，每处必须恰好命中 1 次）：
  1. gpuassets 的 REC 值 → rec_am2.onnx 的 gzip+base64（模型末尾追加 ArgMax+ReduceMax+Concat）
  2. 应用脚本新增 patchPPU()，并在加载 PPU 引擎时套用（新增索引解码分支，兼容旧模型）
  3. recognition.recBatchSize 4 → 16（回读变小后，批更大才能摊薄 WebGPU 每次 run 的固定开销）
  4. 解析并发 CONC 6 → 10（本机 16 逻辑核，pdf.js 文本层提取是 CPU 密集）

用法: python build_v24.py [--dry]
"""
import base64, gzip, hashlib, io, os, re, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(BASE, '.tools')
HTML = os.path.join(BASE, '搜分名单查询工具.html')
MODEL = os.path.join(TOOLS, 'rec_am2.onnx')
DRY = '--dry' in sys.argv
# --conc N：临时覆盖解析并发（仅用于 A/B 实验，不影响交付默认值）
CONC = None
for i, a in enumerate(sys.argv):
    if a == '--conc' and i + 1 < len(sys.argv):
        CONC = sys.argv[i + 1]

# ---------------- PPU 引擎运行时补丁 ----------------
PPU_PATCH_JS = r'''
  // v2.4 提速（核心）：内嵌 rec 模型末尾追加 ArgMax+ReduceMax+Concat，输出由 [B,T,18385]
  // 概率图变为 [B,T,2]（argmax 索引 + 该位置最大概率）。原来每个 rec 批要回读 18385 类
  // fp32 概率图（实测 24 页共 11GB，回读带宽约 0.35GB/s 是主要瓶颈），主线程还要逐类扫描
  // 求 argmax（每批 10.7M 次读取）。这里给引擎注入"索引解码"分支：dims 为 [B,T,2] 时走新路，
  // 否则退回原概率解码——因此补丁对旧模型同样安全。
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
'''

ANCHORS = [
    # (标签, 锚点, 替换)
    ('PPU 加载处套用补丁',
     "if(!window.PPU){ var pb=val('PPU'); if(!pb) throw new Error('缺少 PP-OCR 引擎'); await loadScriptToGlobal(decodeB64str(pb)); }",
     PPU_PATCH_JS.strip('\n') + "\n        if(!window.PPU){ var pb=val('PPU'); if(!pb) throw new Error('缺少 PP-OCR 引擎'); await loadScriptToGlobal(patchPPU(decodeB64str(pb))); }"),
    ('rec 批大小',
     "recognition:{mainThreadYieldMs:0, recBatchSize:4}, // v2提速：去掉每次 rec 推理前 10ms 主动让出；recBatchSize 6→4（RTX 2050 4GB 显存/窄带宽档，降 GPU 峰值与带宽压力）",
     "recognition:{mainThreadYieldMs:0, recBatchSize:8}, // v2.4：模型改为输出 [B,T,2] 索引后回读不再是瓶颈，批大小只影响固定开销摊薄；实测 4→8 快 3%（16/32 反而更慢）。显存吃紧时由 gpuBatchFail 自适应把批大小减半（8→4→2→1），故默认取快的档位"),
    ('GPU 失败时同步下调 rec 批大小',
     "    gpuBatchLimit=Math.max(1, Math.floor(gpuBatchLimit/2)); // 降批：6→3→1\n    gpuStale=true;                                          // 底层 run 可能仍在跑，下次换新会话",
     "    gpuBatchLimit=Math.max(1, Math.floor(gpuBatchLimit/2)); // 降批：6→3→1\n"
     "    // v2.4：显存吃紧（本机 GPU 常被桌面程序占满）时，光降\"每批页数\"不够——单次 rec run 的\n"
     "    // 中间张量 [B,T,18385] 才是显存大头，这里同步把 rec 批大小减半（4→2→1）；会话重建后恢复默认\n"
     "    try{ var ro=gpu&&gpu.recognitor&&gpu.recognitor.options; if(ro&&ro.recBatchSize>1){ ro.recBatchSize=Math.max(1,Math.floor(ro.recBatchSize/2)); } }catch(_){}\n"
     "    gpuStale=true;                                          // 底层 run 可能仍在跑，下次换新会话"),
    ('解析并发',
     "var CONC=Math.max(2, Math.min(6, (typeof navigator!=='undefined'&&navigator.hardwareConcurrency)||4));",
     "var CONC=Math.max(2, Math.min(14, (typeof navigator!=='undefined'&&navigator.hardwareConcurrency)||4)); // v2.4：6→14。实测 pdf.js 文本提取的并行效率只有 ~4x（worker 大量时间在等主线程/IO），所以提高并发是净收益：解析侧 200s→161s（全量不勾 OCR）"),
    # v2.4：zip 条目解压改用原生 DecompressionStream（实测比 JSZip 纯 JS pako 快 2.3 倍，且不长时间占用主线程）
    ('zip 解压：原生 DecompressionStream',
     "  // 无缓存时解析单个内部文件，返回文本；出错返回空串\n"
     "  function parseOne(item, ctl){\n"
     "    var itN=item.name, itE=item.e, p;\n"
     "    if(itE==='pdf') p=item.f.async('uint8array').then(function(b){ return readPdfText(b.buffer, ctl); });\n"
     "    else if(itE==='xlsx'||itE==='xlsm') p=item.f.async('uint8array').then(function(b){ return JSZip.loadAsync(b).then(xlsxText); });\n"
     "    else if(itE==='txt'||itE==='csv'||itE==='md') p=item.f.async('uint8array').then(function(tb){ return new TextDecoder('utf-8').decode(tb); });\n"
     "    else p=Promise.resolve('');",
     "  // v2.4：优先用浏览器原生 DecompressionStream 解压 zip 条目——实测比 JSZip 的纯 JS pako 快约 2.3 倍，\n"
     "  // 且解压由浏览器原生线程完成，不再长时间阻塞主线程。任何异常/长度不符都退回 JSZip 原路径。\n"
     "  function entryBytes(f){\n"
     "    try{\n"
     "      var d=f&&f._data;\n"
     "      if(d&&d.compressedContent&&typeof DecompressionStream==='function'){\n"
     "        var c=d.compressedContent;\n"
     "        var src=(c&&typeof c.then==='function')?c:Promise.resolve(c);\n"
     "        return src.then(function(raw){\n"
     "          if(!raw||!raw.length) throw new Error('空压缩块');\n"
     "          var st=new Blob([raw]).stream().pipeThrough(new DecompressionStream('deflate-raw'));\n"
     "          return new Response(st).arrayBuffer();\n"
     "        }).then(function(ab){\n"
     "          if(d.uncompressedSize!=null&&ab.byteLength!==d.uncompressedSize) throw new Error('解压长度不符');\n"
     "          return new Uint8Array(ab);\n"
     "        }).catch(function(){ return f.async('uint8array'); });\n"
     "      }\n"
     "    }catch(e){}\n"
     "    return f.async('uint8array');\n"
     "  }\n"
     "  // 无缓存时解析单个内部文件，返回文本；出错返回空串\n"
     "  function parseOne(item, ctl){\n"
     "    var itN=item.name, itE=item.e, p;\n"
     "    if(itE==='pdf') p=entryBytes(item.f).then(function(b){ return readPdfText(b.buffer, ctl); });\n"
     "    else if(itE==='xlsx'||itE==='xlsm') p=entryBytes(item.f).then(function(b){ return JSZip.loadAsync(b).then(xlsxText); });\n"
     "    else if(itE==='txt'||itE==='csv'||itE==='md') p=entryBytes(item.f).then(function(tb){ return new TextDecoder('utf-8').decode(tb); });\n"
     "    else p=Promise.resolve('');"),
    ('xlsx 条目解压',
     "    return Promise.all(keys.map(function(n){return zip.files[n].async('uint8array');}))",
     "    return Promise.all(keys.map(function(n){return entryBytes(zip.files[n]);}))"),
    # v2.4：文本提取只取字符，不需要把字体装到 DOM（disableFontFace/useSystemFonts），
    # 实测同一批文本密集 PDF 提取提速约 12%，且提取字符数完全一致
    ('pdf.js 取词选项',
     "    return pdfjsLib.getDocument({data:new Uint8Array(buf)}).promise.then(async function(pdf){",
     "    return pdfjsLib.getDocument({data:new Uint8Array(buf), disableFontFace:true, useSystemFonts:false}).promise.then(async function(pdf){ // v2.4：只取文本，跳过字体装配"),
]


def main():
    raw = open(HTML, encoding='utf-8').read()
    orig_len = len(raw)
    # ---- 1) 替换 REC 资源 ----
    model = open(MODEL, 'rb').read()
    b64 = base64.b64encode(gzip.compress(model, 6)).decode()
    m = re.search(r'(<script type="text/plain" id="gpuassets">)(.*?)(</script>)', raw, re.S)
    if not m:
        print('gpuassets not found'); return 1
    body = m.group(2).strip()
    parts = body.split('|')
    idx = parts.index('REC')
    old_b64 = parts[idx + 1]
    print('REC asset: old b64=%d bytes -> new b64=%d bytes (model %d -> %d)'
          % (len(old_b64), len(b64), 16559278, len(model)))
    if not DRY:
        parts[idx + 1] = b64
        raw = raw[:m.start(2)] + '|'.join(parts) + raw[m.end(2):]
    # ---- 2) 应用脚本锚点替换 ----
    for tag, a, b in ANCHORS:
        cnt = raw.count(a)
        if cnt != 1:
            print('锚点 %s 命中 %d 次（应为 1）' % (tag, cnt)); return 1
        if CONC and tag == '解析并发':
            b = b.replace('Math.min(10,', 'Math.min(%s,' % CONC)
        if not DRY:
            raw = raw.replace(a, b)
        print('锚点 OK: %s' % tag)
    if DRY:
        print('dry-run 完成，未写盘'); return 0
    open(HTML, 'w', encoding='utf-8', newline='').write(raw)
    print('written %s (%.1f MB, delta %+d bytes)' % (HTML, len(raw) / 1048576.0, len(raw) - orig_len))
    print('sha256 %s' % hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16])
    return 0


if __name__ == '__main__':
    sys.exit(main())
