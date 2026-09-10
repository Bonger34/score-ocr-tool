
  // ---------- 关键词邻域解析（与桌面版算法一致） ----------
  function parseOccurrences(text,kw,fuzzy){
    // pdf.js 对部分 PDF 会把姓名与分值都拆成独立 token（姓 名 字 / 美育 | +1.5），
    // 此实现：姓名按"分字拼接"匹配，分值支持"类型token + 符号token"两段合并，学号前后双向反查。
    var tokens=text.split(/[\s|｜]+/).filter(Boolean), out=[];
    var TYPES=['美育','德育','劳育','智育','体育'];
    for(var i=0;i<tokens.length;i++){
      // 姓名块：从 i 起逐 token 拼接，拼出 == kw 记一处命中；若整名为 kw 且其后紧跟"（）备注"亦命中
      var j=i, s0='', ok=false;
      while(j<tokens.length && s0.length<kw.length){ s0+=tokens[j]; if(s0===kw){ok=true;break;} j++; }
      // 姓名+括号备注在同一 token（如"某姓名(曾用名)"）时：整名命中、括号后缀放行
      if(!ok && s0.indexOf(kw)===0 && /^[（(]/.test(s0.substr(kw.length))) ok=true;
      if(!ok) continue;
      // 整名匹配边界：姓名块(结束于 j)之后若紧跟"单字纯汉字"(长度1)token，说明它是更长姓名的
      // 续字（如搜"AB"时命中"AB | C"两块，块后紧跟单字"C"），即 kw 只是更长姓名的一部分
      // -> 拦截，保证完全匹配不误中前缀。
      // 块后为多字词组/字段（"德育""美育"）或含数字的 token 时不算续字 -> 放行。
      // 备注后缀"（xxx）"以括号开头，也不属续字 -> 放行。兼覆单字与多字两种检索词。
      if(!fuzzy){
        var nxt=tokens[j+1]||'';
        if(/^[\u4e00-\u9fff]$/.test(nxt)) continue;
      }
      // 分值：从姓名块后起扫 12 个 token，两种形态
      var score=null;
      for(var m=j;m<Math.min(j+12,tokens.length);m++){
        var mt=tokens[m].replace(/[＋]/g,'+').match(/^(美育|德育|劳育|智育|体育)([＋+\uFF0B-]\d+(?:\.\d+)?)$/);
        if(mt){ score=mt[1]+mt[2].replace(/[＋]/g,'+'); break; }
        if(TYPES.indexOf(tokens[m])>=0){
          var nx=tokens[m+1]||'';
          var nxx=nx.replace(/[＋]/g,'+');
          if(/^[＋+\uFF0B-]\d+(?:\.\d+)?$/.test(nxx)){
            var sign=/^-/.test(nxx)?'-':'+';
            score=tokens[m]+sign+nxx.replace(/^[＋+\uFF0B-]/,'');
            break;
          }
        }
      }
      // 学号：优先姓名块前 20 个 token 内的 ≥6位数字；没有再向后看 12 个 token
      var serial=null;
      for(var n=i-1;n>Math.max(-1,i-20);n--){
        if(/^\d{6,9}$/.test(tokens[n])){ serial=tokens[n]; break; }
      }
      if(!serial){
        for(var q=j;q<Math.min(j+12,tokens.length);q++){
          if(/^\d{6,9}$/.test(tokens[q])){ serial=tokens[q]; break; }
        }
      }
      out.push({score:score,serial:serial});
      if(j>i) i=j; // 跳过已消费的拆分 token
    }
    return out;
  }

  // ---------- 活动名：从文件路径/标题规范化提取（三键判重用：活动+分值+学号） ----------
  function activityKey(p){
    // 活动名规范化：CLone 校验脚本 validate_norm，目的是合并"跨目录、文件名不同"的真实副本，
    // 同时避免误并不同活动。核心：去院校/校区名、日期、前后缀、嵌入数字。
    var n=p.split('/').pop().replace(/\.(pdf|xlsx|xlsm|txt|csv)$/i,'');
    n=n.replace(/_\d{8}\d*$/,'');                    // 去尾部时间戳 _20251218115658
    n=n.replace(/\d{6,}[\s_]*$/,'');                 // 去尾部纯数字(20260312/20251119)
    var noise=['福建农林大学金山学院（安溪）','福建农林大学金山学院（南平校区）',
               '福建农林大学金山学院（南平）','福建农林大学金山学院','金山学院','福建农林大学',
               '（含三校区）','(含三校区)','含三校区','（观众）','(观众)','观众'];
    for(var i=0;i<noise.length;i++){ n=n.split(noise[i]).join(''); }
    n=n.replace(/[（(]\d{1,3}[）)]/g,'');             // 去 (1) 等小括号数字
    n=n.replace(/[（(].{0,6}校区[）)]/g,'');          // 去（安溪）（南平）等校区括号
    var suf=['参与人员名单','加分补充说明名单','加分补充说明','参与人员','加分名单',
             '加分文件补充说明','加分人员名单','加分表','加分文件','加分','说明名单','名单'];
    for(var j=0;j<suf.length;j++){ n=n.replace(new RegExp(suf[j]+'[\\s　]*$'),''); } // 去末尾后缀
    n=n.replace(/^\d{1,2}月\d{1,2}日?\s*/,'');       // 去开头日期 1月1日
    n=n.replace(/^\d{4}年\d{1,2}月\d{1,2}日?\s*/,'');// 去 2025年11月19日
    n=n.replace(/^\d{4}年\s*/,'');                   // 去 2025年
    n=n.replace(/^\d{1,2}[.．/]\d{1,2}[\s-]*/,'');   // 去 11.9 / 5.16
    n=n.replace(/^\d{2,}(?=[\u4e00-\u9fff])/,'');    // 去开场数字编码(119…)
    n=n.replace(/\d{2,}(?!期)(?=[\u4e00-\u9fff])/g,''); // 去中段嵌入数字(系119校园/2025消…)，保留第N期期数
    return n.replace(/\s{2,}/g,' ').replace(/\s+$/,'');
  }

  // ---------- 文本提取 ----------
  function ext(name){ var i=name.lastIndexOf('.'); return i<0?'':name.slice(i+1).toLowerCase(); }
