/**
 * ⚽ 2026 世界杯预测 - HTML 可视化仪表盘
 * 
 * 生成一个独立的 HTML 文件，包含:
 *   - 小组积分榜 + 出线概率条
 *   - 第3轮预测结果
 *   - 出线形势总览
 * 
 * 用法: node dashboard.mjs
 */

import * as fs from 'fs';
import * as path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

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
  console.error('加载失败:', e.message);
  process.exit(1);
}

// 辅助函数
function calcLambda(teamName, opponentName, isHome, ctx) {
  const team = db.TEAM_STRENGTHS[teamName], opponent = db.TEAM_STRENGTHS[opponentName];
  if (!team || !opponent) return 1.0;
  let lambda = team.attackBase;
  if (isHome) lambda *= 1.08;
  lambda *= team.styleFactor;
  const pd = {}; db.COMPLETED_MATCHES.forEach(m => { const [h,a]=m.score.split('-').map(Number); [m.home,m.away].forEach(t=>{if(!pd[t])pd[t]={played:0,gf:0,ga:0}}); pd[m.home].played++; pd[m.home].gf+=h; pd[m.home].ga+=a; pd[m.away].played++; pd[m.away].gf+=a; pd[m.away].ga+=h; });
  const p = pd[teamName];
  if (p && p.played >= 1) lambda = lambda * 0.6 + (p.gf / p.played) * 0.4;
  const od = 1.0 - (opponent.defenseBase - 0.8) * 0.2;
  lambda *= Math.max(0.7, Math.min(1.3, od));
  const sd = (team.attackBase - team.defenseBase) - (opponent.attackBase - opponent.defenseBase);
  if (sd > 0.5) lambda *= (isHome ? 1.08 : 1.05);
  else if (sd < -0.5) lambda *= (isHome ? 0.92 : 0.95);
  if (ctx.isFinalRound) lambda *= 0.92;
  return Math.round(lambda * 100) / 100;
}

function monteCarlo(lH, lA, N = 5000) {
  function ps(lambda) { const L = Math.exp(-lambda); let k = 0, p = 1; do { k++; p *= Math.random(); } while (p > L); return k - 1; }
  const results = {}; let hW = 0, dr = 0, aW = 0, tG = 0;
  for (let i = 0; i < N; i++) { const h = ps(lH), a = ps(lA); results[`${h}-${a}`] = (results[`${h}-${a}`] || 0) + 1; if (h > a) hW++; else if (h === a) dr++; else aW++; tG += h + a; }
  const sorted = Object.entries(results).map(([s, c]) => ({ score: s, h: Number(s.split('-')[0]), a: Number(s.split('-')[1]), count: c, pct: c / N * 100 })).sort((a, b) => b.count - a.count);
  return { sorted, top5: sorted.slice(0, 5), homeWinPct: hW / N * 100, drawPct: dr / N * 100, awayWinPct: aW / N * 100, avgGoals: tG / N };
}

// ============================================================
// 生成 HTML
// ============================================================

function generateHTML() {
  const standings = db.getStandings();
  const stats = db.getStats();
  const groupOrder = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L'];

  // 小组积分榜 HTML
  let groupsHTML = '';
  for (const g of groupOrder) {
    const teams = db.GROUPS[g];
    const gs = teams.map(t => standings[t]).filter(Boolean).sort((a, b) => b.p - a.p || b.gd - a.gd || b.gf - a.gf);
    const rows = gs.map(s => {
      const maxP = Math.max(...gs.map(x => x.p), 1);
      const barPct = (s.p / maxP * 100).toFixed(0);
      return `<tr>
        <td>${s.team}</td>
        <td>${s.played}</td>
        <td>${s.w}</td>
        <td>${s.d}</td>
        <td>${s.l}</td>
        <td>${s.gf}</td>
        <td>${s.ga}</td>
        <td>${s.gd > 0 ? '+' : ''}${s.gd}</td>
        <td><strong>${s.p}</strong></td>
        <td><div class="bar-wrap"><div class="bar" style="width:${barPct}%"></div><span class="bar-label">${s.p}分</span></div></td>
      </tr>`;
    }).join('');
    groupsHTML += `<div class="group-card">
      <h2>Group ${g}</h2>
      <table><thead><tr><th>球队</th><th>赛</th><th>胜</th><th>平</th><th>负</th><th>进</th><th>失</th><th>净</th><th>分</th><th></th></tr></thead><tbody>${rows}</tbody></table>
    </div>`;
  }

  // 第3轮预测 HTML
  let predictionsHTML = '';
  for (const m of db.UPCOMING_MATCHES) {
    const ctx = { isFinalRound: m.round === 3 };
    const lH = calcLambda(m.home, m.away, true, ctx);
    const lA = calcLambda(m.away, m.home, false, ctx);
    const sim = monteCarlo(lH, lA, 5000);
    const top = sim.top5[0];
    const hP = sim.homeWinPct.toFixed(1);
    const dP = sim.drawPct.toFixed(1);
    const aP = sim.awayWinPct.toFixed(1);
    const homeBar = Math.round(sim.homeWinPct);
    const drawBar = Math.round(sim.drawPct);
    const awayBar = Math.round(sim.awayWinPct);

    predictionsHTML += `<div class="pred-card">
      <div class="pred-header">${m.date} | Group ${m.group}</div>
      <div class="pred-teams">${m.home} vs ${m.away}</div>
      <div class="pred-lambda">λ ${lH.toFixed(2)} : ${lA.toFixed(2)}</div>
      <div class="pred-top">最可能: <strong>${top.score}</strong> (${top.pct.toFixed(1)}%)</div>
      <div class="win-bar-wrap">
        <div class="win-bar home-bar" style="width:${homeBar}%">${m.home} ${hP}%</div>
        <div class="win-bar draw-bar" style="width:${Math.max(drawBar, 5)}%">平 ${dP}%</div>
        <div class="win-bar away-bar" style="width:${awayBar}%">${m.away} ${aP}%</div>
      </div>
      <div class="pred-scores">
        ${sim.top5.slice(0, 3).map(s => `<span class="score-chip">${s.score} ${s.pct.toFixed(1)}%</span>`).join('')}
      </div>
    </div>`;
  }

  // 比分分布 HTML
  const topScores = Object.entries(stats.scoreDist).slice(0, 10);
  const maxScore = Math.max(...topScores.map(([_, c]) => c));
  let scoresHTML = '';
  for (const [sc, cnt] of topScores) {
    const pct = (cnt / stats.total * 100).toFixed(1);
    const barW = (cnt / maxScore * 100).toFixed(0);
    scoresHTML += `<div class="score-row">
      <span class="score-label">${sc}</span>
      <div class="bar-wrap"><div class="bar score-bar" style="width:${barW}%"></div></div>
      <span class="score-val">${cnt}次 (${pct}%)</span>
    </div>`;
  }

  // 概览统计
  const overviewHTML = `
    <div class="overview-card">
      <div class="stat"><span class="stat-num">${stats.total}</span><span class="stat-label">已完赛场次</span></div>
      <div class="stat"><span class="stat-num">${stats.avgGoals}</span><span class="stat-label">场均进球</span></div>
      <div class="stat"><span class="stat-num">${stats.homeWinPct}%</span><span class="stat-label">主胜率</span></div>
      <div class="stat"><span class="stat-num">${stats.drawPct}%</span><span class="stat-label">平率</span></div>
      <div class="stat"><span class="stat-num">${stats.awayWinPct}%</span><span class="stat-label">客胜率</span></div>
      <div class="stat"><span class="stat-num">${db.UPCOMING_MATCHES.length}</span><span class="stat-label">剩余小组赛</span></div>
    </div>
  `;

  // 积分榜概览（简版）
  let overviewTable = '';
  for (const g of groupOrder) {
    const teams = db.GROUPS[g];
    const gs = teams.map(t => standings[t]).filter(Boolean).sort((a, b) => b.p - a.p || b.gd - a.gd || b.gf - a.gf);
    const names = gs.map((s, i) => {
      const medal = i === 0 ? '🥇' : i === 1 ? '🥈' : '';
      return `${medal} ${s.team}(${s.p}p)`;
    }).join(' → ');
    overviewTable += `<div class="group-row"><span class="group-label">${g}</span><span class="group-teams">${names}</span></div>`;
  }

  return `<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>🌍 2026 世界杯预测仪表盘</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0a0e17; color: #e0e8f0; padding: 20px; }
.container { max-width: 1400px; margin: 0 auto; }
h1 { font-size: 1.8rem; margin-bottom: 5px; background: linear-gradient(90deg, #f59e0b, #ef4444, #3b82f6); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
.subtitle { color: #8899aa; font-size: 0.9rem; margin-bottom: 20px; }
.overview-card { display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 24px; }
.stat { background: #141b29; border-radius: 12px; padding: 16px 24px; flex: 1; min-width: 100px; text-align: center; border: 1px solid #1e2d45; }
.stat-num { display: block; font-size: 1.8rem; font-weight: 700; color: #f0c040; }
.stat-label { display: block; font-size: 0.8rem; color: #8899aa; margin-top: 4px; }
h2 { font-size: 1.1rem; margin: 16px 0 12px; color: #c8d8e8; border-left: 3px solid #3b82f6; padding-left: 10px; }
.group-row { display: flex; align-items: center; gap: 10px; padding: 6px 12px; background: #141b29; border-radius: 8px; margin-bottom: 4px; border: 1px solid #1e2d45; }
.group-label { font-weight: 700; color: #f0c040; width: 28px; }
.group-teams { color: #b0c0d0; font-size: 0.85rem; }
.groups-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 16px; margin-bottom: 24px; }
.group-card { background: #141b29; border-radius: 12px; padding: 16px; border: 1px solid #1e2d45; }
.group-card h2 { margin: 0 0 10px; font-size: 1rem; border: none; padding: 0; }
table { width: 100%; border-collapse: collapse; font-size: 0.8rem; }
th { color: #8899aa; font-weight: 600; padding: 6px 4px; text-align: center; border-bottom: 1px solid #1e2d45; }
td { padding: 5px 4px; text-align: center; }
td:first-child { text-align: left; font-weight: 600; }
.bar-wrap { position: relative; width: 100%; height: 20px; background: #1e2d45; border-radius: 10px; overflow: hidden; }
.bar { height: 100%; background: linear-gradient(90deg, #3b82f6, #60a5fa); border-radius: 10px; transition: width 0.5s; }
.bar-label { position: absolute; left: 8px; top: 2px; font-size: 0.7rem; font-weight: 600; color: #fff; }
.predictions-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px; margin-bottom: 24px; }
.pred-card { background: #141b29; border-radius: 12px; padding: 14px; border: 1px solid #1e2d45; }
.pred-header { font-size: 0.75rem; color: #8899aa; margin-bottom: 4px; }
.pred-teams { font-size: 1rem; font-weight: 700; margin-bottom: 4px; }
.pred-lambda { font-size: 0.75rem; color: #8899aa; margin-bottom: 6px; }
.pred-top { font-size: 0.85rem; margin-bottom: 8px; }
.pred-top strong { color: #f0c040; font-size: 1rem; }
.win-bar-wrap { display: flex; height: 22px; border-radius: 11px; overflow: hidden; margin-bottom: 8px; font-size: 0.65rem; font-weight: 600; }
.home-bar { background: linear-gradient(90deg, #3b82f6, #60a5fa); display: flex; align-items: center; justify-content: center; color: #fff; min-width: 0; overflow: hidden; white-space: nowrap; }
.draw-bar { background: linear-gradient(90deg, #8b5cf6, #a78bfa); display: flex; align-items: center; justify-content: center; color: #fff; }
.away-bar { background: linear-gradient(90deg, #ef4444, #f87171); display: flex; align-items: center; justify-content: center; color: #fff; }
.pred-scores { display: flex; gap: 6px; flex-wrap: wrap; }
.score-chip { background: #1e2d45; border-radius: 6px; padding: 3px 8px; font-size: 0.75rem; color: #b0c0d0; }
.score-dist { background: #141b29; border-radius: 12px; padding: 16px; border: 1px solid #1e2d45; margin-bottom: 24px; }
.score-row { display: flex; align-items: center; gap: 10px; margin-bottom: 6px; }
.score-label { width: 50px; font-weight: 700; font-size: 0.85rem; }
.score-val { font-size: 0.8rem; color: #8899aa; white-space: nowrap; min-width: 80px; }
.score-bar { background: linear-gradient(90deg, #f59e0b, #f97316); }
.footer { text-align: center; color: #556677; font-size: 0.75rem; margin-top: 24px; padding: 16px; border-top: 1px solid #1e2d45; }
</style>
</head>
<body>
<div class="container">
  <h1>🌍 2026 世界杯 - 预测仪表盘</h1>
  <div class="subtitle">数据来源: 曹昊源  |  蒙特卡洛: 5,000次/场  |  Dixon-Coles修正  |  更新: ${new Date().toISOString().slice(0, 10)}</div>

  ${overviewHTML}

  <h2>📊 小组积分榜总览</h2>
  <div class="groups-grid">
    ${groupsHTML}
  </div>

  <h2>📈 第3轮预测 (${db.UPCOMING_MATCHES.length}场)</h2>
  <div class="predictions-grid">
    ${predictionsHTML}
  </div>

  <h2>📉 已完赛比分分布 (${stats.total}场)</h2>
  <div class="score-dist">
    ${scoresHTML}
  </div>

  <div class="footer">
    2026 美加墨世界杯 | Powered by Kasha Predictor v2.0 | Dixon-Coles + 蒙特卡洛
  </div>
</div>
</body>
</html>`;
}

const html = generateHTML();
const outPath = path.join(__dirname, 'dashboard.html');
fs.writeFileSync(outPath, html, 'utf-8');
console.log('✅ 仪表盘已生成: football/dashboard.html');
console.log(`   文件大小: ${(fs.statSync(outPath).size / 1024).toFixed(0)} KB`);
console.log(`   直接浏览器打开即可查看`);
