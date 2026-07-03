#!/usr/bin/env node

/**
 * ⚽ 世界杯预测引擎 v5.0 — Oracle V2 融合引擎
 *
 * 基于 v4.0 引擎全面升级：
 *   v4.0 三层架构 + v5.0 增强：阶段自适应贝叶斯权重、赔率质量评分、
 *   冷门检测、动态参数体系（统一配置中心接管）
 *
 * 兼容: 可直接替代 engine.mjs（所有导出一致）
 *   使用: import * as engine from './model/_fusion_v5.mjs';
 *   或:   import engine from './model/_fusion_v5.mjs';
 */

import * as v4 from './engine.mjs';
import sharedConfig from './config.mjs';

// 重新导出所有 v4 函数，保持向下兼容
export const factorial = v4.factorial;
export const comb = v4.comb;
export const eloExpected = v4.eloExpected;
export const updateElo = v4.updateElo;
export const rankToElo = v4.rankToElo;
export const economicModel = v4.economicModel;
export const calcLambda = v4.calcLambda;
export const oddsToProb = v4.oddsToProb;
export const handicapAdjust = v4.handicapAdjust;
export const monteCarlo = v4.monteCarlo;
export const calcDynamicRho = v4.calcDynamicRho;
export const fastWinDrawLoss = v4.fastWinDrawLoss;
export const bayesianAdjust = v4.bayesianAdjust;
export const evaluatePredictions = v4.evaluatePredictions;
export const simulateBetting = v4.simulateBetting;
export const getDynamicWeights = v4.getDynamicWeights;
export const computeStandings = v4.computeStandings;
export const getStats = v4.getStats;
export const simulateTournament = v4.simulateTournament;
export const analyzeModel = v4.analyzeModel;
export const batchUpdateElo = v4.batchUpdateElo;

// ============================================================
// v5.0 新增: 赔率质量评分
// ============================================================

/**
 * 评估赔率质量，返回 0.0–1.0 的分数
 *
 * 检查维度:
 * 1. 理论合理性 (隐含概率之和在合理范围内)
 * 2. 赔率深度 (三向赔率是否完整)
 * 3. 市场一致性 (与 Elo 预期的偏差)
 */
export function oddsQualityScore(oddsHome, oddsDraw, oddsAway, eloH, eloA) {
  if (!oddsHome || !oddsDraw || !oddsAway) return 0;
  if (oddsHome <= 0 || oddsDraw <= 0 || oddsAway <= 0) return 0;

  let score = 1.0;

  // 1. 隐含概率检查 (合理范围 0.8–1.15)
  const implied = 1/oddsHome + 1/oddsDraw + 1/oddsAway;
  if (implied < 0.8 || implied > 1.15) score -= 0.2;
  if (implied > 1.20) score -= 0.3; // 严重高水

  // 2. 赔率数值合理性
  if (oddsHome < 1.01 || oddsDraw < 1.01 || oddsAway < 1.01) score -= 0.3;
  if (oddsHome > 100 || oddsDraw > 100 || oddsAway > 100) score -= 0.2;

  // 3. 与 Elo 预期的一致性偏差
  if (eloH != null && eloA != null) {
    const expectedHome = v4.eloExpected(eloH, eloA);
    const impliedHome = (1/oddsHome) / implied;
    const diff = Math.abs(expectedHome - impliedHome);
    if (diff > 0.20) score -= 0.15;  // 偏差过大
    if (diff > 0.35) score -= 0.20;  // 严重偏差
  }

  // 4. 赔率是否为整数 (行业惯例，非整数通常更精确)
  const allInt = [oddsHome, oddsDraw, oddsAway].every(o => Number.isInteger(o));
  if (allInt) score -= 0.1; // 整数赔率精度低

  return Math.max(0, Math.min(1, score));
}

// ============================================================
// v5.0 新增: 冷门检测
// ============================================================

/**
 * 检测冷门风险，返回风险等级和原因列表
 *
 * 风险等级: 0=无, 1=低, 2=中, 3=高
 */
export function detectUpsetRisk(pred, options = {}) {
  const risks = [];
  let level = 0;

  const { fusion, models, weights } = pred;
  const winPct = fusion.winPct;
  const drawPct = fusion.drawPct;
  const awayPct = fusion.awayPct;

  // 1. 热门概率过高 (>80%) 但赔率不支撑
  if (winPct > 80 && models.market) {
    const marketGap = winPct - models.market.winPct;
    if (marketGap > 15) {
      risks.push({ type: 'model_market_divergence', detail: `模型高估主胜 ${marketGap.toFixed(0)}%` });
      level = Math.max(level, 2);
    }
  } else if (awayPct > 80 && models.market) {
    const marketGap = awayPct - models.market.awayPct;
    if (marketGap > 15) {
      risks.push({ type: 'model_market_divergence', detail: `模型高估客胜 ${marketGap.toFixed(0)}%` });
      level = Math.max(level, 2);
    }
  }

  // 2. 平率异常 (赔率隐含平率 vs 模型平率)
  if (models.market) {
    const drawGap = Math.abs(drawPct - models.market.drawPct);
    if (drawGap > 10) {
      risks.push({ type: 'draw_divergence', detail: `平率分歧: 模型${drawPct.toFixed(0)}% vs 市场${models.market.drawPct.toFixed(0)}%` });
    }
  }

  // 3. 模型分歧 (Elo vs Poisson 方向不一致)
  const eloFav = models.elo.winPct >= models.elo.awayPct ? 'home' : (models.elo.awayPct > models.elo.winPct ? 'away' : 'draw');
  const poissonFav = models.poisson.winPct >= models.poisson.awayPct ? 'home' : (models.poisson.awayPct > models.poisson.winPct ? 'away' : 'draw');
  if (eloFav !== poissonFav) {
    risks.push({ type: 'model_disagreement', detail: `Elo=${eloFav}, Poisson=${poissonFav}` });
    level = Math.max(level, 1);
  }

  // 4. 低λ比赛 (0-0/1-0 风险)
  if (fusion.lambda.home < 0.6 && fusion.lambda.away < 0.6) {
    risks.push({ type: 'low_lambda', detail: `双低λ: ${fusion.lambda.home}/${fusion.lambda.away}` });
    level = Math.max(level, 1);
  }

  const threshold = options.upsetThreshold || sharedConfig.UPSET_RISK_THRESHOLDS;
  const finalLevel = level >= threshold.high ? 3 : level >= threshold.medium ? 2 : level >= threshold.low ? 1 : 0;

  return { level: finalLevel, risks, isUpset: finalLevel >= 2 };
}

// ============================================================
// v5.0 融合预测 (增强版)
// ============================================================

/**
 * v5.0 fusionPredict — 在 v4.0 基础上:
 *
 * 1. 使用 config.mjs 的统一参数 (阶段权重、MC次数、DC ρ 等)
 * 2. 赔率质量评分 → 动态调整市场模型权重
 * 3. 冷门检测集成
 * 4. 淘汰赛参数从 config 读取而非硬编码
 * 5. 更清晰的阶段感知贝叶斯融合
 * 6. 赔率缺失时的市场推断优化
 */
export function fusionPredict(home, away, teams, recentMatches, headToHead, options = {}) {
  const {
    monteCarloRuns: optMCRuns, isFinalRound = false, isKnockout = false,
    oddsHome, oddsDraw, oddsAway, handicap, dcRho: optDcRho,
    eloWeight: optElo, poissonWeight: optPoisson, economicWeight: optEco, marketWeight: optMarket,
    teamUrgency = {}, stage = 'group_stage'
  } = options;

  const teamHome = teams[home], teamAway = teams[away];
  if (!teamHome || !teamAway) return { error: `球队不存在: ${!teamHome ? home : away}` };

  // === 从统一配置中心读取参数 ===
  const mcRuns = optMCRuns || sharedConfig.getMCRuns(isKnockout);
  const dcRho = optDcRho != null ? optDcRho : (isKnockout ? sharedConfig.DC_RHO_KNOCKOUT : sharedConfig.DC_RHO_DEFAULT);
  const defaultWeights = { ...sharedConfig.DEFAULT_WEIGHTS };

  // === 动态权重 ===
  const dynWeights = v4.getDynamicWeights(stage);
  const eloWeight = optElo || dynWeights.elo;
  const poissonWeight = optPoisson || dynWeights.poisson;
  const economicWeight = optEco || dynWeights.economic;
  const marketWeight = optMarket || dynWeights.market;

  // === A. Elo ===
  const eloH = teamHome.eloRating || v4.rankToElo(teamHome.rank || 50);
  const eloA = teamAway.eloRating || v4.rankToElo(teamAway.rank || 50);
  const expectedH = v4.eloExpected(eloH, eloA);
  const eloRawHomePct = expectedH * 100;
  const eloRawAwayPct = (1 - expectedH) * 100;

  let baseDrawPct = 27 - Math.abs(eloH - eloA) * 0.012;
  const homeUrgency = teamUrgency[home] || 0;
  const awayUrgency = teamUrgency[away] || 0;
  if ((homeUrgency === 4 || homeUrgency === 5) && (awayUrgency === 4 || awayUrgency === 5)) baseDrawPct *= 1.25;
  if (homeUrgency === 3 || awayUrgency === 3) baseDrawPct *= 0.90;
  if (isKnockout) baseDrawPct *= sharedConfig.KNOCKOUT_DRAW_BOOST;
  baseDrawPct *= 1.25;

  const eloDrawPctEstimate = Math.max(10, Math.min(38, Math.round(baseDrawPct)));
  const eloHomePct = +((eloRawHomePct / (eloRawHomePct + eloRawAwayPct)) * (100 - eloDrawPctEstimate)).toFixed(1);
  const eloAwayPct = +((eloRawAwayPct / (eloRawHomePct + eloRawAwayPct)) * (100 - eloDrawPctEstimate)).toFixed(1);
  const eloDrawPct = +(100 - eloHomePct - eloAwayPct).toFixed(1);

  // === B. 泊松 ===
  const ctx = {
    isFinalRound, isKnockout,
    homeAdvantage: options.homeAdvantage || sharedConfig.ELO_HOME_ADVANTAGE / 1000 + 1.0,
    headToHead, teamUrgency: options.teamUrgency || {},
  };
  const poissonLH = v4.calcLambda(home, away, true, teams, recentMatches, ctx);
  const poissonLA = v4.calcLambda(away, home, false, teams, recentMatches, ctx);

  // v5.0: 淘汰赛 λ 下调从 config 读取
  let effLH = poissonLH, effLA = poissonLA;
  if (isKnockout) {
    const mult = sharedConfig.KNOCKOUT_LAMBDA_MULT;
    effLH = Math.round(poissonLH * mult * 100) / 100;
    effLA = Math.round(poissonLA * mult * 100) / 100;
  }

  const eloDiff = Math.abs(eloH - eloA);
  let dynamicRho = eloDiff < 50 ? sharedConfig.DC_RHO_KNOCKOUT : eloDiff < 100 ? 0.03 : Math.max(0.02, dcRho);
  if (effLH < 0.8 && effLA < 0.8) dynamicRho = Math.max(dynamicRho, sharedConfig.DC_RHO_LOW_LAMBDA);
  if (isKnockout) dynamicRho = Math.max(dynamicRho, sharedConfig.DC_RHO_KNOCKOUT);

  const simRuns = mcRuns;
  const poissonSim = v4.monteCarlo(effLH, effLA, simRuns, dynamicRho, isKnockout, {
    lambdaVolatility: isKnockout ? 0.25 : 0.15,
  });
  const fastRef = v4.fastWinDrawLoss(effLH, effLA);

  // === C. 经济学 ===
  const ecoSim = v4.monteCarlo(
    v4.economicModel(teamHome, teamAway, true),
    v4.economicModel(teamAway, teamHome, false),
    simRuns, 0
  );

  // === D. 市场赔率 ===
  let marketProb = null;
  let oddsQuality = 0;

  if (oddsHome && oddsDraw && oddsAway) {
    // v5.0: 赔率质量评分
    oddsQuality = oddsQualityScore(oddsHome, oddsDraw, oddsAway, eloH, eloA);
    marketProb = v4.oddsToProb(oddsHome, oddsDraw, oddsAway);
    if (handicap && marketProb) {
      marketProb = v4.handicapAdjust(marketProb.homeWinPct, marketProb.drawPct, marketProb.awayWinPct, handicap);
    }
  } else if (handicap) {
    oddsQuality = 0.3; // 仅有盘口，质量低
    const impliedHomePct = expectedH * 100;
    const impliedAwayPct = (1 - expectedH) * 100;
    const eloBasedDraw = Math.max(10, Math.min(32, 28 - eloDiff * 0.015));
    const totalNonDraw = impliedHomePct + impliedAwayPct;
    marketProb = {
      homeWinPct: +((impliedHomePct / totalNonDraw) * (100 - eloBasedDraw)).toFixed(1),
      drawPct: +eloBasedDraw.toFixed(1),
      awayWinPct: +((impliedAwayPct / totalNonDraw) * (100 - eloBasedDraw)).toFixed(1),
      overround: 100, isInferred: true
    };
    marketProb = v4.handicapAdjust(marketProb.homeWinPct, marketProb.drawPct, marketProb.awayWinPct, handicap);
  } else {
    oddsQuality = 0;
    const impliedHomePct = expectedH * 100;
    const impliedAwayPct = (1 - expectedH) * 100;
    const eloBasedDraw = Math.max(10, Math.min(32, 28 - eloDiff * 0.015));
    const totalNonDraw = impliedHomePct + impliedAwayPct;
    marketProb = {
      homeWinPct: +((impliedHomePct / totalNonDraw) * (100 - eloBasedDraw)).toFixed(1),
      drawPct: +eloBasedDraw.toFixed(1),
      awayWinPct: +((impliedAwayPct / totalNonDraw) * (100 - eloBasedDraw)).toFixed(1),
      overround: 100, isInferred: true
    };
  }

  // v5.0: 赔率质量影响市场权重
  const effectiveMarketWeight = marketWeight * (0.3 + oddsQuality * 0.7);
  const totalWeight = eloWeight + poissonWeight + economicWeight + (marketProb ? effectiveMarketWeight : 0);
  const baseW = eloWeight + poissonWeight + economicWeight;

  let fusedHomePct = (eloHomePct * eloWeight + poissonSim.homeWinPct * poissonWeight + ecoSim.homeWinPct * economicWeight) / baseW;
  let fusedDrawPct = (eloDrawPct * eloWeight + poissonSim.drawPct * poissonWeight + ecoSim.drawPct * economicWeight) / baseW;
  let fusedAwayPct = (eloAwayPct * eloWeight + poissonSim.awayWinPct * poissonWeight + ecoSim.awayWinPct * economicWeight) / baseW;

  if (marketProb) {
    fusedHomePct = (fusedHomePct * baseW + marketProb.homeWinPct * effectiveMarketWeight) / totalWeight;
    fusedDrawPct = (fusedDrawPct * baseW + marketProb.drawPct * effectiveMarketWeight) / totalWeight;
    fusedAwayPct = (fusedAwayPct * baseW + marketProb.awayWinPct * effectiveMarketWeight) / totalWeight;
  }

  const fTotal = fusedHomePct + fusedDrawPct + fusedAwayPct;
  fusedHomePct = +(fusedHomePct / fTotal * 100).toFixed(1);
  fusedDrawPct = +(fusedDrawPct / fTotal * 100).toFixed(1);
  fusedAwayPct = +(fusedAwayPct / fTotal * 100).toFixed(1);

  // 融合 λ
  let fusedLH = effLH * (poissonWeight + economicWeight) + (eloHomePct / 50) * eloWeight;
  let fusedLA = effLA * (poissonWeight + economicWeight) + (eloAwayPct / 50) * eloWeight;

  if (marketProb) {
    const marketLH = Math.max(0.3, Math.min(4.0, 0.15 + marketProb.homeWinPct * 0.035));
    const marketLA = Math.max(0.3, Math.min(4.0, 0.15 + marketProb.awayWinPct * 0.035));
    fusedLH = (fusedLH * (1 - effectiveMarketWeight) + marketLH * effectiveMarketWeight);
    fusedLA = (fusedLA * (1 - effectiveMarketWeight) + marketLA * effectiveMarketWeight);
  } else {
    fusedLH = fusedLH / baseW;
    fusedLA = fusedLA / baseW;
  }

  if (handicap) {
    const handicapBoost = Math.abs(handicap) * 0.25;
    if (handicap > 0) fusedLH += handicapBoost;
    else fusedLA += handicapBoost;
  }
  fusedLH = +(fusedLH).toFixed(2);
  fusedLA = +(fusedLA).toFixed(2);
  const fusedSim = v4.monteCarlo(fusedLH, fusedLA, simRuns, dcRho, isKnockout);

  // === v5.0: 阶段感知贝叶斯融合 ===
  let bayesianResult = null;
  if (marketProb && oddsHome && oddsDraw && oddsAway) {
    const modelProbs = {
      homeWinPct: fusedHomePct / 100,
      drawPct: fusedDrawPct / 100,
      awayWinPct: fusedAwayPct / 100,
    };
    const marketProbs = v4.market_probs_from_odds(oddsHome, oddsDraw, oddsAway);

    if (marketProbs) {
      const allProbs = [
        eloHomePct / 100,
        poissonSim.homeWinPct / 100,
        ecoSim.homeWinPct / 100,
        marketProbs.homeWinPct,
      ];
      const maxP = Math.max(...allProbs);
      const minP = Math.min(...allProbs);
      const spread = maxP - minP;
      const modelConfidence = Math.max(0.3, Math.min(0.9, 1.0 - spread * 1.5));

      // v5.0: 使用 config.mjs 的阶段权重
      const stageKey = isKnockout
        ? (stage || 'round_of_16')
        : 'group_stage';
      bayesianResult = v4.bayesian_fusion_js(modelProbs, marketProbs, stageKey, modelConfidence);

      if (bayesianResult) {
        fusedHomePct = bayesianResult.home_win;
        fusedDrawPct = bayesianResult.draw;
        fusedAwayPct = bayesianResult.away_win;
      }
    }
  }

  // === v5.0: 冷门检测 ===
  const predForUpset = {
    fusion: { winPct: fusedHomePct, drawPct: fusedDrawPct, awayPct: fusedAwayPct, lambda: { home: fusedLH, away: fusedLA } },
    models: {
      elo: { winPct: eloHomePct, awayPct: eloAwayPct },
      poisson: { winPct: poissonSim.homeWinPct, awayPct: poissonSim.awayWinPct },
      market: marketProb ? { winPct: marketProb.homeWinPct, drawPct: marketProb.drawPct, awayPct: marketProb.awayWinPct } : null,
    },
    weights: { elo: eloWeight, poisson: poissonWeight, economic: economicWeight, market: effectiveMarketWeight },
  };
  const upsetRisk = detectUpsetRisk(predForUpset, options);

  return {
    home, away,
    models: {
      elo: { rating: { home: eloH, away: eloA }, expected: eloHomePct, winPct: eloHomePct, drawPct: eloDrawPct, awayPct: eloAwayPct },
      poisson: { lambda: { home: effLH, away: effLA }, winPct: poissonSim.homeWinPct, drawPct: poissonSim.drawPct, awayPct: poissonSim.awayWinPct, dcRho: dynamicRho },
      economic: { winPct: ecoSim.homeWinPct, drawPct: ecoSim.drawPct, awayPct: ecoSim.awayWinPct },
      market: marketProb ? {
        odds: { home: oddsHome, draw: oddsDraw, away: oddsAway },
        handicap: handicap || null,
        winPct: marketProb.homeWinPct,
        drawPct: marketProb.drawPct,
        awayPct: marketProb.awayWinPct,
        oddsQuality,
      } : null,
    },
    weights: { elo: eloWeight, poisson: poissonWeight, economic: economicWeight, market: effectiveMarketWeight },
    bayesian: bayesianResult,
    fusion: {
      lambda: { home: fusedLH, away: fusedLA },
      winPct: fusedHomePct, drawPct: fusedDrawPct, awayPct: fusedAwayPct,
      top5: fusedSim.top5, avgGoals: fusedSim.avgGoals,
      totalRuns: fusedSim.totalRuns,
    },
    upsetRisk,
    engineVersion: 'v5.0-oracle-v2',
    timestamp: new Date().toISOString()
  };
}

// 默认导出兼容
export default {
  ...v4,
  fusionPredict,
  oddsQualityScore,
  detectUpsetRisk,
};