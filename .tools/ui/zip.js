  // v2.8：按综测报送格式导出材料包（zip）。目录：学号姓名 / 五育测评 / +分值 (事由).<原扩展名>
  // 说明：工具手里是"加分名单原件"，不是学生的证明材料——包里放的是命中的名单文件。
  // 同一份名单里某人有多条加分项时，会按每个加分项各放一份到对应的五育目录（格式要求一项一文件）。
  // 内存策略：只记 {来源文件, zip 内路径}，导出时才按文件逐个取字节，包体不常驻。
  var YU_DIR={'德育':'德育测评','智育':'智育测评','体育':'体育测评','美育':'美育测评','劳育':'劳育测评'};
  var ZIP_CAP=300*1024*1024;      // 材料包体积上限：超过就提示先精确检索（模糊检索容易命中上百份名单）
  var zipCache=new Map();

  function safeName(s,n){
    var t=String(s==null?'':s).replace(/[\\/:*?"<>|\r\n\t]+/g,'_').replace(/\s+/g,' ').trim();
    t=t.replace(/[. ]+$/,'');            // Windows 不允许文件名/目录名以点或空格结尾
    return t.slice(0,n||80)||'未命名';
  }
  function splitExt(p){
    var m=/\.([A-Za-z0-9]{1,5})$/.exec(String(p||''));
    return m?{stem:String(p).slice(0,m.index), ext:m[0]}:{stem:String(p||''), ext:''};
  }
  function personDir(p,kw){ return safeName((p.sid||'未标学号')+kw,60); }
  function yuDir(t){ return YU_DIR[t]||'未识别'; }
  // 命名：原文件名保持不变，只在最前面加上分值（截断只截名字，不截扩展名）
  function itemFile(it){
    var v=(it.val===null||it.val===undefined)?'未识别分值':itemStr(it.val);
    var base=String(it.src||'').split(/[\\/]/).pop();
    var se=splitExt(base);
    return safeName(v+' '+se.stem,96)+se.ext;
  }
  // 按来源文件缓存已加载的 zip：同一份名单含多人时只解一次
  function loadSrcZip(file){
    if(zipCache.has(file)) return zipCache.get(file);
    var pr=file.arrayBuffer().then(function(b){ return JSZip.loadAsync(new Uint8Array(b)); });
    zipCache.set(file,pr);
    return pr;
  }
  function bytesOf(ref){
    if(!ref||!ref.file) return Promise.resolve(null);
    if(!ref.path) return ref.file.arrayBuffer().then(function(b){ return new Uint8Array(b); });
    return loadSrcZip(ref.file).then(function(z){
      var f=z.file(ref.path);
      return f?f.async('uint8array'):null;
    });
  }
  function zipReadme(people,kw,n){
    return ['综测加分材料包（按报送格式生成）','',
      '检索词：'+kw+'    人数：'+people.length+'    加分项：'+n,
      '',
      '目录结构：学号姓名 / 五育测评 / 分值 + 原文件名（文件名保持原样，只在最前面加分值）',
      '包内每个文件都是命中的【加分名单原件】，不是学生的证明材料；',
      '同一份名单里某人有多条加分项时，会按每个加分项各放一份到对应的五育目录。',
      '若需要"班级"这一层（如 24级计科（专）1班/），请自行在外层再套一层目录。',
      '',
      '上限提醒（闽农大金山学〔2025〕26 号）：德育奖励分超出 25 分按 25 分计；',
      '同一学年智育奖励分累计不超过 10 分。',
      ''].join('\r\n');
  }
  function zipCsv(tasks,kw){
    var q=function(c){ return '"'+String(c==null?'':c).replace(/"/g,'""')+'"'; };
    var rows=[['学号','姓名','五育','加分值','事由','材料文件名','来源名单文件']];
    tasks.forEach(function(tk){
      rows.push([tk.p.sid||'未标学号', kw, tk.t==='未标注'?'未识别':tk.t,
                 (tk.it.val===null?'':itemStr(tk.it.val)), tk.it.why||'', tk.nm, tk.it.src||'']);
    });
    return '\ufeff'+rows.map(function(r){ return r.map(q).join(','); }).join('\r\n')+'\r\n';
  }

  async function exportMaterialZip(){
    var st=lastStats||{}, people=st.people||[], kw=st.kw||'';
    var btn=$('dlzip'), stEl=$('status'), anEl=$('announce');
    if(!people.length) return false;

    // 1) 摊平任务并定名（CSV 与包内路径共用同一套名字，重名加序号）
    var tasks=[], est=0, used={};
    people.forEach(function(p){
      YU.concat(['未标注']).forEach(function(t){
        p.items.filter(function(it){ return it.yu===t; }).forEach(function(it){
          var dir=personDir(p,kw)+'/'+yuDir(t)+'/', base=itemFile(it), nm=base, seq=1;
          while(used[dir+nm]){ seq++; nm=base.replace(/(\.[^.]*)?$/, ' ('+seq+')$1'); }
          used[dir+nm]=1;
          est+=(it.size||0);
          tasks.push({p:p, it:it, t:t, dir:dir, nm:nm});
        });
      });
    });
    if(!tasks.length) return false;
    if(est>ZIP_CAP){
      var mb=est/1048576;
      var sizeTxt=(mb>=1024)?(Math.round(mb/102.4)/10)+' GB':Math.round(mb)+' MB';
      var msg='材料包约 '+sizeTxt+'（每个加分项都要放一份来源名单，同一名单会重复复制），超过 '
              +Math.round(ZIP_CAP/1048576)+' MB 上限——请先用姓名精确检索再导出。';
      if(stEl) stEl.textContent=msg;
      if(anEl) anEl.textContent=msg;
      return false;
    }

    if(btn) btn.disabled=true;
    if(stEl) stEl.textContent='正在打包 0/'+tasks.length+' …';
    try{
      zipCache.clear();
      var pkg=new JSZip();
      pkg.file('说明.txt', zipReadme(people,kw,tasks.length));
      pkg.file('清单.csv', zipCsv(tasks,kw));
      for(var i=0;i<tasks.length;i++){
        var tk=tasks[i], b=null, why='';
        if(!tk.it.srcRef) why='该记录没有来源文件引用（可能来自旧版缓存或解析异常）';
        else{
          try{ b=await bytesOf(tk.it.srcRef); }catch(e){ b=null; why=String((e&&e.message)||e); }
          if(!b&&!why) why='来源文件取到空内容';
        }
        if(b) pkg.file(tk.dir+tk.nm, b);
        else pkg.file(tk.dir+tk.nm+'.取不到来源.txt',
                     '未能取到来源文件：'+(tk.it.src||'')+'\r\n原因：'+why
                     +'\r\n分值：'+itemStr(tk.it.val)+'\r\n事由：'+(tk.it.why||'')+'\r\n');
        if(stEl&&(i+1)%5===0) stEl.textContent='正在打包 '+(i+1)+'/'+tasks.length+' …';
      }
      var blob=await pkg.generateAsync({type:'blob', compression:'STORE'});  // 名单多为已压缩 PDF，再压一遍不划算
      var u=URL.createObjectURL(blob), a=document.createElement('a');
      a.href=u; a.download='综测加分材料包.zip'; a.type='application/zip';
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(function(){ URL.revokeObjectURL(u); },2000);
      var ok='材料包已生成：'+tasks.length+' 个文件 · '+(Math.round(blob.size/104857.6)/10)+' MB';
      if(stEl) stEl.textContent=ok;
      if(anEl) anEl.textContent=ok;
    }catch(e){
      var bad='材料包生成失败：'+((e&&e.message)||e);
      if(stEl) stEl.textContent=bad;
      if(anEl) anEl.textContent=bad;
    }finally{
      zipCache.clear();
      if(btn) btn.disabled=false;
    }
    return false;
  }
  window.exportMaterialZip=exportMaterialZip;   // 内联 onclick 在全局作用域，必须挂到 window
