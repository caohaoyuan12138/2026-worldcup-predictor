#!/usr/bin/env node

/**
 * 趋势数据生成器
 * 
 * 从 prediction_log.jsonl + worldcup.json 中提取时间序列数据，
 * 供前端图表展示：
 * 1. Elo 评分趋势
 * 2. 预测准确率趋势
 * 3. 模型分歧趋势
 * 4. 进球期望趋势
 * 
 * 用法: node trend_generator.mjs
 */

import * as fs from 'fs';
import * as path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = __dirname + '/';
const DB_PATH = path.join(ROOT, 'db', 'worldcup.json');
const LOG_PATH = path.join(ROOT, 'prediction_log.jsonl');

function generateTrends() {
  console.log('📈 生成趋势数据...\n');
  
  const dbRaw = fs.readFileSync(DB_PATH, 'utf8');
  const db = JSON.parse(dbRaw);
  const teams = db.teams || {};
  
  // 1. Elo 历史趋势
  const eloTrend = [];
  for (const [name, data] of Object.entries(teams)) {
    if (data.eloRating) {
      eloTrend.push({
        team: name,
        elo: data.eloRating,
        rank: data.rank,
        attackBase: data.attackBase,
        defenseBase: data.defenseBase,
      });
    }
  }
  eloTrend.sort((a, b) => b.elo - a.elo);
  
  // 2. 预测日志趋势
  const predictionTrend = [];
  if (fs.existsSync(LOG_PATH)) {
    const logs = fs.readFileSync(LOG_PATH, 'utf8').split('\n').filter(Boolean);
    for (const line of logs.slice(-50)) { // 最近50条
      try {
        const log = JSON.parse(line);
        if (log.fusion && log.fusion.winPct !== undefined) {
          predictionTrend.push({
            timestamp: log.timestamp || new Date().toISOString(),
            home: log.home || log.match?.split(' vs ')[0],
            away: log.away || log.match?.split(' vs ')[1],
            homeWinPct: log.fusion.winPct,
            drawPct: log.fusion.drawPct,
            awayWinPct: log.fusion.awayPct,
            topScore: log.fusion.top5?.[0]?.score,
          });
        }
      } catch (e) { /* skip */ }
    }
  }
  predictionTrend.reverse();
  
  // 3. 模型分歧趋势 (Elo vs Poisson vs Market)
  const divergenceTrend = [];
  for (const log of predictionTrend.slice(-20)) {
    // 简化: 用胜率最大值与最小值的差衡量分歧
    const probs = [log.homeWinPct, log.drawPct, log.awayWinPct];
    const spread = Math.max(...probs) - Math.min(...probs);
    divergenceTrend.push({
      timestamp: log.timestamp,
      match: `${log.home} vs ${log.away}`,
      spread: spread.toFixed(1),
      maxProb: Math.max(...probs).toFixed(1),
    });
  }
  
  // 4. 进球期望趋势
  const lambdaTrend = [];
  for (const log of predictionTrend.slice(-20)) {
    if (log.fusion?.lambda) {
      lambdaTrend.push({
        timestamp: log.timestamp,
        match: `${log.home} vs ${log.away}`,
        homeLambda: log.fusion.lambda.home,
        awayLambda: log.fusion.lambda.away,
        totalGoals: log.fusion.avgGoals,
      });
    }
  }
  
  // 5. 准确率趋势 (如果有实际结果对比)
  const accuracyTrend = [];
  const completed = db.completedMatches || [];
  for (const match of completed.slice(-20)) {
    if (!match.score) continue;
    // 简化: 用Elo差值判断预测方向
    const home = match.home;
    const away = match.away;
    if (!teams[home] || !teams[away]) continue;
    
    const eloH = teams[home].eloRating || 1500;
    const eloA = teams[away].eloRating || 1500;
    const predDir = eloH > eloA ? 'home' : eloH < eloA ? 'away' : 'draw';
    
    const [hG, aG] = match.score.split('-').map(Number);
    const actualDir = hG > aG ? 'home' : hG < aG ? 'away' : 'draw';
    
    accuracyTrend.push({
      date: match.date,
      match: `${home} vs ${away}`,
      predicted: predDir,
      actual: actualDir,
      correct: predDir === actualDir,
    });
  }
  
  const result = {
    eloTrend,
    predictionTrend,
    divergenceTrend,
    lambdaTrend,
    accuracyTrend,
    generatedAt: new Date().toISOString(),
  };
  
  // 保存到 data_local
  const outPath = path.join(ROOT, 'data_local', 'trends.json');
  fs.mkdirSync(path.dirname(outPath), { recursive: true });
  fs.writeFileSync(outPath, JSON.stringify(result, null, 2));
  
  console.log(`  Elo趋势: ${eloTrend.length} 队`);
  console.log(`  预测趋势: ${predictionTrend.length} 条`);
  console.log(`  模型分歧: ${divergenceTrend.length} 场`);
  console.log(`  进球期望: ${lambdaTrend.length} 场`);
  console.log(`  准确率: ${accuracyTrend.length} 场`);
  console.log(`  📁 已保存: ${outPath}\n`);
  
  return result;
}

generateTrends();
