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
    xm['xl/worksheets/sheet2.xml']='<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'+rows2+'</sheetData></worksheet>';

