
  // ---------- 导出 .xlsx（用 JSZip 本地构造） ----------
  var lastStats=null;   // 由 render() 写入，导出时复用，保证清单与 Excel 完全一致
  function setupDownload(keep,removed,doDedup){
    var st=lastStats||{}, sums=st.sums||{}, cnts=st.cnts||{};
    var total=st.total||0, cntTotal=st.totalCnt||0;
    var people=st.people||[], kw=st.kw||'';
    var xm={};
    xm['[Content_Types].xml']='<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'+
      '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'+
      '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'+
      '<Default Extension="xml" ContentType="application/xml"/>'+
      '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'+
      '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'+
      '<Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'+
      '</Types>';
    xm['_rels/.rels']='<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'+
      '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'+
      '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'+
      '</Relationships>';
    xm['xl/workbook.xml']='<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'+
      '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'+
      '<sheets><sheet name="加分证明清单" sheetId="1" r:id="rId1"/><sheet name="五育汇总" sheetId="2" r:id="rId2"/></sheets></workbook>';
    xm['xl/_rels/workbook.xml.rels']='<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'+
      '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'+
      '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'+
      '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/>'+
      '</Relationships>';

    function cell(v,ref){ var t='<c r="'+ref+'"><v>'+v+'</v></c>'; return t; }
    function scell(v,ref){ return '<c r="'+ref+'" t="inlineStr"><is><t xml:space="preserve">'+esc(String(v))+'</t></is></c>'; }
    function num(v,ref){ return (v===''||v===null)?'<c r="'+ref+'"/>':'<c r="'+ref+'"><v>'+v+'</v></c>'; }

    // 列号：列数固定小于 26，够用
    function colRef(i){ return String.fromCharCode(65+i); }
    function rowOf(cells){ return '<row r="'+r+'">'+cells.join('')+'</row>'; }

    // Sheet1 加分证明清单：一行一个加分项，按 人 → 五育 排序，便于在 Excel 里筛选与逐项核对
    var head1=['序号','学号','姓名','五育','加分值','事由','来源文件'];
    var rows='<row r="1">'+head1.map(function(c,i){ return scell(c,colRef(i)+'1'); }).join('')+'</row>';
    var r=2;
    people.forEach(function(p){
      YU.concat(['未标注']).forEach(function(t){
        p.items.filter(function(it){ return it.yu===t; }).forEach(function(it){
          rows+='<row r="'+r+'">'+num(r-1,'A'+r)+scell(p.sid||'—','B'+r)+scell(kw,'C'+r)+
                scell(t,'D'+r)+num(it.val===null?'':it.val,'E'+r)+scell(it.why,'F'+r)+scell(it.src,'G'+r)+'</row>';
          r++;
        });
      });
    });
    xm['xl/worksheets/sheet1.xml']='<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'+rows+'</sheetData></worksheet>';

    // Sheet2 五育汇总：一行一人、五育各一列，直接对着综测计分表抄
    var head2=['学号','姓名'].concat(YU).concat(['合计']);
    var r2=2, rows2='<row r="1">'+head2.map(function(c,i){ return scell(c,colRef(i)+'1'); }).join('')+'</row>';
    var gsum={}, gall=0;
    people.forEach(function(p){
      var pt=0, line=[scell(p.sid||'—','A'+r2), scell(kw,'B'+r2)];
      YU.forEach(function(t,i){
        var v=p.sums[t]||0; pt+=v; gsum[t]=(gsum[t]||0)+v;
        line.push(num(v,colRef(2+i)+r2));
      });
      line.push(num(pt,colRef(2+YU.length)+r2));
      rows2+=rowOf(line); r2++;
    });
    var tot=[scell('合计','A'+r2), scell('','B'+r2)];
    YU.forEach(function(t,i){ var v=gsum[t]||0; gall+=v; tot.push(num(v,colRef(2+i)+r2)); });
    tot.push(num(gall,colRef(2+YU.length)+r2));
    rows2+=rowOf(tot);
    xm['xl/worksheets/sheet2.xml']='<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'+rows2+'</sheetData></worksheet>';    var zb=new JSZip();
    Object.keys(xm).forEach(function(n){ zb.file(n, xm[n]); });
    // mimeType 用 Excel 官方类型，避免部分浏览器按默认 application/zip 推断错误后缀
    zb.generateAsync({type:'blob', mimeType:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'}).then(function(blob){
      lastBlob=blob;
      var a=$('dlxlsx');
      a.style.display='inline-flex'; // v2.5：按钮改为 inline-flex 排版
    });
  }
  // 程序化合成 <a> 并主动 click 触发下载：相比"纯静态链接"，更能在内嵌 WebView 中让 download 文件名生效
  function exportNow(){
    if(!lastBlob) return false;
    var u=URL.createObjectURL(lastBlob);
    var a=document.createElement('a');
    a.href=u;
    a.download='加分明细汇总.xlsx';           // 期望文件名（含扩展名）
    a.type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(function(){ URL.revokeObjectURL(u); }, 2000); // 点击后释放 Blob 内存
    return false; // 阻止链接默认跳转
  }

