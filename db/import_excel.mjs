#!/usr/bin/env node

/**
 * ⚽ 从 Excel 导入48队完整数据
 * 
 * 来源: C:\Users\L\Desktop\2026世界杯48队数据汇总.xlsx
 * 
 * 写入:
 * - worldcup.json (球队数据/ElO/历史交锋/近10场)
 */

import * as fs from 'fs';
import * as path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const DB_PATH = path.join(__dirname, 'worldcup.json');
const XLSX_PATH = 'C:/Users/L/Desktop/2026世界杯48队数据汇总.xlsx';

// ============================================================
// 读取 Excel
// ============================================================
const XLSX = (await import('xlsx')).default;
const wb = XLSX.readFile(XLSX_PATH);

const rankData = XLSX.utils.sheet_to_json(wb.Sheets['FIFA排名与ELO评分'], { defval: '' });
const h2hData = XLSX.utils.sheet_to_json(wb.Sheets['小组赛历史交锋'], { defval: '' });
const recentData = XLSX.utils.sheet_to_json(wb.Sheets['近10场战绩'], { defval: '' });

// ============================================================
// 加载现有数据库
// ============================================================
let db;
if (fs.existsSync(DB_PATH)) {
  db = JSON.parse(fs.readFileSync(DB_PATH, 'utf8'));
} else {
  console.error('❌ worldcup.json 不存在，先运行 db/init.mjs');
  process.exit(1);
}

// ============================================================
// 1. 更新球队数据 (FIFA排名 + ELO)
// ============================================================
let updated = 0, newTeam = 0;
for (const row of rankData) {
  const name = row['球队'];
  if (!name) continue;
  
  // 映射风格（从现有数据保留，Excel 没有风格字段）
  const existing = db.teams[name];
  
  db.teams[name] = {
    ...(existing || {}),
    attackBase: existing?.attackBase || 1.0,
    defenseBase: existing?.defenseBase || 1.0,
    style: existing?.style || '',
    styleFactor: existing?.styleFactor || 1.0,
    rank: row['FIFA排名'],
    fifaPoints: row['FIFA积分'],
    eloRating: row['ELO评分'],
    confederation: row['所属足联'],
    // 保留经济学数据
    population: existing?.population,
    gdpPerCapita: existing?.gdpPerCapita,
    climate: existing?.climate,
    avgAltitude: existing?.avgAltitude,
    isHost: existing?.isHost || false,
  };
  
  if (existing) updated++;
  else newTeam++;
}

console.log(`✅ 球队数据更新: ${updated} 已更新, ${newTeam} 新增`);

// ============================================================
// 2. 写入历史交锋
// ============================================================
db.headToHead = {};
for (const row of h2hData) {
  const a = row['球队A'], b = row['球队B'];
  const key = [a, b].sort().join('|');
  db.headToHead[key] = {
    teamA: a, teamB: b,
    total: row['总场次'],
    aWins: row['A队胜'],
    draws: row['平局'],
    bWins: row['B队胜'],
  };
}
console.log(`✅ 历史交锋: ${Object.keys(db.headToHead).length} 组`);

// ============================================================
// 3. 写入近10场战绩
// ============================================================
const teamRecent = {};
for (const row of recentData) {
  const team = row['球队'];
  if (!teamRecent[team]) teamRecent[team] = [];
  teamRecent[team].push({
    date: row['日期'],
    opponent: row['对手'],
    score: row['比分'],
    venue: row['主/客'],
    competition: row['赛事'],
    result: row['结果'],
  });
}
// 按日期降序排列
for (const team of Object.keys(teamRecent)) {
  teamRecent[team].sort((a, b) => b.date.localeCompare(a.date));
}
db.recentMatches = teamRecent;
console.log(`✅ 近10场战绩: ${Object.keys(teamRecent).length} 队, ${recentData.length} 条记录`);

// ============================================================
// 4. 重新计算 Elo (用真实 Elo 覆盖)
// ============================================================
// 注意: 用户提供的 ELO 已经是赛后更新过的
// 不需要再 batchUpdateElo

// ============================================================
// 5. 保存
// ============================================================
db.meta.updatedAt = new Date().toISOString();
db.meta.dataVersion = 4;
db.meta.dataSource = '2026世界杯48队数据汇总.xlsx';
db.meta.dataDate = '2026-06-24';

fs.writeFileSync(DB_PATH, JSON.stringify(db, null, 2), 'utf8');
console.log(`\n✅ 全部数据已写入 worldcup.json`);

// ============================================================
// 统计
// ============================================================
const eloList = Object.entries(db.teams)
  .map(([n, t]) => ({ name: n, elo: t.eloRating }))
  .sort((a, b) => b.elo - a.elo);
console.log('\nElo Top 10:');
eloList.slice(0, 10).forEach((t, i) => console.log(`  ${i+1}. ${t.name}: ${t.elo}`));
console.log('Elo Bottom 5:');
eloList.slice(-5).forEach((t, i) => console.log(`  ${i+1}. ${t.name}: ${t.elo}`));

// 统计每队近10场胜负
for (const [team, matches] of Object.entries(teamRecent)) {
  const wins = matches.filter(m => m.result === '胜').length;
  const draws = matches.filter(m => m.result === '平').length;
  const losses = matches.filter(m => m.result === '负').length;
  if (db.teams[team]) {
    db.teams[team].recentWins = wins;
    db.teams[team].recentDraws = draws;
    db.teams[team].recentLosses = losses;
  }
}
fs.writeFileSync(DB_PATH, JSON.stringify(db, null, 2), 'utf8');
console.log('\n✅ 近10场胜负已同步到球队数据');