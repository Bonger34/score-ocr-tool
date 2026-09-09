  // v2.7：结果区按"综测报送格式"重排——台账 + 明细清单（学号 · 姓名 → 五育测评 → +分值（事由））。
  // 五育顺序与上限口径取自《福建农林大学金山学院学生综合素质测评管理规定》（闽农大金山学〔2025〕26号）：
  //   第五条 德育/智育/体育/美育/劳育五项；
  //   第九条 德育奖励分超出 25 分按 25 分计算；
  //   第十三条（五）同一学年智育奖励分累计不超过 10 分。
  var YU=['德育','智育','体育','美育','劳育'];
  var YU_CLS={'德育':'t-de','智育':'t-zhi','体育':'t-ti','美育':'t-mei','劳育':'t-lao'};
  var YU_CAP={'德育':25,'智育':10};   // 只有这两项是"学年累计上限"；其余各育的限值按单项规定，不在此汇总
  function numStr(v){ return String(Math.round(v*100)/100); }
  function itemStr(v){ return (v>0?'+':'')+numStr(v); }    // 加分项照报送写法：+10 / +0.5
  function sumStr(v){ return (v>0?'+':'')+v.toFixed(1); }  // 小计/合计保留一位小数
  function baseName(p){ return String(p).split(/[\\/]/).pop(); }

  function render(keep,removed,doDedup,kw){
    // 1) 展平为"加分项"：每条带 人（学号）/ 育 / 分值 / 事由 / 来源
    var items=[];
    keep.forEach(function(m){
      var why=m.act||baseName(m.name), src=m.name;
      m.records.forEach(function(r){
        var raw=r.score?String(r.score):'';
        var t=raw?parseType(raw):'';
        var vm=raw?/[-+]?\d+(?:\.\d+)?/.exec(raw):null;
        var v=vm?parseFloat(vm[0]):NaN;
        items.push({sid:r.serial?String(r.serial):'', yu:(YU.indexOf(t)>=0?t:'未标注'),
                    val:isFinite(v)?v:null, why:why, src:src,
                    srcRef:m.src||null, size:m.size||0});   // srcRef/size 供材料包导出取原始字节
      });
    });
    // 2) 按学号归人（顺序沿用命中顺序）；同一学号的多条记录聚成一块
    var people=[], idx={};
    items.forEach(function(it){
      var k=it.sid||'~', p=idx[k];
      if(!p){ p=idx[k]={sid:it.sid, items:[], files:{}, sums:{}, cnts:{}}; people.push(p); }
      p.items.push(it); p.files[it.src]=1;
      if(it.yu!=='未标注'&&it.val!==null){
        p.sums[it.yu]=(p.sums[it.yu]||0)+it.val;
        p.cnts[it.yu]=(p.cnts[it.yu]||0)+1;
      }
    });
    // 3) 全局汇总：合计只算进了五育且分值可解析的记录，未标注单列
    var sums={}, cnts={}, total=0, totalCnt=0;
    people.forEach(function(p){
      YU.forEach(function(t){
        if(p.cnts[t]){ sums[t]=(sums[t]||0)+p.sums[t]; cnts[t]=(cnts[t]||0)+p.cnts[t]; }
      });
    });
    Object.keys(sums).forEach(function(t){ total+=sums[t]; });
    items.forEach(function(it){ if(it.yu!=='未标注'&&it.val!==null) totalCnt++; });

    // 4) 台账：列随"有记录的育"变化，缺的育在下面一句话点名
    var liveYu=YU.filter(function(t){ return cnts[t]>0; });
    var led='<div class="ledger">'+
      '<div class="cell"><b>'+keep.length+'</b><span>命中文件'+(doDedup?'（去重后）':'')+'</span></div>';
    liveYu.forEach(function(t){
      led+='<div class="cell"><b class="'+YU_CLS[t]+'">'+sumStr(sums[t]||0)+'</b><span>'+t+'（'+cnts[t]+' 条）</span></div>';
    });
    led+='<div class="cell"><b>'+sumStr(total)+'</b><span>加分合计（'+totalCnt+' 条）</span></div></div>';
    var miss=YU.filter(function(t){ return !(cnts[t]>0); });
    if(liveYu.length&&miss.length){
      led+='<p class="hint">本次命中只涉及 '+liveYu.join('、')+'；'+miss.join('、')+' 没有记录。</p>';
    }
    if(liveYu.length>1&&total>0){
      var aria=liveYu.map(function(t){ return t+' '+sumStr(sums[t]||0); }).join('，');
      led+='<div class="compo" role="img" aria-label="加分构成：'+aria+'">';
      liveYu.forEach(function(t){ led+='<i class="'+YU_CLS[t]+'" style="width:'+(sums[t]/total*100).toFixed(2)+'%"></i>'; });
      led+='</div>';
    }
    $('summary').innerHTML=led;

    // 5) 同名不同人提醒（无学号的记录不参与判断，避免误报）
    var serialSet={}, sn=0;
    items.forEach(function(it){ if(it.sid&&!(it.sid in serialSet)){serialSet[it.sid]=1;sn++;} });
    var warn=sn>1
      ? '<div class="alert"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M12 4 2.5 20h19z"/><path d="M12 10v4"/><path d="M12 17.2v.2"/></svg><span>本次命中记录里出现了 <b>'+sn+'</b> 个不同学号，姓名与学号不是一一对应，可能有<b>同名不同人</b>，请人工核对学号栏。</span></div>'
      : '';

    // 6) 明细清单
    var tb='<h3 class="sub">检索明细（共 '+keep.length+' 份 · '+items.length+' 条）</h3>'+warn+
      '<p class="hint">按综测报送格式排列：<b>学号 · 姓名 → 五育测评 → +分值（事由）</b>。事由取名单文件里的活动名，来源列是命中文件；姓名取检索词，模糊匹配时请以学号为准。</p>';
    people.forEach(function(p){
      var pt=0; YU.forEach(function(t){ pt+=p.sums[t]||0; });
      tb+='<article class="mperson"><header class="mp-head"><h4 class="mp-id">'+
        (p.sid?esc(p.sid):'<span class="mp-na">未标学号</span>')+'<i>·</i>'+esc(kw)+'</h4>'+
        '<span class="mp-tot">合计 <b>'+sumStr(pt)+'</b>（'+p.items.length+' 条 · '+
        Object.keys(p.files).length+' 份文件）</span></header>';
      YU.concat(['未标注']).forEach(function(t){
        var list=p.items.filter(function(it){ return it.yu===t; });
        if(!list.length) return;
        var cap=YU_CAP[t]||0, over=cap>0&&(p.sums[t]||0)>cap;
        tb+='<section class="mp-yu"><h5 class="mp-yuhead"><span class="tag '+(YU_CLS[t]||'t-other')+'">'+
          (t==='未标注'?'未标注':t)+'</span>';
        if(t==='未标注'){
          tb+='<span class="mp-cnt">'+list.length+' 条（没识别到育别或分值，请人工看原件）</span>';
        }else{
          tb+='<b class="mp-yusum">'+sumStr(p.sums[t]||0)+'</b><span class="mp-cnt">'+list.length+' 条</span>';
        }
        if(over) tb+='<span class="mp-cap">累计 '+sumStr(p.sums[t]||0)+' 分，超出 '+cap+' 分上限，按 '+cap+' 分计（需手动修改）</span>';
        tb+='</h5><ul class="mp-items">';
        list.forEach(function(it){
          tb+='<li class="mp-item"><b class="mp-v">'+(it.val===null?'—':itemStr(it.val))+'</b>'+
              '<span class="mp-why">'+esc(it.why)+'</span>'+
              '<span class="mp-src" title="'+esc(it.src)+'">'+esc(baseName(it.src))+'</span></li>';
        });
        tb+='</ul></section>';
      });
      tb+='</article>';
    });
    $('detail').innerHTML=tb;

    if(doDedup&&removed.length){
      var d='<details class="dups"><summary>已剔除的重复副本（'+removed.length+' 份）</summary>'+
        '<div class="tablewrap"><table><caption class="sr-only">被判为重复副本的文件</caption>'+
        '<thead><tr><th scope="col">文件</th></tr></thead><tbody>';
      removed.forEach(function(m){ d+='<tr class="dup"><td class="fname">'+esc(m.name)+'</td></tr>'; });
      d+='</tbody></table></div><p class="hint">同一活动可能被归档到多个目录，工具按「活动 + 加分值 + 学号」三键识别重复副本并各保留一份；没有学号的记录不参与判重。</p></details>';
      $('dupbox').innerHTML=d; $('dupbox').style.display='block';
    } else { $('dupbox').innerHTML=''; $('dupbox').style.display='none'; }

    lastStats={sums:sums,cnts:cnts,total:total,totalCnt:totalCnt,people:people,items:items,kw:kw};
    var zb=$('dlzip'); if(zb) zb.style.display='inline-flex';   // 有结果才显示材料包按钮
    setupDownload(keep,removed,doDedup);
  }
