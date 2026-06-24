/**
 * ⚽ 世界杯 2026 出线形势分析 + 可视化
 * 
 * 规则:
 *   - 12组, 每组前2名直接出线 (24队)
 *   - 8个成绩最好的第3名出线 (8队)
 *   - 共32强 → 1/16决赛
 * 
 * 用法: node advance.mjs
 */

import * as fs from 'fs';
import * as path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// 加载数据库
let db;
try {
  db = await import(new URL('database.mjs', import.meta.url).href);
} catch (e) {
  console.error('数据库加载失败:', e.message);
  process.exit(1);
}

// 加载用户数据
let userData = {};
try {
  userData = JSON.parse(fs.readFileSync(path.join(__dirname, 'user_team_data.json'), 'utf8'));
  // 覆盖球队特征
  for (const [name, data] of Object.entries(userData)) {
    if (db.TEAM_STRENGTHS[name]) {
      db.TEAM_STRENGTHS[name].attackBase = data.attackBase;
      db.TEAM_STRENGTHS[name].defenseBase = data.defenseBase;
      db.TEAM_STRENGTHS[name].styleFactor = data.styleFactor;
      db.TEAM_STRENGTHS[name].rank = data.rank;
    }
  }
} catch (e) {
  console.log('未找到用户数据，使用默认特征');
}

// ============================================================
// 辅助函数
// ============================================================

function calcLambda(teamName, opponentName, isHome, ctx, playedData, strengths) {
  const team = strengths[teamName];
  const opponent = strengths[opponentName];
  if (!team || !opponent) return 1.0;
  let lambda = team.attackBase;
  if (isHome) lambda *= 1.08;
  lambda *= team.styleFactor;
  const pd = playedData[teamName];
  if (pd && pd.played >= 1) {
    lambda = lambda * 0.6 + (pd.gf / pd.played) * 0.4;
  }
  const oppDef = 1.0 - (opponent.defenseBase - 0.8) * 0.2;
  lambda *= Math.max(0.7, Math.min(1.3, oppDef));
  const sd = (team.attackBase - team.defenseBase) - (opponent.attackBase - opponent.defenseBase);
  if (sd > 0.5) lambda *= (isHome ? 1.08 : 1.05);
  else if (sd < -0.5) lambda *= (isHome ? 0.92 : 0.95);
  if (ctx.isFinalRound) lambda *= 0.92;
  return Math.round(lambda * 100) / 100;
}

function monteCarlo(lH, lA, N = 5000) {
  function ps(lambda) {
    const L = Math.exp(-lambda); let k = 0, p = 1;
    do { k++; p *= Math.random(); } while (p > L);
    return k - 1;
  }
  const results = {};
  let hW = 0, dr = 0, aW = 0, tG = 0;
  for (let i = 0; i < N; i++) {
    const h = ps(lH), a = ps(lA);
    results[`${h}-${a}`] = (results[`${h}-${a}`] || 0) + 1;
    if (h > a) hW++; else if (h === a) dr++; else aW++;
    tG += h + a;
  }
  const sorted = Object.entries(results).map(([s, c]) => ({ score: s, h: Number(s.split('-')[0]), a: Number(s.split('-')[1]), count: c, pct: c / N * 100 })).sort((a, b) => b.count - a.count);
  return { sorted, top5: sorted.slice(0, 5), homeWinPct: hW / N * 100, drawPct: dr / N * 100, awayWinPct: aW / N * 100 };
}

// ============================================================
// 蒙特卡洛模拟全部剩余比赛
// ============================================================

function simulateAllRemaining(standings) {
  const playedData = {};
  for (const m of db.COMPLETED_MATCHES) {
    const [hG, aG] = m.score.split('-').map(Number);
    for (const t of [m.home, m.away]) {
      if (!playedData[t]) playedData[t] = { team: t, played: 0, gf: 0, ga: 0 };
    }
    playedData[m.home].played++;
    playedData[m.home].gf += hG;
    playedData[m.home].ga += aG;
    playedData[m.away].played++;
    playedData[m.away].gf += aG;
    playedData[m.away].ga += hG;
  }

  // 模拟 N 次完整剩余赛程
  const SIMS = 10000;
  const advanceCount = {};
  const thirdPlaceScores = [];

  for (let sim = 0; sim < SIMS; sim++) {
    // 深拷贝积分榜
    const simStandings = JSON.parse(JSON.stringify(standings));

    // 模拟每场剩余比赛
    const allRemaining = [...db.UPCOMING_MATCHES];
    for (const m of allRemaining) {
      const ctx = { isFinalRound: m.round === 3 };
      const lH = calcLambda(m.home, m.away, true, ctx, playedData, db.TEAM_STRENGTHS);
      const lA = calcLambda(m.away, m.home, false, ctx, playedData, db.TEAM_STRENGTHS);
      const mc = monteCarlo(lH, lA, 1); // 单次模拟
      const [hG, aG] = [mc.sorted[0].h, mc.sorted[0].a];

      const h = simStandings[m.home];
      const a = simStandings[m.away];
      if (!h || !a) continue;
      h.played++; a.played++;
      h.gf += hG; h.ga += aG;
      a.gf += aG; a.ga += hG;
      if (hG > aG) { h.w++; h.p += 3; a.l++; }
      else if (hG === aG) { h.d++; h.p += 1; a.d++; a.p += 1; }
      else { h.l++; a.w++; a.p += 3; }
    }

    // 每组排名
    const groupOrder = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L'];
    const top2 = [];
    const thirdPlace = [];

    for (const g of groupOrder) {
      const teams = db.GROUPS[g];
      const ranked = teams
        .map(t => simStandings[t])
        .filter(Boolean)
        .sort((a, b) => b.p - a.p || b.gd - a.gd || b.gf - a.gf || a.rank - b.rank);

      for (let i = 0; i < Math.min(2, ranked.length); i++) {
        top2.push(ranked[i].team);
        advanceCount[ranked[i].team] = (advanceCount[ranked[i].team] || 0) + 1;
      }
      if (ranked.length >= 3) {
        thirdPlace.push(ranked[2]);
      }
    }

    // 前8个最佳第3名
    const bestThird = thirdPlace
      .sort((a, b) => b.p - a.p || b.gd - a.gd || b.gf - a.gf)
      .slice(0, 8);

    for (const t of bestThird) {
      advanceCount[t.team] = (advanceCount[t.team] || 0) + 1;
    }
  }

  // 计算概率
  const result = {};
  for (const [team, count] of Object.entries(advanceCount)) {
    result[team] = {
      prob: (count / SIMS * 100).toFixed(1),
      group: db.getTeamGroup(team),
    };
  }

  return result;
}

// ============================================================
// 可视化输出
// ============================================================

function generateReport(standings, advanceProbs) {
  const lines = [];
  lines.push('');
  lines.push('╔══════════════════════════════════════════════════════════════════════════════╗');
  lines.push('║  🌍 2026 世界杯 - 出线形势分析');
  lines.push(`║  蒙特卡洛模拟: 10,000 次`);
  lines.push(`║  更新: ${new Date().toISOString().slice(0, 10)}`);
  lines.push('╚══════════════════════════════════════════════════════════════════════════════╝');
  lines.push('');

  const groupOrder = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L'];

  for (const g of groupOrder) {
    const teams = db.GROUPS[g];
    const groupStandings = teams
      .map(t => standings[t])
      .filter(Boolean)
      .sort((a, b) => b.p - a.p || b.gd - a.gd || b.gf - a.gf);

    if (groupStandings.length === 0) continue;

    lines.push(`  ━━━ Group ${g} ━━━`);
    lines.push(`  ${'球队'.padEnd(14)} 赛 胜 平 负 进 失 净 分  ${'出线概率'.padEnd(8)}  ${'状态'.padEnd(14)}`);
    lines.push(`  ${'─'.repeat(14)} ─ ─ ─ ─ ─ ─ ─  ${'─'.repeat(8)}  ${'─'.repeat(14)}`);

    for (const s of groupStandings) {
      const prob = advanceProbs[s.team] ? advanceProbs[s.team].prob : '0.0';
      const probNum = Number(prob);
      const bar = probNum >= 90 ? '🟢' : probNum >= 60 ? '🔵' : probNum >= 30 ? '🟡' : probNum >= 10 ? '🟠' : '🔴';
      let status = '';
      if (s.played === 3 && s.p >= 6) status = '✅ 已出线';
      else if (probNum >= 90) status = '🔒 锁定出线';
      else if (probNum >= 60) status = '👍 占优';
      else if (probNum >= 30) status = '⚖️ 争夺中';
      else if (probNum >= 10) status = '⚠️ 需奇迹';
      else if (s.played === 3) status = '❌ 已出局';
      else status = '🏳️ 濒临出局';

      lines.push(`  ${s.team.padEnd(14)} ${s.played}  ${s.w}  ${s.d}  ${s.l}  ${s.gf}  ${s.ga} ${s.gd > 0 ? '+' : ''}${s.gd}  ${s.p.toString().padStart(2)}  ${bar} ${prob.padStart(5)}%  ${status}`);
    }
    lines.push('');
  }

  // 第3名出线分析
  lines.push('  ━━━ 最佳第3名争夺 ━━━');
  const allThird = Object.entries(advanceProbs)
    .filter(([t, p]) => {
      const st = standings[t];
      return st && st.played >= 2;
    })
    .sort((a, b) => Number(b[1].prob) - Number(a[1].prob));

  for (const [team, info] of allThird.slice(0, 20)) {
    const st = standings[team];
    if (!st || st.played < 2) continue;
    // 检查是否大概率前2
    const top2Prob = allThird
      .filter(([t]) => {
        const s = standings[t];
        return s && s.group === info.group;
      })
      .sort((a, b) => Number(b[1].prob) - Number(a[1].prob))
      .slice(0, 2)
      .map(([t]) => t);

    const isLikelyTop2 = top2Prob.includes(team);
    if (!isLikelyTop2) {
      const barLen = Math.round(Number(info.prob) / 5);
      const bar = '█'.repeat(barLen) + '░'.repeat(Math.max(0, 20 - barLen));
      lines.push(`  ${team.padEnd(12)} Group ${info.group}  ${info.prob.padStart(5)}% ${bar}`);
    }
  }

  lines.push('');
  lines.push('  ━━━ 已出线球队 ━━━');
  const advanced = Object.entries(advanceProbs)
    .filter(([t, p]) => Number(p.prob) >= 99.9)
    .sort((a, b) => a[1].group.localeCompare(b[1].group) || Number(b[1].prob) - Number(a[1].prob));
  for (const [team, info] of advanced) {
    lines.push(`  ✅ Group ${info.group} ${team}`);
  }

  return lines.join('\n');
}

// ============================================================
// 主流程
// ============================================================

const standings = db.getStandings();
console.log('模拟 10,000 次剩余比赛...');
const probs = simulateAllRemaining(standings);
const report = generateReport(standings, probs);
console.log(report);

// 保存报告
const reportFile = path.join(__dirname, `advance_analysis_${new Date().toISOString().slice(0, 10)}.txt`);
fs.writeFileSync(reportFile, report, 'utf-8');
console.log(`\n📁 报告已保存: ${reportFile}`);
