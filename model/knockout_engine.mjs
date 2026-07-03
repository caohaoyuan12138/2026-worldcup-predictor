#!/usr/bin/env node

/**
 * 淘汰赛专项预测引擎 v2.0
 * 
 * 核心改进：
 * 1. 淘汰赛独立参数体系（低进球、高平率、点球概率）
 * 2. 基于近期表现的动态模型权重
 * 3. 冷门检测与预警
 * 4. 置信度校准
 * 5. 赛后评估回测
 * 
 * 使用方法：
 *   node knockout_engine.mjs predict 西班牙 奥地利 --knockout
 *   node knockout_engine.mjs backtest
 *   node knockout_engine.mjs upsets
 */

import * as fs from 'fs';
import * as path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.join(__dirname, '..');

// ============================================================
// 加载数据
// ============================================================
let db, userData;
try {
  db = await import(new URL('../database.mjs', import.meta.url).href);
  let userDataPath = path.join(ROOT, '..', 'user_team_data.json');
  let userData;
  try {
    userData = JSON.parse(fs.readFileSync(userDataPath, 'utf8'));
  } catch (e) {
    userData = {};
  }
  for (const [name, data] of Object.entries(userData)) {
    if (db.TEAM_STRENGTHS[name]) {
      db.TEAM_STRENGTHS[name].attackBase = data.attackBase;
      db.TEAM_STRENGTHS[name].defenseBase = data.defenseBase;
      db.TEAM_STRENGTHS[name].styleFactor = data.styleFactor;
      db.TEAM_STRENGTHS[name].rank = data.rank;
    }
  }
} catch (e) {
  console.error('❌ 加载失败:', e.message);
  process.exit(1);
}

// ============================================================
// 1. 淘汰赛专用参数
// ============================================================
const KNOCKOUT_CONFIG = {
  // 淘汰赛进球整体下调
  lambdaMultiplier: 0.85,
  // 淘汰赛平局基线提升
  drawBaseRate: 0.30,
  // 淘汰赛点球概率基线
  penaltyShootoutBase: 0.15,
  // 冷门概率基线（弱队爆冷）
  upsetBaseRate: 0.12,
  // 模拟次数
  simulations: 20000,
  // 波动系数（淘汰赛更不稳定）
  lambdaVolatility: 0.25,
  // Dixon-Coles rho（淘汰赛低比分更多）
  dcRho: 0.06,
  // 加时赛进球系数
  extraTimeFactor: 0.35,
  // 点球命中率
  penaltyConversion: 0.75,
};

// ============================================================
// 2. 动态模型融合权重
// ============================================================

/**
 * 基于各模型近期表现计算动态权重
 * @param {string} stage - 'group_stage' | 'round_of_16' | 'quarter_final' | 'semi_final' | 'final'
 * @param {Object} recentPerformance - 各模型近期准确率 { elo: 0.65, poisson: 0.55, market: 0.60 }
 * @returns {Object} 权重 { elo, poisson, economic, market }
 */
export function getDynamicWeights(stage, recentPerformance = {}) {
  // 基础权重
  let weights = {
    elo: 0.22,
    poisson: 0.28,
    economic: 0.10,
    market: 0.40,
  };
  
  // 阶段调整
  if (stage === 'round_of_16' || stage === '16强' || stage === '1/16') {
    // 淘汰赛早期：降低Elo权重（样本少），提高市场权重
    weights.elo *= 0.85;
    weights.poisson *= 1.10;
    weights.market *= 1.15;
  } else if (stage === 'quarter_final' || stage === '1/4') {
    weights.elo *= 0.80;
    weights.poisson *= 1.15;
    weights.market *= 1.20;
  } else if (stage === 'semi_final' || stage === '半决赛') {
    weights.elo *= 0.75;
    weights.poisson *= 1.20;
    weights.market *= 1.25;
  } else if (stage === 'final' || stage === '决赛') {
    weights.elo *= 0.70;
    weights.poisson *= 1.25;
    weights.market *= 1.30;
  }
  
  // 基于近期表现调整
  if (recentPerformance.elo && recentPerformance.elo > 0.60) {
    weights.elo *= 1.15;
  } else if (recentPerformance.elo && recentPerformance.elo < 0.45) {
    weights.elo *= 0.80;
  }
  
  if (recentPerformance.poisson && recentPerformance.poisson > 0.55) {
    weights.poisson *= 1.10;
  }
  
  if (recentPerformance.market && recentPerformance.market > 0.65) {
    weights.market *= 1.20;
  } else if (recentPerformance.market && recentPerformance.market < 0.50) {
    weights.market *= 0.85;
  }
  
  // 归一化
  const sum = Object.values(weights).reduce((a, b) => a + b, 0);
  for (const k in weights) weights[k] = Math.round(weights[k] / sum * 100) / 100;
  
  return weights;
}

// ============================================================
// 3. 冷门检测
// ============================================================

/**
 * 检测潜在冷门
 * @param {Object} prediction - 预测结果
 * @param {Object} context - 比赛上下文
 * @returns {{ isUpset: boolean, risk: 'low'|'medium'|'high'|'critical', reasons: string[] }}
 */
export function detectUpsetRisk(prediction, context = {}) {
  const reasons = [];
  let riskScore = 0;
  
  const { homeWinPct, drawPct, awayWinPct } = prediction;
  const favorite = homeWinPct >= awayWinPct ? 'home' : 'away';
  const favoritePct = favorite === 'home' ? homeWinPct : awayWinPct;
  
  // 1. 热门方概率过高但并非绝对
  if (favoritePct > 70 && favoritePct < 85) {
    riskScore += 1;
    reasons.push('热门方优势明显但非绝对（70-85%）');
  }
  
  // 2. 平局概率异常高
  if (drawPct > 28) {
    riskScore += 2;
    reasons.push(`平局概率异常高 (${drawPct}%)`);
  }
  
  // 3. 模型分歧大
  if (prediction.models) {
    const probs = [];
    if (prediction.models.elo) probs.push(prediction.models.elo.winPct || prediction.models.elo.homeWinPct);
    if (prediction.models.poisson) probs.push(prediction.models.poisson.winPct || prediction.models.poisson.homeWinPct);
    if (prediction.models.market && prediction.models.market.winPct) probs.push(prediction.models.market.winPct);
    
    if (probs.length >= 2) {
      const maxP = Math.max(...probs);
      const minP = Math.min(...probs);
      if (maxP - minP > 20) {
        riskScore += 2;
        reasons.push(`模型间分歧巨大（${maxP.toFixed(0)}% vs ${minP.toFixed(0)}%）`);
      }
    }
  }
  
  // 4. 实力接近但赔率差距大（市场信号异常）
  if (context.rankDiff && context.oddsRatio) {
    const impliedRankStrong = context.rankDiff > 10 ? 'home' : 'away';
    const impliedOddsStrong = context.oddsRatio > 1 ? 'home' : 'away';
    if (impliedRankStrong !== impliedOddsStrong) {
      riskScore += 1;
      reasons.push('排名与赔率方向矛盾');
    }
  }
  
  // 5. 淘汰赛 + 低λ场景
  if (context.isKnockout) {
    const totalLambda = (context.lambdaHome || 0) + (context.lambdaAway || 0);
    if (totalLambda < 2.0) {
      riskScore += 1;
      reasons.push('淘汰赛 + 低预期进球 = 高平局概率');
    }
  }
  
  // 6. 历史交锋不利
  if (context.h2hDisadvantage) {
    riskScore += 1;
    reasons.push('历史交锋处于劣势');
  }
  
  // 7. 战意差异
  if (context.motivationGap) {
    riskScore += 1;
    reasons.push(`战意差异显著（${context.motivationGap}）`);
  }
  
  // 判定风险等级
  let risk, isUpset;
  if (riskScore >= 5) { risk = 'critical'; isUpset = true; }
  else if (riskScore >= 3) { risk = 'high'; isUpset = true; }
  else if (riskScore >= 2) { risk = 'medium'; isUpset = false; }
  else { risk = 'low'; isUpset = false; }
  
  return { isUpset, risk, riskScore, reasons };
}

// ============================================================
// 4. 置信度校准
// ============================================================

/**
 * 根据模型一致性和数据质量计算预测置信度
 * @param {Object} prediction - 预测结果
 * @param {Object} oddsQuality - 赔率质量评分
 * @returns {{ level: 'high'|'medium'|'low', score: number, factors: string[] }}
 */
export function calibrateConfidence(prediction, oddsQuality = {}) {
  const factors = [];
  let score = 50; // 基础50分
  
  // 1. 热门方概率
  const maxP = Math.max(prediction.homeWinPct, prediction.drawPct, prediction.awayWinPct);
  if (maxP > 70) { score += 20; factors.push('热门方概率>70%'); }
  else if (maxP > 55) { score += 10; factors.push('热门方概率55-70%'); }
  else { score -= 10; factors.push('热门方概率<55%，不确定性高'); }
  
  // 2. 模型一致性
  if (prediction.models) {
    const modelProbs = [];
    if (prediction.models.elo) modelProbs.push(prediction.models.elo.winPct || prediction.models.elo.homeWinPct);
    if (prediction.models.poisson) modelProbs.push(prediction.models.poisson.winPct || prediction.models.poisson.homeWinPct);
    if (prediction.models.market && prediction.models.market.winPct) modelProbs.push(prediction.models.market.winPct);
    
    if (modelProbs.length >= 2) {
      const agreement = modelProbs.every(p => Math.abs(p - modelProbs[0]) < 15);
      if (agreement) { score += 15; factors.push('多模型意见一致'); }
      else { score -= 15; factors.push('多模型分歧严重'); }
    }
  }
  
  // 3. 赔率质量
  if (oddsQuality.quality >= 0.8) { score += 10; factors.push('赔率数据质量高'); }
  else if (oddsQuality.quality >= 0.5) { score += 5; factors.push('赔率数据质量一般'); }
  else { score -= 10; factors.push('赔率数据质量差或缺失'); }
  
  // 4. 数据完整性
  const dataCompleteness = prediction.dataCompleteness || 0;
  if (dataCompleteness > 0.8) { score += 10; factors.push('数据完整'); }
  else if (dataCompleteness < 0.5) { score -= 10; factors.push('数据不完整'); }
  
  score = Math.max(10, Math.min(95, score));
  
  let level;
  if (score >= 70) level = 'high';
  else if (score >= 45) level = 'medium';
  else level = 'low';
  
  return { level, score: Math.round(score), factors };
}

// ============================================================
// 5. 淘汰赛专用 Lambda 计算
// ============================================================

function calcKnockoutLambda(teamName, opponentName, isHome, teams, recentMatches, ctx = {}) {
  const team = teams[teamName];
  const opponent = teams[opponentName];
  if (!team || !opponent) return 0.8;
  
  let lambda = team.attackBase || 1.0;
  if (isHome) lambda *= 1.06; // 淘汰赛主场优势略降
  lambda *= (team.styleFactor || 1.0);
  
  // 动量
  const momentumData = calcMomentum(teamName, recentMatches, 5);
  if (momentumData.played >= 3) {
    lambda = lambda * 0.5 + momentumData.gfPerGame * 0.5;
    const formFactor = 0.9 + momentumData.winRate * 0.2;
    lambda *= formFactor;
  }
  
  // 对手防守
  const od = 1.0 - ((opponent.defenseBase || 1.0) - 0.8) * 0.2;
  lambda *= Math.max(0.7, Math.min(1.3, od));
  
  // 攻防差
  const sd = ((team.attackBase || 1.0) - (team.defenseBase || 1.0)) - 
             ((opponent.attackBase || 1.0) - (opponent.defenseBase || 1.0));
  if (sd > 0.5) lambda *= (isHome ? 1.06 : 1.04);
  else if (sd < -0.5) lambda *= (isHome ? 0.94 : 0.96);
  
  // H2H
  const h2hFactor = headToHeadFactor(teamName, opponentName, ctx.headToHead || {});
  lambda *= h2hFactor;
  
  // 大赛光环
  const titles = team.worldCupTitles || 0;
  if (titles >= 2) lambda *= 1.03;
  
  // 淘汰赛整体下调
  lambda *= KNOCKOUT_CONFIG.lambdaMultiplier;
  
  // 战意调整
  const urgency = (ctx.teamUrgency && ctx.teamUrgency[teamName]) || 0;
  if (urgency === 3) lambda *= 1.10;
  else if (urgency === 5) lambda *= 0.85;
  else if (urgency === 0) lambda *= 0.88;
  
  return Math.round(Math.max(0.3, Math.min(3.0, lambda)) * 100) / 100;
}

function calcMomentum(teamName, recentMatches, N = 5) {
  if (!recentMatches || !recentMatches[teamName]) return { played: 0, gfPerGame: 0, winRate: 0 };
  const matches = recentMatches[teamName].slice(0, N);
  let totalGf = 0, wins = 0, count = 0;
  for (const m of matches) {
    if (!m.score) continue;
    const parts = m.score.split('-').map(Number);
    if (parts.length !== 2 || isNaN(parts[0]) || isNaN(parts[1])) continue;
    let [h, a] = parts;
    h = Math.min(h, 4); a = Math.min(a, 4);
    const isHome = m.venue === '主';
    if (isHome) { totalGf += h; if (h > a) wins++; }
    else { totalGf += a; if (a > h) wins++; }
    count++;
  }
  return { played: count, gfPerGame: count > 0 ? totalGf / count : 0, winRate: count > 0 ? wins / count : 0 };
}

function headToHeadFactor(home, away, headToHead) {
  if (!headToHead) return 1.0;
  const key = [home, away].sort().join('|');
  const h2h = headToHead[key];
  if (!h2h || h2h.total < 3) return 1.0;
  const aWins = home === h2h.teamA ? h2h.aWins : h2h.bWins;
  const homeWinRate = aWins / h2h.total;
  if (homeWinRate > 0.5) return 1.02 + (homeWinRate - 0.5) * 0.04;
  if (homeWinRate < 0.4) return 0.98 - (0.5 - homeWinRate) * 0.04;
  return 1.0;
}

// ============================================================
// 6. 淘汰赛蒙特卡洛
// ============================================================

function knockoutMonteCarlo(lH, lA, N = KNOCKOUT_CONFIG.simulations) {
  function ps(lambda) {
    const L = Math.exp(-lambda);
    let k = 0, p = 1;
    do { k++; p *= Math.random(); } while (p > L);
    return k - 1;
  }
  
  // Dixon-Coles tau for knockout
  function tau(i, j, l1, l2, r) {
    if (i === 0 && j === 0) return 1 - l1 * l2 * r;
    if (i === 0 && j === 1) return 1 + l1 * r;
    if (i === 1 && j === 0) return 1 + l2 * r;
    if (i === 1 && j === 1) return 1 + r * 0.5;
    return 1;
  }
  
  const rho = KNOCKOUT_CONFIG.dcRho;
  const volatility = KNOCKOUT_CONFIG.lambdaVolatility;
  const results = {};
  let hW = 0, dr = 0, aW = 0, tG = 0;
  let drawCount = 0;
  
  for (let i = 0; i < N; i++) {
    // Log-normal sampling
    const hRand = Math.exp(Math.log(lH) + (Math.random() + Math.random() + Math.random() - 1.5) * volatility);
    const aRand = Math.exp(Math.log(lA) + (Math.random() + Math.random() + Math.random() - 1.5) * volatility);
    const hLambda = Math.max(0.15, Math.min(lH * 2.0, hRand));
    const aLambda = Math.max(0.15, Math.min(lA * 2.0, aRand));
    
    let h = ps(hLambda);
    let a = ps(aLambda);
    
    // Cap at 6
    h = Math.min(h, 6);
    a = Math.min(a, 6);
    
    // DC adjustment
    const t = tau(h, a, lH, lA, rho);
    if (t < 1 && Math.random() > t) { i--; continue; }
    
    const key = `${h}-${a}`;
    results[key] = (results[key] || 0) + 1;
    if (h > a) hW++;
    else if (h === a) { dr++; drawCount++; }
    else aW++;
    tG += h + a;
  }
  
  // 平局后点球模拟
  const drawProb = drawCount / N;
  const penHomeWin = drawProb * KNOCKOUT_CONFIG.penaltyConversion;
  const penAwayWin = drawProb * (1 - KNOCKOUT_CONFIG.penaltyConversion);
  
  const sorted = Object.entries(results)
    .map(([score, count]) => ({ 
      score, 
      home: Number(score.split('-')[0]), 
      away: Number(score.split('-')[1]), 
      count, 
      pct: +(count / N * 100).toFixed(1) 
    }))
    .sort((a, b) => b.count - a.count);
  
  return {
    sorted,
    top5: sorted.slice(0, 5),
    top10: sorted.slice(0, 10),
    homeWinPct: +((hW / N + penHomeWin) * 100).toFixed(1),
    drawPct: +(drawProb * 100).toFixed(1),
    awayWinPct: +((aW / N + penAwayWin) * 100).toFixed(1),
    avgGoals: +(tG / N).toFixed(2),
    totalRuns: N,
    drawAfter90: +(drawProb * 100).toFixed(1),
    penaltyHomeWin: +(penHomeWin * 100).toFixed(1),
    penaltyAwayWin: +(penAwayWin * 100).toFixed(1),
    scoreMatrix: buildScoreMatrix(sorted, 6),
  };
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

// ============================================================
// 7. Elo 模型（淘汰赛版）
// ============================================================

function eloKnockoutPrediction(eloH, eloA) {
  const expectedH = 1 / (1 + Math.pow(10, (eloA - eloH) / 400));
  const rawHome = expectedH * 100;
  const rawAway = (1 - expectedH) * 100;
  
  // 淘汰赛平局率提升
  let baseDraw = KNOCKOUT_CONFIG.drawBaseRate;
  const eloDiff = Math.abs(eloH - eloA);
  baseDraw -= eloDiff * 0.001;
  baseDraw = Math.max(0.22, Math.min(0.38, baseDraw));
  
  const nonDraw = 100 - baseDraw;
  const home = +(rawHome / (rawHome + rawAway) * nonDraw).toFixed(1);
  const away = +(rawAway / (rawHome + rawAway) * nonDraw).toFixed(1);
  
  return { homeWinPct: home, drawPct: +baseDraw.toFixed(1), awayWinPct: away };
}

// ============================================================
// 8. 经济模型
// ============================================================

function economicKnockoutPrediction(team, opponent, isHome) {
  let base = 1.0;
  const gdpRatio = Math.log(team.gdpPerCapita || 20000) / Math.log(50000);
  base *= (0.7 + gdpRatio * 0.5);
  const popRatio = Math.log(team.population || 10) / Math.log(200);
  base *= (0.8 + popRatio * 0.4);
  if (team.isHost) base *= 1.15;
  return Math.round(Math.max(0.3, Math.min(2.5, base)) * 100) / 100;
}

// ============================================================
// 9. 主预测引擎 — 淘汰赛版
// ============================================================

export function predictKnockout(home, away, teams, recentMatches, headToHead, options = {}) {
  const {
    oddsHome, oddsDraw, oddsAway,
    isKnockout = true,
    stage = 'round_of_16',
    teamUrgency = {},
  } = options;
  
  const teamHome = teams[home];
  const teamAway = teams[away];
  if (!teamHome || !teamAway) return { error: `球队不存在: ${!teamHome ? home : away}` };
  
  // --- 动态权重 ---
  const weights = getDynamicWeights(stage);
  
  // --- A. Elo ---
  function rankToEloFn(rank) {
    if (!rank || rank < 1 || rank > 50) return 1500;
    if (rank <= 10) return Math.round(1750 + (10 - rank) * (100 / 9));
    if (rank <= 30) return Math.round(1550 + (30 - rank) * (100 / 20));
    return Math.round(1400 + (50 - rank) * (50 / 20));
  }
  
  const eloH = teamHome.eloRating || rankToEloFn(teamHome.rank || 50);
  const eloA = teamAway.eloRating || rankToEloFn(teamAway.rank || 50);
  const eloResult = eloKnockoutPrediction(eloH, eloA);
  
  // --- B. 泊松 ---
  const lambdaH = calcKnockoutLambda(home, away, true, teams, recentMatches, { 
    headToHead, teamUrgency, headToHead: headToHead || {} 
  });
  const lambdaA = calcKnockoutLambda(away, home, false, teams, recentMatches, { 
    headToHead, teamUrgency, headToHead: headToHead || {} 
  });
  const poissonResult = knockoutMonteCarlo(lambdaH, lambdaA, KNOCKOUT_CONFIG.simulations);
  
  // --- C. 经济 ---
  const ecoH = economicKnockoutPrediction(teamHome, teamAway, true);
  const ecoA = economicKnockoutPrediction(teamAway, teamHome, false);
  const ecoTotal = ecoH + ecoA;
  const economicResult = {
    homeWinPct: +(ecoH / ecoTotal * 100).toFixed(1),
    drawPct: 28, // 经济模型不提供平局，用默认值
    awayWinPct: +(ecoA / ecoTotal * 100).toFixed(1),
  };
  
  // --- D. 市场赔率 ---
  function oddsToFairProbFn(h, d, a) {
    if (!h || !d || !a || h <= 0 || d <= 0 || a <= 0) return null;
    const implied = 1/h + 1/d + 1/a;
    return {
      homeWinPct: +( (1/h) / implied * 100 ).toFixed(1),
      drawPct: +( (1/d) / implied * 100 ).toFixed(1),
      awayWinPct: +( (1/a) / implied * 100 ).toFixed(1),
      overround: +(implied * 100).toFixed(2),
    };
  }
  
  let marketProb = null;
  if (oddsHome && oddsDraw && oddsAway) {
    marketProb = oddsToFairProbFn(oddsHome, oddsDraw, oddsAway);
  }
  
  // --- 融合 ---
  const mktWeight = marketProb ? weights.market : 0;
  const baseW = weights.elo + weights.poisson + weights.economic;
  
  let fusedHome = (eloResult.homeWinPct * weights.elo + poissonResult.homeWinPct * weights.poisson + economicResult.homeWinPct * weights.economic) / baseW;
  let fusedDraw = (eloResult.drawPct * weights.elo + poissonResult.drawPct * weights.poisson + economicResult.drawPct * weights.economic) / baseW;
  let fusedAway = (eloResult.awayWinPct * weights.elo + poissonResult.awayWinPct * weights.poisson + economicResult.awayWinPct * weights.economic) / baseW;
  
  if (marketProb) {
    const tw = baseW + mktWeight;
    fusedHome = (fusedHome * baseW + marketProb.homeWinPct * weights.market) / tw;
    fusedDraw = (fusedDraw * baseW + marketProb.drawPct * weights.market) / tw;
    fusedAway = (fusedAway * baseW + marketProb.awayWinPct * weights.market) / tw;
  }
  
  const total = fusedHome + fusedDraw + fusedAway;
  fusedHome = +(fusedHome / total * 100).toFixed(1);
  fusedDraw = +(fusedDraw / total * 100).toFixed(1);
  fusedAway = +(fusedAway / total * 100).toFixed(1);
  
  // --- 贝叶斯融合 ---
  let bayesianResult = null;
  if (marketProb) {
    const modelProbs = {
      homeWinPct: fusedHome / 100,
      drawPct: fusedDraw / 100,
      awayWinPct: fusedAway / 100,
    };
    const marketProbs = {
      homeWinPct: marketProb.homeWinPct / 100,
      drawPct: marketProb.drawPct / 100,
      awayWinPct: marketProb.awayWinPct / 100,
    };
    // 模型置信度: 基于四模型一致性
    const allProbs = [eloResult.homeWinPct / 100, poissonResult.homeWinPct / 100, economicResult.homeWinPct / 100, marketProb.homeWinPct / 100];
    const maxP = Math.max(...allProbs);
    const minP = Math.min(...allProbs);
    const modelConfidence = Math.max(0.3, 1.0 - (maxP - minP));
    
    const stage = options.stage || 'round_of_16';
    const sw = {
      'round_of_16': [0.55, 0.45], '16强': [0.55, 0.45], '1/16': [0.55, 0.45],
      'quarter_final': [0.50, 0.50], '1/4': [0.50, 0.50],
      'semi_final': [0.40, 0.60], '半决赛': [0.40, 0.60],
      'final': [0.35, 0.65], '决赛': [0.35, 0.65],
      'group_stage': [0.70, 0.30],
    };
    const [wM, wMK] = sw[stage] || [0.55, 0.45];
    const tw = wM * modelConfidence + wMK;
    const bHome = (wM * modelConfidence * modelProbs.homeWinPct + wMK * marketProbs.homeWinPct) / tw;
    const bDraw = (wM * modelConfidence * modelProbs.drawPct + wMK * marketProbs.drawPct) / tw;
    const bAway = (wM * modelConfidence * modelProbs.awayWinPct + wMK * marketProbs.awayWinPct) / tw;
    const agreement = 1.0 - (Math.abs(modelProbs.homeWinPct - marketProbs.homeWinPct) + Math.abs(modelProbs.drawPct - marketProbs.drawPct) + Math.abs(modelProbs.awayWinPct - marketProbs.awayWinPct)) / 2;
    bayesianResult = {
      home_win: +(bHome * 100).toFixed(1),
      draw: +(bDraw * 100).toFixed(1),
      away_win: +(bAway * 100).toFixed(1),
      confidence: +Math.min(agreement * modelConfidence * 2, 1.0).toFixed(3),
      weight_model: +(wM * modelConfidence / tw).toFixed(3),
      weight_market: +(wMK / tw).toFixed(3),
    };
    fusedHome = bayesianResult.home_win;
    fusedDraw = bayesianResult.draw;
    fusedAway = bayesianResult.away_win;
  }
  
  // --- 冷门检测 ---
  const upsetCheck = detectUpsetRisk(
    { homeWinPct: fusedHome, drawPct: fusedDraw, awayWinPct: fusedAway, models: {
      elo: { winPct: eloResult.homeWinPct },
      poisson: { winPct: poissonResult.homeWinPct },
      market: marketProb ? { winPct: marketProb.homeWinPct } : null,
    }},
    {
      isKnockout: true,
      rankDiff: Math.abs(teamHome.rank - teamAway.rank),
      lambdaHome: lambdaH,
      lambdaAway: lambdaA,
      motivationGap: Math.abs((teamUrgency[home] || 0) - (teamUrgency[away] || 0)),
    }
  );
  
  // --- 置信度 ---
  const oddsQuality = marketProb ? assessOddsQualitySimple(oddsHome, oddsDraw, oddsAway) : { quality: 0 };
  const confidence = calibrateConfidence(
    { homeWinPct: fusedHome, drawPct: fusedDraw, awayWinPct: fusedAway, 
      models: { elo: { winPct: eloResult.homeWinPct }, poisson: { winPct: poissonResult.homeWinPct } } },
    oddsQuality
  );
  
  return {
    home, away, stage,
    isKnockout: true,
    models: {
      elo: { rating: { home: eloH, away: eloA }, winPct: eloResult.homeWinPct, drawPct: eloResult.drawPct, awayPct: eloResult.awayWinPct },
      poisson: { lambda: { home: lambdaH, away: lambdaA }, winPct: poissonResult.homeWinPct, drawPct: poissonResult.drawPct, awayPct: poissonResult.awayWinPct },
      economic: { winPct: economicResult.homeWinPct, drawPct: economicResult.drawPct, awayPct: economicResult.awayWinPct },
      market: marketProb ? { odds: { home: oddsHome, draw: oddsDraw, away: oddsAway }, winPct: marketProb.homeWinPct, drawPct: marketProb.drawPct, awayPct: marketProb.awayWinPct } : null,
    },
    weights,
    bayesian: bayesianResult,
    fusion: {
      lambda: { home: lambdaH, away: lambdaA },
      winPct: fusedHome, drawPct: fusedDraw, awayPct: fusedAway,
      top5: poissonResult.top5,
      avgGoals: poissonResult.avgGoals,
      totalRuns: poissonResult.totalRuns,
      drawAfter90: poissonResult.drawAfter90,
      penaltyHomeWin: poissonResult.penaltyHomeWin,
      penaltyAwayWin: poissonResult.penaltyAwayWin,
    },
    upsetRisk: upsetCheck,
    confidence,
    timestamp: new Date().toISOString(),
  };
}

function assessOddsQualitySimple(h, d, a) {
  if (!h || !d || !a || h <= 0 || d <= 0 || a <= 0) return { quality: 0 };
  const implied = 1/h + 1/d + 1/a;
  if (implied < 1.01 || implied > 1.25) return { quality: 0.3 };
  return { quality: implied <= 1.10 ? 1.0 : 0.7 };
}

// ============================================================
// 10. 回测系统
// ============================================================

async function runBacktest() {
  console.log('\n' + '='.repeat(60));
  console.log('  淘汰赛预测回测系统');
  console.log('='.repeat(60));
  
  const completed = db.COMPLETED_MATCHES || [];
  const knockoutMatches = completed.filter(m => 
    m.round && (m.round.includes('强') || m.round === 'KO' || m.group === 'KO')
  );
  
  if (knockoutMatches.length === 0) {
    console.log('  暂无淘汰赛数据可回测');
    return;
  }
  
  let correct = 0;
  let exact = 0;
  let top3Hits = 0;
  let total = 0;
  const results = [];
  
  for (const match of knockoutMatches) {
    if (!match.score) continue;
    const [hG, aG] = match.score.split('-').map(Number);
    if (isNaN(hG) || isNaN(aG)) continue;
    
    const pred = predictKnockout(match.home, match.away, db.TEAM_STRENGTHS, {}, {});
    if (pred.error) continue;
    
    total++;
    const predDir = pred.fusion.winPct >= pred.fusion.awayPct && pred.fusion.winPct >= pred.fusion.drawPct ? 'home' :
                    pred.fusion.drawPct >= pred.fusion.homeWinPct && pred.fusion.drawPct >= pred.fusion.awayPct ? 'draw' : 'away';
    const actualDir = hG > aG ? 'home' : hG === aG ? 'draw' : 'away';
    
    const top5Scores = pred.fusion.top5.map(s => s.score);
    const actualScore = `${hG}-${aG}`;
    
    const dirCorrect = predDir === actualDir;
    const exactHit = top5Scores.includes(actualScore);
    const top3Hit = top5Scores.slice(0, 3).includes(actualScore);
    
    if (dirCorrect) correct++;
    if (exactHit) exact++;
    if (top3Hit) top3Hits++;
    
    results.push({
      match: `${match.home} vs ${match.away}`,
      actual: actualScore,
      predicted: top5Scores[0],
      top5: top5Scores,
      direction: predDir,
      actualDirection: actualDir,
      dirCorrect,
      exactHit,
      top3Hit,
      confidence: pred.confidence,
      upsetRisk: pred.upsetRisk,
    });
  }
  
  console.log(`\n  回测场次: ${total}`);
  console.log(`  方向准确率: ${(correct/total*100).toFixed(1)}% (${correct}/${total})`);
  console.log(`  Top1比分命中: ${(exact/total*100).toFixed(1)}% (${exact}/${total})`);
  console.log(`  Top3比分命中: ${(top3Hits/total*100).toFixed(1)}% (${top3Hits}/${total})`);
  
  console.log('\n  ── 逐场明细 ──');
  for (const r of results) {
    const icon = r.dirCorrect ? '✅' : '❌';
    const exactIcon = r.exactHit ? '🎯' : '';
    console.log(`  ${icon} ${r.match.padEnd(30)} 实际${r.actual} 预测${r.predicted} ${exactIcon} 置信度${r.confidence.level}(${r.confidence.score})`);
  }
  
  // 保存结果
  const logPath = path.join(ROOT, 'data_local', 'backtest_results.json');
  try {
    fs.mkdirSync(path.dirname(logPath), { recursive: true });
    fs.writeFileSync(logPath, JSON.stringify({ 
      date: new Date().toISOString(), 
      matches: total, 
      wdlAccuracy: +(correct/total*100).toFixed(1),
      top1Accuracy: +(exact/total*100).toFixed(1),
      top3Accuracy: +(top3Hits/total*100).toFixed(1),
      results 
    }, null, 2));
    console.log(`\n  📁 结果已保存: ${logPath}`);
  } catch (e) { /* ignore */ }
}

// ============================================================
// 11. 冷门预警
// ============================================================

function showUpsetWarnings(matches) {
  console.log('\n' + '='.repeat(60));
  console.log('  冷门预警系统');
  console.log('='.repeat(60));
  
  const warnings = [];
  
  for (const m of matches) {
    if (m.score) continue; // 只检查未赛
    
    const pred = predictKnockout(m.home, m.away, db.TEAM_STRENGTHS, {}, {});
    if (pred.error) continue;
    
    if (pred.upsetRisk.isUpset) {
      warnings.push({
        match: `${m.home} vs ${m.away}`,
        risk: pred.upsetRisk.risk,
        reasons: pred.upsetRisk.reasons,
        prediction: pred.fusion,
        confidence: pred.confidence,
      });
    }
  }
  
  if (warnings.length === 0) {
    console.log('  暂无冷门预警');
    return;
  }
  
  for (const w of warnings.sort((a, b) => {
    const order = { critical: 0, high: 1, medium: 2, low: 3 };
    return (order[a.risk] || 9) - (order[b.risk] || 9);
  })) {
    const emoji = w.risk === 'critical' ? '🔴🔴🔴' : w.risk === 'high' ? '🔴🔴' : '🟡';
    console.log(`\n  ${emoji} ${w.match}`);
    console.log(`     风险等级: ${w.risk.toUpperCase()}`);
    for (const reason of w.reasons) {
      console.log(`     • ${reason}`);
    }
    console.log(`     预测: 主胜${w.prediction.winPct}% 平${w.prediction.drawPct}% 客胜${w.prediction.awayPct}%`);
    console.log(`     置信度: ${w.confidence.level} (${w.confidence.score})`);
  }
}

// ============================================================
// 12. CLI 入口
// ============================================================

const cmd = process.argv[2];
const home = process.argv[3];
const away = process.argv[4];

switch (cmd) {
  case 'predict':
    if (home && away) {
      const pred = predictKnockout(home, away, db.TEAM_STRENGTHS, {}, {});
      
      console.log('\n' + '='.repeat(60));
      console.log(`  ⚽ 淘汰赛预测: ${pred.home} vs ${pred.away}`);
      console.log('='.repeat(60));
      
      console.log(`\n  【融合结果】`);
      console.log(`    主胜: ${pred.fusion.winPct}%  |  平: ${pred.fusion.drawPct}%  |  客胜: ${pred.fusion.awayPct}%`);
      console.log(`    预期进球: ${pred.home} ${pred.fusion.lambda.home.toFixed(2)} : ${pred.fusion.lambda.away.toFixed(2)} ${pred.away}`);
      console.log(`    场均总进球: ${pred.fusion.avgGoals}`);
      
      console.log(`\n  【TOP5 比分】`);
      for (const s of pred.fusion.top5) {
        const bar = '█'.repeat(Math.round(s.pct / 2));
        console.log(`    ${s.score.padEnd(6)} ${s.pct.toString().padStart(5)}%  ${bar}`);
      }
      
      console.log(`\n  【各模型预测】`);
      console.log(`    Elo:    主${(pred.models.elo.homeWinPct || pred.models.elo.winPct).toFixed(1)}% 平${(pred.models.elo.drawPct || 28).toFixed(1)}% 客${(pred.models.elo.awayWinPct || (100-(pred.models.elo.homeWinPct||0)-(pred.models.elo.drawPct||28))).toFixed(1)}%`);
      console.log(`    泊松:   主${pred.models.poisson.winPct.toFixed(1)}% 平${(pred.models.poisson.drawPct||0).toFixed(1)}% 客${(pred.models.poisson.awayPct||pred.models.poisson.awayWinPct||0).toFixed(1)}%`);
      if (pred.models.market) {
        console.log(`    市场:   主${pred.models.market.winPct.toFixed(1)}% 平${pred.models.market.drawPct.toFixed(1)}% 客${pred.models.market.awayWinPct.toFixed(1)}%`);
      }
      
      console.log(`\n  【权重分配】`);
      for (const [k, v] of Object.entries(pred.weights)) {
        console.log(`    ${k.padEnd(10)}: ${(v * 100).toFixed(0)}%`);
      }
      
      console.log(`\n  【冷门预警】`);
      if (pred.upsetRisk.isUpset) {
        console.log(`    ⚠️ 检测到冷门风险 (${pred.upsetRisk.risk})`);
        for (const r of pred.upsetRisk.reasons) {
          console.log(`    • ${r}`);
        }
      } else {
        console.log(`    ✅ 无明显冷门信号`);
      }
      
      console.log(`\n  【置信度】`);
      console.log(`    等级: ${pred.confidence.level.toUpperCase()} (${pred.confidence.score}/100)`);
      for (const f of pred.confidence.factors) {
        console.log(`    • ${f}`);
      }
      
      // 保存
      const ts = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
      const saveDir = path.join(ROOT, 'predictions');
      try {
        fs.mkdirSync(saveDir, { recursive: true });
        fs.writeFileSync(
          path.join(saveDir, `${pred.home}_vs_${pred.away}_${ts}.json`),
          JSON.stringify(pred, null, 2)
        );
      } catch (e) { /* ignore */ }
    } else {
      console.log('用法: node knockout_engine.mjs predict 主队 客队');
    }
    break;
    
  case 'backtest':
    runBacktest().catch(console.error);
    break;
    
  case 'upsets':
    const upcoming = db.KNOCKOUT_MATCHES || [];
    showUpsetWarnings(upcoming);
    break;
    
  case 'all':
    const allKnockout = db.KNOCKOUT_MATCHES || [];
    for (const m of allKnockout) {
      if (m.score) continue;
      const pred = predictKnockout(m.home, m.away, db.TEAM_STRENGTHS, {}, {});
      if (pred.error) continue;
      const top = pred.fusion.top5[0];
      const dir = pred.fusion.winPct >= pred.fusion.awayPct && pred.fusion.winPct >= pred.fusion.drawPct ? '主胜' :
                  pred.fusion.drawPct >= pred.fusion.winPct && pred.fusion.drawPct >= pred.fusion.awayPct ? '平' : '客胜';
      console.log(`  ${m.label.padEnd(12)} ${m.home.padEnd(10)} vs ${m.away.padEnd(10)} → ${top.score} (${top.pct}%) [${dir}] 冷门:${pred.upsetRisk.risk} 置信:${pred.confidence.level}`);
    }
    break;
    
  default:
    console.log(`
⚽ 淘汰赛预测引擎 v2.0

用法:
  node knockout_engine.mjs predict 主队 客队    - 预测单场淘汰赛
  node knockout_engine.mjs backtest             - 回测历史淘汰赛
  node knockout_engine.mjs upsets               - 冷门预警
  node knockout_engine.mjs all                  - 预测所有剩余淘汰赛
`);
}
