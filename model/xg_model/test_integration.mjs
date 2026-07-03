/**
 * xG 模型集成测试
 * 验证 engine.mjs 中 xG 模型的正确加载和使用
 */

import { fusionPredict, calcLambda } from '../engine.mjs';

// 加载 worldcup.json
import fs from 'fs';
const wc = JSON.parse(fs.readFileSync(new URL('../../db/worldcup.json', import.meta.url), 'utf-8'));

const teams = wc.teams;
const recentMatches = wc.recentMatches || {};
const headToHead = wc.headToHead || {};

console.log('='.repeat(60));
console.log('xG 模型集成测试');
console.log('='.repeat(60));

// 检查 xg_model 数据
let teamsWithXG = 0;
for (const [name, team] of Object.entries(teams)) {
  if (team.xg_model) teamsWithXG++;
}
console.log(`\n有 xg_model 的球队: ${teamsWithXG} / ${Object.keys(teams).length}`);

// 打印几支美加墨球队的 xG 数据
console.log('\n--- 美加墨东道主 xG 数据 ---');
for (const host of ['美国', '墨西哥', '加拿大']) {
  const t = teams[host];
  if (t?.xg_model) {
    const xg = t.xg_model;
    console.log(`\n${host}:`);
    console.log(`  进攻xG: ${xg.offensive_xg}  防守xG: ${xg.defensive_xg}  xG差: ${xg.xg_diff}`);
    console.log(`  射门/场: ${xg.shot_volume}  射正率: ${xg.shot_accuracy}  终结效率: ${xg.conversion_ratio}`);
  }
}

// 测试 calcLambda
console.log('\n--- calcLambda 测试 ---');
const ctx = { teams, isKnockout: false };
const lambdaUS = calcLambda('美国', '巴西', true, teams, recentMatches, ctx);
const lambdaBR = calcLambda('巴西', '美国', false, teams, recentMatches, ctx);
console.log(`美国 vs 巴西: λ_美国=${lambdaUS}, λ_巴西=${lambdaBR}`);

const lambdaMX = calcLambda('墨西哥', '阿根廷', true, teams, recentMatches, ctx);
const lambdaAR = calcLambda('阿根廷', '墨西哥', false, teams, recentMatches, ctx);
console.log(`墨西哥 vs 阿根廷: λ_墨西哥=${lambdaMX}, λ_阿根廷=${lambdaAR}`);

// 测试预测
console.log('\n--- 预测测试 ---');

const testMatches = [
  { home: '美国', away: '巴西', isKO: false },
  { home: '墨西哥', away: '阿根廷', isKO: false },
  { home: '加拿大', away: '德国', isKO: true },
  { home: '法国', away: '西班牙', isKO: true },
  { home: '英格兰', away: '荷兰', isKO: false },
];

for (const m of testMatches) {
  try {
    const result = fusionPredict(
      m.home, m.away, teams, recentMatches, headToHead,
      { isKnockout: m.isKO }
    );
    const f = result?.fusion;
    console.log(`\n${m.home} vs ${m.away} ${m.isKO ? '(淘汰赛)' : '(小组赛)'}`);
    if (f) {
      console.log(`  胜: ${f.winPct}%  平: ${f.drawPct}%  负: ${f.awayPct}%`);
      console.log(`  λ: 主=${f.lambda?.home} 客=${f.lambda?.away}`);
      console.log(`  最可能比分: ${f.top5?.[0]?.score || 'N/A'} (${f.top5?.[0]?.pct || 0}%)`);
    } else {
      console.log(`  结果: ${JSON.stringify(result).slice(0, 100)}`);
    }
  } catch (e) {
    console.log(`\n${m.home} vs ${m.away}: 错误 - ${e.message}`);
    console.log(e.stack?.split('\n').slice(0, 3).join('\n'));
  }
}

// 对比：有 xG vs 无 xG
console.log('\n--- xG 影响对比 ---');
const testHome = '美国';
const testAway = '巴西';

// 有 xG
const resultWithXG = fusionPredict(
  testHome, testAway, teams, recentMatches, headToHead, {}
);

// 临时移除 xg_model
const savedXG = {};
for (const [name, team] of Object.entries(teams)) {
  if (team.xg_model) {
    savedXG[name] = team.xg_model;
    delete team.xg_model;
  }
}

const resultWithoutXG = fusionPredict(
  testHome, testAway, teams, recentMatches, headToHead, {}
);

// 恢复
for (const [name, xg] of Object.entries(savedXG)) {
  teams[name].xg_model = xg;
}

console.log(`\n${testHome} vs ${testAway}:`);
const wx = resultWithXG?.fusion;
const wox = resultWithoutXG?.fusion;
if (wx && wox) {
  console.log(`  有 xG: 胜=${wx.winPct}% 平=${wx.drawPct}% 负=${wx.awayPct}% λ=${wx.lambda?.home}/${wx.lambda?.away}`);
  console.log(`  无 xG: 胜=${wox.winPct}% 平=${wox.drawPct}% 负=${wox.awayPct}% λ=${wox.lambda?.home}/${wox.lambda?.away}`);
  console.log(`  xG影响: 胜${(wx.winPct - wox.winPct).toFixed(1)}% 平${(wx.drawPct - wox.drawPct).toFixed(1)}% 负${(wx.awayPct - wox.awayPct).toFixed(1)}%`);
}

console.log('\n' + '='.repeat(60));
console.log('测试完成!');
console.log('='.repeat(60));
