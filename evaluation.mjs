#!/usr/bin/env node

/**
 * ⚽ 预测评估器 — 量化模型表现
 * 
 * 用法: node evaluation.mjs
 * 
 * 评估指标:
 * 1. WDL 准确率 (胜平负)
 * 2. Top1/Top3 比分命中率
 * 3. 大小球准确率
 * 4. 期望进球误差 (MAE)
 * 5. Log Loss / Brier Score
 * 6. 冷门检测率
 * 7. 置信度校准 (可靠性曲线)
 */

import * as fs from 'fs';
import * as path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const DB_DIR = path.join(__dirname, 'db');

// ============================================================
// 加载数据
// ============================================================

const worldcupData = JSON.parse(fs.readFileSync(path.join(DB_DIR, 'worldcup.json'), 'utf8'));
const completedMatches = (worldcupData.completedMatches || []).filter(m => m.score && m.score.includes('-'));

// 加载预测日志
const predLogPath = path.join(__dirname, 'prediction_log.jsonl');
const predictions = [];
if (fs.existsSync(predLogPath)) {
  const lines = fs.readFileSync(predLogPath, 'utf8').trim().split('\n');
  for (const line of lines) {
    try {
      predictions.push(JSON.parse(line));
    } catch (e) { /* skip invalid */ }
  }
}

// ============================================================
// 核心评估函数
// ============================================================

/** 解析比分字符串 */
function parseScore(scoreStr) {
  if (!scoreStr) return null;
  const parts = scoreStr.split('-').map(Number);
  if (parts.some(isNaN)) return null;
  return { home: parts[0], away: parts[1] };
}

/** 计算 WDL */
function getWDL(homeGoals, awayGoals) {
  if (homeGoals > awayGoals) return 'home';
  if (homeGoals < awayGoals) return 'away';
  return 'draw';
}

/** 计算 Log Loss */
function logLoss(actualProb, predictedProb) {
  if (predictedProb <= 0.001) predictedProb = 0.001;
  if (predictedProb >= 0.999) predictedProb = 0.999;
  return -Math.log(predictedProb);
}

/** 计算 Brier Score */
function brierScore(actualOutcome, predictedProb) {
  const actualBinary = actualOutcome ? 1 : 0;
  return Math.pow(predictedProb - actualBinary, 2);
}

// ============================================================
// 1. WDL 准确率
// ============================================================

function evaluateWDLPrediction() {
  const results = { correct: 0, total: 0, byConfidence: {}, byStage: {} };
  
  for (const pred of predictions) {
    if (!pred.topPredictions || !pred.match) continue;
    
    // 找到对应的实际比赛结果
    const actualMatch = completedMatches.find(m => {
      const mStr = `${m.home} vs ${m.away}`;
      const pStr = pred.match.replace(' vs ', ' vs ');
      return mStr === pStr || 
             m.home === pred.home && m.away === pred.away;
    });
    
    if (!actualMatch || !actualMatch.score) continue;
    
    const actual = parseScore(actualMatch.score);
    if (!actual) continue;
    
    const actualWDL = getWDL(actual.home, actual.away);
    results.total++;
    
    // 方法1: 用 fusionProb 的 WDL 预测（概率最高的结果）
    let probWDL = null;
    if (pred.fusionProb) {
      if (pred.fusionProb.winPct >= pred.fusionProb.drawPct && pred.fusionProb.winPct >= pred.fusionProb.awayPct) probWDL = 'home';
      else if (pred.fusionProb.awayPct >= pred.fusionProb.winPct && pred.fusionProb.awayPct >= pred.fusionProb.drawPct) probWDL = 'away';
      else probWDL = 'draw';
    }
    
    // 方法2: 用 Top1 比分的 WDL
    const topPred = pred.topPredictions?.[0];
    let scoreWDL = null;
    if (topPred) {
      scoreWDL = topPred.h > topPred.a ? 'home' : topPred.h < topPred.a ? 'away' : 'draw';
    }
    
    // 记录概率预测的准确率
    if (probWDL === actualWDL) results.correct++;
    
    // 按阶段统计
    const stage = pred.isKnockout ? 'knockout' : 'group';
    if (!results.byStage[stage]) results.byStage[stage] = { correct: 0, total: 0 };
    results.byStage[stage].total++;
    if (probWDL === actualWDL) {
      results.byStage[stage].correct++;
    }
  }
  
  return {
    accuracy: results.total > 0 ? (results.correct / results.total * 100).toFixed(1) : 'N/A',
    total: results.total,
    correct: results.correct,
    byStage: results.byStage,
  };
}

// ============================================================
// 2. 比分命中率
// ============================================================

function evaluateScorePrediction() {
  const results = { top1: 0, top3: 0, top5: 0, total: 0 };
  
  for (const pred of predictions) {
    if (!pred.topPredictions || !pred.match) continue;
    
    const actualMatch = completedMatches.find(m => 
      m.home === pred.home && m.away === pred.away && m.score
    );
    if (!actualMatch) continue;
    
    const actual = parseScore(actualMatch.score);
    if (!actual) continue;
    
    const actualScore = `${actual.home}-${actual.away}`;
    results.total++;
    
    // Top1
    if (pred.topPredictions[0]?.score === actualScore) results.top1++;
    
    // Top3
    if (pred.topPredictions.slice(0, 3).some(p => p.score === actualScore)) results.top3++;
    
    // Top5
    if (pred.topPredictions.slice(0, 5).some(p => p.score === actualScore)) results.top5++;
  }
  
  return {
    top1: results.total > 0 ? (results.top1 / results.total * 100).toFixed(1) : 'N/A',
    top3: results.total > 0 ? (results.top3 / results.total * 100).toFixed(1) : 'N/A',
    top5: results.total > 0 ? (results.top5 / results.total * 100).toFixed(1) : 'N/A',
    total: results.total,
  };
}

// ============================================================
// 3. 大小球准确率
// ============================================================

function evaluateOverUnder() {
  const thresholds = [1.5, 2.5, 3.5];
  const results = {};
  
  for (const th of thresholds) {
    let correct = 0, total = 0;
    
    for (const pred of predictions) {
      if (!pred.topPredictions || !pred.match) continue;
      
      const actualMatch = completedMatches.find(m =>
        m.home === pred.home && m.away === pred.away && m.score
      );
      if (!actualMatch || !actualMatch.score) continue;
      
      const actual = parseScore(actualMatch.score);
      if (!actual) continue;
      
      const actualTotal = actual.home + actual.away;
      const actualOver = actualTotal > th;
      
      // 用预测 Top1 比分的总进球数
      const predTotal = pred.topPredictions[0]?.h + pred.topPredictions[0]?.a;
      const predOver = predTotal > th;
      
      total++;
      if (predOver === actualOver) correct++;
    }
    
    results[`over_under_${th}`] = {
      total,
      accuracy: total > 0 ? (correct / total * 100).toFixed(1) : 'N/A',
    };
  }
  
  return results;
}

// ============================================================
// 4. 期望进球误差
// ============================================================

function evaluateGoalError() {
  let totalError = 0, count = 0;
  const errorsByStage = { group: [], knockout: [] };
  
  for (const pred of predictions) {
    if (!pred.fusionLambda || !pred.match) continue;
    
    const actualMatch = completedMatches.find(m =>
      m.home === pred.home && m.away === pred.away && m.score
    );
    if (!actualMatch || !actualMatch.score) continue;
    
    const actual = parseScore(actualMatch.score);
    if (!actual) continue;
    
    const predHomeGoals = pred.fusionLambda.home;
    const predAwayGoals = pred.fusionLambda.away;
    
    const homeError = Math.abs(predHomeGoals - actual.home);
    const awayError = Math.abs(predAwayGoals - actual.away);
    totalError += homeError + awayError;
    count++;
    
    const arr = pred.isKnockout ? errorsByStage.knockout : errorsByStage.group;
    arr.push(homeError + awayError);
  }
  
  return {
    mae: count > 0 ? (totalError / count).toFixed(2) : 'N/A',
    groupMAE: errorsByStage.group.length > 0 ? 
      (errorsByStage.group.reduce((a,b) => a+b, 0) / errorsByStage.group.length).toFixed(2) : 'N/A',
    knockoutMAE: errorsByStage.knockout.length > 0 ? 
      (errorsByStage.knockout.reduce((a,b) => a+b, 0) / errorsByStage.knockout.length).toFixed(2) : 'N/A',
  };
}

// ============================================================
// 5. Log Loss / Brier Score
// ============================================================

function evaluateProbabilisticScores() {
  let totalLogLoss = 0, totalBrier = 0, count = 0;
  
  for (const pred of predictions) {
    if (!pred.fusionProb || !pred.match) continue;
    
    const actualMatch = completedMatches.find(m =>
      m.home === pred.home && m.away === pred.away && m.score
    );
    if (!actualMatch || !actualMatch.score) continue;
    
    const actual = parseScore(actualMatch.score);
    if (!actual) continue;
    
    const actualWDL = getWDL(actual.home, actual.away);
    
    // Log Loss
    let prob;
    if (actualWDL === 'home') prob = pred.fusionProb.winPct / 100;
    else if (actualWDL === 'away') prob = pred.fusionProb.awayPct / 100;
    else prob = pred.fusionProb.drawPct / 100;
    
    totalLogLoss += logLoss(true, prob);
    
    // Brier Score (binary: did the predicted outcome happen?)
    const topPredWDL = pred.topPredictions[0] ? 
      (pred.topPredictions[0].h > pred.topPredictions[0].a ? 'home' :
       pred.topPredictions[0].h < pred.topPredictions[0].a ? 'away' : 'draw') : null;
    
    if (topPredWDL) {
      let binaryProb;
      if (topPredWDL === 'home') binaryProb = pred.fusionProb.winPct / 100;
      else if (topPredWDL === 'away') binaryProb = pred.fusionProb.awayPct / 100;
      else binaryProb = pred.fusionProb.drawPct / 100;
      
      totalBrier += brierScore(topPredWDL === actualWDL, binaryProb);
    }
    
    count++;
  }
  
  return {
    avgLogLoss: count > 0 ? (totalLogLoss / count).toFixed(3) : 'N/A',
    avgBrier: count > 0 ? (totalBrier / count).toFixed(3) : 'N/A',
  };
}

// ============================================================
// 6. 冷门检测
// ============================================================

function evaluateUpsetDetection() {
  let detected = 0, totalUpsets = 0, correct = 0;
  
  for (const pred of predictions) {
    if (!pred.fusionProb || !pred.match) continue;
    
    const actualMatch = completedMatches.find(m =>
      m.home === pred.home && m.away === pred.away && m.score
    );
    if (!actualMatch || !actualMatch.score) continue;
    
    const actual = parseScore(actualMatch.score);
    if (!actual) continue;
    
    const actualWDL = getWDL(actual.home, actual.away);
    const predWDL = pred.fusionProb.winPct >= pred.fusionProb.awayPct ? 'home' : 'away';
    
    // 冷门定义: 预测 favored 一方输
    const favored = pred.fusionProb.winPct > pred.fusionProb.awayPct ? pred.home : pred.away;
    const underdog = pred.fusionProb.winPct > pred.fusionProb.awayPct ? pred.away : pred.home;
    
    // 判断是否是冷门
    const probDiff = Math.abs(pred.fusionProb.winPct - pred.fusionProb.awayPct);
    if (probDiff > 15) { // 概率差 > 15% 才算有明确 favored
      totalUpsets++;
      if (actualWDL === 'away' && pred.fusionProb.winPct > 55) {
        // 预测主胜但客胜 = 冷门
        detected++;
        // 检查模型是否标记了 upset
        if (pred.upset) correct++;
      } else if (actualWDL === 'home' && pred.fusionProb.awayPct > 55) {
        detected++;
        if (pred.upset) correct++;
      }
    }
  }
  
  return {
    totalUpsets: detected,
    modelMarked: correct,
    detectionRate: detected > 0 ? (correct / detected * 100).toFixed(1) : 'N/A',
  };
}

// ============================================================
// 7. 模型一致性
// ============================================================

function evaluateModelAgreement() {
  let consistent = 0, total = 0, disagreements = [];
  
  for (const pred of predictions) {
    if (!pred.modelProb || !pred.fusionProb) continue;
    
    // 各模型对 WDL 的看法是否一致
    const models = [pred.modelProb.elo, pred.modelProb.poisson, pred.modelProb.economic];
    if (!models[0] || !models[1] || !models[2]) continue;
    
    total++;
    
    const eloWinner = models[0].winPct > models[0].awayPct ? 'home' : 'away';
    const poisWinner = models[1].winPct > models[1].awayPct ? 'home' : 'away';
    const econWinner = models[2].winPct > models[2].awayPct ? 'home' : 'away';
    
    if (eloWinner === poisWinner && poisWinner === econWinner) {
      consistent++;
    } else {
      disagreements.push({
        match: pred.match,
        elo: eloWinner,
        poisson: poisWinner,
        economic: econWinner,
      });
    }
  }
  
  return {
    agreementRate: total > 0 ? (consistent / total * 100).toFixed(1) : 'N/A',
    total,
    disagreements: disagreements.slice(0, 5), // 只显示前5个
  };
}

// ============================================================
// 主函数
// ============================================================

async function main() {
  console.log('');
  console.log('╔═══════════════════════════════════════════════════════════╗');
  console.log('║  ⚽ 世界杯预测模型评估报告                                ║');
  console.log('╚═══════════════════════════════════════════════════════════╝');
  console.log('');
  
  console.log(`📊 总比赛场次: ${completedMatches.length}`);
  console.log(`📝 总预测记录: ${predictions.length}`);
  console.log('');
  
  // 1. WDL 准确率
  const wdl = evaluateWDLPrediction();
  console.log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
  console.log('📋 1. WDL 准确率 (胜平负)');
  console.log(`   总准确率: ${wdl.accuracy}% (${wdl.correct}/${wdl.total})`);
  if (wdl.byStage.knockout) {
    console.log(`   淘汰赛: ${(wdl.byStage.knockout.correct / wdl.byStage.knockout.total * 100).toFixed(1)}%`);
  }
  if (wdl.byStage.group) {
    console.log(`   小组赛: ${(wdl.byStage.group.correct / wdl.byStage.group.total * 100).toFixed(1)}%`);
  }
  console.log('');
  
  // 2. 比分命中率
  const score = evaluateScorePrediction();
  console.log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
  console.log('📋 2. 比分命中率');
  console.log(`   Top1: ${score.top1}%`);
  console.log(`   Top3: ${score.top3}%`);
  console.log(`   Top5: ${score.top5}%`);
  console.log(`   有效样本: ${score.total}`);
  console.log('');
  
  // 3. 大小球
  const ou = evaluateOverUnder();
  console.log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
  console.log('📋 3. 大小球准确率');
  for (const [key, val] of Object.entries(ou)) {
    console.log(`   ${key}: ${val.accuracy}% (${val.total} 场)`);
  }
  console.log('');
  
  // 4. 期望进球误差
  const mae = evaluateGoalError();
  console.log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
  console.log('📋 4. 期望进球误差 (MAE)');
  console.log(`   总体 MAE: ${mae.mae}`);
  console.log(`   小组赛 MAE: ${mae.groupMAE}`);
  console.log(`   淘汰赛 MAE: ${mae.knockoutMAE}`);
  console.log('');
  
  // 5. Log Loss / Brier
  const probs = evaluateProbabilisticScores();
  console.log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
  console.log('📋 5. 概率评分');
  console.log(`   Log Loss: ${probs.avgLogLoss} (越低越好, <0.8 优秀)`);
  console.log(`   Brier Score: ${probs.avgBrier} (越低越好, <0.15 优秀)`);
  console.log('');
  
  // 6. 冷门检测
  const upset = evaluateUpsetDetection();
  console.log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
  console.log('📋 6. 冷门检测');
  console.log(`   检测到的冷门: ${upset.totalUpsets}`);
  console.log(`   模型标记率: ${upset.detectionRate}%`);
  console.log('');
  
  // 7. 模型一致性
  const agree = evaluateModelAgreement();
  console.log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
  console.log('📋 7. 模型一致性');
  console.log(`   一致率: ${agree.agreementRate}% (${agree.total} 场)`);
  if (agree.disagreements.length > 0) {
    console.log('   分歧案例 (前5):');
    for (const d of agree.disagreements) {
      console.log(`     ${d.match}: Elo=${d.elo}, Poisson=${d.poisson}, Economic=${d.economic}`);
    }
  }
  console.log('');
  
  // 总结
  console.log('╔═══════════════════════════════════════════════════════════╗');
  console.log('║  📌 总结                                                  ║');
  console.log('╚═══════════════════════════════════════════════════════════╝');
  
  const wdlNum = parseFloat(wdl.accuracy) || 0;
  if (wdlNum >= 60) {
    console.log('✅ WDL 准确率优秀 (>60%)');
  } else if (wdlNum >= 50) {
    console.log('⚠️ WDL 准确率一般 (50-60%)');
  } else {
    console.log('❌ WDL 准确率偏低 (<50%)');
  }
  
  const scoreNum = parseFloat(score.top3) || 0;
  if (scoreNum < 20) {
    console.log('⚠️ Top3 比分命中率偏低 (<20%) — 这是正常的，足球比分本来就难猜');
  }
  
  const logLossNum = parseFloat(probs.avgLogLoss) || 999;
  if (logLossNum > 1.0) {
    console.log('❌ Log Loss 偏高，概率预测不够准');
  }
  
  const agreeNum = parseFloat(agree.agreementRate) || 0;
  if (agreeNum < 60) {
    console.log('⚠️ 模型间分歧较大，需要统一数据源');
  }
  
  console.log('');
}

main().catch(console.error);
