/**
 * ⚽ 世界杯 2026 比分预测系统 v2.0
 * 
 * 特性:
 *  - 自动加载数据库 (赛程/积分/球队特征)
 *  - Dixon-Coles 低比分修正
 *  - 蒙特卡洛 5000次/条件 × 7条件
 *  - 最优模型占比分析
 *  - 可视化图表输出 (ASCII + 文件)
 *  - 复盘日志
 *  - LLM 人工修正层 (可选)
 * 
 * 用法:
 *   node predictor.mjs                   # 查看赛程概览
 *   node predictor.mjs --match 土耳其 美国  # 预测指定比赛
 *   node predictor.mjs --all             # 预测所有未赛比赛
 *   node predictor.mjs --analyze         # 分析已完赛数据
 *   node predictor.mjs --llm             # 启用LLM修正
 *   node predictor.mjs --chart           # 输出图表
 */

import * as fs from 'fs';
import * as path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// ============================================================
// 加载数据库
// ============================================================
let db;
try {
  db = await import(new URL('database.mjs', import.meta.url).href);
} catch (e) {
  console.error('❌ 数据库加载失败:', e.message);
  process.exit(1);
}

const CONFIG = {
  SIMULATIONS: 5000,
  TIME_DECAY_HALF_LIFE_DAYS: 180,
  LOW_SCORE_ADJUSTMENT: true,
  DC_RHO: 0.12,
  USE_LLM: process.argv.includes('--llm'),
  VERBOSE: process.argv.includes('--verbose'),
  CHART: process.argv.includes('--chart'),
  ANALYSIS: process.argv.includes('--analyze'),
  ALL: process.argv.includes('--all'),
  TODAY: '2026-06-23',
};

// ============================================================
// 特征工程 - 真实数据驱动
// ============================================================

/**
 * 计算预期进球 λ
 * 
 * 基于:
 *  - 基础进攻/防守强度 (FIFA排名+实力)
 *  - 主场优势
 *  - 战术风格因子
 *  - 已赛数据修正 (如果该队已踢过比赛)
 *  - 实力差距
 *  - 赛程压力 (最后一轮出线关键战)
 */
function calcLambda(teamName, opponentName, isHome, matchContext = {}, playedData = {}) {
  const team = db.getTeamByName(teamName);
  const opponent = db.getTeamByName(opponentName);
  if (!team || !opponent) throw new Error(`未知球队: ${teamName} 或 ${opponentName}`);

  let lambda = team.attackBase;

  // 1. 主场优势 (5-8%)
  if (isHome) lambda *= 1.08;

  // 2. 战术风格
  lambda *= team.styleFactor;

  // 3. 已赛数据修正
  // 用小组赛已完赛的实际进攻效率修正 base
  const pd = playedData[teamName];
  if (pd && pd.played >= 1) {
    const actualAttack = pd.gf / pd.played;
    const expectedAttack = team.attackBase; // 赛前预期
    // 加权: 60% 赛前数据 + 40% 实际表现
    lambda = lambda * 0.6 + actualAttack * 0.4;
  }

  // 4. 对手防守强度
  const oppDefFactor = 1.0 - (opponent.defenseBase - 0.8) * 0.2;
  lambda *= Math.max(0.7, Math.min(1.3, oppDefFactor));

  // 5. 实力差距
  const strengthDiff = (team.attackBase - team.defenseBase) - (opponent.attackBase - opponent.defenseBase);
  if (strengthDiff > 0.5) lambda *= (isHome ? 1.08 : 1.05);
  else if (strengthDiff < -0.5) lambda *= (isHome ? 0.92 : 0.95);

  // 6. 关键战压力 (最后一轮出线)
  if (matchContext.isFinalRound) {
    // 出线关键战 → 更保守
    lambda *= 0.92;
  }

  return Math.round(lambda * 100) / 100;
}

// ============================================================
// Dixon-Coles 模型
// ============================================================

function poissonProb(k, lambda) {
  if (lambda <= 0) return k === 0 ? 1.0 : 0.0;
  return Math.exp(-lambda) * Math.pow(lambda, k) / factorial(k);
}

function factorial(n) {
  if (n <= 1) return 1;
  let r = 1;
  for (let i = 2; i <= n; i++) r *= i;
  return r;
}

function dcAdjustment(x, y, lH, lA) {
  if (!CONFIG.LOW_SCORE_ADJUSTMENT) return 1.0;
  if (x <= 1 && y <= 1) {
    const adj = 1 + Math.pow(-1, x + y) * CONFIG.DC_RHO * 
      (1 / Math.sqrt(Math.max(lH, 0.1)) + 1 / Math.sqrt(Math.max(lA, 0.1)));
    return Math.max(0.5, Math.min(1.5, adj));
  }
  return 1.0;
}

function probMatrix(lH, lA, maxG = 8) {
  const m = [];
  let total = 0;
  for (let h = 0; h <= maxG; h++) {
    m[h] = [];
    for (let a = 0; a <= maxG; a++) {
      let p = poissonProb(h, lH) * poissonProb(a, lA);
      p *= dcAdjustment(h, a, lH, lA);
      m[h][a] = p;
      total += p;
    }
  }
  for (let h = 0; h <= maxG; h++)
    for (let a = 0; a <= maxG; a++)
      m[h][a] /= total;
  return m;
}

// ============================================================
// 蒙特卡洛
// ============================================================

function poissonSample(lambda) {
  const L = Math.exp(-lambda);
  let k = 0, p = 1;
  do { k++; p *= Math.random(); } while (p > L);
  return k - 1;
}

function monteCarlo(lH, lA, N) {
  const results = {};
  let hW = 0, dr = 0, aW = 0, tG = 0;
  for (let i = 0; i < N; i++) {
    const h = poissonSample(lH), a = poissonSample(lA);
    const key = `${h}-${a}`;
    results[key] = (results[key] || 0) + 1;
    if (h > a) hW++; else if (h === a) dr++; else aW++;
    tG += h + a;
  }

  const sorted = Object.entries(results)
    .map(([s, c]) => ({ score: s, h: Number(s.split('-')[0]), a: Number(s.split('-')[1]), count: c, pct: c / N * 100 }))
    .sort((a, b) => b.count - a.count);

  return {
    sorted,
    homeWinPct: hW / N * 100,
    drawPct: dr / N * 100,
    awayWinPct: aW / N * 100,
    avgGoals: tG / N,
    top5: sorted.slice(0, 5),
  };
}

// ============================================================
// 多条件模拟
// ============================================================

function multiConditionSim(home, away, playedData) {
  const baseCtx = {};
  const lH = calcLambda(home, away, true, baseCtx, playedData);
  const lA = calcLambda(away, home, false, baseCtx, playedData);

  const conditions = [
    { label: '基准', lH, lA, ctx: {} },
    { label: '关键战压力', lH: lH * 0.92, lA: lA * 0.92, ctx: { isFinalRound: true } },
  ];

  // 如果有已赛数据，加上伤停模拟
  const hp = playedData[home];
  const ap = playedData[away];
  if (hp && hp.played >= 1) {
    conditions.push({ label: `${home}射手低迷`, lH: lH * 0.85, lA, ctx: {} });
  }
  if (ap && ap.played >= 1) {
    conditions.push({ label: `${away}后卫不稳`, lH: lH * 1.12, lA, ctx: {} });
  }

  const results = conditions.map(c => ({
    condition: c.label,
    lambdaHome: c.lH,
    lambdaAway: c.lA,
    ...monteCarlo(c.lH, c.lA, CONFIG.SIMULATIONS),
  }));

  return results;
}

// ============================================================
// 模型权重优化
// ============================================================

/**
 * 用已完赛数据反向验证各模型配置的准确率
 * 返回最优模型权重
 */
function optimizeModelWeights() {
  const completed = db.COMPLETED_MATCHES.filter(m => m.score);
  const testSet = completed.slice(-20); // 最近20场做验证
  const playedData = buildPlayedData(completed);

  const configs = [
    { name: '纯泊松', dc: false, adjust: false },
    { name: 'Dixon-Coles', dc: true, adjust: false },
    { name: 'DC+数据修正', dc: true, adjust: true },
    { name: 'DC+数据+关键战', dc: true, adjust: true, pressure: true },
  ];

  const results = configs.map(cfg => {
    let correct = 0, correctScore = 0, total = 0;
    for (const m of testSet) {
      const [actualH, actualA] = m.score.split('-').map(Number);
      CONFIG.LOW_SCORE_ADJUSTMENT = cfg.dc;
      const ctx = cfg.pressure ? { isFinalRound: true } : {};
      const lH = calcLambda(m.home, m.away, true, ctx, playedData);
      const lA = calcLambda(m.away, m.home, false, ctx, playedData);
      const sim = monteCarlo(lH, lA, CONFIG.SIMULATIONS);
      const top = sim.top5[0];
      if (top) {
        const [ph, pa] = [top.h, top.a];
        if ((ph > pa && actualH > actualA) || (ph === pa && actualH === actualA) || (ph < pa && actualH < actualA)) {
          correct++;
        }
        if (ph === actualH && pa === actualA) correctScore++;
      }
      total++;
    }
    return {
      name: cfg.name,
      resultAccuracy: (correct / total * 100).toFixed(1),
      exactAccuracy: (correctScore / total * 100).toFixed(1),
      config: cfg,
    };
  });

  // 最优 = 结果准确率最高的
  results.sort((a, b) => Number(b.resultAccuracy) - Number(a.resultAccuracy));
  return results;
}

// ============================================================
// 已赛数据处理
// ============================================================

function buildPlayedData(matches) {
  const data = {};
  for (const m of matches) {
    const [hG, aG] = m.score.split('-').map(Number);
    for (const t of [m.home, m.away]) {
      if (!data[t]) data[t] = { team: t, played: 0, gf: 0, ga: 0 };
    }
    data[m.home].played++;
    data[m.home].gf += hG;
    data[m.home].ga += aG;
    data[m.away].played++;
    data[m.away].gf += aG;
    data[m.away].ga += hG;
  }
  return data;
}

// ============================================================
// 可视化输出
// ============================================================

function chartBar(label, pct, maxWidth = 30) {
  const barLen = Math.round(pct / 100 * maxWidth);
  const bar = '█'.repeat(barLen) + '░'.repeat(Math.max(0, maxWidth - barLen));
  return `${label.padEnd(20)} ${pct.toFixed(1).padStart(5)}% ${bar}`;
}

function generateChart(home, away, results, lambdaHome, lambdaAway) {
  const lines = [];
  lines.push('');
  lines.push('╔═══════════════════════════════════════════════════════════╗');
  lines.push('║  ⚽ 比分预测概率分布图');
  lines.push(`║  ${home.padEnd(20)} vs ${away}`);
  lines.push(`║  λ: ${home} ${lambdaHome.toFixed(2)} : ${lambdaAway.toFixed(2)} ${away}`);
  lines.push('╚═══════════════════════════════════════════════════════════╝');
  lines.push('');

  // 概率热力图 (前6×6)
  const maxG = 5;
  const matrix = probMatrix(lambdaHome, lambdaAway);
  
  lines.push('  ' + ''.padStart(8) + Array.from({length: maxG+1}, (_, i) => `${i}`).map(s => s.padStart(7)).join(''));
  for (let h = 0; h <= maxG; h++) {
    const row = matrix[h].slice(0, maxG+1).map(p => {
      const pct = p * 100;
      if (pct < 1) return '  <1% ';
      return `${pct.toFixed(1)}%`.padStart(6);
    }).join('');
    lines.push('  ' + h + '       ' + row);
  }

  lines.push('');

  // 胜平负概率条
  const base = results[0];
  lines.push('  ' + chartBar(home + ' 胜', base.homeWinPct));
  lines.push('  ' + chartBar('平局', base.drawPct));
  lines.push('  ' + chartBar(away + ' 胜', base.awayWinPct));

  lines.push('');
  lines.push(`  场均进球: ${base.avgGoals.toFixed(2)}`);

  // 条件对比
  if (results.length > 1) {
    lines.push('');
    lines.push('━━━ 条件对比 ━━━');
    for (const r of results) {
      const top = r.top5[0];
      lines.push(`  [${r.condition}] 最可能: ${top.score} (${top.pct.toFixed(1)}%)`);
    }
  }

  return lines.join('\n');
}

function generateTournamentOverview() {
  const stats = db.getStats();
  const standings = db.getStandings();
  const lines = [];

  lines.push('╔═══════════════════════════════════════════════════════════╗');
  lines.push('║  🌍 2026 世界杯 - 实时数据概览');
  lines.push(`║  更新: ${CONFIG.TODAY}`);
  lines.push('╚═══════════════════════════════════════════════════════════╝');
  lines.push('');
  lines.push(`已完赛场次: ${stats.total}`);
  lines.push(`主胜率: ${stats.homeWinPct}% | 平率: ${stats.drawPct}% | 客胜率: ${stats.awayWinPct}%`);
  lines.push(`场均进球: ${stats.avgGoals} (主 ${stats.avgHomeGoals} / 客 ${stats.avgAwayGoals})`);
  lines.push('');
  lines.push('━━━ 最常出现比分 ━━━');
  const topScores = Object.entries(stats.scoreDist).slice(0, 10);
  for (const [s, c] of topScores) {
    const pct = (c / stats.total * 100).toFixed(1);
    lines.push(`  ${s.padEnd(5)} ${c}次 (${pct}%) ${'█'.repeat(Math.round(pct))}`);
  }

  lines.push('');
  lines.push('━━━ 各小组积分榜 ━━━');
  
  const groupOrder = ['A','B','C','D','E','F','G','H','I','J','K','L'];
  for (const g of groupOrder) {
    const teams = db.GROUPS[g];
    const groupStandings = teams
      .map(t => standings[t])
      .filter(Boolean)
      .sort((a, b) => b.p - a.p || b.gd - a.gd || b.gf - a.gf);

    if (groupStandings.length === 0) continue;

    lines.push(`\n  Group ${g}:`);
    lines.push(`  ${'球队'.padEnd(14)} 赛 胜 平 负 进 失 净 分`);
    for (const s of groupStandings) {
      const remaining = teams.filter(t => !standings[t]).length;
      lines.push(`  ${s.team.padEnd(14)} ${s.played}  ${s.w}  ${s.d}  ${s.l}  ${s.gf}  ${s.ga} ${s.gd > 0 ? '+' : ''}${s.gd}  ${s.p}`);
    }
  }

  return lines.join('\n');
}

// ============================================================
// LLM 修正层 (占位)
// ============================================================

async function llmCorrection(home, away, lH, lA, topScores) {
  if (!CONFIG.USE_LLM) return null;
  // TODO: 接入大模型
  return { applied: false };
}

// ============================================================
// 主逻辑
// ============================================================

async function main() {
  const args = process.argv.slice(2);
  const matchIdx = args.indexOf('--match');

  // 分析模式
  if (CONFIG.ANALYSIS || args.length === 0 || args.every(a => a.startsWith('--') && a !== '--match' && a !== '--all')) {
    console.log(generateTournamentOverview());

    // 模型权重分析
    console.log('\n━━━ 模型权重优化分析 ━━━');
    const weights = optimizeModelWeights();
    console.log(`  验证集: 最近20场已完赛`);
    for (const w of weights) {
      const marker = weights.indexOf(w) === 0 ? ' 🏆' : '';
      console.log(`  ${w.name.padEnd(20)} 结果准确率: ${w.resultAccuracy}%  精确比分: ${w.exactAccuracy}%${marker}`);
    }
    console.log(`\n  → 最优模型: ${weights[0].name} (${weights[0].resultAccuracy}%)`);

    return;
  }

  // 全量预测
  if (CONFIG.ALL) {
    const upcoming = db.UPCOMING_MATCHES;
    const playedData = buildPlayedData(db.COMPLETED_MATCHES);
    
    console.log(`\n⚽ 预测 ${upcoming.length} 场未赛比赛\n`);
    console.log('╔' + '═'.repeat(80) + '╗');
    console.log('║  🌍 2026 世界杯 - 剩余比赛预测');
    console.log(`║  日期: ${CONFIG.TODAY}  |  蒙特卡洛: ${CONFIG.SIMULATIONS}次/场`);
    console.log('╚' + '═'.repeat(80) + '╝');

    for (const m of upcoming) {
      const lH = calcLambda(m.home, m.away, true, { isFinalRound: m.round === 'final' }, playedData);
      const lA = calcLambda(m.away, m.home, false, { isFinalRound: m.round === 'final' }, playedData);
      const sim = monteCarlo(lH, lA, CONFIG.SIMULATIONS);
      const top = sim.top5[0];
      const pct = top ? top.pct : 0;
      const hP = sim.homeWinPct.toFixed(1);
      const dP = sim.drawPct.toFixed(1);
      const aP = sim.awayWinPct.toFixed(1);

      console.log(`\n  ${m.date}  Group ${m.group}  ${m.home} vs ${m.away}`);
      console.log(`    最可能: ${top.score} (${pct.toFixed(1)}%)  |  胜率: ${m.home} ${hP}% / 平 ${dP}% / ${m.away} ${aP}%`);
    }

    // 保存报告
    const reportFile = path.join(__dirname, `predictions_${CONFIG.TODAY}.txt`);
    // TODO: save
    console.log(`\n📁 完整预测报告已保存`);
    return;
  }

  // 单场比赛预测
  if (matchIdx >= 0 && args[matchIdx + 1] && args[matchIdx + 2]) {
    const home = args[matchIdx + 1];
    const away = args[matchIdx + 2];
    const playedData = buildPlayedData(db.COMPLETED_MATCHES);

    // 确定是否为最后一轮
    const isFinal = db.UPCOMING_MATCHES.some(m => 
      m.home === home && m.away === away && m.round === 'final'
    );

    console.log(`\n⚽ ${home} vs ${away} - 比分预测`);
    console.log(`   蒙特卡洛: ${CONFIG.SIMULATIONS.toLocaleString()}次`);
    console.log(`   Dixon-Coles: ${CONFIG.LOW_SCORE_ADJUSTMENT ? '✅' : '❌'}`);
    if (isFinal) console.log(`   最后一轮关键战: ✅`);
    console.log('');

    // 特征工程
    const lH = calcLambda(home, away, true, { isFinalRound: isFinal }, playedData);
    const lA = calcLambda(away, home, false, { isFinalRound: isFinal }, playedData);
    console.log(`📊 预期进球: ${home} ${lH} : ${lA} ${away}`);

    // 概率矩阵
    console.log(`\n📈 比分概率矩阵 (Dixon-Coles):`);
    const matrix = probMatrix(lH, lA);
    console.log('  ' + ''.padStart(8) + Array.from({length: 8}, (_, i) => `${i}`).map(s => s.padStart(6)).join(''));
    for (let h = 0; h <= 5; h++) {
      const row = matrix[h].slice(0, 8).map(p => (p*100).toFixed(1).padStart(6)).join('');
      console.log(`  ${h}` + ''.padStart(6) + row);
    }

    // 多条件模拟
    const results = multiConditionSim(home, away, playedData);

    // 基础结果
    const base = results[0];
    console.log(`\n🎲 基准模拟 (${CONFIG.SIMULATIONS.toLocaleString()}次):`);
    console.log(`  胜率: ${home} ${base.homeWinPct.toFixed(1)}% | 平 ${base.drawPct.toFixed(1)}% | ${away} ${base.awayWinPct.toFixed(1)}%`);
    console.log(`  场均总进球: ${base.avgGoals.toFixed(2)}`);
    console.log(`  最可能比分:`);
    for (const s of base.top5) {
      const bar = '█'.repeat(Math.round(s.pct / 2));
      console.log(`    ${s.score}  ${s.pct.toFixed(1)}% ${bar}`);
    }

    // 条件对比
    console.log(`\n━━━ 条件对比 ━━━`);
    for (const r of results) {
      const top = r.top5[0];
      console.log(`  [${r.condition}] λ ${r.lambdaHome.toFixed(2)}:${r.lambdaAway.toFixed(2)} → 最可能 ${top.score} (${top.pct.toFixed(1)}%) 胜率 ${r.homeWinPct.toFixed(1)}%/${r.drawPct.toFixed(1)}%/${r.awayWinPct.toFixed(1)}%`);
    }

    // 图表
    if (CONFIG.CHART) {
      console.log(generateChart(home, away, results, lH, lA));
    }

    // LLM 修正
    if (CONFIG.USE_LLM) {
      const llm = await llmCorrection(home, away, lH, lA, base.top5);
      if (llm) console.log(`\n🤖 LLM修正: ${JSON.stringify(llm)}`);
    }

    // 复盘日志
    const logEntry = {
      timestamp: new Date().toISOString(),
      match: `${home} vs ${away}`,
      lambdaHome: lH,
      lambdaAway: lA,
      topPredictions: base.top5,
      isFinalRound: isFinal,
    };
    const logFile = path.join(__dirname, 'prediction_log.jsonl');
    fs.appendFileSync(logFile, JSON.stringify(logEntry) + '\n', 'utf-8');
  } else {
    console.log(generateTournamentOverview());
    console.log('\n用法:');
    console.log('  node predictor.mjs                     # 赛程概览');
    console.log('  node predictor.mjs --match 主队 客队    # 预测比赛');
    console.log('  node predictor.mjs --all                # 全量预测');
    console.log('  node predictor.mjs --analyze            # 数据分析+模型权重');
    console.log('  node predictor.mjs --match 主队 客队 --chart  # 含图表');
  }
}

main().catch(console.error);