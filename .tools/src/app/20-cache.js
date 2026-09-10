
  // ---------- 性能优化：可持久化提取文本缓存（IndexedDB + 内存双级） ----------
  // 同一文件（路径+大小+时间戳）二次检索不再重新解析 PDF，大幅加速"换关键词再查"与重复扫描。
  var TEXT_CACHE_VER='v5'; // v5：v2.1 命中修复——OCR 文本改为保留空格/换行（形态变化令旧缓存失效）；v4 空白页判定亦含
  var textCache={_m:{},_db:null,_ready:null,stats:{hit:0,miss:0}};
  function cacheOpen(){
    if(textCache._db) return Promise.resolve(textCache._db);
    if(textCache._ready) return textCache._ready;
    textCache._ready=new Promise(function(resolve){
      try{
        var rq=indexedDB.open('bonus_text_cache',2);
        rq.onupgradeneeded=function(){ var db=rq.result; if(db&&!db.objectStoreNames.contains('t')) db.createObjectStore('t',{keyPath:'k'}); };
        rq.onsuccess=function(){
          var db=rq.result||null;
          if(db&&!db.objectStoreNames.contains('t')){
            // v2加固：库已存在但缺 't' 存储（外部残留/旧版破损）→ 本次会话禁用缓存，OCR 照常执行
            console.warn('文本缓存库结构异常（缺 t 存储），本次会话禁用缓存，不影响识别');
            textCache._db=false; resolve(false); return;
          }
          textCache._db=db; resolve(db);
        };
        rq.onerror=function(){ textCache._db=null; textCache._ready=null; resolve(null); };
      }catch(e){ resolve(null); }
    });
    return textCache._ready;
  }
  // 缓存键按 OCR 开关分流：勾选 OCR 与不勾选走两套命名空间，避免"先省OCR再补OCR"时命中空缓存漏识别
  function cacheMode(){ return ($('ocr')&&$('ocr').checked)?'o':'n'; }
  function directKey(f){ return TEXT_CACHE_VER+'|'+cacheMode()+'|f|'+(f.webkitRelativePath||f.name||'')+'|'+f.size+'|'+f.lastModified; }
  function zipItemKey(it){ var F=it.f; return TEXT_CACHE_VER+'|'+cacheMode()+'|z|'+it.name+'|'+((F&&F._data&&F._data.uncompressedSize)||'')+'|'+((F&&F.date&&F.date.getTime())||''); }
  function cacheGet(key){
    var m=textCache._m;
    if(Object.prototype.hasOwnProperty.call(m,key)) return Promise.resolve({text:m[key]});
    return cacheOpen().then(function(db){
      if(!db) return null;
      try{
        return new Promise(function(res){
          var rq=db.transaction('t','readonly').objectStore('t').get(key);
          rq.onsuccess=function(){ if(rq.result){ m[key]=rq.result.v; res({text:rq.result.v}); } else res(null); };
          rq.onerror=function(){ res(null); };
        });
      }catch(e){
        // v2加固：存储异常按未命中处理（走解析），并丢弃坏连接让下次重开
        textCache._db=null; textCache._ready=null; return null;
      }
    });
  }
  function cachePut(key,text){
    try{ textCache._m[key]=text; }catch(e){}
    return cacheOpen().then(function(db){
      if(!db) return;
      try{ db.transaction('t','readwrite').objectStore('t').put({k:key,v:text}); }catch(e){}
    });
  }
  // 命中缓存直接返回；否则执行 parseFn 解析并写缓存。
  // 返回 {text, hit}：hit=true 表示未实际执行解析（未产生页级步进），调用方据此补足任务计数，保证 done≤total
  function cachedText(key, parseFn){
    return cacheGet(key).then(function(hit){
      if(hit){ textCache.stats.hit++; return {text:hit.text, hit:true}; }
      textCache.stats.miss++;
      return Promise.resolve().then(parseFn).then(function(t){ if(key!=null) cachePut(key,t); return {text:t, hit:false}; });
    });
  }
