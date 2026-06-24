#!/usr/bin/env node

/**
 * ⚽ 复盘分析引擎 v2
 * 对已完赛48场逐一模拟，计算偏差
 */

import * as fs from 'fs';
import * as path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const dbPath = path.join(__dirname, 'db', 'worldcup.json');

const db = JSON.parse(fs.readFileSync(dbPath, 'utf8'));
const matches = db.completedMatches || [];
const teams = db.teams || {};
const recentMatches = db.recentMatches || {};
const headToHead = db.headToHead || {};

// ============================================================
// 导入引擎
// ============================================================
const enginePath = path.join(__dirname, 'model', 'engine.mjs');
const engine = await import(`file:///${enginePath.replace(/\\/g, '/')}`);

// 初始化 Elo
engine.batchUpdateElo(teams, matches);

// ============================================================
// 模拟函数
// ============================================================
function simulate(match, weightOverrides = {}) {
  try {
    const [hScore, aScore] = match.score.split('-').map(Number);
    const actualResult = hScore > aScore ? 'home' : hScore === aScore ? 'draw' : 'away';
    
    const opts = {
      monteCarloRuns: 5000,
      isFinalRound: false,
      isKnockout: false,
      eloWeight: weightOverrides.elo ?? 0.25,
      poissonWeight: weightOverrides.poisson ?? 0.30,
      economicWeight: weightOverrides.economic ?? 0.10,
      marketWeight: weightOverrides.market ?? 0.35,
    };
    
    if (match.oddsHome) {
      opts.oddsHome = match.oddsHome;
      opts.oddsDraw = match.oddsDraw;
      opts.oddsAway = match.oddsAway;
    }
    if (match.handicap) {
      opts.handicap = match.handicap;
    }
    
    const pred = engine.fusionPredict(match.home, match.away, teams, recentMatches, headToHead, opts);
    if (pred.error) return null;
    
    // 模型最高概率结果
    const topResult = pred.fusion.winPct >= pred.fusion.drawPct && pred.fusion.winPct >= pred.fusion.awayPct ? 'home'
      : pred.fusion.drawPct >= pred.fusion.winPct && pred.fusion.drawPct >= pred.fusion.awayPct ? 'draw'
      : 'away';
    
    const correctDirection = topResult === actualResult;
    
    // 预测比分偏差
    const predScore = pred.fusion.top5[0].score;
    const [pH, pA] = predScore.split('-').map(Number);
    const scoreDiff = Math.abs(pH - hScore) + Math.abs(pA - aScore);
    
    return {
      home: match.home,
      away: match.away,
      score: match.score,
      actualResult,
      predResult: topResult,
      correctDirection,
      predTop1: predScore,
      top1Pct: pred.fusion.top5[0].pct,
      homePct: pred.fusion.winPct,
      drawPct: pred.fusion.drawPct,
      awayPct: pred.fusion.awayPct,
      lambdaH: pred.fusion.lambda.home,
      lambdaA: pred.fusion.lambda.away,
      scoreDiff,
      hasOdds: !!match.oddsHome,
      handicap: match.handicap || 0,
      oddsStr: match.oddsHome ? `${match.oddsHome}/${match.oddsDraw}/${match.oddsAway}` : '无',
      top5: pred.fusion.top5.map(s => `${s.score}(${s.pct}%)`).join(' '),
    };
  } catch (e) {
    return null;
  }
}

// ============================================================
// 执行复盘
// ============================================================
console.log('╔' + '═'.repeat(68) + '╗');
console.log('║  ⚽ 世界杯预测系统 v3.0 - 复盘分析                    ║');
console.log('║  48 场小组赛全面回测 + 偏差计算                       ║');
console.log('╚' + '═'.repeat(68) + '╝\n');

// 权重组合
const profiles = [
  { name: '默认(25/30/10/35)', w: { elo:0.25, poisson:0.30, economic:0.10, market:0.35 } },
  { name: '高Elo(40/30/10/20)', w: { elo:0.40, poisson:0.30, economic:0.10, market:0.20 } },
  { name: '高泊松(20/50/10/20)', w: { elo:0.20, poisson:0.50, economic:0.10, market:0.20 } },
  { name: '高市场(15/20/05/60)', w: { elo:0.15, poisson:0.20, economic:0.05, market:0.60 } },
  { name: '均衡(25/25/25/25)', w: { elo:0.25, poisson:0.25, economic:0.25, market:0.25 } },
];

// 主复盘: 默认权重
const results = matches.map(m => simulate(m, profiles[0].w)).filter(Boolean);
const total = results.length;
const correct = results.filter(r => r.correctDirection).length;
const correctPct = (correct / total * 100).toFixed(1);

const withOdds = results.filter(r => r.hasOdds);
const woOddsCorrect = withOdds.filter(r => r.correctDirection).length;
const noOdds = results.filter(r => !r.hasOdds);
const noOddsCorrect = noOdds.filter(r => r.correctDirection).length;

console.log(`📊 默认权重复盘结果:\n`);
console.log(`   总场次: ${total}`);
console.log(`   ✅ 方向正确: ${correct}/${total} (${correctPct}%)`);
console.log(`   📊 有赔率: ${withOdds.length} 场 (正确 ${woOddsCorrect}, ${(woOddsCorrect/withOdds.length*100).toFixed(1)}%)`);
console.log(`   ❓ 无赔率: ${noOdds.length} 场 (正确 ${noOddsCorrect}, ${noOddsCorrect > 0 ? (noOddsCorrect/noOdds.length*100).toFixed(1)+'%' : 'N/A'})`);

// 按小组
const groups = {};
for (const r of results) {
  const m = matches.find(x => x.home === r.home && x.away === r.away);
  const g = m?.group || '?';
  if (!groups[g]) groups[g] = { t:0, c:0 };
  groups[g].t++;
  if (r.correctDirection) groups[g].c++;
}
console.log('\n📋 按小组方向正确率:\n');
for (const [g, s] of Object.entries(groups).sort()) {
  const bar = '█'.repeat(Math.round(s.c/s.t*10)) + '░'.repeat(10 - Math.round(s.c/s.t*10));
  console.log(`   ${g}组: ${bar} ${s.c}/${s.t} (${(s.c/s.t*100).toFixed(0)}%)`);
}

// 错误比赛
console.log('\n❌ 方向错误比赛详情:\n');
const wrong = results.filter(r => !r.correctDirection);
for (const r of wrong) {
  const emoji = r.actualResult === 'home' ? '🏠' : r.actualResult === 'draw' ? '🤝' : '✈️';
  console.log(`   ${r.home} ${r.score} ${r.away}`);
  console.log(`     模型: ${r.homePct}% / ${r.drawPct}% / ${r.awayPct}%  | 实际: ${emoji} ${r.actualResult}`);
  console.log(`     Top1: ${r.predTop1} (${r.top1Pct}%)  | 赔率: ${r.oddsStr}`);
  console.log(`     λ: ${r.lambdaH.toFixed(2)} : ${r.lambdaA.toFixed(2)}  | 让球: ${r.handicap}`);
  console.log('');
}

// 比分偏差
console.log('📊 比分偏差分布:\n');
const bins = { '0分(精确命中)': 0, '1-2分': 0, '3-4分': 0, '5分+': 0 };
for (const r of results) {
  if (r.scoreDiff === 0) bins['0分(精确命中)']++;
  else if (r.scoreDiff <= 2) bins['1-2分']++;
  else if (r.scoreDiff <= 4) bins['3-4分']++;
  else bins['5分+']++;
}
for (const [k, v] of Object.entries(bins)) {
  console.log(`   ${k}: ${v} 场 (${(v/total*100).toFixed(1)}%)`);
}

// 权重组合对比
console.log('\n🔄 权重组合对比:\n');
for (const p of profiles) {
  const r2 = matches.map(m => simulate(m, p.w)).filter(Boolean);
  const c = r2.filter(r => r.correctDirection).length;
  const pct = (c / r2.length * 100).toFixed(1);
  const bar = '█'.repeat(Math.round(c/r2.length*10)) + '░'.repeat(10 - Math.round(c/r2.length*10));
  console.log(`   ${p.name}: ${bar} ${c}/${r2.length} (${pct}%)`);
}

// 赔率偏差
console.log('\n📈 模型 vs 市场 偏差 >15%:\n');
for (const r of results) {
  if (!r.hasOdds) continue;
  const m = matches.find(x => x.home === r.home && x.away === r.away);
  if (!m) continue;
  const ih = 1/m.oddsHome, id = 1/m.oddsDraw, ia = 1/m.oddsAway;
  const ti = ih + id + ia;
  const mktHome = (ih/ti*100);
  const diff = (r.homePct - mktHome);
  if (Math.abs(diff) > 15) {
    const dir = diff > 0 ? '模型更看好主队' : '市场更看好主队';
    console.log(`   ${r.home} vs ${r.away}: 模型=${r.homePct.toFixed(0)}% 市场=${mktHome.toFixed(0)}% (${dir}, 偏差${Math.abs(diff).toFixed(0)}%)`);
  }
}

// 让球盘口
console.log('\n📐 让球盘口方向:\n');
let hdcpT=0, hdcpC=0;
for (const r of results) {
  if (!r.handicap) continue;
  hdcpT++;
  const m = matches.find(x => x.home === r.home && x.away === r.away);
  if (!m) continue;
  const [h,a] = m.score.split('-').map(Number);
  const effH = h + r.handicap;
  const hdcpActual = effH > a ? 'home' : effH === a ? 'draw' : 'away';
  const hdcpPred = r.homePct >= r.drawPct && r.homePct >= r.awayPct ? 'home' : r.awayPct > r.homePct && r.awayPct > r.drawPct ? 'away' : 'draw';
  if (hdcpActual === hdcpPred) hdcpC++;
}
console.log(`   让球方向正确: ${hdcpC}/${hdcpT} (${(hdcpC/hdcpT*100).toFixed(1)}%)`);

// 改进建议
console.log('\n💡 改进建议:\n');
const wrongHomeFav = wrong.filter(r => r.homePct > 50).length;
const wrongAwayFav = wrong.filter(r => r.awayPct > 50).length;
const wrongDraws = wrong.filter(r => r.drawPct > Math.max(r.homePct, r.awayPct)).length;
const oddsWrong = wrong.filter(r => r.hasOdds).length;

if (wrongHomeFav > wrongAwayFav + 1) console.log(`   1️⃣ 主队偏多: 猜错${wrongHomeFav}场主队热门 — 主场优势因子偏高`);
if (wrongAwayFav > wrongHomeFav + 1) console.log(`   2️⃣ 客队偏多: 猜错${wrongAwayFav}场客队热门 — 客场λ偏低`);
if (wrongDraws > 2) console.log(`   3️⃣ 平局偏差: 猜错${wrongDraws}场平局 — 平率模型需调整`);
if (oddsWrong > 2) console.log(`   4️⃣ 有赔率仍错${oddsWrong}场 — 赔率权重${profiles[0].w.market*100}%不够或赔率λ转换需改进`);

// 精确命中比赛
const exact = results.filter(r => r.scoreDiff === 0);
console.log(`\n🎯 精确命中比分: ${exact.length} 场`);
for (const r of exact) {
  console.log(`   ✅ ${r.home} ${r.score} ${r.away} (λ ${r.lambdaH.toFixed(2)}:${r.lambdaA.toFixed(2)})`);
}

console.log(`\n${'─'.repeat(68)}`);
console.log('✅ 复盘完成');
