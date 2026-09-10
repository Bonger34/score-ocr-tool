
  // ---------- 持续填充的并发池：限制并发但让任务不间断地启动，使 PDF worker 满载、不整批空转 ----------
  function mapLimit(items, limit, fn){
    var out=new Array(items.length), cursor=0, running=0, finished=0;
    return new Promise(function(resolve,reject){
      if(!items.length){ resolve(out); return; }
      var settled=false;
      function pump(){
        while(running<limit && cursor<items.length && !settled){
          (function(idx){ running++;
            Promise.resolve().then(function(){ return fn(items[idx], idx); })
              .then(function(r){ out[idx]=r; running--; finished++; if(finished===items.length) resolve(out); else pump(); },
                    function(e){ if(!settled){ settled=true; reject(e); } });
          })(cursor++);
        }
      }
      pump();
    });
  }

  async function extractEntries(file, ctl){
    // 返回 [{name, text}]：直接选择的文件各占一条；zip 则按内部文件逐一产出
    // ctl 为进度回调对象：{add(n):调整总解析单元数, step(label):完成一个单元}
    var nm=file.name||file.path||'', e=ext(nm), buf=await file.arrayBuffer();
    if(e==='pdf'){
      // 命中缓存则跳过解析；否则解析并写入缓存
      var k=directKey(file);
      var tRes=await cachedText(k, function(){ return readPdfText(buf, ctl); });
      // 命中缓存时 readPdfText 未执行页级步进，需补 1 个完成单元（该文件以 1 单元计数）
      var t=tRes.text;
      if(tRes.hit && ctl) ctl.step(nm);
      return [{name:nm, text:t, src:{file:file}, size:file.size||0}];
    }
    if(e==='xlsx'||e==='xlsm'){
      var z0=await JSZip.loadAsync(new Uint8Array(buf));
      var k2=directKey(file);
      var tRes2=await cachedText(k2, function(){ return xlsxText(z0); });
      var t2=tRes2.text;
      if(ctl) ctl.step(nm); // xlsx 每次均按 1 单元跳进一次
      return [{name:nm, text:t2, src:{file:file}, size:file.size||0}];
    }
    if(e==='zip'){
      var z=await JSZip.loadAsync(new Uint8Array(buf));
      var inner=[];
      Object.keys(z.files).forEach(function(n){
        var f=z.files[n];
        if(f.dir||n.indexOf('__MACOSX')>=0) return;
        inner.push({name:n, f:f, e:ext(n), size:(f&&f._data&&f._data.uncompressedSize)||0});
      });
      if(ctl&&inner.length>1){
        // v2.6：内部文件按各自体积估工作量（zip 中央目录里有 uncompressedSize）。
        // 原来一律按 150ms 记，一个 285MB 的 zip 里大小文件能差几个数量级，进度条会失真
        var innerMs=0;
        inner.forEach(function(it){ innerMs+=predMs(it.size); });
        ctl.add(inner.length-1,'file',innerMs);
      }
      // 用持续并发池并行解析，不再按固定批次整批等待，让 PDF worker 始终满载
      var CONC=Math.max(2, Math.min(14, (typeof navigator!=='undefined'&&navigator.hardwareConcurrency)||4)); // v2.4：6→14。实测 pdf.js 文本提取的并行效率只有 ~4x（worker 大量时间在等主线程/IO），所以提高并发是净收益：解析侧 200s→161s（全量不勾 OCR）
      var parsed=await mapLimit(inner, CONC, function(item){
        return (async function(){
          var itN=item.name;
          var k3=zipItemKey(item);
          var r3=await cachedText(k3, function(){ return parseOne(item, ctl); }); // 命中缓存即刻返回，无解析
          var t3=r3.text;
          // 已发生页级步进的 PDF（未命中缓存、readPdfText 内部按页步进）不再额外计数；
          // 非 PDF 或命中缓存的 PDF 均只按 1 单元补一次，避免 done 溢出 total
          var pdfFresh=(item.e==='pdf'&&!r3.hit);
          if(ctl&&!pdfFresh) ctl.step(itN);
          return {name:itN, text:t3, src:{file:file, path:item.name}, size:(item.f&&item.f._data&&item.f._data.uncompressedSize)||0};
        })();
      });
      return parsed;
    }
    if(ctl) ctl.step(nm);
    return [{name:nm, text:new TextDecoder('utf-8').decode(buf), src:{file:file}, size:file.size||0}];
  }
  // v2.4：优先用浏览器原生 DecompressionStream 解压 zip 条目——实测比 JSZip 的纯 JS pako 快约 2.3 倍，
  // 且解压由浏览器原生线程完成，不再长时间阻塞主线程。任何异常/长度不符都退回 JSZip 原路径。
  function entryBytes(f){
    try{
      var d=f&&f._data;
      if(d&&d.compressedContent&&typeof DecompressionStream==='function'){
        var c=d.compressedContent;
        var src=(c&&typeof c.then==='function')?c:Promise.resolve(c);
        return src.then(function(raw){
          if(!raw||!raw.length) throw new Error('空压缩块');
          var st=new Blob([raw]).stream().pipeThrough(new DecompressionStream('deflate-raw'));
          return new Response(st).arrayBuffer();
        }).then(function(ab){
          if(d.uncompressedSize!=null&&ab.byteLength!==d.uncompressedSize) throw new Error('解压长度不符');
          return new Uint8Array(ab);
        }).catch(function(){ return f.async('uint8array'); });
      }
    }catch(e){}
    return f.async('uint8array');
  }
  // 无缓存时解析单个内部文件，返回文本；出错返回空串
  function parseOne(item, ctl){
    var itN=item.name, itE=item.e, p;
    if(itE==='pdf') p=entryBytes(item.f).then(function(b){ return readPdfText(b.buffer, ctl); });
    else if(itE==='xlsx'||itE==='xlsm') p=entryBytes(item.f).then(function(b){ return JSZip.loadAsync(b).then(xlsxText); });
    else if(itE==='txt'||itE==='csv'||itE==='md') p=entryBytes(item.f).then(function(tb){ return new TextDecoder('utf-8').decode(tb); });
    else p=Promise.resolve('');
    return p.then(function(x){ return x; }, function(err){ console.warn('解析失败',itN,err); return ''; });
  }
