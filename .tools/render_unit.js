/* 检索明细渲染的确定性单测：把 .tools/ui/render.js 的真实源码抽出来，
 * 配一层假 DOM + 假 parseType，喂合成数据，断言"格式"与"上限提醒"都对。
 * 真机跑不出德育 > 25 的样本（本次语料最大才 2 分），这条分支只能在这里覆盖。
 *
 * 用法: node .tools/render_unit.js
 */
'use strict';
const fs = require('fs');
const path = require('path');

const src = fs.readFileSync(path.join(__dirname, 'ui', 'render.js'), 'utf8') + '\n' +
            fs.readFileSync(path.join(__dirname, 'ui', 'zip.js'), 'utf8');

// ---- 假 DOM：$() 返回带 innerHTML/style 的对象 ----
const nodes = {};
const document = {
  getElementById(id) {
    if (!nodes[id]) nodes[id] = { innerHTML: '', style: {}, textContent: '' };
    return nodes[id];
  },
};
const $ = id => document.getElementById(id);
const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
const parseType = score => {
  if (!score) return '';
  const m = /^([^\d+\-＋]+)/.exec(score);
  return m ? m[1] : score;
};
const setupDownload = () => {};

// render.js 里会写 lastStats，包一层作用域声明，避免污染全局；zip.js 需要 window 与 JSZip 两个全局
const fakeWindow = {};
const api = new Function('$', 'esc', 'parseType', 'setupDownload', 'JSZip', 'window',
  'var lastStats=null;\n' + src +
  '\nreturn {render: render, YU: YU, safeName: safeName, itemFile: itemFile, personDir: personDir, yuDir: yuDir};'
)($, esc, parseType, setupDownload, {}, fakeWindow);

// ---- 合成输入：覆盖 五育齐全 / 超上限 / 负分 / 无学号 / 无分值 / HTML 转义 ----
const keep = [
  {
    name: '德育测评/志愿活动.pdf', act: '在校志愿时长累计101.44',
    records: [
      { score: '德育+10', serial: '2024000001' },
      { score: '德育+17.5', serial: '2024000001' },
      { score: '智育+12', serial: '2024000001' },
      { score: '体育+6', serial: '2024000001' },
    ],
  },
  {
    name: '美育/<script>bad</script>.pdf', act: '文艺演出<script>',
    records: [
      { score: '美育+2.5', serial: '2024000001' },
      { score: '美育-0.5', serial: '2024000002' },
      { score: '劳育+1', serial: '2024000002' },
      { score: null, serial: null },
      { score: '德育+3', serial: null },
    ],
  },
];

api.render(keep, [], false, '某同学');
const detail = nodes.detail.innerHTML;
const summary = nodes.summary.innerHTML;

const checks = [
  ['按人分块（3 组：2 个学号 + 未标）', (detail.match(/class="mperson"/g) || []).length === 3],
  ['五育分段齐全', ['德育', '智育', '体育', '美育', '劳育'].every(t => detail.includes('>' + t + '</span>'))],
  ['育序为 德智体美劳', (() => {
    const pos = ['德育', '智育', '体育', '美育', '劳育'].map(t => detail.indexOf('>' + t + '</span>'));
    return pos.every((v, i) => v >= 0 && (i === 0 || v > pos[i - 1]));
  })()],
  ['德育超 25 提醒', detail.includes('超出 25 分上限，按 25 分计')],
  ['智育超 10 提醒', detail.includes('超出 10 分上限，按 10 分计')],
  ['未超上限不提醒劳育', !/劳育[\s\S]*?超出/.test(detail.slice(detail.lastIndexOf('>劳育</span>')))],
  ['加分项写法 +10', detail.includes('>+10</b>')],
  ['负分写法 -0.5', detail.includes('>-0.5</b>')],
  ['未标学号成组', detail.includes('未标学号')],
  ['无分值显示占位', detail.includes('>—</b>')],
  ['事由取自活动名', detail.includes('在校志愿时长累计101.44')],
  ['来源取文件名', detail.includes('志愿活动.pdf')],
  ['HTML 转义（事由）', detail.includes('&lt;script&gt;') && !detail.includes('<script>bad')],
  ['台账含命中文件数', summary.includes('命中文件')],
  ['台账合计 +51.5', summary.includes('+51.5')],
  ['台账列数 = 文件 + 5 育 + 合计', (summary.match(/class="cell"/g) || []).length === 7],
];

// 场景 2：只有德育 → 台账要显式点名其余四育没有记录，且列数跟着变
nodes.detail.innerHTML = '';
nodes.summary.innerHTML = '';
api.render([{ name: 'a.pdf', act: 'x', records: [{ score: '德育+1', serial: '1' }] }], [], false, '甲');
checks.push(['缺项提示', nodes.summary.innerHTML.includes('没有记录')]);
checks.push(['缺项时列数 = 文件 + 1 育 + 合计', (nodes.summary.innerHTML.match(/class="cell"/g) || []).length === 3]);

// 场景 3：材料包的目录与命名（方案 C：学号姓名/五育测评/+分值 (事由).扩展名）
checks.push(['材料包·挂到 window', typeof fakeWindow.exportMaterialZip === 'function']);
checks.push(['材料包·非法字符清理', api.safeName('a/b\\c:d*e?f"g<h>i|j') === 'a_b_c_d_e_f_g_h_i_j']);
checks.push(['材料包·点与空格结尾清理', api.safeName('x. ') === 'x']);
checks.push(['材料包·五育目录名', api.yuDir('德育') === '德育测评' && api.yuDir('劳育') === '劳育测评' && api.yuDir('未标注') === '未识别']);
checks.push(['材料包·原文件名只加分值前缀', api.itemFile({ val: 2, why: '无关', src: 'dir/晚归打卡公示汇总.pdf' }) === '+2 晚归打卡公示汇总.pdf']);
checks.push(['材料包·负分与无分值', api.itemFile({ val: -0.5, why: 'a', src: 'b.pdf' }) === '-0.5 b.pdf'
  && api.itemFile({ val: null, why: 'a', src: 'b.xlsx' }) === '未识别分值 b.xlsx']);
checks.push(['材料包·扩展名大小写保留', api.itemFile({ val: 1, src: 'X.PDF' }) === '+1 X.PDF']);
checks.push(['材料包·截断不截扩展名', /\.pdf$/.test(api.itemFile({ val: 1, src: '很长的名字'.repeat(30) + '.pdf' }))]);
checks.push(['材料包·人目录名', api.personDir({ sid: '2024000001' }, '张三') === '2024000001张三'
  && api.personDir({ sid: '' }, '甲') === '未标学号甲']);

let bad = 0;
for (const [name, ok] of checks) {
  if (!ok) bad++;
  console.log('  %s %s', name.padEnd(26, ' '), ok ? 'OK' : 'FAIL <<<');
}
console.log('失败项: ' + bad);
process.exit(bad ? 1 : 0);
