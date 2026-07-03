#!/usr/bin/env node

/**
 * 数据质量评分仪表板 (Data Quality Dashboard)
 * 
 * 对 worldcup.json 进行全面数据质量扫描，输出：
 * 1. 总体质量评分 (0-100)
 * 2. 各维度评分（完整性/一致性/时效性/准确性）
 * 3. 具体问题清单
 * 4. 修复建议
 * 
 * 用法: node data_quality.mjs
 */

import * as fs from 'fs';
import * as path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.join(__dirname);
const DB_PATH = path.join(ROOT, 'db', 'worldcup.json');

// ============================================================
// 质量评分计算
// ============================================================

function assessDataQuality() {
  const dbRaw = fs.readFileSync(DB_PATH, 'utf8');
  const db = JSON.parse(dbRaw);
  
  const scores = {
    completeness: { max: 30, earned: 0, issues: [] },
    consistency: { max: 25, earned: 0, issues: [] },
    timeliness: { max: 25, earned: 0, issues: [] },
    accuracy: { max: 20, earned: 0, issues: [] },
  };
  
  // ---- 完整性 (Completeness) ----
  const teams = db.teams || {};
  const completed = db.completedMatches || [];
  const upcoming = db.upcomingMatches || [];
  const knockout = db.knockoutMatches || [];
  
  // 球队字段完整度
  const requiredTeamFields = ['attackBase', 'defenseBase', 'styleFactor', 'rank', 'eloRating'];
  let teamFieldTotal = 0;
  let teamFieldFilled = 0;
  for (const [, data] of Object.entries(teams)) {
    for (const f of requiredTeamFields) {
      teamFieldTotal++;
      if (data[f] !== undefined && data[f] !== null) teamFieldFilled++;
    }
  }
  const teamCompleteness = teamFieldTotal > 0 ? teamFieldFilled / teamFieldTotal : 0;
  scores.completeness.earned += teamCompleteness * 10;
  if (teamCompleteness < 0.95) {
    scores.completeness.issues.push('球队字段完整度仅 ' + (teamCompleteness * 100).toFixed(1) + '%');
  }
  
  // 已完赛场次
  const scoredMatches = completed.filter(m => m.score).length;
  scores.completeness.earned += Math.min(10, scoredMatches / 78 * 10);
  if (scoredMatches < 78) {
    scores.completeness.issues.push(`已完赛场次: ${scoredMatches}/78`);
  }
  
  // 赔率覆盖
  const withOdds = [...upcoming, ...knockout].filter(m => m.oddsHome && m.oddsDraw && m.oddsAway).length;
  const totalPending = upcoming.length + knockout.length;
  const oddsCoverage = totalPending > 0 ? withOdds / totalPending : 1;
  scores.completeness.earned += oddsCoverage * 10;
  if (oddsCoverage < 0.8) {
    scores.completeness.issues.push('赔率覆盖率仅 ' + (oddsCoverage * 100).toFixed(1) + '%');
  }
  
  // ---- 一致性 (Consistency) ----
  // 检查赔率隐含概率合理性
  let oddsIssues = 0;
  for (const m of [...upcoming, ...knockout]) {
    if (m.oddsHome && m.oddsDraw && m.oddsAway) {
      const implied = 1/m.oddsHome + 1/m.oddsDraw + 1/m.oddsAway;
      if (implied < 1.01 || implied > 1.25) oddsIssues++;
    }
  }
  const consistencyScore = totalPending > 0 ? Math.max(0, 1 - oddsIssues / totalPending) : 1;
  scores.consistency.earned += consistencyScore * 12.5;
  if (oddsIssues > 0) {
    scores.consistency.issues.push(`${oddsIssues} 场赔率隐含概率异常`);
  }
  
  // 检查Elo范围
  const elos = Object.values(teams).map(t => t.eloRating).filter(Boolean);
  if (elos.length > 0) {
    const minElo = Math.min(...elos);
    const maxElo = Math.max(...elos);
    if (maxElo - minElo < 100) {
      scores.consistency.issues.push('Elo评分范围过窄 (仅' + (maxElo - minElo) + '分)');
      scores.consistency.earned -= 5;
    }
  }
  
  // ---- 时效性 (Timeliness) ----
  const lastCompleted = completed.filter(m => m.score).sort((a, b) => b.date.localeCompare(a.date))[0];
  if (lastCompleted) {
    const daysSince = (Date.now() - new Date(lastCompleted.date).getTime()) / 86400000;
    if (daysSince <= 1) {
      scores.timeliness.earned += 25;
    } else if (daysSince <= 3) {
      scores.timeliness.earned += 20;
    } else if (daysSince <= 7) {
      scores.timeliness.earned += 10;
      scores.timeliness.issues.push(`最后更新: ${daysSince.toFixed(0)} 天前`);
    } else {
      scores.timeliness.issues.push(`数据陈旧: ${daysSince.toFixed(0)} 天未更新`);
    }
  } else {
    scores.timeliness.issues.push('无已完成比赛记录');
  }
  
  // ---- 准确性 (Accuracy) ----
  // 检查已完成比赛分数格式
  let badScores = 0;
  for (const m of completed) {
    if (m.score) {
      const parts = m.score.split('-');
      if (parts.length !== 2 || isNaN(parseInt(parts[0])) || isNaN(parseInt(parts[1]))) {
        badScores++;
      }
    }
  }
  const accuracyScore = completed.length > 0 ? 1 - badScores / completed.length : 1;
  scores.accuracy.earned += accuracyScore * 20;
  if (badScores > 0) {
    scores.accuracy.issues.push(`${badScores} 场比分格式异常`);
  }
  
  // 计算总分
  const totalMax = Object.values(scores).reduce((s, v) => s + v.max, 0);
  const totalEarned = Object.values(scores).reduce((s, v) => s + v.earned, 0);
  const overall = Math.max(0, Math.min(100, (totalEarned / totalMax * 100)));
  
  return {
    overall: Math.round(overall),
    dimensions: scores,
    totalIssues: Object.values(scores).reduce((s, v) => s + v.issues.length, 0),
    teamCount: Object.keys(teams).length,
    matchCount: completed.length,
    lastUpdated: lastCompleted ? lastCompleted.date : null,
  };
}

// ============================================================
// 输出报告
// ============================================================

function printReport(quality) {
  console.log('\n' + '═'.repeat(60));
  console.log('  ⚽ 数据质量评分仪表板');
  console.log('═'.repeat(60));
  
  // 总体评分
  const emoji = quality.overall >= 80 ? '🟢' : quality.overall >= 60 ? '🟡' : '🔴';
  console.log(`\n  总体评分: ${emoji} ${quality.overall}/100`);
  console.log(`  问题数量: ${quality.totalIssues}`);
  console.log(`  球队数: ${quality.teamCount} | 比赛数: ${quality.matchCount}`);
  console.log(`  最后更新: ${quality.lastUpdated || '未知'}\n`);
  
  // 各维度
  const dimLabels = {
    completeness: '📋 完整性',
    consistency: '🔗 一致性',
    timeliness: '⏰ 时效性',
    accuracy: '🎯 准确性',
  };
  
  for (const [key, label] of Object.entries(dimLabels)) {
    const d = quality.dimensions[key];
    const pct = Math.round(d.earned / d.max * 100);
    const bar = '█'.repeat(Math.round(pct / 5)) + '░'.repeat(20 - Math.round(pct / 5));
    console.log(`  ${label}: ${pct}% [${bar}]`);
    
    if (d.issues.length > 0) {
      for (const issue of d.issues) {
        console.log(`    ⚠️ ${issue}`);
      }
    }
  }
  
  // 修复建议
  console.log('\n  【修复建议】');
  if (quality.overall < 80) {
    console.log('    1. 运行 node sync_service.mjs run 同步最新数据');
    console.log('    2. 运行 node db/sync_to_json.mjs 同步球队数据');
    console.log('    3. 检查并修正异常赔率');
    console.log('    4. 补充缺失的球队字段');
  } else {
    console.log('    ✅ 数据质量良好，继续保持');
  }
  console.log('');
}

// ============================================================
// 保存报告
// ============================================================

function saveReport(quality) {
  const reportPath = path.join(ROOT, 'data_local', 'quality_report.json');
  try {
    fs.mkdirSync(path.dirname(reportPath), { recursive: true });
    fs.writeFileSync(reportPath, JSON.stringify(quality, null, 2));
  } catch (e) { /* ignore */ }
}

// ============================================================
// CLI
// ============================================================

const quality = assessDataQuality();
printReport(quality);
saveReport(quality);
