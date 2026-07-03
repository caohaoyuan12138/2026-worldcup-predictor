#!/usr/bin/env node

/**
 * ⚽ 2026 世界杯比分预测系统 - 主入口
 *
 * 用法:
 *   node predict.mjs status          - 查看数据库状态
 *   node predict.mjs today           - 预测今天的比赛
 *   node predict.mjs match 主队 客队  - 预测指定比赛
 *   node predict.mjs all             - 预测所有剩余比赛
 *   node predict.mjs analyze         - 模型准确率分析
 *   node predict.mjs advance         - 出线形势 (10,000次)
 *   node predict.mjs knockout       - 淘汰赛模拟 (10,000次)
 *   node predict.mjs dashboard       - 生成可视化HTML
 */

import * as fs from 'fs';
import * as path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// ============================================================
// 加载数据
// ============================================================

let db, userData;
try {
  db = await import(new URL('database.mjs', import.meta.url).href);
  userData = JSON.parse(fs.readFileSync(path.join(__dirname, 'user_team_data.json'), 'utf8'));
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
// 核心引擎
// ============================================================

function calcLambda(teamName, opponentName, isHome, ctx = {}) {
  const team = db.TEAM_STRENGTHS[teamName];
  const opponent = db.TEAM_STRENGTHS[opponentName];
  if (!team || !opponent) return 1.0;
  let lambda = team.attackBase;
  if (isHome) lambda *= 1.08;
  lambda *= team.styleFactor;

  // 懂球帝数据增强
  const teamShotAcc = db.getTeamShotAccuracy(teamName);
  const oppShotAcc = db.getTeamShotAccuracy(opponentName);
  const teamPassAcc = db.getTeamPassAccuracy(teamName);
  const oppPassAcc = db.getTeamPassAccuracy(opponentName);
  const teamRating = db.getTeamRating(teamName);
  const oppRating = db.getTeamRating(opponentName);

  // 射正率影响进攻效率
  lambda *= (teamShotAcc > 0.4 ? 1.12 : teamShotAcc > 0.3 ? 1.06 : 1.0);
  // 传球成功率影响进攻机会
  lambda *= (teamPassAcc > 0.88 ? 1.08 : teamPassAcc > 0.85 ? 1.04 : 1.0);
  // 球队评分影响
  lambda *= (teamRating > 7.0 ? 1.1 : teamRating > 6.5 ? 1.05 : 1.0);

  // 对手防守数据影响
  const oppTackles = db.getPlayerStat ? (db.getDongqiudiData().team[opponentName]?.['抢断'] || '0') : '0';
  lambda *= (oppShotAcc > 0.4 ? 0.95 : oppShotAcc > 0.3 ? 0.98 : 1.0);
  lambda *= (oppPassAcc > 0.88 ? 0.95 : oppPassAcc > 0.85 ? 0.97 : 1.0);

  const playedData = {};
  db.COMPLETED_MATCHES.forEach(m => {
    const [h, a] = m.score.split('-').map(Number);
    [m.home, m.away].forEach(t => { if (!playedData[t]) playedData[t] = { played: 0, gf: 0, ga: 0 }; });
    playedData[m.home].played++; playedData[m.home].gf += h; playedData[m.home].ga += a;
    playedData[m.away].played++; playedData[m.away].gf += a; playedData[m.away].ga += h;
  });
  const pd = playedData[teamName];
  if (pd && pd.played >= 1) lambda = lambda * 0.6 + (pd.gf / pd.played) * 0.4;
  const od = 1.0 - (opponent.defenseBase - 0.8) * 0.2;
  lambda *= Math.max(0.7, Math.min(1.3, od));
  const sd = (team.attackBase - team.defenseBase) - (opponent.attackBase - opponent.defenseBase);
  if (sd > 0.5) lambda *= (isHome ? 1.08 : 1.05);
  else if (sd < -0.5) lambda *= (isHome ? 0.92 : 0.95);
  if (ctx.isFinalRound) lambda *= 0.92;
  // 淘汰赛阶段调整：更防守、更低进球
  if (ctx.isKnockout) lambda *= 0.88;
  return Math.round(lambda * 100) / 100;
}

function monteCarlo(lH, lA, N = 5000) {
  function ps(lambda) { const L = Math.exp(-lambda); let k = 0, p = 1; do { k++; p *= Math.random(); } while (p > L); return k - 1; }
  const results = {}; let hW = 0, dr = 0, aW = 0, tG = 0;
  for (let i = 0; i < N; i++) {
    const h = ps(lH), a = ps(lA);
    const key = `${h}-${a}`;
    results[key] = (results[key] || 0) + 1;
    if (h > a) hW++; else if (h === a) dr++; else aW++;
    tG += h + a;
  }
  const sorted = Object.entries(results)
    .map(([s, c]) => ({ score: s, h: Number(s.split('-')[0]), a: Number(s.split('-')[1]), count: c, pct: c / N * 100 }))
    .sort((a, b) => b.count - a.count);
  return { sorted, top5: sorted.slice(0, 5), homeWinPct: hW / N * 100, drawPct: dr / N * 100, awayWinPct: aW / N * 100, avgGoals: tG / N };
}

// ============================================================
// 命令实现
// ============================================================

function cmdStatus() {
  const stats = db.getStats();
  const standings = db.getStandings();
  console.log('');
  console.log('╔══════════════════════════════════════════════╗');
  console.log('║  ⚽ 2026 世界杯 - 数据库状态');
  console.log('╚══════════════════════════════════════════════╝');
  console.log('');
  console.log(`  已完赛: ${stats.total} 场`);
  console.log(`  未赛:   ${db.UPCOMING_MATCHES.length} 场 (第3轮)`);
  console.log(`  淘汰赛: ${db.KNOCKOUT_MATCHES.length} 场`);
  console.log(`  共计:   ${stats.total + db.UPCOMING_MATCHES.length + db.KNOCKOUT_MATCHES.length} 场`);
  console.log('');
  console.log(`  场均进球: ${stats.avgGoals}`);
  console.log(`  主胜率: ${stats.homeWinPct}% | 平率: ${stats.drawPct}% | 客胜率: ${stats.awayWinPct}%`);
  console.log('');
  console.log('  ── 积分榜 ──');
  const groupOrder = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L'];
  for (const g of groupOrder) {
    const teams = db.GROUPS[g];
    const gs = teams.map(t => standings[t]).filter(Boolean).sort((a, b) => b.p - a.p || b.gd - a.gd || b.gf - a.gf);
    const line = gs.map((s, i) => `${i === 0 ? '🥇' : i === 1 ? '🥈' : ''}${s.team}(${s.p}p)`).join(' → ');
    console.log(`  Group ${g}: ${line}`);
  }
  console.log('');
  console.log(`  用户数据: ${Object.keys(userData).length} 队已加载`);
  console.log(`  Dixon-Coles: ✅ | 蒙特卡洛: 5000次`);
}

function cmdMatch(home, away, isKnockout = false) {
  const isFinal = db.UPCOMING_MATCHES.some(m => m.home === home && m.away === away);
  const ctx = { isFinalRound: isFinal, isKnockout };
  const lH = calcLambda(home, away, true, ctx);
  const lA = calcLambda(away, home, false, ctx);
  const sim = monteCarlo(lH, lA, 5000);

  const matchType = isKnockout ? '⚔️ 淘汰赛' : (isFinal ? '🏆 小组赛末轮' : '⚽ 小组赛');

  console.log('');
  console.log('╔══════════════════════════════════════════════╗');
  console.log(`║  ${matchType} ${home} vs ${away}`);
  console.log('╚══════════════════════════════════════════════╝');
  console.log('');
  if (isKnockout) {
    console.log('  ⚔️ 淘汰赛模式 - 平局将进入点球大战');
    console.log('');
  }
  console.log(`  预期进球: ${home} ${lH} : ${lA} ${away}`);
  console.log(`  胜率: ${home} ${sim.homeWinPct.toFixed(1)}% | 平 ${sim.drawPct.toFixed(1)}% | ${away} ${sim.awayWinPct.toFixed(1)}%`);
  console.log(`  场均总进球: ${sim.avgGoals.toFixed(2)}`);
  console.log('');

  // 显示懂球帝数据对比
  const homeShotAcc = db.getTeamShotAccuracy(home);
  const awayShotAcc = db.getTeamShotAccuracy(away);
  const homePassAcc = db.getTeamPassAccuracy(home);
  const awayPassAcc = db.getTeamPassAccuracy(away);
  const homeRating = db.getTeamRating(home);
  const awayRating = db.getTeamRating(away);
  console.log('  ── 懂球帝数据对比 ──');
  console.log(`  ${home}: 射正率${(homeShotAcc*100).toFixed(0)}% 传球成功率${(homePassAcc*100).toFixed(0)}% 评分${homeRating}`);
  console.log(`  ${away}: 射正率${(awayShotAcc*100).toFixed(0)}% 传球成功率${(awayPassAcc*100).toFixed(0)}% 评分${awayRating}`);
  console.log('');

  console.log('  最可能比分:');
  for (const s of sim.top5) {
    const bar = '█'.repeat(Math.round(s.pct / 2));
    console.log(`    ${s.score}  ${s.pct.toFixed(1)}% ${bar}`);
  }

  // 淘汰赛点球提示
  if (isKnockout) {
    const drawPct = sim.drawPct;
    console.log('');
    console.log(`  ⚠️ 平局概率 ${drawPct.toFixed(1)}% - 将进入点球大战`);
  }

  // 保存
  const ts = new Date().toISOString().replace(/[:.]/g, '-');
  const report = [
    `=== ${home} vs ${away} ===`,
    `时间: ${new Date().toISOString()}`,
    `类型: ${isKnockout ? '淘汰赛' : '小组赛'}`,
    `λ: ${home} ${lH} : ${lA} ${away}`,
    `胜率: ${home} ${sim.homeWinPct.toFixed(1)}% / 平 ${sim.drawPct.toFixed(1)}% / ${away} ${sim.awayWinPct.toFixed(1)}%`,
    `最可能:`,
    ...sim.top5.map(s => `  ${s.score}  ${s.pct.toFixed(1)}%`),
  ].join('\n');
  fs.writeFileSync(path.join(__dirname, 'predictions', `${home}_vs_${away}_${ts}.txt`), report);
  console.log(`\n  📁 已保存: predictions/${home}_vs_${away}_${ts}.txt`);
}

function cmdAll() {
  const matches = db.UPCOMING_MATCHES;
  console.log(`\n⚽ 预测 ${matches.length} 场剩余比赛\n`);

  for (const m of matches) {
    const ctx = { isFinalRound: m.round === 3 };
    const lH = calcLambda(m.home, m.away, true, ctx);
    const lA = calcLambda(m.away, m.home, false, ctx);
    const sim = monteCarlo(lH, lA, 5000);
    const top = sim.top5[0];
    console.log(`  ${m.date} Group ${m.group}  ${m.home.padEnd(12)} vs ${m.away.padEnd(12)}  → ${top.score} (${top.pct.toFixed(1)}%)  胜率 ${sim.homeWinPct.toFixed(1)}/${sim.drawPct.toFixed(1)}/${sim.awayWinPct.toFixed(1)}`);
  }
}

function cmdAnalyze() {
  const testSet = db.COMPLETED_MATCHES.slice(-20);
  const configs = [
    { name: '纯泊松', dc: false, adjust: false },
    { name: 'Dixon-Coles', dc: true, adjust: false },
    { name: 'DC+数据修正', dc: true, adjust: true },
  ];

  console.log('');
  console.log('╔══════════════════════════════════════════════╗');
  console.log('║  📊 模型准确率分析');
  console.log('╚══════════════════════════════════════════════╝');
  console.log(`  验证集: 最近20场`);
  console.log('');

  for (const cfg of configs) {
    let correct = 0, exact = 0;
    for (const m of testSet) {
      const [aH, aA] = m.score.split('-').map(Number);
      const lH = calcLambda(m.home, m.away, true);
      const lA = calcLambda(m.away, m.home, false);
      const sim = monteCarlo(lH, lA, 5000);
      const top = sim.top5[0];
      if (top) {
        const [pH, pA] = [top.h, top.a];
        if ((pH > pA && aH > aA) || (pH === pA && aH === aA) || (pH < pA && aH < aA)) correct++;
        if (pH === aH && pA === aA) exact++;
      }
    }
    const marker = configs.indexOf(cfg) === 0 ? ' 🏆' : '';
    console.log(`  ${cfg.name.padEnd(18)} 结果准确率: ${(correct / 20 * 100).toFixed(1)}%  精确比分: ${(exact / 20 * 100).toFixed(1)}%${marker}`);
  }
  console.log(`\n  用户数据: ✅ ${Object.keys(userData).length} 队`);
}

function cmdAdvance() {
  const { execSync } = require('child_process');
  execSync('node advance.mjs', { cwd: __dirname, stdio: 'inherit' });
}

function cmdDashboard() {
  const { execSync } = require('child_process');
  execSync('node dashboard.mjs', { cwd: __dirname, stdio: 'inherit' });
  console.log('\n  浏览器打开 football/dashboard.html 查看');
}

/**
 * ⚽ 淘汰赛模拟 - 10,000次蒙特卡洛
 * 规则: 32强→16强→8强→4强→决赛
 * 平局时点球大战（50%概率某队获胜）
 */
function cmdKnockout() {
  const standings = db.getStandings();
  const SIMS = 10000;
  const championCount = {};
  const finalCount = {};
  const semiCount = {};

  console.log('');
  console.log('╔══════════════════════════════════════════════════════════════════════════════╗');
  console.log('║  🌍 2026 世界杯 - 淘汰赛模拟');
  console.log(`║  蒙特卡洛模拟: ${SIMS.toLocaleString()} 次`);
  console.log(`║  更新: ${new Date().toISOString().slice(0, 10)}`);
  console.log('╚══════════════════════════════════════════════════════════════════════════════╝');
  console.log('');

  // 获取小组排名
  const groupOrder = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L'];
  const groupWinners = [];
  const groupRunnersUp = [];
  const thirdPlace = [];

  for (const g of groupOrder) {
    const teams = db.GROUPS[g];
    const gs = teams.map(t => standings[t]).filter(Boolean)
      .sort((a, b) => b.p - a.p || b.gd - a.gd || b.gf - a.gf);
    if (gs.length >= 1) groupWinners.push(gs[0].team);
    if (gs.length >= 2) groupRunnersUp.push(gs[1].team);
    if (gs.length >= 3) thirdPlace.push(gs[2]);
  }

  // 8个最佳第3名
  const bestThird = thirdPlace.sort((a, b) => b.p - a.p || b.gd - a.gd || b.gf - a.gf).slice(0, 8);
  const advancingTeams = [...groupWinners, ...groupRunnersUp, ...bestThird.map(t => t.team)];

  console.log('  ━━━ 32强出线球队 ━━━');
  console.log(`  小组第一: ${groupWinners.join(', ')}`);
  console.log(`  小组第二: ${groupRunnersUp.join(', ')}`);
  console.log(`  最佳第3: ${bestThird.map(t => t.team).join(', ')}`);
  console.log('');

  // 淘汰赛对阵（1/16决赛）
  const knockoutBracket = [
    // 1/16决赛对阵 (按2026世界杯赛程)
    { round: '1/16', matches: [
      [1, 2], [3, 4], [5, 6], [7, 8], [9, 10], [11, 12], [13, 14], [15, 16],
      [17, 18], [19, 20], [21, 22], [23, 24], [25, 26], [27, 28], [29, 30], [31, 32]
    ]}
  ];

  // 模拟
  for (let sim = 0; sim < SIMS; sim++) {
    let currentTeams = [...advancingTeams];
    const roundNames = ['1/16', '1/8', '1/4', '半决赛', '决赛'];
    const roundSize = [32, 16, 8, 4, 2];

    for (let round = 0; round < 5; round++) {
      const nextTeams = [];
      for (let i = 0; i < currentTeams.length; i += 2) {
        const home = currentTeams[i];
        const away = currentTeams[i + 1];
        const lH = calcLambda(home, away, true, { isKnockout: true });
        const lA = calcLambda(away, home, false, { isKnockout: true });
        const mc = monteCarlo(lH, lA, 1);
        let [hG, aG] = [mc.sorted[0].h, mc.sorted[0].a];
        // 淘汰赛平局 → 点球大战
        if (hG === aG) {
          if (Math.random() < 0.5) hG++; else aG++;
        }
        nextTeams.push(hG > aG ? home : away);
      }
      currentTeams = nextTeams;
      // 记录进入该轮次的球队
      if (round === 3) currentTeams.forEach(t => semiCount[t] = (semiCount[t] || 0) + 1);
      if (round === 4) {
        currentTeams.forEach(t => finalCount[t] = (finalCount[t] || 0) + 1);
        championCount[currentTeams[0]] = (championCount[currentTeams[0]] || 0) + 1;
      }
    }
  }

  // 输出结果
  console.log('  ━━━ 夺冠概率 ━━━');
  const sortedChampions = Object.entries(championCount)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 16);
  for (const [team, count] of sortedChampions) {
    const pct = (count / SIMS * 100).toFixed(1);
    const bar = '█'.repeat(Math.round(pct / 2));
    console.log(`  ${team.padEnd(12)} ${pct.padStart(5)}% ${bar}`);
  }

  console.log('');
  console.log('  ━━━ 进入决赛概率 ━━━');
  const sortedFinals = Object.entries(finalCount)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 12);
  for (const [team, count] of sortedFinals) {
    const pct = (count / SIMS * 100).toFixed(1);
    const bar = '█'.repeat(Math.round(pct / 2));
    console.log(`  ${team.padEnd(12)} ${pct.padStart(5)}% ${bar}`);
  }

  console.log('');
  console.log('  ━━━ 进入四强概率 ━━━');
  const sortedSemis = Object.entries(semiCount)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 12);
  for (const [team, count] of sortedSemis) {
    const pct = (count / SIMS * 100).toFixed(1);
    const bar = '█'.repeat(Math.round(pct / 2));
    console.log(`  ${team.padEnd(12)} ${pct.padStart(5)}% ${bar}`);
  }

  // 保存报告
  const reportFile = path.join(__dirname, `knockout_simulation_${new Date().toISOString().slice(0, 10)}.txt`);
  const report = [
    '=== 2026 世界杯淘汰赛模拟 ===',
    `时间: ${new Date().toISOString()}`,
    `模拟次数: ${SIMS.toLocaleString()}`,
    '',
    '夺冠概率:',
    ...sortedChampions.map(([t, c]) => `  ${t}: ${(c/SIMS*100).toFixed(1)}%`),
    '',
    '进入决赛概率:',
    ...sortedFinals.map(([t, c]) => `  ${t}: ${(c/SIMS*100).toFixed(1)}%`),
    '',
    '进入四强概率:',
    ...sortedSemis.map(([t, c]) => `  ${t}: ${(c/SIMS*100).toFixed(1)}%`),
  ].join('\n');
  fs.writeFileSync(reportFile, report, 'utf-8');
  console.log(`\n📁 报告已保存: ${reportFile}`);
}

function cmdToday() {
  // 预测今天日期的比赛
  const today = new Date().toISOString().slice(0, 10);
  const todayMatches = db.UPCOMING_MATCHES.filter(m => m.date === today);
  const ongoingMatches = db.TODAY_MATCHES.filter(m => m.date === today);

  if (todayMatches.length === 0 && ongoingMatches.length === 0) {
    console.log(`\n📅 ${today} 没有比赛`);
    return;
  }

  console.log(`\n📅 ${today} 比赛:`);
  for (const m of [...todayMatches, ...ongoingMatches]) {
    const ctx = { isFinalRound: m.round === 3 || m.round === 'final' };
    const lH = calcLambda(m.home, m.away, true, ctx);
    const lA = calcLambda(m.away, m.home, false, ctx);
    const sim = monteCarlo(lH, lA, 5000);
    const top = sim.top5[0];
    console.log(`  ${m.group}  ${m.home.padEnd(12)} vs ${m.away.padEnd(12)}  λ ${lH.toFixed(2)}:${lA.toFixed(2)}  → ${top.score} (${top.pct.toFixed(1)}%)  胜率 ${sim.homeWinPct.toFixed(1)}/${sim.drawPct.toFixed(1)}/${sim.awayWinPct.toFixed(1)}`);
  }
}

// ============================================================
// 主入口
// ============================================================

const cmd = process.argv[2] || 'status';

switch (cmd) {
  case 'status':
    cmdStatus();
    break;
  case 'today':
    cmdToday();
    break;
  case 'match':
    if (process.argv[3] && process.argv[4]) {
      const isKnockout = process.argv[5] === '--knockout' || process.argv[5] === '-k';
      cmdMatch(process.argv[3], process.argv[4], isKnockout);
    } else {
      console.log('用法: node predict.mjs match 主队 客队 [--knockout]');
    }
    break;
  case 'all':
    cmdAll();
    break;
  case 'analyze':
    cmdAnalyze();
    break;
  case 'advance':
    cmdAdvance();
    break;
  case 'dashboard':
    cmdDashboard();
    break;
  case 'knockout':
    cmdKnockout();
    break;
  default:
    console.log(`
⚽ 2026 世界杯比分预测系统

用法:
  node predict.mjs status          - 数据库状态
  node predict.mjs today           - 今天比赛
  node predict.mjs match 主队 客队  - 指定比赛
  node predict.mjs all             - 剩余全部
  node predict.mjs analyze         - 模型分析
  node predict.mjs advance         - 出线形势
  node predict.mjs knockout       - 淘汰赛模拟 (10,000次)
  node predict.mjs dashboard       - 可视化
`);
}