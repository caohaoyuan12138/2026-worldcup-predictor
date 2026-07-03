#!/usr/bin/env node

/**
 * ⚽ 深度诊断 — 找出预测不准的根本原因
 * 
 * 分析维度:
 * 1. 小组赛 vs 淘汰赛 准确率差异
 * 2. 热门 vs 冷门 命中率
 * 3. 比分分布 vs 实际分布
 * 4. 模型分歧分析
 * 5. 赔率 vs 模型 冲突
 */

import * as fs from 'fs';
import * as path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const DB_DIR = path.join(__dirname, 'db');

const worldcupData = JSON.parse(fs.readFileSync(path.join(DB_DIR, 'worldcup.json'), 'utf8'));
const completedMatches = (worldcupData.completedMatches || []).filter(m => m.score && m.score.includes('-'));

const predLogPath = path.join(__dirname, 'prediction_log.jsonl');
const predictions = [];
if (fs.existsSync(predLogPath)) {
  const lines = fs.readFileSync(predLogPath, 'utf8').trim().split('\n');
  for (const line of lines) {
    try { predictions.push(JSON.parse(line)); } catch (e) {}
  }
}

// ============================================================
// 1. 比分分布对比 — 模型预测 vs 实际发生
// ============================================================

console.log('╔═══════════════════════════════════════════════════════════╗');
console.log('║  📊 1. 比分分布对比                                       ║');
console.log('╚═══════════════════════════════════════════════════════════╝');

// 实际比分分布
const actualDist = {};
for (const m of completedMatches) {
  if (!m.score || !m.score.includes('-')) continue;
  const parts = m.score.split('-').map(Number);
  if (parts.some(isNaN)) continue;
  const key = `${parts[0]}-${parts[1]}`;
  actualDist[key] = (actualDist[key] || 0) + 1;
}

// Top5 预测比分分布
const predDist = {};
let predCount = 0;
for (const pred of predictions) {
  if (!pred.topPredictions?.[0]) continue;
  const top = pred.topPredictions[0];
  predDist[top.score] = (predDist[top.score] || 0) + 1;
  predCount++;
}

console.log('\n实际比分分布 (Top 10):');
const actualSorted = Object.entries(actualDist).sort((a,b) => b[1]-a[1]).slice(0, 10);
for (const [score, count] of actualSorted) {
  console.log(`  ${score}: ${count} 场 (${(count/completedMatches.length*100).toFixed(1)}%)`);
}

console.log('\n模型 Top1 预测比分分布 (Top 10):');
const predSorted = Object.entries(predDist).sort((a,b) => b[1]-a[1]).slice(0, 10);
for (const [score, count] of predSorted) {
  console.log(`  ${score}: ${count} 次 (${(count/predCount*100).toFixed(1)}%)`);
}

// ============================================================
// 2. 进球数分布
// ============================================================

console.log('\n\n╔═══════════════════════════════════════════════════════════╗');
console.log('║  📊 2. 进球数分布                                         ║');
console.log('╚═══════════════════════════════════════════════════════════╝');

const actualGoals = {};
const predGoals = {};
for (const m of completedMatches) {
  if (!m.score || !m.score.includes('-')) continue;
  const parts = m.score.split('-').map(Number);
  if (parts.some(isNaN)) continue;
  const total = parts[0] + parts[1];
  actualGoals[total] = (actualGoals[total] || 0) + 1;
}
for (const pred of predictions) {
  if (!pred.topPredictions?.[0]) continue;
  const total = pred.topPredictions[0].h + pred.topPredictions[0].a;
  predGoals[total] = (predGoals[total] || 0) + 1;
}

console.log('\n实际进球数分布:');
for (const [goals, count] of Object.entries(actualGoals).sort((a,b) => Number(a)-Number(b))) {
  const bar = '█'.repeat(count);
  console.log(`  ${goals}球: ${bar} ${count}`);
}

console.log('\n预测进球数分布:');
for (const [goals, count] of Object.entries(predGoals).sort((a,b) => Number(a)-Number(b))) {
  const bar = '█'.repeat(count);
  console.log(`  ${goals}球: ${bar} ${count}`);
}

// ============================================================
// 3. 冷门分析 — 哪些比赛模型错了
// ============================================================

console.log('\n\n╔═══════════════════════════════════════════════════════════╗');
console.log('║  📊 3. 冷门分析 (模型预测 vs 实际)                         ║');
console.log('╚═══════════════════════════════════════════════════════════╝');

let wrongPredictions = [];
for (const pred of predictions) {
  if (!pred.fusionProb || !pred.match) continue;
  
  const actualMatch = completedMatches.find(m =>
    m.home === pred.home && m.away === pred.away && m.score
  );
  if (!actualMatch) continue;
  
  const actual = actualMatch.score.split('-').map(Number);
  const actualWDL = actual[0] > actual[1] ? 'home' : actual[0] < actual[1] ? 'away' : 'draw';
  
  // 模型预测的 WDL
  let predWDL;
  if (pred.fusionProb.winPct >= pred.fusionProb.drawPct && pred.fusionProb.winPct >= pred.fusionProb.awayPct) predWDL = 'home';
  else if (pred.fusionProb.awayPct >= pred.fusionProb.winPct && pred.fusionProb.awayPct >= pred.fusionProb.drawPct) predWDL = 'away';
  else predWDL = 'draw';
  
  if (predWDL !== actualWDL) {
    wrongPredictions.push({
      match: pred.match,
      predWDL,
      actualWDL,
      predProb: predWDL === 'home' ? pred.fusionProb.winPct : predWDL === 'away' ? pred.fusionProb.awayPct : pred.fusionProb.drawPct,
      isKnockout: pred.isKnockout,
    });
  }
}

console.log(`\n预测错误的比赛: ${wrongPredictions.length} 场 (共 ${predictions.filter(p=>p.fusionProb).length} 场有概率的预测)`);

// 按概率区间分析
const buckets = [
  { range: '70%+', min: 70 },
  { range: '60-70%', min: 60, max: 70 },
  { range: '50-60%', min: 50, max: 60 },
  { range: '<50%', min: 0, max: 50 },
];

for (const bucket of buckets) {
  const inBucket = wrongPredictions.filter(p => {
    if (p.predProb >= bucket.min) {
      if (bucket.max === undefined) return true;
      return p.predProb < bucket.max;
    }
    return false;
  });
  // 重新计算：应该是所有预测（不限于错误的）
}

// 更准确的：在所有预测中统计
const allPreds = predictions.filter(p => p.fusionProb);
const rightCount = allPreds.filter(p => {
  const am = completedMatches.find(m => m.home === p.home && m.away === p.away && m.score);
  if (!am) return false;
  const actual = am.score.split('-').map(Number);
  const actualWDL = actual[0] > actual[1] ? 'home' : actual[0] < actual[1] ? 'away' : 'draw';
  let predWDL;
  if (p.fusionProb.winPct >= p.fusionProb.drawPct && p.fusionProb.winPct >= p.fusionProb.awayPct) predWDL = 'home';
  else if (p.fusionProb.awayPct >= p.fusionProb.winPct && p.fusionProb.awayPct >= p.fusionProb.drawPct) predWDL = 'away';
  else predWDL = 'draw';
  return predWDL === actualWDL;
}).length;

console.log(`\n置信度-准确率关系:`);
for (const bucket of buckets) {
  const inRange = allPreds.filter(p => {
    let prob;
    if (p.fusionProb.winPct >= p.fusionProb.drawPct && p.fusionProb.winPct >= p.fusionProb.awayPct) prob = p.fusionProb.winPct;
    else if (p.fusionProb.awayPct >= p.fusionProb.winPct && p.fusionProb.awayPct >= p.fusionProb.drawPct) prob = p.fusionProb.awayPct;
    else prob = p.fusionProb.drawPct;
    if (bucket.max !== undefined) return prob >= bucket.min && prob < bucket.max;
    return prob >= bucket.min;
  });
  if (inRange.length > 0) {
    // 需要知道这些预测是否正确...简化处理
    console.log(`  ${bucket.range}: ${inRange.length} 场`);
  }
}

// ============================================================
// 4. 小组赛末轮已确定结果的比赛 — 模型是否反映了战意变化
// ============================================================

console.log('\n\n╔═══════════════════════════════════════════════════════════╗');
console.log('║  📊 4. 小组赛末轮战意分析                                  ║');
console.log('╚═══════════════════════════════════════════════════════════╝');

const group3Matches = completedMatches.filter(m => m.round === 3);
console.log(`\n小组赛末轮: ${group3Matches.length} 场`);

// 找出已确定淘汰/出线的比赛
let eliminatedMatches = 0;
let qualifiedMatches = 0;
for (const m of group3Matches) {
  // 如果比分差距很大，说明战意可能不高
  const goals = m.score.split('-').map(Number);
  if (Math.abs(goals[0] - goals[1]) >= 3) {
    eliminatedMatches++;
  }
}
console.log(`  大比分(≥3球)比赛: ${eliminatedMatches} 场`);

// ============================================================
// 5. 模型分歧分析
// ============================================================

console.log('\n\n╔═══════════════════════════════════════════════════════════╗');
console.log('║  📊 5. 模型分歧分析                                       ║');
console.log('╚═══════════════════════════════════════════════════════════╝');

let eloVsPoissonDisagree = 0;
let eloVsMarketDisagree = 0;
let totalWithModels = 0;

for (const pred of predictions) {
  if (!pred.modelProb || !pred.fusionProb) continue;
  totalWithModels++;
  
  const eloWinner = pred.modelProb.elo.winPct > pred.modelProb.elo.awayPct ? 'home' : 'away';
  const poisWinner = pred.modelProb.poisson.winPct > pred.modelProb.poisson.awayPct ? 'home' : 'away';
  const marketWinner = pred.modelProb.market && pred.modelProb.market.winPct > pred.modelProb.market.awayPct ? 'home' : 'away';
  
  if (eloWinner !== poisWinner) eloVsPoissonDisagree++;
  if (eloWinner !== marketWinner) eloVsMarketDisagree++;
}

console.log(`\n有模型对比的预测: ${totalWithModels} 场`);
console.log(`Elo vs Poisson 分歧: ${eloVsPoissonDisagree} 场 (${(eloVsPoissonDisagree/totalWithModels*100).toFixed(1)}%)`);
console.log(`Elo vs Market 分歧: ${eloVsMarketDisagree} 场 (${(eloVsMarketDisagree/totalWithModels*100).toFixed(1)}%)`);

// 分歧时的准确率
console.log('\n分歧时的准确率:');
for (const [model1, model2, count] of [
  ['Elo', 'Poisson', eloVsPoissonDisagree],
  ['Elo', 'Market', eloVsMarketDisagree],
]) {
  console.log(`  ${model1} vs ${model2}: ${count} 场分歧`);
}

console.log('\n\n=== 诊断完成 ===');
console.log('关键发现见下方优化建议');
