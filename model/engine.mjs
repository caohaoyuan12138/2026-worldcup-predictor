#!/usr/bin/env node

/**
 * ⚽ 世界杯预测引擎 v4.0 — 三层架构
 * 
 *   第一层 (λ计算层): calcLambda() — 进攻/防守/动量/战意 → 预期进球
 *   第二层 (修正层):   monteCarlo() — Dixon-Coles + 动态ρ + 低λ平率权重
 *   第三层 (情境层):   bayesianAdjust() — 贝叶斯情境 + 赔率融合 + 集成加权
 * 
 *   评估层: evaluatePredictions() — Log Loss / Brier Score / ROI
 */

import * as fs from 'fs';
import * as path from 'path';
import { fileURLToPath } from 'url';

// 战术分析模块 (可选加载)
let __tactics = {};
try {
  __tactics = await import('./tactics.mjs');
  __tactics.loadTactics();
} catch (e) {
  __tactics = { tacticalLambdaAdjust: () => ({ adjust: 1.0 }), fullTacticalAnalysis: () => ({}), loadTactics: () => ({}) };
}

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const DB_DIR = path.join(__dirname, '..', 'db');

// ============================================================
// 0. 工具函数 & 常量
// ============================================================
export function factorial(n) {
  if (n <= 1) return 1;
  let r = 1;
  for (let i = 2; i <= n; i++) r *= i;
  return r;
}

export function comb(n, k) {
  if (k < 0 || k > n) return 0;
  if (k === 0 || k === n) return 1;
  k = Math.min(k, n - k);
  let r = 1;
  for (let i = 1; i <= k; i++) r = r * (n - k + i) / i;
  return r;
}

export function eloExpected(eloA, eloB) {
  return 1 / (1 + Math.pow(10, (eloB - eloA) / 400));
}

export function updateElo(eloA, eloB, goalA, goalB, K = 30) {
  const expectedA = eloExpected(eloA, eloB);
  const gd = goalA - goalB;
  let scoreA;
  if (gd > 0) { 
    // 大胜过热限制: 净胜4球以上时, gdFactor不再增长
    // 7-1的Elo提升效果与5-0相当, 避免一场大胜扭曲全局
    const cappedGd = Math.min(Math.abs(gd), 4);  // 最多算4球净胜
    const gdFactor = Math.min(Math.log(cappedGd + 1) / Math.LN2, 1.5); 
    scoreA = 1 + gdFactor * 0.3; 
  }
  else if (gd === 0) scoreA = 0.5;
  else scoreA = 0;  // 输球方score固定为0, 但gdBias会体现在expected差值中
  return { home: Math.round(eloA + K * (scoreA - expectedA)), away: Math.round(eloB + K * ((1 - scoreA) - (1 - expectedA))) };
}

export function rankToElo(rank) {
  return Math.round(2100 - (rank - 1) * (900 / 47));
}

// ============================================================
// 2. 经济学模型
// ============================================================
export function economicModel(team, opponent, isHome) {
  let base = 1.0;
  const gdpRatio = Math.log(team.gdpPerCapita || 20000) / Math.log(50000);
  base *= (0.7 + gdpRatio * 0.5);
  const popRatio = Math.log(team.population || 10) / Math.log(200);
  base *= (0.8 + popRatio * 0.4);
  if (team.isHost) base *= 1.20;
  const climatePenalty = climateFactor(team.climate, opponent.climate, isHome);
  base *= climatePenalty;
  const altDiff = (team.avgAltitude || 0) - (opponent.avgAltitude || 0);
  if (altDiff > 1000 && !isHome) base *= 1.10;
  return Math.round(base * 100) / 100;
}

function climateFactor(homeClimate, awayClimate, isHome) {
  const m = { '热带': { '热带': 1.0, '温带': 0.95, '寒带': 0.90, '干旱': 0.95 },
    '温带': { '热带': 0.95, '温带': 1.0, '寒带': 0.95, '干旱': 1.0 },
    '寒带': { '热带': 0.92, '温带': 0.97, '寒带': 1.0, '干旱': 0.97 },
    '干旱': { '热带': 0.95, '温带': 1.0, '寒带': 0.95, '干旱': 1.0 } };
  return (m[homeClimate] || {})[awayClimate] || 1.0;
}

// ============================================================
// 3. 动量计算 (从 recentMatches 读取真实数据)
// ============================================================
function calcMomentum(teamName, recentMatches, N = 10) {
  if (!recentMatches || !recentMatches[teamName]) return { played: 0, gfPerGame: 0, gaPerGame: 0, winRate: 0, drawRate: 0, lossRate: 0, gd: 0 };
  const matches = recentMatches[teamName].slice(0, N);
  let totalGf = 0, totalGa = 0, wins = 0, draws = 0, losses = 0;
  for (const m of matches) {
    if (!m.score) continue;
    const parts = m.score.split('-').map(Number);
    if (parts.length !== 2 || isNaN(parts[0]) || isNaN(parts[1])) continue;
    let [h, a] = parts;
    // 大胜过热限制: 单场进球最多算4球, 失球最多算4球
    // 避免7-1这种极端比分扭曲 momentum 数据
    h = Math.min(h, 4);
    a = Math.min(a, 4);
    const isHome = m.venue === '主';
    if (isHome) { totalGf += h; totalGa += a; if (h > a) wins++; else if (h === a) draws++; else losses++; }
    else { totalGf += a; totalGa += h; if (a > h) wins++; else if (a === h) draws++; else losses++; }
  }
  const count = matches.length;
  return { played: count, gfPerGame: count > 0 ? totalGf / count : 0, gaPerGame: count > 0 ? totalGa / count : 0, winRate: count > 0 ? wins / count : 0, drawRate: count > 0 ? draws / count : 0, lossRate: count > 0 ? losses / count : 0, gd: totalGf - totalGa };
}

// ============================================================
// 4. 历史交锋修正
// ============================================================
function headToHeadFactor(home, away, headToHead) {
  if (!headToHead) return 1.0;
  const key = [home, away].sort().join('|');
  const h2h = headToHead[key];
  if (!h2h || h2h.total < 3) return 1.0;
  const aWins = home === h2h.teamA ? h2h.aWins : h2h.bWins;
  const bWins = away === h2h.teamA ? h2h.aWins : h2h.bWins;
  const draws = h2h.draws;
  const total = h2h.total;
  const homeWinRate = aWins / total;
  const awayWinRate = bWins / total;
  // 如果历史交手有明显倾向，微调 ±5%
  if (homeWinRate > 0.5) return 1.03 + (homeWinRate - 0.5) * 0.06;
  if (awayWinRate > 0.5) return 0.97 - (awayWinRate - 0.5) * 0.06;
  return 1.0;
}

// ============================================================
// 5. 泊松 λ 计算 (含真实近10场 + 历史交锋)
// ============================================================
export function calcLambda(teamName, opponentName, isHome, teams, recentMatches, ctx = {}) {
  const team = teams[teamName];
  const opponent = teams[opponentName];
  if (!team || !opponent) return 1.0;

  let lambda = team.attackBase || 1.0;
  if (isHome) lambda *= (ctx.homeAdvantage || 1.08);
  lambda *= (team.styleFactor || 1.0);

  // 真实近10场数据修正 (你的 Excel 数据)
  const momentumData = calcMomentum(teamName, recentMatches, ctx.momentumGames || 10);
  if (momentumData.played >= 3) {
    const preseasonW = ctx.preseasonWeight || 0.6;
    const realW = ctx.realPerformanceWeight || 0.4;
    lambda = lambda * preseasonW + momentumData.gfPerGame * realW;
    // 状态修正 (胜率高 → 进攻加成)
    const formFactor = 0.9 + momentumData.winRate * 0.2;
    lambda *= formFactor;
    // 防守表现修正对手进球
  }

  // 对手防守修正
  const od = 1.0 - ((opponent.defenseBase || 1.0) - 0.8) * 0.2;
  lambda *= Math.max(0.7, Math.min(1.3, od));

  // 攻防差值
  const sd = ((team.attackBase || 1.0) - (team.defenseBase || 1.0)) - ((opponent.attackBase || 1.0) - (opponent.defenseBase || 1.0));
  if (sd > 0.5) lambda *= (isHome ? 1.08 : 1.05);
  else if (sd < -0.5) lambda *= (isHome ? 0.92 : 0.95);

  // 补充数据 (可选, 没有就跳过)
  if (team.attackThirdPassPct !== undefined && team.attackThirdPassPct > 0) lambda *= (0.8 + team.attackThirdPassPct / 500);
  if (team.shotConversion !== undefined && team.shotConversion > 0) lambda *= (0.85 + team.shotConversion / 200);
  if (team.top50Scorers !== undefined && team.top50Scorers >= 2) lambda *= 1.08;
  else if (team.top50Scorers !== undefined && team.top50Scorers >= 1) lambda *= 1.04;

  // 历史交锋修正
  const h2h = ctx.headToHead || {};
  const h2hFactor = headToHeadFactor(teamName, opponentName, h2h);
  lambda *= h2hFactor;

  // 大赛光环
  const titles = team.worldCupTitles || 0;
  if (titles >= 2) lambda *= 1.05;
  if (titles >= 4) lambda *= 1.03;

  // 末轮战意修正 (出线形势影响) — v3.2 增强版
  // 基于复盘教训: 已出线球队轮换效应、必须赢球队拼劲加成
  if (ctx.isFinalRound) {
    const urgency = (ctx.teamUrgency && ctx.teamUrgency[teamName]) || 0;
    // urgency: 0=已出局(无战意), 1=渺茫(负战意), 2=需赢+看别人(强战意), 3=需赢(极强战意), 4=打平就出线(稳), 5=已出线(保守)
    if (urgency === 3) lambda *= 1.15;  // 需赢球: 全力进攻 (从1.12→1.15)
    else if (urgency === 2) lambda *= 1.08;  // 需赢+看别人: 有希望, 进攻 (从1.06→1.08)
    else if (urgency === 1) lambda *= 0.92;  // 渺茫: 信心不足 (从0.95→0.92)
    else if (urgency === 0) lambda *= 0.85;  // 已出局: 斗志低落 (从0.88→0.85)
    else if (urgency === 5) lambda *= 0.82;  // 已出线: 轮换保存体力 (从0.90→0.82, 大幅调低)
    else if (urgency === 4) lambda *= 0.93;  // 打平就出线: 保守 (从0.95→0.93)
    // 已出线球队防守也会受影响
    if (urgency === 5) {
      // 已出线球队防守注意力下降 → 对手进球λ增加
      // 在对手的calcLambda中通过对手防守修正体现
    }
    lambda *= (ctx.finalRoundFactor || 0.93);  // 从0.95→0.93, 最后一轮整体进球偏低
  }
  
  // 对手已出线时, 本方进攻加成 (对手轮换防守下降)
  if (ctx.isFinalRound) {
    const oppUrgency = (ctx.teamUrgency && ctx.teamUrgency[opponentName]) || 0;
    if (oppUrgency === 5) lambda *= 1.12;  // 对手已出线轮换 → 本方进攻机会增加
    else if (oppUrgency === 0) lambda *= 1.08;  // 对手已出局斗志低 → 本方进攻机会增加
  }
  if (ctx.isKnockout) lambda *= 0.88;

  // 战术修正 (由外层 fusionPredict 传入)
  if (ctx.tacticalAdj && ctx.tacticalAdj.teamName === teamName && ctx.tacticalAdj.adjust != null) {
    lambda *= ctx.tacticalAdj.adjust;
  }

  return Math.round(lambda * 100) / 100;
}

// ============================================================
// 6. 赔率市场模型
// ============================================================
export function oddsToProb(oddsHome, oddsDraw, oddsAway) {
  if (!oddsHome || !oddsDraw || !oddsAway || oddsHome <= 0 || oddsDraw <= 0 || oddsAway <= 0) return null;
  const impliedHome = 1 / oddsHome, impliedDraw = 1 / oddsDraw, impliedAway = 1 / oddsAway;
  const overround = impliedHome + impliedDraw + impliedAway;
  return { homeWinPct: +(impliedHome / overround * 100).toFixed(1), drawPct: +(impliedDraw / overround * 100).toFixed(1), awayWinPct: +(impliedAway / overround * 100).toFixed(1), overround: +(overround * 100).toFixed(2) };
}

export function handicapAdjust(homeWinPct, drawPct, awayWinPct, handicap) {
  if (!handicap || handicap === 0) return { homeWinPct, drawPct, awayWinPct };
  let adj = { homeWinPct, drawPct, awayWinPct };
  // 深盘修正: 让-2 = 主队需赢3球, 市场认为实力悬殊
  const absH = Math.abs(handicap);
  if (handicap > 0) {
    // 主队让球
    const boost = Math.min(absH * 15, 40); // -2 → +30%, -3 → +40%
    adj.homeWinPct = Math.min(homeWinPct + boost, 92);
    adj.awayWinPct = Math.max(awayWinPct - boost * 0.6, 2);
    adj.drawPct = Math.max(drawPct - boost * 0.4, 3);
  } else {
    // 客队让球
    const boost = Math.min(absH * 15, 40);
    adj.awayWinPct = Math.min(awayWinPct + boost, 92);
    adj.homeWinPct = Math.max(homeWinPct - boost * 0.6, 2);
    adj.drawPct = Math.max(drawPct - boost * 0.4, 3);
  }
  const total = adj.homeWinPct + adj.drawPct + adj.awayWinPct;
  adj.homeWinPct = +(adj.homeWinPct / total * 100).toFixed(1);
  adj.drawPct = +(adj.drawPct / total * 100).toFixed(1);
  adj.awayWinPct = +(adj.awayWinPct / total * 100).toFixed(1);
  return adj;
}

// ============================================================
// 7. 蒙特卡洛 (含 Dixon-Coles 低比分修正)
// ============================================================
export function monteCarlo(lH, lA, N = 5000, rho = 0.02) {
  function ps(lambda) {
    const L = Math.exp(-lambda);
    let k = 0, p = 1;
    do { k++; p *= Math.random(); } while (p > L);
    return k - 1;
  }

  // Dixon-Coles tau: 调整 0-0, 0-1, 1-0, 1-1 概率
  function tau(i, j, l1, l2, r) {
    if (i === 0 && j === 0) return 1 - l1 * l2 * r;
    if (i === 0 && j === 1) return 1 + l1 * r;
    if (i === 1 && j === 0) return 1 + l2 * r;
    if (i === 1 && j === 1) return 1 - r;
    return 1;
  }

  const results = {};
  let hW = 0, dr = 0, aW = 0, tG = 0;

  for (let i = 0; i < N; i++) {
    const h = ps(lH);
    const a = ps(lA);
    const t = tau(h, a, lH, lA, rho);
    if (t < 1 && Math.random() > t) { i--; continue; }
    const key = `${h}-${a}`;
    results[key] = (results[key] || 0) + 1;
    if (h > a) hW++;
    else if (h === a) dr++;
    else aW++;
    tG += h + a;
  }

  const sorted = Object.entries(results)
    .map(([score, count]) => ({ score, home: Number(score.split('-')[0]), away: Number(score.split('-')[1]), count, pct: +(count / N * 100).toFixed(1) }))
    .sort((a, b) => b.count - a.count);

  return { sorted, top5: sorted.slice(0, 5), top10: sorted.slice(0, 10), homeWinPct: +(hW / N * 100).toFixed(1), drawPct: +(dr / N * 100).toFixed(1), awayWinPct: +(aW / N * 100).toFixed(1), avgGoals: +(tG / N).toFixed(2), totalRuns: N, scoreMatrix: buildScoreMatrix(sorted, 6) };
}

function buildScoreMatrix(sorted, size = 6) {
  const matrix = [];
  for (let h = 0; h < size; h++) {
    const row = [];
    for (let a = 0; a < size; a++) {
      const found = sorted.find(s => s.home === h && s.away === a);
      row.push(found ? found.pct : 0);
    }
    matrix.push(row);
  }
  return matrix;
}

/**
 * 计算动态 DC ρ
 */
export function calcDynamicRho(eloH, eloA, lambdaH, lambdaA, dcRho = 0.02, isFinalRound = false, teamUrgency = {}, home = '', away = '') {
  const eloDiff = Math.abs(eloH - eloA);
  let rho = eloDiff < 50 ? 0.06 : eloDiff < 100 ? 0.03 : Math.max(0.02, dcRho);
  if (lambdaH < 0.8 && lambdaA < 0.8) rho = Math.max(rho, 0.08);
  if ((lambdaH < 0.5 || lambdaA < 0.5) && lambdaH < 1.0 && lambdaA < 1.0) rho = Math.max(rho, 0.10);
  if (isFinalRound) {
    const hU = teamUrgency[home] || 0, aU = teamUrgency[away] || 0;
    if ((hU === 4 || hU === 5) && (aU === 4 || aU === 5)) rho = Math.max(rho, 0.09);
  }
  return Math.min(rho, 0.15);
}

/**
 * 快速解析胜负估算 (曹昊源模型)
 */
export function fastWinDrawLoss(a, b) {
  if (a <= 0 || b <= 0) return { homeWinPct: a > b ? 100 : 0, drawPct: 0, awayWinPct: b > a ? 100 : 0 };
  const p1 = a / (a + b), p2 = b / (a + b), tl = a + b;
  function pp(k, lam) { return Math.exp(-lam) * Math.pow(lam, k) / factorial(k); }
  let hw = 0, dr = 0, aw = 0;
  for (let t = 0; t <= 15; t++) {
    const pt = pp(t, tl);
    if (pt < 0.001) continue;
    if (t % 2 === 0) {
      dr += pt * comb(t, t/2) * Math.pow(p1 * p2, t/2);
      for (let hg = Math.floor(t/2)+1; hg <= t; hg++) hw += pt * comb(t, hg) * Math.pow(p1, hg) * Math.pow(p2, t - hg);
      for (let ag = Math.floor(t/2)+1; ag <= t; ag++) aw += pt * comb(t, ag) * Math.pow(p2, ag) * Math.pow(p1, t - ag);
    } else {
      for (let hg = Math.ceil(t/2); hg <= t; hg++) {
        const ag = t - hg;
        if (hg > ag) hw += pt * comb(t, hg) * Math.pow(p1, hg) * Math.pow(p2, ag);
        else aw += pt * comb(t, ag) * Math.pow(p2, ag) * Math.pow(p1, hg);
      }
    }
  }
  const tp = hw + dr + aw || 1;
  return { homeWinPct: +(hw/tp*100).toFixed(1), drawPct: +(dr/tp*100).toFixed(1), awayWinPct: +(aw/tp*100).toFixed(1) };
}

// ════════════════════════════════════════════════════════════
// 第三层: 情境调整层 — 贝叶斯风格调整
// ════════════════════════════════════════════════════════════

/**
 * 贝叶斯情境调整
 */
export function bayesianAdjust(baseProbs, context = {}) {
  let h = baseProbs.homeWinPct, d = baseProbs.drawPct, a = baseProbs.awayWinPct;
  const hU = context.homeUrgency || 0, aU = context.awayUrgency || 0;
  if (hU === 3) { h *= 1.08; d *= 0.90; a *= 0.85; }
  if (aU === 3) { a *= 1.08; d *= 0.90; h *= 0.85; }
  if ((hU === 4 || hU === 5) && (aU === 4 || aU === 5)) { d *= 1.20; h *= 0.92; a *= 0.92; }
  const hm = context.homeKeyInjuries || 0, am = context.awayKeyInjuries || 0;
  if (hm > 0) { h *= (1 - 0.05*hm); a *= (1 + 0.03*hm); }
  if (am > 0) { a *= (1 - 0.05*am); h *= (1 + 0.03*am); }
  const h2 = context.h2hHomeAdvantage || 1.0;
  if (h2 > 1.05) { h *= 1.03; a *= 0.97; } else if (h2 < 0.95) { a *= 1.03; h *= 0.97; }
  if (context.isKnockout) { d *= 1.10; h *= 0.95; a *= 0.95; }
  const total = h + d + a;
  return { homeWinPct: +(h/total*100).toFixed(1), drawPct: +(d/total*100).toFixed(1), awayWinPct: +(a/total*100).toFixed(1) };
}

// ════════════════════════════════════════════════════════════
// 评估层: 模型评估指标
// ════════════════════════════════════════════════════════════

/**
 * 评估预测结果
 */
export function evaluatePredictions(predictions, actualResults) {
  if (!predictions || !actualResults || predictions.length === 0) return { error: '无数据' };
  let ll = 0, bs = 0, dc = 0, cnt = 0;
  for (let i = 0; i < Math.min(predictions.length, actualResults.length); i++) {
    const p = predictions[i], a = actualResults[i];
    if (!p || !a) continue;
    const [hs, as] = a.score.split('-').map(Number);
    if (isNaN(hs) || isNaN(as)) continue;
    const ar = hs > as ? 'home' : hs === as ? 'draw' : 'away';
    const ph = p.homeWinPct/100, pd = p.drawPct/100, pa = p.awayWinPct/100;
    const pa_ = ar === 'home' ? ph : ar === 'draw' ? pd : pa;
    ll += Math.log(Math.max(pa_, 0.0001));
    if (ar === 'home') bs += Math.pow(ph-1,2) + Math.pow(pd,2) + Math.pow(pa,2);
    else if (ar === 'draw') bs += Math.pow(pd-1,2) + Math.pow(ph,2) + Math.pow(pa,2);
    else bs += Math.pow(pa-1,2) + Math.pow(ph,2) + Math.pow(pd,2);
    const pr = ph > pd && ph > pa ? 'home' : pd > ph && pd > pa ? 'draw' : 'away';
    if (pr === ar) dc++;
    cnt++;
  }
  return { logLoss: cnt > 0 ? +(-ll/cnt).toFixed(4) : 0, brierScore: cnt > 0 ? +(bs/cnt).toFixed(4) : 0, directionAccuracy: cnt > 0 ? +(dc/cnt*100).toFixed(1) : 0, sampleCount: cnt };
}

/**
 * 模拟投注 ROI
 */
export function simulateBetting(predictions, actualResults, threshold = 0.05) {
  let tb = 0, w = 0, pft = 0;
  for (let i = 0; i < Math.min(predictions.length, actualResults.length); i++) {
    const p = predictions[i], a = actualResults[i];
    if (!p || !a || !p.oddsHome) continue;
    const [hs, as] = a.score.split('-').map(Number);
    if (isNaN(hs) || isNaN(as)) continue;
    const ar = hs > as ? 'home' : hs === as ? 'draw' : 'away';
    for (const bet of [{t:'home',mp:p.homeWinPct/100,od:p.oddsHome},{t:'draw',mp:p.drawPct/100,od:p.oddsDraw},{t:'away',mp:p.awayWinPct/100,od:p.oddsAway}]) {
      if (!bet.od) continue;
      if (bet.mp - 1/bet.od > threshold) {
        tb++;
        if (bet.t === ar) { w++; pft += bet.od - 1; } else { pft -= 1; }
      }
    }
  }
  return { totalBets: tb, wins: w, winRate: tb > 0 ? +(w/tb*100).toFixed(1) : 0, profit: +pft.toFixed(2), roi: tb > 0 ? +(pft/tb*100).toFixed(1) : 0 };
}

// ============================================================
// 8. 融合预测
// ============================================================
export function fusionPredict(home, away, teams, recentMatches, headToHead, options = {}) {
  const {
    monteCarloRuns = 5000, isFinalRound = false, isKnockout = false,
    oddsHome, oddsDraw, oddsAway, handicap, dcRho = 0.02,
    eloWeight = 0.25, poissonWeight = 0.30, economicWeight = 0.10, marketWeight = 0.35,
    teamUrgency = {}
  } = options;

  const teamHome = teams[home], teamAway = teams[away];
  if (!teamHome || !teamAway) return { error: `球队不存在: ${!teamHome ? home : away}` };

  // === 战术分析 (tactics.mjs) ===
  let tacticalInfo = null;
  let hTacticalAdj = null, aTacticalAdj = null;
  try {
    const { tacticalLambdaAdjust, fullTacticalAnalysis, loadTactics } = __tactics;
    const tactics = loadTactics();
    if (tactics && Object.keys(tactics).length > 0 && tactics[home] && tactics[away]) {
      tacticalInfo = fullTacticalAnalysis(home, away);
      const hAdj = tacticalLambdaAdjust(home, away, true, tactics);
      const aAdj = tacticalLambdaAdjust(away, home, false, tactics);
      if (hAdj && hAdj.adjust != null) hTacticalAdj = hAdj;
      if (aAdj && aAdj.adjust != null) aTacticalAdj = aAdj;
    }
  } catch (e) {
    // 战术数据未加载, 跳过
  }

  // === A. Elo ===
  const eloH = teamHome.eloRating || rankToElo(teamHome.rank || 50);
  const eloA = teamAway.eloRating || rankToElo(teamAway.rank || 50);
  const expectedH = eloExpected(eloH, eloA);
  const eloRawHomePct = expectedH * 100;
  const eloRawAwayPct = (1 - expectedH) * 100;
  // Elo 平率估算 — 考虑多种因素
  let baseDrawPct = 27 - Math.abs(eloH - eloA) * 0.012;  // 基础: 实际世界杯平率25.9%, 提升基准并降低Elo差衰减
  // 主观因素: 末轮战意影响平率
  const homeUrgency = teamUrgency[home] || 0;
  const awayUrgency = teamUrgency[away] || 0;
  // 双方都保守（已出线/打平就出线）→ 平率升高
  if ((homeUrgency === 4 || homeUrgency === 5) && (awayUrgency === 4 || awayUrgency === 5)) {
    baseDrawPct *= 1.25;  // 都保守, 各拿1分
  }
  // 一方需赢球 → 平率降低（但世界杯实战中需赢球方经常被逼平, 降低调整幅度）
  if (homeUrgency === 3 || awayUrgency === 3) baseDrawPct *= 0.90;
  // 淘汰赛平率降低
  if (isKnockout) baseDrawPct *= 0.85;
  // 大赛修正: 世界杯小组赛平局显著更多(实际25.9%), 提高系数
  baseDrawPct *= 1.25;
  
  const eloDrawPctEstimate = Math.max(10, Math.min(38, Math.round(baseDrawPct)));
  const eloHomePct = +((eloRawHomePct / (eloRawHomePct + eloRawAwayPct)) * (100 - eloDrawPctEstimate)).toFixed(1);
  const eloAwayPct = +((eloRawAwayPct / (eloRawHomePct + eloRawAwayPct)) * (100 - eloDrawPctEstimate)).toFixed(1);
  const eloDrawPct = +(100 - eloHomePct - eloAwayPct).toFixed(1);

  // === B. 泊松 (含真实近10场 + 历史交锋 + Dixon-Coles) ===
  const ctx = { isFinalRound, isKnockout, homeAdvantage: options.homeAdvantage || 1.08, headToHead, teamUrgency: options.teamUrgency || {} };
  const poissonLH = calcLambda(home, away, true, teams, recentMatches, { ...ctx, tacticalAdj: hTacticalAdj ? { teamName: home, adjust: hTacticalAdj.adjust } : null });
  const poissonLA = calcLambda(away, home, false, teams, recentMatches, { ...ctx, tacticalAdj: aTacticalAdj ? { teamName: away, adjust: aTacticalAdj.adjust } : null });
  // 动态 DC ρ: 实力接近 ρ 升高 (增加平局), 实力悬殊 ρ 降低
  const eloDiff = Math.abs(eloH - eloA);
  let dynamicRho = eloDiff < 50 ? 0.06 : eloDiff < 100 ? 0.03 : Math.max(0.02, dcRho);
  // 低λ平率权重: 当两队预期进球都低时, 平率应显著提升
  // 复盘教训: 巴拉圭0-0澳大利亚(λ≈0.5/0.7), 实际0-0但模型选了客胜方向
  if (poissonLH < 0.8 && poissonLA < 0.8) {
    dynamicRho = Math.max(dynamicRho, 0.08);  // 低λ场景ρ从0.02-0.06提升到至少0.08
  }
  const poissonSim = monteCarlo(poissonLH, poissonLA, monteCarloRuns, dynamicRho);
  const fastRef = fastWinDrawLoss(poissonLH, poissonLA);

  // === C. 经济学 ===
  const ecoSim = monteCarlo(economicModel(teamHome, teamAway, true), economicModel(teamAway, teamHome, false), monteCarloRuns, 0);

  // === D. 市场赔率 ===
  let marketProb = null;
  if (oddsHome && oddsDraw && oddsAway) {
    marketProb = oddsToProb(oddsHome, oddsDraw, oddsAway);
    if (handicap && marketProb) marketProb = handicapAdjust(marketProb.homeWinPct, marketProb.drawPct, marketProb.awayWinPct, handicap);
  } else if (handicap) {
    // 有让球无赔率: 基于 Elo 生成隐含概率后再做 handicap 修正
    const eloDiff = Math.abs(eloH - eloA);
    const impliedHomePct = expectedH * 100;
    const impliedAwayPct = (1 - expectedH) * 100;
    const eloBasedDraw = Math.max(10, Math.min(32, 28 - eloDiff * 0.015));
    const totalNonDraw = impliedHomePct + impliedAwayPct;
    marketProb = {
      homeWinPct: +((impliedHomePct / totalNonDraw) * (100 - eloBasedDraw)).toFixed(1),
      drawPct: +eloBasedDraw.toFixed(1),
      awayWinPct: +((impliedAwayPct / totalNonDraw) * (100 - eloBasedDraw)).toFixed(1),
      overround: 100,
      isInferred: true
    };
    marketProb = handicapAdjust(marketProb.homeWinPct, marketProb.drawPct, marketProb.awayWinPct, handicap);
  } else {
    // 无赔率时, 用 Elo 差值生成隐含赔率
    const eloDiff = Math.abs(eloH - eloA);
    const impliedHomePct = expectedH * 100;
    const impliedAwayPct = (1 - expectedH) * 100;
    // 用 Elo 差值估算平率 (Elo 越接近平率越高)
    const eloBasedDraw = Math.max(10, Math.min(32, 28 - eloDiff * 0.015));
    const totalNonDraw = impliedHomePct + impliedAwayPct;
    marketProb = {
      homeWinPct: +((impliedHomePct / totalNonDraw) * (100 - eloBasedDraw)).toFixed(1),
      drawPct: +eloBasedDraw.toFixed(1),
      awayWinPct: +((impliedAwayPct / totalNonDraw) * (100 - eloBasedDraw)).toFixed(1),
      overround: 100,
      isInferred: true
    };
  }

  // === 融合 ===
  const totalWeight = eloWeight + poissonWeight + economicWeight + (marketProb ? marketWeight : 0);
  const baseW = eloWeight + poissonWeight + economicWeight;
  let fusedHomePct = (eloHomePct * eloWeight + poissonSim.homeWinPct * poissonWeight + ecoSim.homeWinPct * economicWeight) / baseW;
  let fusedDrawPct = (eloDrawPct * eloWeight + poissonSim.drawPct * poissonWeight + ecoSim.drawPct * economicWeight) / baseW;
  let fusedAwayPct = (eloAwayPct * eloWeight + poissonSim.awayWinPct * poissonWeight + ecoSim.awayWinPct * economicWeight) / baseW;

  if (marketProb) {
    fusedHomePct = (fusedHomePct * baseW + marketProb.homeWinPct * marketWeight) / totalWeight;
    fusedDrawPct = (fusedDrawPct * baseW + marketProb.drawPct * marketWeight) / totalWeight;
    fusedAwayPct = (fusedAwayPct * baseW + marketProb.awayWinPct * marketWeight) / totalWeight;
  }

  const fTotal = fusedHomePct + fusedDrawPct + fusedAwayPct;
  fusedHomePct = +(fusedHomePct / fTotal * 100).toFixed(1);
  fusedDrawPct = +(fusedDrawPct / fTotal * 100).toFixed(1);
  fusedAwayPct = +(fusedAwayPct / fTotal * 100).toFixed(1);

  // 融合 λ = 各模型加权, 含赔率
  let fusedLH = poissonLH * (poissonWeight + economicWeight) + (eloHomePct / 50) * eloWeight;
  let fusedLA = poissonLA * (poissonWeight + economicWeight) + (eloAwayPct / 50) * eloWeight;
  
  // 如果有赔率, 将赔率转换成 λ 并加权
  if (marketProb) {
    const marketLH = Math.max(0.3, Math.min(4.0, 0.15 + marketProb.homeWinPct * 0.035));
    const marketLA = Math.max(0.3, Math.min(4.0, 0.15 + marketProb.awayWinPct * 0.035));
    fusedLH = (fusedLH * (1 - marketWeight) + marketLH * marketWeight);
    fusedLA = (fusedLA * (1 - marketWeight) + marketLA * marketWeight);
  } else {
    fusedLH = fusedLH / (baseW);
    fusedLA = fusedLA / (baseW);
  }
  
  // 让球盘口 λ 修正 — 确保泊松模拟反映让球预期 (独立于赔率)
  if (handicap) {
    const handicapBoost = Math.abs(handicap) * 0.25;  // 让1球→λ+0.25, 让2球→λ+0.5
    if (handicap > 0) fusedLH += handicapBoost;
    else fusedLA += handicapBoost;
  }
  fusedLH = +(fusedLH).toFixed(2);
  fusedLA = +(fusedLA).toFixed(2);
  const fusedSim = monteCarlo(fusedLH, fusedLA, monteCarloRuns, dcRho);

  return {
    home, away,
    models: {
      elo: { rating: { home: eloH, away: eloA }, expected: eloHomePct, winPct: eloHomePct, drawPct: eloDrawPct, awayPct: eloAwayPct },
      poisson: { lambda: { home: poissonLH, away: poissonLA }, winPct: poissonSim.homeWinPct, drawPct: poissonSim.drawPct, awayPct: poissonSim.awayWinPct, dcRho },
      economic: { winPct: ecoSim.homeWinPct, drawPct: ecoSim.drawPct, awayPct: ecoSim.awayWinPct },
      market: marketProb ? { odds: { home: oddsHome, draw: oddsDraw, away: oddsAway }, handicap: handicap || null, winPct: marketProb.homeWinPct, drawPct: marketProb.drawPct, awayPct: marketProb.awayWinPct } : null,
    },
    weights: { elo: eloWeight, poisson: poissonWeight, economic: economicWeight, market: marketProb ? marketWeight : 0 },
    fusion: { lambda: { home: fusedLH, away: fusedLA }, winPct: fusedHomePct, drawPct: fusedDrawPct, awayPct: fusedAwayPct, top5: fusedSim.top5, avgGoals: fusedSim.avgGoals, totalRuns: fusedSim.totalRuns },
    tactics: tacticalInfo,
    timestamp: new Date().toISOString()
  };
}

// ============================================================
// 9. 积分榜 & 统计
// ============================================================
export function computeStandings(completedMatches, groups) {
  const standings = {};
  const teamGroup = {};
  for (const [g, teams] of Object.entries(groups)) for (const t of teams) teamGroup[t] = g;
  for (const m of completedMatches) {
    if (!m.score) continue;
    const [hG, aG] = m.score.split('-').map(Number);
    if (isNaN(hG) || isNaN(aG)) continue;
    for (const t of [m.home, m.away]) { if (!standings[t]) standings[t] = { team: t, group: teamGroup[t] || m.group, p: 0, w: 0, d: 0, l: 0, gf: 0, ga: 0, gd: 0, played: 0 }; }
    const h = standings[m.home], a = standings[m.away];
    h.played++; a.played++;
    h.gf += hG; h.ga += aG; a.gf += aG; a.ga += hG;
    if (hG > aG) { h.w++; h.p += 3; a.l++; }
    else if (hG === aG) { h.d++; h.p += 1; a.d++; a.p += 1; }
    else { h.l++; a.w++; a.p += 3; }
  }
  for (const s of Object.values(standings)) s.gd = s.gf - s.ga;
  return standings;
}

export function getStats(completedMatches) {
  const total = completedMatches.filter(m => m.score).length;
  let homeW = 0, draw = 0, awayW = 0, totalG = 0;
  const scoreDist = {};
  for (const m of completedMatches) {
    if (!m.score) continue;
    const [h, a] = m.score.split('-').map(Number);
    if (isNaN(h) || isNaN(a)) continue;
    if (h > a) homeW++; else if (h === a) draw++; else awayW++;
    totalG += h + a;
    scoreDist[`${h}-${a}`] = (scoreDist[`${h}-${a}`] || 0) + 1;
  }
  return { total, homeWinPct: total > 0 ? +(homeW / total * 100).toFixed(1) : 0, drawPct: total > 0 ? +(draw / total * 100).toFixed(1) : 0, awayWinPct: total > 0 ? +(awayW / total * 100).toFixed(1) : 0, avgGoals: total > 0 ? +(totalG / total).toFixed(2) : 0, scoreDist: Object.fromEntries(Object.entries(scoreDist).sort((a, b) => b[1] - a[1])) };
}

// ============================================================
// 10. 出线模拟
// ============================================================
export function simulateTournament(dbData, N = 10000, onProgress = null) {
  const { groups, teams, completedMatches, upcomingMatches, recentMatches, headToHead } = dbData;
  const groupNames = Object.keys(groups);
  const advanceCount = {};
  for (const g of groupNames) for (const t of groups[g]) advanceCount[t] = { groupWin: 0, groupRunnerUp: 0, bestThird: 0, round16: 0, round8: 0, round4: 0, runnerUp: 0, champion: 0, totalSims: 0 };

  const REPORT_INTERVAL = Math.max(1, Math.floor(N / 20));  // 报告 20 次进度
  let nextReport = REPORT_INTERVAL;

  for (let sim = 0; sim < N; sim++) {
    // 进度报告
    if (onProgress && sim >= nextReport) {
      onProgress({ current: sim, total: N, pct: Math.round((sim / N) * 100) });
      nextReport += REPORT_INTERVAL;
    }
    const standings = { ...computeStandings(completedMatches, groups) };
    for (const t of Object.keys(standings)) standings[t] = { ...standings[t] };
    for (const g of groupNames) for (const t of groups[g]) if (!standings[t]) standings[t] = { team: t, group: g, p: 0, w: 0, d: 0, l: 0, gf: 0, ga: 0, gd: 0, played: 0 };

    for (const m of upcomingMatches) {
      const lH = calcLambda(m.home, m.away, true, teams, recentMatches, { isFinalRound: m.round === 3, headToHead });
      const lA = calcLambda(m.away, m.home, false, teams, recentMatches, { isFinalRound: m.round === 3, headToHead });
      const simR = monteCarlo(lH, lA, 100);
      const top = simR.top5[0];
      if (!top) continue;
      const hG = top.home, aG = top.away;
      const h = standings[m.home], a = standings[m.away];
      h.played++; a.played++; h.gf += hG; h.ga += aG; a.gf += aG; a.ga += hG;
      if (hG > aG) { h.w++; h.p += 3; a.l++; } else if (hG === aG) { h.d++; h.p += 1; a.d++; a.p += 1; } else { h.l++; a.w++; a.p += 3; }
    }

    const groupRankings = {};
    for (const g of groupNames) groupRankings[g] = groups[g].map(t => standings[t]).filter(Boolean).sort((a, b) => b.p - a.p || b.gd - a.gd || b.gf - a.gf || 0);

    const allThirds = [];
    for (const g of groupNames) { const r = groupRankings[g]; if (r.length >= 3) allThirds.push({ team: r[2].team, group: g, pts: r[2].p, gd: r[2].gd, gf: r[2].gf }); }
    const bestThirds = allThirds.sort((a, b) => b.pts - a.pts || b.gd - a.gd || b.gf - a.gf).slice(0, 8);
    const bestThirdTeams = new Set(bestThirds.map(t => t.team));

    // 每次模拟开始, 标记哪些队进了16强
    const advancedThisSim = new Set();

    for (const g of groupNames) {
      const r = groupRankings[g];
      if (r.length >= 2) {
        advancedThisSim.add(r[0].team);
        advancedThisSim.add(r[1].team);
        advanceCount[r[0].team].groupWin++;
        advanceCount[r[1].team].groupRunnerUp++;
      }
    }
    for (const t of bestThirdTeams) {
      advanceCount[t].bestThird++;
      if (!advancedThisSim.has(t)) {
        advancedThisSim.add(t);
      }
    }
    // 本轮16强总计数 (每人只加一次)
    for (const t of advancedThisSim) advanceCount[t].round16++;

    const round16Teams = [];
    for (const g of groupNames) { const r = groupRankings[g]; if (r.length >= 2) { round16Teams.push(r[0].team); round16Teams.push(r[1].team); } }
    for (const t of bestThirdTeams) { if (!round16Teams.includes(t)) round16Teams.push(t); }

    function knockWinner(t1, t2) {
      const s1 = teams[t1], s2 = teams[t2];
      if (!s1 && !s2) return Math.random() > 0.5 ? t1 : t2;
      if (!s1) return t2; if (!s2) return t1;
      return (s1.eloRating || rankToElo(s1.rank || 50)) / 400 + Math.random() * 0.3 >= (s2.eloRating || rankToElo(s2.rank || 50)) / 400 + Math.random() * 0.3 ? t1 : t2;
    }

    let current = [...round16Teams];
    for (const round of ['round8', 'round4', 'final']) {
      if (current.length < 2) break;
      const next = [];
      for (let i = 0; i < current.length - 1; i += 2) {
        const w = knockWinner(current[i], current[i + 1]);
        next.push(w);
        const loser = w === current[i] ? current[i + 1] : current[i];
        if (round === 'round8') { advanceCount[w].round8++; advanceCount[loser].round8++; }
        else if (round === 'round4') { advanceCount[w].round4++; advanceCount[loser].round4++; }
        else if (round === 'final') { advanceCount[w].champion++; advanceCount[loser].runnerUp++; }
      }
      current = next;
    }
    for (const t of Object.keys(advanceCount)) advanceCount[t].totalSims++;
  }

  // 最终报告
  if (onProgress) onProgress({ current: N, total: N, pct: 100 });

  const result = {};
  for (const [team, counts] of Object.entries(advanceCount)) {
    result[team] = { groupWinPct: +(counts.groupWin / N * 100).toFixed(1), groupRunnerUpPct: +(counts.groupRunnerUp / N * 100).toFixed(1), bestThirdPct: +(counts.bestThird / N * 100).toFixed(1), advancePct: +(counts.round16 / N * 100).toFixed(1), round8Pct: +(counts.round8 / N * 100).toFixed(1), round4Pct: +(counts.round4 / N * 100).toFixed(1), runnerUpPct: +(counts.runnerUp / N * 100).toFixed(1), championPct: +(counts.champion / N * 100).toFixed(1) };
  }
  return { totalSims: N, group: groups, results: result, timestamp: new Date().toISOString() };
}

// ============================================================
// 11. 模型分析 (使用真实近10场数据)
// ============================================================
export function analyzeModel(completedMatches, teams, recentMatches) {
  const testSet = completedMatches.filter(m => m.score).slice(-20);
  let correct = 0, exact = 0;
  for (const m of testSet) {
    const [aH, aA] = m.score.split('-').map(Number);
    const lH = calcLambda(m.home, m.away, true, teams, recentMatches);
    const lA = calcLambda(m.away, m.home, false, teams, recentMatches);
    const sim = monteCarlo(lH, lA, 5000);
    const top = sim.top5[0];
    if (!top) continue;
    if ((top.home > top.away && aH > aA) || (top.home === top.away && aH === aA) || (top.home < top.away && aH < aA)) correct++;
    if (top.home === aH && top.away === aA) exact++;
  }
  return { testSize: testSet.length, resultAccuracy: +(correct / testSet.length * 100).toFixed(1), exactScore: +(exact / testSet.length * 100).toFixed(1) };
}

// ============================================================
// 12. Elo 批量更新
// ============================================================
export function batchUpdateElo(teams, completedMatches) {
  const sorted = [...completedMatches].filter(m => m.score).sort((a, b) => a.date.localeCompare(b.date));
  for (const m of sorted) {
    const tHome = teams[m.home], tAway = teams[m.away];
    if (!tHome || !tAway) continue;
    const eloH = tHome.eloRating || rankToElo(tHome.rank || 50);
    const eloA = tAway.eloRating || rankToElo(tAway.rank || 50);
    const [hG, aG] = m.score.split('-').map(Number);
    const K = m.round && m.round.toString().includes('/') ? 40 : 30;
    const updated = updateElo(eloH, eloA, hG, aG, K);
    tHome.eloRating = updated.home;
    tAway.eloRating = updated.away;
  }
  return teams;
}