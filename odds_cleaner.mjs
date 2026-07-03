#!/usr/bin/env node

/**
 * ⚽ 赔率数据清洗器
 * 
 * 功能:
 * 1. 检查赔率一致性 (隐含概率总和应在 1.05-1.15 之间)
 * 2. 检测赔率异常 (负数、零、极端值)
 * 3. 检测赔率反转 (同一场比赛主客胜赔率颠倒)
 * 4. 输出清洗报告
 * 
 * 用法: node odds_cleaner.mjs
 */

import * as fs from 'fs';
import * as path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const predLogPath = path.join(__dirname, 'prediction_log.jsonl');
const predictions = [];
const lines = fs.readFileSync(predLogPath, 'utf8').trim().split('\n');
for (const line of lines) {
  try { predictions.push(JSON.parse(line)); } catch (e) {}
}

console.log('╔═══════════════════════════════════════════════════════════╗');
console.log('║  🔧 赔率数据清洗器                                        ║');
console.log('╚═══════════════════════════════════════════════════════════╝');
console.log('');

// ============================================================
// 1. 按比赛分组，检查赔率一致性
// ============================================================

const matchOdds = {};
for (const pred of predictions) {
  if (!pred.home || !pred.away || !pred.hasOdds || !pred.odds) continue;
  const key = `${pred.home} vs ${pred.away}`;
  if (!matchOdds[key]) matchOdds[key] = [];
  matchOdds[key].push({
    odds: pred.odds,
    timestamp: pred.timestamp,
    weights: pred.weights,
    fusionProb: pred.fusionProb,
    isKnockout: pred.isKnockout,
  });
}

let totalIssues = 0;
const issues = [];

for (const [match, records] of Object.entries(matchOdds)) {
  if (records.length <= 1) continue;
  
  // 检查赔率是否一致
  const firstOdds = records[0].odds;
  for (let i = 1; i < records.length; i++) {
    const curr = records[i].odds;
    
    // 检查是否反转
    if ((curr.home > 2 && firstOdds.home < 2) || (curr.away > 2 && firstOdds.away < 2)) {
      issues.push({
        match,
        type: 'REVERSAL',
        severity: 'HIGH',
        detail: `赔率反转: ${JSON.stringify(firstOdds)} → ${JSON.stringify(curr)}`,
      });
      totalIssues++;
    }
    
    // 检查隐含概率差异
    const imp1 = 1/firstOdds.home + 1/firstOdds.draw + 1/firstOdds.away;
    const imp2 = 1/curr.home + 1/curr.draw + 1/curr.away;
    if (Math.abs(imp1 - imp2) > 0.1) {
      issues.push({
        match,
        type: 'DRIFT',
        severity: 'MEDIUM',
        detail: `赔率漂移: 隐含概率 ${imp1.toFixed(3)} → ${imp2.toFixed(3)}`,
      });
      totalIssues++;
    }
  }
}

// ============================================================
// 2. 检查每场比赛赔率的合理性
// ============================================================

let validOdds = 0, invalidOdds = 0;

for (const pred of predictions) {
  if (!pred.hasOdds || !pred.odds) continue;
  
  const { home, draw, away } = pred.odds;
  let isValid = true;
  let reason = '';
  
  // 检查负数或零
  if (home <= 0 || draw <= 0 || away <= 0) {
    isValid = false;
    reason = '负数或零赔率';
  }
  // 检查隐含概率范围
  else {
    const implied = 1/home + 1/draw + 1/away;
    if (implied < 1.0 || implied > 1.2) {
      isValid = false;
      reason = `隐含概率异常: ${implied.toFixed(3)}`;
    }
  }
  
  if (isValid) validOdds++;
  else {
    invalidOdds++;
    issues.push({
      match: pred.match,
      type: 'INVALID',
      severity: 'HIGH',
      detail: `${reason} (${JSON.stringify(pred.odds)})`,
    });
  }
}

// ============================================================
// 3. 输出报告
// ============================================================

console.log(`📊 总预测记录: ${predictions.length}`);
console.log(`📊 有赔率的预测: ${validOdds + invalidOdds}`);
console.log(`📊 有效赔率: ${validOdds}`);
console.log(`📊 无效赔率: ${invalidOdds}`);
console.log(`📊 发现 ${totalIssues + issues.filter(i=>i.severity==='HIGH').length} 个问题`);
console.log('');

if (issues.length > 0) {
  console.log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
  console.log('📋 问题详情:');
  console.log('');
  
  const highIssues = issues.filter(i => i.severity === 'HIGH');
  const medIssues = issues.filter(i => i.severity === 'MEDIUM');
  
  if (highIssues.length > 0) {
    console.log(`⛔ HIGH 问题 (${highIssues.length}):`);
    for (const issue of highIssues.slice(0, 10)) {
      console.log(`   ${issue.type}: ${issue.match} — ${issue.detail}`);
    }
    console.log('');
  }
  
  if (medIssues.length > 0) {
    console.log(`⚠️ MEDIUM 问题 (${medIssues.length}):`);
    for (const issue of medIssues.slice(0, 10)) {
      console.log(`   ${issue.type}: ${issue.match} — ${issue.detail}`);
    }
    console.log('');
  }
}

// ============================================================
// 4. 建议
// ============================================================

console.log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
console.log('💡 建议:');
console.log('');

if (invalidOdds > 0) {
  console.log(`1. 修复 ${invalidOdds} 个无效赔率: 在预测前自动过滤`);
}
if (totalIssues > 0) {
  console.log(`2. 统一赔率数据源: 确保同一场比赛使用同一时间点的赔率`);
}
console.log(`3. 建议: 预测前运行 odds_validator.mjs 自动检查`);
console.log('');

// ============================================================
// 5. 生成赔率质量报告
// ============================================================

const qualityReport = {
  totalPredictions: predictions.length,
  withOdds: validOdds + invalidOdds,
  validOdds,
  invalidOdds,
  issues: issues.length,
  highSeverity: issues.filter(i => i.severity === 'HIGH').length,
  mediumSeverity: issues.filter(i => i.severity === 'MEDIUM').length,
};

fs.writeFileSync(
  path.join(__dirname, 'data_local', 'odds_quality_report.json'),
  JSON.stringify(qualityReport, null, 2),
  'utf8'
);

console.log('📄 报告已保存到: data_local/odds_quality_report.json');
