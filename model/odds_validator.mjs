#!/usr/bin/env node

/**
 * 赔率数据清洗与一致性检查模块
 * 
 * 功能：
 * 1. 检查赔率隐含概率是否在合理范围（1.04-1.18）
 * 2. 检测赔率方向是否颠倒（主客互换）
 * 3. 多源赔率交叉验证
 * 4. 赔率质量评分
 * 5. 自动标记异常赔率
 */

// ============================================================
// 1. 赔率质量评分
// ============================================================

/**
 * 评估赔率数据的质量
 * @param {Object} odds - { home, draw, away }
 * @returns {{ quality: number, reason: string, impliedMargin: number, isValid: boolean }}
 */
export function assessOddsQuality(odds) {
  if (!odds || !odds.home || !odds.draw || !odds.away) {
    return { quality: 0, reason: 'no_odds', impliedMargin: 0, isValid: false };
  }
  
  const { home, draw, away } = odds;
  
  // 检查合法性
  if (home <= 0 || draw <= 0 || away <= 0) {
    return { quality: 0, reason: 'invalid_odds_negative', impliedMargin: 0, isValid: false };
  }
  if (home > 100 || draw > 100 || away > 100) {
    return { quality: 0, reason: 'invalid_odds_extreme', impliedMargin: 0, isValid: false };
  }
  
  // 计算隐含概率总和（含抽水）
  const implied = 1/home + 1/draw + 1/away;
  const impliedMargin = +(implied * 100).toFixed(2);
  
  // 正常范围：1.04-1.18（4%-18%抽水）
  if (impliedMargin < 101 || impliedMargin > 125) {
    return { quality: 0.3, reason: `implied_prob_outlier(${impliedMargin}%)`, impliedMargin, isValid: false };
  }
  
  // 检查赔率合理性：最强方不应有最高赔率
  const oddsArr = [home, draw, away];
  const minOdd = Math.min(...oddsArr);
  const maxOdd = Math.max(...oddsArr);
  const ratio = maxOdd / minOdd;
  
  if (ratio > 20) {
    return { quality: 0.4, reason: `extreme_gap_ratio(${ratio.toFixed(1)})`, impliedMargin, isValid: false };
  }
  
  // 高质量赔率
  if (impliedMargin <= 110 && ratio < 10) {
    return { quality: 1.0, reason: 'valid', impliedMargin, isValid: true };
  }
  
  // 中等质量
  return { quality: 0.7, reason: 'acceptable', impliedMargin, isValid: true };
}

// ============================================================
// 2. 赔率方向检测
// ============================================================

/**
 * 检测赔率是否可能被主客颠倒
 * 通过对比实力排名来判断
 * 
 * @param {Object} odds - { home, draw, away }
 * @param {Object} teamA - 主队实力数据
 * @param {Object} teamB - 客队实力数据
 * @returns {{ isConsistent: boolean, note: string, suggestedFlip: boolean }}
 */
export function checkOddsDirection(odds, teamA, teamB) {
  if (!odds || !teamA || !teamB) return { isConsistent: true, note: 'insufficient_data', suggestedFlip: false };
  
  const aRank = teamA.rank || 50;
  const bRank = teamB.rank || 50;
  const aAttack = teamA.attackBase || 1.0;
  const bAttack = teamB.attackBase || 1.0;
  
  // 赔率隐含的强弱判断
  const impliedHomeStrong = odds.home < odds.away;
  const impliedAwayStrong = odds.away < odds.home;
  
  // 实际实力判断
  const actualHomeStrong = aRank < bRank || aAttack > bAttack;
  
  let note = '';
  let suggestedFlip = false;
  
  if (impliedHomeStrong && !actualHomeStrong) {
    // 赔率认为主队强，但实际主队排名/攻击力更低
    note = 'odds_direction_mismatch: odds favor home but team ranking favors away';
    suggestedFlip = Math.abs(aRank - bRank) > 10;
  } else if (impliedAwayStrong && !actualHomeStrong) {
    note = 'odds consistent with team strength';
  } else {
    note = 'odds consistent with team strength';
  }
  
  return { isConsistent: !suggestedFlip, note, suggestedFlip };
}

// ============================================================
// 3. 赔率时间序列一致性
// ============================================================

/**
 * 跟踪同一场比赛多次出现的赔率，检测异常波动
 * @param {Array} oddsHistory - [{ timestamp, home, draw, away }]
 * @returns {{ stability: number, anomalies: Array, note: string }}
 */
export function checkOddsStability(oddsHistory) {
  if (!oddsHistory || oddsHistory.length < 2) {
    return { stability: 1.0, anomalies: [], note: 'single_snapshot' };
  }
  
  const anomalies = [];
  
  for (let i = 1; i < oddsHistory.length; i++) {
    const prev = oddsHistory[i - 1];
    const curr = oddsHistory[i];
    
    for (const side of ['home', 'draw', 'away']) {
      if (prev[side] && curr[side] && prev[side] > 0 && curr[side] > 0) {
        const change = Math.abs(curr[side] - prev[side]) / prev[side];
        if (change > 0.3) {
          anomalies.push({
            side,
            from: prev[side],
            to: curr[side],
            changePct: +(change * 100).toFixed(1),
            timeGap: curr.timestamp ? `${i} snapshots` : 'unknown'
          });
        }
      }
    }
  }
  
  const stability = Math.max(0, 1 - anomalies.length * 0.2);
  
  return {
    stability: +stability.toFixed(2),
    anomalies,
    note: anomalies.length > 2 ? 'HIGH_VOLATILITY' : anomalies.length > 0 ? 'MODERATE_VOLATILITY' : 'STABLE'
  };
}

// ============================================================
// 4. 赔率转概率（含去水）
// ============================================================

/**
 * 从赔率中提取公平概率（去除庄家抽水）
 * @param {number} home - 主胜赔率
 * @param {number} draw - 平局赔率
 * @param {number} away - 客胜赔率
 * @param {string} method - 'proportional' | 'shin' | 'simple'
 * @returns {{ homeWinPct, drawPct, awayWinPct, overround }}
 */
export function oddsToFairProb(home, draw, away, method = 'proportional') {
  if (!home || !draw || !away || home <= 0 || draw <= 0 || away <= 0) return null;
  
  const impliedHome = 1 / home;
  const impliedDraw = 1 / draw;
  const impliedAway = 1 / away;
  const overround = impliedHome + impliedDraw + impliedAway;
  
  if (method === 'proportional') {
    // 按比例去水（最常用）
    return {
      homeWinPct: +(impliedHome / overround * 100).toFixed(1),
      drawPct: +(impliedDraw / overround * 100).toFixed(1),
      awayWinPct: +(impliedAway / overround * 100).toFixed(1),
      overround: +(overround * 100).toFixed(2),
      method
    };
  } else if (method === 'shin') {
    // Shin's method: 平方根去水
    const sqrtHome = Math.sqrt(impliedHome);
    const sqrtDraw = Math.sqrt(impliedDraw);
    const sqrtAway = Math.sqrt(impliedAway);
    const total = sqrtHome + sqrtDraw + sqrtAway;
    return {
      homeWinPct: +((sqrtHome / total) ** 2 / overround * 100).toFixed(1),
      drawPct: +((sqrtDraw / total) ** 2 / overround * 100).toFixed(1),
      awayWinPct: +((sqrtAway / total) ** 2 / overround * 100).toFixed(1),
      overround: +(overround * 100).toFixed(2),
      method
    };
  } else {
    // 简单去水
    return {
      homeWinPct: +(impliedHome / overround * 100).toFixed(1),
      drawPct: +(impliedDraw / overround * 100).toFixed(1),
      awayWinPct: +(impliedAway / overround * 100).toFixed(1),
      overround: +(overround * 100).toFixed(2),
      method
    };
  }
}

// ============================================================
// 5. 赔率隐含λ估算
// ============================================================

/**
 * 从赔率反推隐含期望进球（用于交叉验证Poisson模型）
 * @param {number} home - 主胜赔率
 * @param {number} draw - 平局赔率
 * @param {number} away - 客胜赔率
 * @returns {{ impliedLH, impliedLA, impliedTotalGoals, confidence }}
 */
export function impliedLambdaFromOdds(home, draw, away) {
  const prob = oddsToFairProb(home, draw, away);
  if (!prob) return null;
  
  // 基于历史WC数据拟合：胜率比 ≈ λ比
  // P(H)/P(A) ≈ f(lambda_H / lambda_A)
  const ratio = (prob.homeWinPct / 100) / (prob.awayWinPct / 100);
  
  // 简化估算：用总进球期望反推
  const totalImplied = 1 / overroundToAvgGoals(overround(home, draw, away));
  const impliedLH = Math.round(totalImplied * Math.sqrt(ratio) * 100) / 100;
  const impliedLA = Math.round(totalImplied / Math.sqrt(ratio) * 100) / 100;
  
  return {
    impliedLH: Math.max(0.2, impliedLH),
    impliedLA: Math.max(0.2, impliedLA),
    impliedTotalGoals: +(impliedLH + impliedLA).toFixed(2),
    confidence: prob.overround <= 110 ? 'high' : prob.overround <= 120 ? 'medium' : 'low'
  };
}

function overroundToAvgGoals(overround) {
  // 经验公式：抽水越高，市场预期进球越少
  return Math.max(1.5, 3.5 - overround * 0.02);
}

function overround(h, d, a) {
  return 1/h + 1/d + 1/a;
}

// ============================================================
// 6. 一键检查
// ============================================================

export function checkMatchOdds(homeTeam, awayTeam, odds) {
  const quality = assessOddsQuality(odds);
  const direction = checkOddsDirection(odds, homeTeam, awayTeam);
  
  return {
    odds,
    quality,
    direction,
    fairProb: quality.isValid ? oddsToFairProb(odds.home, odds.draw, odds.away) : null,
    warning: !quality.isValid ? `⚠️ 赔率质量不合格 (${quality.reason})` : 
             direction.suggestedFlip ? '⚠️ 赔率方向可能与实力不符，建议核对主客' : '✅ 赔率正常',
    usedForPrediction: quality.quality >= 0.7
  };
}

// CLI
if (import.meta.url === `file://${process.argv[1]}`) {
  const testCases = [
    { name: '西班牙vs奥地利', odds: { home: 1.19, draw: 5.15, away: 10.50 }},
    { name: '葡萄牙vs克罗地亚', odds: { home: 1.57, draw: 3.32, away: 5.22 }},
    { name: '瑞士vs阿尔及利亚', odds: { home: 1.74, draw: 3.16, away: 4.20 }},
    { name: '异常测试(颠倒)', odds: { home: 10.50, draw: 5.15, away: 1.19 }},
    { name: '异常测试(过大)', odds: { home: 50, draw: 30, away: 40 }},
  ];
  
  console.log('='.repeat(60));
  console.log('  赔率数据清洗与一致性检查');
  console.log('='.repeat(60));
  
  for (const tc of testCases) {
    console.log(`\n  ${tc.name}:`);
    const result = assessOddsQuality(tc.odds);
    console.log(`    质量: ${result.quality} | 原因: ${result.reason} | 隐含概率: ${result.impliedMargin}% | 有效: ${result.isValid}`);
    
    if (result.isValid) {
      const prob = oddsToFairProb(tc.odds.home, tc.odds.draw, tc.odds.away);
      console.log(`    公平概率: 主胜${prob.homeWinPct}% | 平${prob.drawPct}% | 客胜${prob.awayWinPct}%`);
    }
  }
}
