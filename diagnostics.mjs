import * as fs from 'fs';
import * as path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const engine = await import('./model/engine.mjs');

const dbPath = path.join(__dirname, 'db', 'worldcup.json');
const db = JSON.parse(fs.readFileSync(dbPath, 'utf8'));
const teams = db.teams;
const recentMatches = db.recentMatches || {};
const headToHead = db.headToHead || {};
const completedMatches = db.completedMatches || [];

console.log('='.repeat(70));
console.log('🔍 模型诊断报告 — 系统性审查');
console.log('='.repeat(70));

// 1. 检查所有球队的数据完整性
console.log('\n--- 1. 数据完整性检查 ---');
const issues = [];
for (const [name, team] of Object.entries(teams)) {
  if (!team.attackBase) issues.push(`${name}: 缺少attackBase`);
  if (!team.defenseBase) issues.push(`${name}: 缺少defenseBase`);
  if (!team.xg_model) issues.push(`${name}: 缺少xg_model`);
  if (!team.xg_model?.offensive_xg) issues.push(`${name}: xg_model.offensive_xg为空`);
  if (!team.xg_model?.defensive_xg) issues.push(`${name}: xg_model.defensive_xg为空`);
  if (!recentMatches[name]) issues.push(`${name}: 缺少recentMatches`);
}
if (issues.length === 0) console.log('✅ 所有球队数据完整');
else { console.log('⚠️ 发现问题:'); issues.forEach(i => console.log('  - ' + i)); }

// 2. 检查xG模型数值合理性
console.log('\n--- 2. xG模型数值合理性 ---');
const xgOff = Object.values(teams).map(t => t.xg_model?.offensive_xg).filter(Boolean);
const xgDef = Object.values(teams).map(t => t.xg_model?.defensive_xg).filter(Boolean);
console.log(`进攻xG: min=${Math.min(...xgOff).toFixed(3)} max=${Math.max(...xgOff).toFixed(3)} avg=${(xgOff.reduce((a,b)=>a+b,0)/xgOff.length).toFixed(3)}`);
console.log(`防守xG: min=${Math.min(...xgDef).toFixed(3)} max=${Math.max(...xgDef).toFixed(3)} avg=${(xgDef.reduce((a,b)=>a+b,0)/xgDef.length).toFixed(3)}`);

// 检查极端值
for (const [name, team] of Object.entries(teams)) {
  if (team.xg_model?.defensive_xg > 3.5) {
    console.log(`  ⚠️ ${name} 防守xG=${team.xg_model.defensive_xg} (异常高，对手预期进球太多)`);
  }
  if (team.xg_model?.offensive_xg < 0.5) {
    console.log(`  ⚠️ ${name} 进攻xG=${team.xg_model.offensive_xg} (异常低)`);
  }
}

// 3. 检查calcLambda的xG融合效果
console.log('\n--- 3. calcLambda xG融合测试 ---');
const testMatches = [
  {home:'法国', away:'瑞典', isKO:true},
  {home:'墨西哥', away:'厄瓜多尔', isKO:true},
  {home:'科特迪瓦', away:'挪威', isKO:true},
  {home:'德国', away:'巴拉圭', isKO:true},
  {home:'荷兰', away:'摩洛哥', isKO:true},
];

for (const t of testMatches) {
  const ctx = { teams, isKnockout: t.isKO };
  const lh = engine.calcLambda(t.home, t.away, true, teams, recentMatches, ctx);
  const la = engine.calcLambda(t.away, t.home, false, teams, recentMatches, ctx);
  
  // 临时移除xG看差异
  const savedXG = {};
  for (const [name, team] of Object.entries(teams)) {
    if (team.xg_model) { savedXG[name] = team.xg_model; delete team.xg_model; }
  }
  const ctxNoXG = { teams, isKnockout: t.isKO };
  const lhNo = engine.calcLambda(t.home, t.away, true, teams, recentMatches, ctxNoXG);
  const laNo = engine.calcLambda(t.away, t.home, false, teams, recentMatches, ctxNoXG);
  for (const [name, xg] of Object.entries(savedXG)) { teams[name].xg_model = xg; }
  
  const diffH = (lh - lhNo).toFixed(3);
  const diffA = (la - laNo).toFixed(3);
  console.log(`  ${t.home} vs ${t.away}: λ(${lh}/${la}) vs 无xG(${lhNo}/${laNo}) 差(${diffH}/${diffA})`);
}

// 4. 检查蒙特卡洛在淘汰赛的波动系数
console.log('\n--- 4. 蒙特卡洛波动系数检查 ---');
const mcKO = engine.monteCarlo(1.5, 1.5, 1000, 0.02, true);
const mcGR = engine.monteCarlo(1.5, 1.5, 1000, 0.02, false);
console.log(`淘汰赛: 平局率=${mcKO.drawPct}% 平均进球=${mcKO.avgGoals}`);
console.log(`小组赛: 平局率=${mcGR.drawPct}% 平均进球=${mcGR.avgGoals}`);

// 5. 检查fusionPredict的权重分配
console.log('\n--- 5. Fusion权重分配检查 ---');
const fusionTest = engine.fusionPredict('墨西哥', '厄瓜多尔', teams, recentMatches, headToHead, {isKnockout:true});
if (fusionTest && fusionTest.weights) {
  console.log('当前权重:', JSON.stringify(fusionTest.weights));
  console.log('总权重:', Object.values(fusionTest.weights).reduce((a,b)=>a+b,0));
}

// 6. 检查赔率转换是否合理
console.log('\n--- 6. 赔率转换测试 ---');
const oddsTests = [
  {h:1.16, d:5.8, a:10.5, label:'法国vs瑞典'},
  {h:1.94, d:2.7, a:4.1, label:'墨西哥vs厄瓜多尔'},
  {h:3.55, d:3.35, a:1.82, label:'科特迪瓦vs挪威'},
];
for (const ot of oddsTests) {
  const prob = engine.oddsToProb(ot.h, ot.d, ot.a);
  if (prob) {
    console.log(`  ${ot.label}: ${prob.homeWinPct}%/${prob.drawPct}%/${prob.awayWinPct}% (overround=${prob.overround}%)`);
  }
}

// 7. 检查环境修正模块
console.log('\n--- 7. 环境修正测试 ---');
const envResult = engine.applyMatchEnvironment(1.5, 1.5, {
  venueAltitude: 2240,
  temperature: 30,
  isRain: false,
  homeTzDiff: 8,
  awayTzDiff: 0,
  isHighStakes: true,
  homeStyle: 'possession',
  awayStyle: 'counter'
});
console.log('高原+高温+淘汰赛环境修正:', JSON.stringify(envResult));

console.log('\n' + '='.repeat(70));
console.log('诊断完成');
console.log('='.repeat(70));
