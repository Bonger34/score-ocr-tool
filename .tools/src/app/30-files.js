
  // ---------- 上传 ----------
  $('file').addEventListener('change',function(){ if(this.files.length) onFiles(this.files,true); }); // v2.5：追加而非替换
  var drop=$('drop');
  ['dragenter','dragover'].forEach(function(ev){drop.addEventListener(ev,function(e){e.preventDefault();drop.classList.add('hover');});});
  ['dragleave','drop'].forEach(function(ev){drop.addEventListener(ev,function(e){e.preventDefault();drop.classList.remove('hover');});});
  drop.addEventListener('drop',function(e){e.preventDefault();drop.classList.remove('hover');if(e.dataTransfer.files.length)onFiles(e.dataTransfer.files,true);}); // v2.5：追加
  function fmtSize(b){
    if(!b) return '';
    var u=['B','KB','MB','GB'], i=0;
    while(b>=1024&&i<u.length-1){ b/=1024; i++; }
    return (i===0?b:Math.round(b*10)/10)+' '+u[i];
  }
  // v2.5：再次选择/拖入时"追加"而不是替换（文案写的是"继续添加文件"，行为必须一致）
  function onFiles(fs, append){
    var list=[];
    if(append&&uploadedFiles) list=[].slice.call(uploadedFiles);
    for(var k=0;k<fs.length;k++){
      var f=fs[k], dup=false;
      for(var j=0;j<list.length;j++){
        if(list[j].name===f.name&&list[j].size===f.size&&list[j].lastModified===f.lastModified){ dup=true; break; }
      }
      if(!dup) list.push(f);
    }
    uploadedFiles=list;
    $('runBtn').disabled=false;
    var n=list.length, bytes=0;
    for(var i=0;i<n;i++) bytes+=(list[i]&&list[i].size)||0;
    // v2.5：选完文件后给出"选了什么"的确认，并提供清空
    var meta=$('fileMeta'), wrap=$('fileMetaWrap');
    if(meta) meta.textContent='已选 '+n+' 个文件'+(bytes?'（'+fmtSize(bytes)+'）':'');
    if(wrap) wrap.style.display='flex';
    var dp=$('drop'); if(dp) dp.classList.add('compact');   // v2.5：已选文件后拖放区收成一条，把纵向空间还给结果
    $('status').textContent='点「开始解析」开始查找。';
    $('announce').textContent='已选 '+n+' 个文件';
  }
  function clearFiles(){
    uploadedFiles=null; matched=[]; lastBlob=null;
    var f=$('file'); if(f) f.value='';
    var wrap=$('fileMetaWrap'); if(wrap) wrap.style.display='none';
    var dp=$('drop'); if(dp) dp.classList.remove('compact');
    $('runBtn').disabled=true;
    $('resultCard').style.display='none';
    $('status').textContent='先放入名单文件，再点「开始解析」。';
    $('announce').textContent='已清空已选文件';
  }
