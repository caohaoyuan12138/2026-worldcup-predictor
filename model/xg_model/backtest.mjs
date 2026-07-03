/**
 * xG 模型回测
 * 用 75 场已完赛数据验证 xG 模型对预测准确性的影响
 */

import fs from 'fs';
import { calcLambda, fusionPredict, evaluatePredictions } from '../engine.mjs';

const wc = JSON.parse(fs.readFileSync(new URL('../../db/worldcup.json', import.meta.url), 'utf-8'));

const teams = wc.teams;
const recentMatches = wc.recentMatches || {};
const headToHead = wc.headToHead || {};
const completedMatches = wc.completedMatches || [];

console.log('='.repeat(60));
console.log('xG 模型回测');
console.log('='.repeat(60));
console.log(`已完赛: ${completedMatches.length} 场`);

// ── 1. calcLambda 回测 ──
console.log('\n--- calcLambda 回测 ---');

// 有 xG 模型
const ctxWithXG = { teams, isKnockout: false };
const lambdaWithXG = completedMatches.map(m => {
  const lh = calcLambda(m.home, m.away, true, teams, recentMatches, ctxWithXG);
  const la = calcLambda(m.away, m.home, false, teams, recentMatches, ctxWithXG);
  const [actualH, actualA] = m.score.split('-').map(Number);
  return { home: m.home, away: m.away, lh, la, actualH, actualA, score: m.score };
});

// 无 xG 模型（移除 xg_model）
const savedXG = {};
for (const [name, team] of Object.entries(teams)) {
  if (team.xg_model) {
    savedXG[name] = team.xg_model;
    delete team.xg_model;
  }
}
const ctxNoXG = { teams, isKnockout: false };
const lambdaNoXG = completedMatches.map(m => {
  const lh = calcLambda(m.home, m.away, true, teams, recentMatches, ctxNoXG);
  const la = calcLambda(m.away, m.home, false, teams, recentMatches, ctxNoXG);
  const [actualH, actualA] = m.score.split('-').map(Number);
  return { home: m.home, away: m.away, lh, la, actualH, actualA, score: m.score };
});

// 恢复 xg_model
for (const [name, xg] of Object.entries(savedXG)) {
  teams[name].xg_model = xg;
}

// 计算预测误差
function calcLambdaError(results) {
  let totalError = 0;
  let homeError = 0;
  let awayError = 0;
  let correctDir = 0;

  for (const r of results) {
    const predTotal = r.lh + r.la;
    const actualTotal = r.actualH + r.actualA;
    totalError += Math.abs(predTotal - actualTotal);

    homeError += Math.abs(r.lh - r.actualH);
    awayError += Math.abs(r.la - r.actualA);

    // 方向正确性
    const predDir = r.lh > r.actualA ? 'home' : (r.la > r.actualA ? 'draw' : 'away');
    const actualDir = r.actualH > r.actualA ? 'home' : (r.actualH === r.actualA ? 'draw' : 'away');
    if (predDir === actualDir) correctDir++;
  }

  return {
    count: results.length,
    avgTotalError: +(totalError / results.length).toFixed(3),
    avgHomeError: +(homeError / results.length).toFixed(3),
    avgAwayError: +(awayError / results.length).toFixed(3),
    directionAccuracy: +(correctDir / results.length * 100).toFixed(1),
  };
}

const errWithXG = calcLambdaError(lambdaWithXG);
const errNoXG = calcLambdaError(lambdaNoXG);

console.log('\n有 xG 模型:');
console.log(`  场均总误差: ${errWithXG.avgTotalError} 球`);
console.log(`  主队误差:   ${errWithXG.avgHomeError} 球`);
console.log(`  客队误差:   ${errWithXG.avgAwayError} 球`);
console.log(`  方向准确率: ${errWithXG.directionAccuracy}%`);

console.log('\n无 xG 模型:');
console.log(`  场均总误差: ${errNoXG.avgTotalError} 球`);
console.log(`  主队误差:   ${errNoXG.avgHomeError} 球`);
console.log(`  客队误差:   ${errNoXG.avgAwayError} 球`);
console.log(`  方向准确率: ${errNoXG.directionAccuracy}%`);

const improvement = parseFloat(errNoXG.avgTotalError) - parseFloat(errWithXG.avgTotalError);
console.log(`\nxG 模型改进: ${improvement > 0 ? '+' : ''}${improvement.toFixed(3)} 球/场`);

// ── 2. 典型比赛对比 ──
console.log('\n--- 典型比赛 λ 对比 ---');
const showcase = [
  { home: '美国', away: '巴西' },
  { home: '墨西哥', away: '阿根廷' },
  { home: '法国', away: '西班牙' },
  { home: '英格兰', away: '荷兰' },
  { home: '德国', away: '巴西' },
];

console.log('\n' + '比赛'.padEnd(25) + '有xG l'.padStart(15) + '无xG l'.padStart(15) + '差值'.padStart(10));
console.log('-'.repeat(70));

for (const m of showcase) {
  const withX = lambdaWithXG.find(r => r.home === m.home && r.away === m.away) ||
    ((ctxWithXG.isKnockout = false), calcLambda(m.home, m.away, true, teams, recentMatches, ctxWithXG) && {
      lh: calcLambda(m.home, m.away, true, teams, recentMatches, { teams, isKnockout: false }),
      la: calcLambda(m.away, m.home, false, teams, recentMatches, { teams, isKnockout: false })
    });

  const noX = lambdaNoXG.find(r => r.home === m.home && r.away === m.away) ||
    ((ctxNoXG.isKnockout = false), calcLambda(m.home, m.away, true, teams, recentMatches, ctxNoXG) && {
      lh: calcLambda(m.home, m.away, true, teams, recentMatches, { teams, isKnockout: false }),
      la: calcLambda(m.away, m.home, false, teams, recentMatches, { teams, isKnockout: false })
    });

  const match = `${m.home} vs ${m.away}`;
  const withStr = withX ? `${withX.lh}/${withX.la}` : 'N/A';
  const noStr = noX ? `${noX.lh}/${noX.la}` : 'N/A';
  const diff = withX && noX ? `${(withX.lh - noX.lh).toFixed(2)}/${(withX.la - noX.la).toFixed(2)}` : 'N/A';

  console.log('  ' + match.padEnd(23) + withStr.padStart(15) + noStr.padStart(15) + diff.padStart(10));
}

// ── 3. 东道主球队 λ 对比 ──
console.log('\n--- 东道主 λ 对比 ---');
for (const host of ['美国', '墨西哥', '加拿大']) {
  const matches = completedMatches.filter(m => m.home === host || m.away === host);
  if (matches.length === 0) continue;

  let withTotal = 0, noTotal = 0, actualTotal = 0;
  for (const m of matches) {
    const isHome = m.home === host;
    const opp = isHome ? m.away : m.home;
    const actual = isHome ? parseInt(m.score.split('-')[0]) : parseInt(m.score.split('-')[1]);

    const lWith = calcLambda(host, opp, isHome, teams, recentMatches, { teams, isKnockout: false });

    // 临时移除 xG
    const saved = teams[host].xg_model;
    delete teams[host].xg_model;
    const lNo = calcLambda(host, opp, isHome, teams, recentMatches, { teams, isKnockout: false });
    teams[host].xg_model = saved;

    withTotal += lWith;
    noTotal += lNo;
    actualTotal += actual;
  }

  console.log(`  ${host}: 有xG λ=${withTotal.toFixed(2)} 无xG λ=${noTotal.toFixed(2)} 实际进球=${actualTotal} 场数=${matches.length}`);
}

console.log('\n' + '='.repeat(60));
console.log('回测完成!');
console.log('='.repeat(60));
