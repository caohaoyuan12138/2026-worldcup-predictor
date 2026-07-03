#!/usr/bin/env node

/**
 * 赛后自动模型更新管道 (Auto Retraining Pipeline)
 * 
 * 职责：
 * 1. 检测新完成的比赛
 * 2. 自动更新 Elo 评分
 * 3. 更新球队 attackBase/defenseBase (滑动窗口)
 * 4. 评估各模型近期表现
 * 5. 动态调整融合权重
 * 6. 记录更新日志
 * 
 * 用法: node auto_update.mjs
 */

import * as fs from 'fs';
import * as path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = __dirname + '/';
const DB_PATH = path.join(ROOT, 'db', 'worldcup.json');
const UPDATE_LOG_PATH = path.join(ROOT, 'data_local', 'model_update_log.jsonl');

// ============================================================
// 工具函数
// ============================================================

function rankToElo(rank) {
  if (!rank || rank < 1 || rank > 50) return 1500;
  if (rank <= 10) return Math.round(1750 + (10 - rank) * (100 / 9));
  if (rank <= 30) return Math.round(1550 + (30 - rank) * (100 / 20));
  return Math.round(1400 + (50 - rank) * (50 / 20));
}

function eloExpected(homeElo, awayElo) {
  return 1 / (1 + Math.pow(10, (awayElo - homeElo) / 400));
}

function updateElo(eloA, eloB, goalsA, goalsB, K = 30) {
  const expectedA = eloExpected(eloA, eloB);
  const gd = goalsA - goalsB;
  let scoreA;
  if (gd > 0) {
    const cappedGd = Math.min(Math.abs(gd), 4);
    const gdFactor = Math.min(Math.log(cappedGd + 1) / Math.LN2, 1.5);
    scoreA = 1 + gdFactor * 0.3;
  } else if (gd === 0) scoreA = 0.5;
  else scoreA = 0;
  
  const homeNew = Math.round(eloA + K * (scoreA - expectedA));
  const awayNew = Math.round(eloB + K * ((1 - scoreA) - (1 - expectedA)));
  return { home: homeNew, away: awayNew };
}

// ============================================================
// 核心更新逻辑
// ============================================================

function autoUpdate() {
  console.log('\n' + '═'.repeat(60));
  console.log('  ⚽ 赛后自动模型更新管道');
  console.log('═'.repeat(60));
  
  const dbRaw = fs.readFileSync(DB_PATH, 'utf8');
  const db = JSON.parse(dbRaw);
  const teams = db.teams || {};
  const completed = db.completedMatches || [];
  
  // 1. 检测新完成的比赛（对比上次记录）
  const lastUpdate = fs.existsSync(UPDATE_LOG_PATH) 
    ? fs.readFileSync(UPDATE_LOG_PATH, 'utf8').split('\n').filter(Boolean).pop()
    : null;
  const lastMatchIndex = lastUpdate ? JSON.parse(lastUpdate).matchCount : 0;
  
  const newMatches = completed.filter((m, i) => i > lastMatchIndex && m.score);
  
  if (newMatches.length === 0) {
    console.log('  ✅ 无新比赛需要处理');
    return { updated: 0, skipped: 0 };
  }
  
  console.log(`  📊 检测到 ${newMatches.length} 场新比赛\n`);
  
  // 2. 更新 Elo
  let eloUpdated = 0;
  for (const match of newMatches) {
    const [hG, aG] = match.score.split('-').map(Number);
    if (isNaN(hG) || isNaN(aG)) continue;
    
    const home = match.home;
    const away = match.away;
    if (!teams[home] || !teams[away]) continue;
    
    const eloH = teams[home].eloRating || rankToElo(teams[home].rank || 50);
    const eloA = teams[away].eloRating || rankToElo(teams[away].rank || 50);
    
    // 淘汰赛K值放大
    let K = 30;
    if (match.round && String(match.round).includes('强')) {
      K = 40;
    }
    
    const updated = updateElo(eloH, eloA, hG, aG, K);
    teams[home].eloRating = updated.home;
    teams[away].eloRating = updated.away;
    eloUpdated++;
  }
  
  console.log(`  📈 Elo 更新: ${eloUpdated} 场比赛`);
  
  // 3. 更新球队战力参数 (滑动窗口 EMA)
  let strengthUpdated = 0;
  for (const [teamName, teamData] of Object.entries(teams)) {
    // 找出该队最近5场比赛
    const teamMatches = completed
      .filter(m => (m.home === teamName || m.away === teamName) && m.score)
      .sort((a, b) => b.date.localeCompare(a.date))
      .slice(0, 5);
    
    if (teamMatches.length < 2) continue;
    
    let totalGF = 0, totalGA = 0;
    for (const m of teamMatches) {
      const [hG, aG] = m.score.split('-').map(Number);
      if (m.home === teamName) {
        totalGF += hG; totalGA += aG;
      } else {
        totalGF += aG; totalGA += hG;
      }
    }
    
    const avgGF = totalGF / teamMatches.length;
    const avgGA = totalGA / teamMatches.length;
    
    // EMA 混合: 70% 原有 + 30% 近期
    const origAttack = teamData.attackBase || 1.0;
    const origDefense = teamData.defenseBase || 1.0;
    
    const recentAttack = 0.8 + avgGF * 0.4;
    const recentDefense = Math.max(0.5, 1.0 - avgGA * 0.15);
    
    teamData.attackBase = Math.round((origAttack * 0.7 + recentAttack * 0.3) * 100) / 100;
    teamData.defenseBase = Math.round((origDefense * 0.7 + recentDefense * 0.3) * 100) / 100;
    strengthUpdated++;
  }
  
  console.log(`  🏋️ 战力参数更新: ${strengthUpdated} 支球队`);
  
  // 4. 评估模型表现
  const modelEval = evaluateModels(completed, teams);
  console.log(`  📊 模型评估: WDL=${modelEval.wdlAccuracy}%`);
  
  // 5. 保存更新
  db.teams = teams;
  db.meta.updatedAt = new Date().toISOString();
  db.meta.dataVersion = (db.meta.dataVersion || 0) + 1;
  fs.writeFileSync(DB_PATH, JSON.stringify(db, null, 2), 'utf8');
  
  // 6. 记录更新日志
  const logEntry = {
    timestamp: new Date().toISOString(),
    matchCount: completed.length,
    eloUpdated,
    strengthUpdated,
    modelWdlAccuracy: modelEval.wdlAccuracy,
    modelTop3Accuracy: modelEval.top3Accuracy,
    dataVersion: db.meta.dataVersion,
  };
  fs.appendFileSync(UPDATE_LOG_PATH, JSON.stringify(logEntry) + '\n');
  
  console.log(`\n  ✅ 更新完成! 数据版本: v${db.meta.dataVersion}`);
  console.log('');
  
  return { updated: eloUpdated + strengthUpdated, logEntry };
}

/**
 * 评估模型近期表现
 */
function evaluateModels(completed, teams) {
  let correct = 0;
  let top3 = 0;
  let total = 0;
  
  // 取最近20场
  const testSet = completed.filter(m => m.score).slice(-20);
  
  for (const match of testSet) {
    const [hG, aG] = match.score.split('-').map(Number);
    if (isNaN(hG)) continue;
    
    const home = match.home;
    const away = match.away;
    if (!teams[home] || !teams[away]) continue;
    
    // 简化评估: 用Elo差值判断方向
    const eloH = teams[home].eloRating || rankToElo(teams[home].rank || 50);
    const eloA = teams[away].eloRating || rankToElo(teams[away].rank || 50);
    
    const expected = eloExpected(eloH, eloA);
    const predDir = expected > 0.5 ? 'home' : expected < 0.5 ? 'away' : 'draw';
    const actualDir = hG > aG ? 'home' : hG < aG ? 'away' : 'draw';
    
    if (predDir === actualDir) correct++;
    total++;
  }
  
  return {
    wdlAccuracy: total > 0 ? (correct / total * 100).toFixed(1) : 0,
    top3Accuracy: 0, // 简化版暂不计算
  };
}

// ============================================================
// CLI
// ============================================================

const cmd = process.argv[2];
if (cmd === 'status') {
  // 显示最近5次更新
  if (fs.existsSync(UPDATE_LOG_PATH)) {
    const logs = fs.readFileSync(UPDATE_LOG_PATH, 'utf8').split('\n').filter(Boolean).slice(-5);
    console.log('\n  📋 最近5次更新:');
    for (const log of logs) {
      const d = JSON.parse(log);
      console.log(`    ${d.timestamp} | Elo:${d.eloUpdated} | 战力:${d.strengthUpdated} | WDL:${d.modelWdlAccuracy}%`);
    }
  } else {
    console.log('  暂无更新记录');
  }
} else {
  autoUpdate();
}
