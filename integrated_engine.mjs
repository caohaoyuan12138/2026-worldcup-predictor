#!/usr/bin/env node

/**
 * 预测引擎 v3.0 — 集成优化版
 * 
 * 整合所有P0-P2优化：
 * 1. 实时Elo更新 + 战力反哺
 * 2. 赔率数据清洗
 * 3. 动态模型融合权重
 * 4. 淘汰赛专项引擎
 * 5. 冷门检测与预警
 * 6. 置信度校准
 * 7. 赛后评估回测
 * 
 * 用法:
 *   node integrated_engine.mjs predict 西班牙 奥地利 --odds 1.19 5.15 10.50 --handicap 0 -1
 *   node integrated_engine.mjs predict 葡萄牙 克罗地亚 --odds 1.57 3.32 5.22 --handicap 0 -1
 *   node integrated_engine.mjs predict 瑞士 阿尔及利亚 --odds 1.74 3.16 4.20 --handicap 0 -1
 *   node integrated_engine.mjs update     - 更新所有球队Elo和战力
 *   node integrated_engine.mjs backtest   - 回测
 *   node integrated_engine.mjs all        - 预测所有剩余淘汰赛
 */

import * as fs from 'fs';
import * as path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.join(__dirname, '..');

// 加载数据库
let db, userData;
try {
  db = await import(new URL('database.mjs', import.meta.url).href);
  try {
    userData = JSON.parse(fs.readFileSync(path.join(ROOT, 'user_team_data.json'), 'utf8'));
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

// 加载引擎
import { 
  fusionPredict, calcLambda, monteCarlo, monteCarlo as mc,
  batchUpdateElo, rankToElo, eloExpected, updateElo,
  getDynamicWeights 
} from './model/engine.mjs';

// 加载Elo更新器
import { loadAndUpdateTeams, saveUpdatedTeams, fullUpdate as runFullUpdate } from './model/elo_updater.mjs';

// 加载赔率验证器
import { assessOddsQuality, oddsToFairProb, checkOddsDirection, checkMatchOdds } from './model/odds_validator.mjs';

// 加载淘汰赛引擎
import { predictKnockout as kp, detectUpsetRisk, calibrateConfidence } from './model/knockout_engine.mjs';

// ============================================================
// 工具函数
// ============================================================

function parseArgs(args) {
  const result = { cmd: args[0], home: args[1], away: args[2], odds: null, handicap: null, isKnockout: true };
  for (let i = 3; i < args.length; i++) {
    if (args[i] === '--odds' && i + 3 < args.length) {
      result.odds = { 
        home: parseFloat(args[i+1]), 
        draw: parseFloat(args[i+2]), 
        away: parseFloat(args[i+3]) 
      };
      i += 3;
    }
    if (args[i] === '-h' || args[i] === '--handicap') {
      result.handicap = parseFloat(args[i+1]) || 0;
      i++;
    }
  }
  return result;
}

// ============================================================
// 主预测函数（集成版）
// ============================================================

function predictMatch(home, away, options = {}) {
  const { odds, handicap, isKnockout = true } = options;
  const teams = db.TEAM_STRENGTHS;
  const recentMatches = db.RECENT_MATCHES || {};
  const headToHead = db.HEAD_TO_HEAD || {};
  
  // 赔率验证
  let oddsValidation = null;
  if (odds) {
    oddsValidation = checkMatchOdds(teams[home], teams[away], odds);
    if (!oddsValidation.usedForPrediction) {
      console.log(`  ⚠️ 赔率数据质量不佳: ${oddsValidation.warning}`);
    }
  }
  
  // 使用淘汰赛引擎
  const stage = options.stage || 'round_of_16';
  const result = kp(home, away, teams, recentMatches, headToHead, {
    oddsHome: odds?.home,
    oddsDraw: odds?.draw,
    oddsAway: odds?.away,
    handicap: handicap || 0,
    isKnockout: true,
    stage,
    teamUrgency: options.teamUrgency || {},
  });
  
  if (result.error) {
    console.error(`  ❌ ${result.error}`);
    return null;
  }
  
  return { ...result, oddsValidation };
}

// ============================================================
// 输出格式化
// ============================================================

function formatPrediction(result) {
  if (!result) return;
  
  console.log('\n' + '═'.repeat(65));
  console.log(`  ⚽ ${result.home} vs ${result.away}  [${result.stage || '淘汰赛'}]`);
  console.log('═'.repeat(65));
  
  // 融合结果
  console.log(`\n  【🎯 融合预测 — 90分钟】`);
  console.log(`    主胜: ${result.fusion.winPct}%  |  平: ${result.fusion.drawPct}%  |  客胜: ${result.fusion.awayPct}%`);
  console.log(`    预期进球: ${result.home} ${result.fusion.lambda.home.toFixed(2)} : ${result.fusion.lambda.away.toFixed(2)} ${result.away}`);
  console.log(`    场均总进球: ${result.fusion.avgGoals}`);
  
  // TOP5 比分
  console.log(`\n  【📊 TOP5 比分】`);
  for (const s of result.fusion.top5) {
    const bar = '█'.repeat(Math.round(s.pct / 2));
    console.log(`    ${s.score.padEnd(6)} ${s.pct.toString().padStart(5)}%  ${bar}`);
  }
  
  // 各模型
  console.log(`\n  【🤖 各模型分解】`);
  console.log(`    Elo:    主${(result.models.elo.winPct || result.models.elo.homeWinPct).toFixed(1).padStart(5)}%  平${(result.models.elo.drawPct || 28).toFixed(1).padStart(4)}%  客${(result.models.elo.awayWinPct || (100-result.models.elo.winPct-result.models.elo.drawPct)).toFixed(1).padStart(4)}%`);
  console.log(`    泊松:   主${(result.models.poisson.winPct||0).toFixed(1).padStart(5)}%  平${(result.models.poisson.drawPct||0).toFixed(1).padStart(4)}%  客${(result.models.poisson.awayPct||result.models.poisson.awayWinPct||0).toFixed(1).padStart(4)}%`);
  if (result.models.market) {
    console.log(`    市场:   主${(result.models.market.winPct||0).toFixed(1).padStart(5)}%  平${(result.models.market.drawPct||0).toFixed(1).padStart(4)}%  客${(result.models.market.awayPct||result.models.market.awayWinPct||0).toFixed(1).padStart(4)}%`);
  }
  
  // 权重
  console.log(`\n  【⚖️ 融合权重】`);
  for (const [k, v] of Object.entries(result.weights)) {
    console.log(`    ${k.padEnd(10)}: ${(v * 100).toFixed(0).padStart(4)}%`);
  }
  
  // 贝叶斯融合
  if (result.bayesian) {
    console.log(`\n  【🔗 贝叶斯融合】`);
    console.log(`    融合后: 主${result.bayesian.home_win}% 平${result.bayesian.draw}% 客${result.bayesian.away_win}%`);
    console.log(`    权重: 模型${(result.bayesian.weight_model * 100).toFixed(0)}% / 市场${(result.bayesian.weight_market * 100).toFixed(0)}%`);
    console.log(`    置信度: ${(result.bayesian.confidence * 100).toFixed(0)}%`);
  }
  
  // 冷门预警
  if (result.upsetRisk) {
    console.log(`\n  【⚠️ 冷门预警】`);
    if (result.upsetRisk.isUpset) {
      const emoji = result.upsetRisk.risk === 'critical' ? '🔴🔴🔴' : result.upsetRisk.risk === 'high' ? '🔴🔴' : '🟡';
      console.log(`    ${emoji} 风险等级: ${result.upsetRisk.risk.toUpperCase()} (得分: ${result.upsetRisk.riskScore})`);
      for (const r of result.upsetRisk.reasons) {
        console.log(`    • ${r}`);
      }
    } else {
      console.log(`    ✅ 无明显冷门信号 (风险得分: ${result.upsetRisk.riskScore})`);
    }
  }
  
  // 置信度
  if (result.confidence) {
    console.log(`\n  【📈 置信度】`);
    const levelEmoji = result.confidence.level === 'high' ? '🟢' : result.confidence.level === 'medium' ? '🟡' : '🔴';
    console.log(`    ${levelEmoji} ${result.confidence.level.toUpperCase()} (${result.confidence.score}/100)`);
    for (const f of result.confidence.factors) {
      console.log(`    • ${f}`);
    }
  }
  
  // 赔率验证
  if (result.oddsValidation) {
    console.log(`\n  【📋 赔率验证】`);
    console.log(`    ${result.oddsValidation.warning}`);
    if (result.oddsValidation.fairProb) {
      const fp = result.oddsValidation.fairProb;
      console.log(`    公平概率: 主${fp.homeWinPct}% | 平${fp.drawPct}% | 客${fp.awayWinPct}% (抽水${fp.overround}%)`);
    }
  }
  
  console.log('');
}

// ============================================================
// CLI 入口
// ============================================================

const args = process.argv.slice(2);
const cmd = args[0];

switch (cmd) {
  case 'predict': {
    const home = args[1];
    const away = args[2];
    let odds = null;
    let handicap = 0;
    
    for (let i = 3; i < args.length; i++) {
      if (args[i] === '--odds' && i + 3 < args.length) {
        odds = { 
          home: parseFloat(args[i+1]), 
          draw: parseFloat(args[i+2]), 
          away: parseFloat(args[i+3]) 
        };
        i += 3;
      }
      if ((args[i] === '-h' || args[i] === '--handicap') && i + 1 < args.length) {
        handicap = parseFloat(args[i+1]) || 0;
        i++;
      }
    }
    
    if (!home || !away) {
      console.log('用法: node integrated_engine.mjs predict 主队 客队 --odds H D A -h 让球');
      break;
    }
    
    const result = predictMatch(home, away, { odds, handicap, stage: 'round_of_16' });
    formatPrediction(result);
    break;
  }
  
  case 'all': {
    const knockout = db.KNOCKOUT_MATCHES || [];
    console.log('\n' + '═'.repeat(65));
    console.log('  所有剩余淘汰赛预测');
    console.log('═'.repeat(65));
    
    for (const m of knockout) {
      if (m.score) continue;
      const result = predictMatch(m.home, m.away, { stage: m.round || 'round_of_16' });
      if (!result) continue;
      
      const top = result.fusion.top5[0];
      const dir = result.fusion.winPct >= result.fusion.awayPct && result.fusion.winPct >= result.fusion.drawPct ? '主胜' :
                  result.fusion.drawPct >= result.fusion.winPct && result.fusion.drawPct >= result.fusion.awayPct ? '平' : '客胜';
      const upset = result.upsetRisk?.isUpset ? ` ⚠️${result.upsetRisk.risk}` : '';
      const conf = result.confidence?.level || '?';
      
      console.log(`  ${m.label.padEnd(12)} ${m.home.padEnd(12)} vs ${m.away.padEnd(12)} → ${top.score}(${top.pct}%) [${dir}${upset}] 置信:${conf}`);
    }
    break;
  }
  
  case 'update': {
    console.log('\n🔄 更新球队数据...\n');
    runFullUpdate();
    break;
  }
  
  case 'backtest': {
    console.log('\n📊 回测淘汰赛预测...\n');
    const completed = db.COMPLETED_MATCHES.filter(m => m.score && (m.round && m.round.includes('强')));
    let correct = 0, top3 = 0, total = 0;
    
    for (const m of completed) {
      const [hG, aG] = m.score.split('-').map(Number);
      if (isNaN(hG)) continue;
      
      const result = predictMatch(m.home, m.away, { stage: m.round });
      if (!result) continue;
      
      total++;
      const predDir = result.fusion.winPct >= result.fusion.awayPct && result.fusion.winPct >= result.fusion.drawPct ? 'home' :
                      result.fusion.drawPct >= result.fusion.winPct ? 'draw' : 'away';
      const actualDir = hG > aG ? 'home' : hG === aG ? 'draw' : 'away';
      if (predDir === actualDir) correct++;
      
      const top5 = result.fusion.top5.map(s => s.score);
      const actualScore = `${hG}-${aG}`;
      if (top5.slice(0, 3).includes(actualScore)) top3++;
    }
    
    console.log(`  回测场次: ${total}`);
    console.log(`  方向准确率: ${total > 0 ? (correct/total*100).toFixed(1) : 0}% (${correct}/${total})`);
    console.log(`  Top3比分命中: ${total > 0 ? (top3/total*100).toFixed(1) : 0}% (${top3}/${total})`);
    console.log('');
    break;
  }
  
  default:
    console.log(`
⚽ 足球预测引擎 v3.0 — 集成优化版

用法:
  node integrated_engine.mjs predict 主队 客队 --odds H D A -h 让球    预测单场
  node integrated_engine.mjs all                                        预测所有剩余比赛
  node integrated_engine.mjs update                                     更新球队Elo和战力
  node integrated_engine.mjs backtest                                   回测历史淘汰赛

示例:
  node integrated_engine.mjs predict 西班牙 奥地利 --odds 1.19 5.15 10.50 -h -1
  node integrated_engine.mjs predict 葡萄牙 克罗地亚 --odds 1.57 3.32 5.22 -h -1
  node integrated_engine.mjs predict 瑞士 阿尔及利亚 --odds 1.74 3.16 4.20 -h -1
`);
}
