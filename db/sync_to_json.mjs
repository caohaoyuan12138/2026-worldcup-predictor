#!/usr/bin/env node

/**
 * 同步 database.mjs 到 worldcup.json
 * 
 * 解决 C1 问题：worldcup.json.teams 为空
 * 解决 C2/L6 问题：Elo 评分从未持久化
 * 
 * 用法: node db/sync_to_json.mjs
 */

import * as fs from 'fs';
import * as path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.join(__dirname, '..');

// 加载 database.mjs
const dbModule = await import(new URL('../database.mjs', import.meta.url).href);
const TEAM_STRENGTHS = dbModule.TEAM_STRENGTHS;

// 加载现有 worldcup.json
const wcPath = path.join(__dirname, 'worldcup.json');
const wcRaw = fs.readFileSync(wcPath, 'utf8');
const wcData = JSON.parse(wcRaw);

console.log('📋 同步 database.mjs → worldcup.json\n');
console.log(`  原 teams 数量: ${Object.keys(wcData.teams || {}).length}`);
console.log(`  database.mjs 球队数: ${Object.keys(TEAM_STRENGTHS).length}`);

// 构建 teams 对象
const teams = {};
for (const [name, data] of Object.entries(TEAM_STRENGTHS)) {
  // 计算初始 Elo
  const rank = data.rank || 50;
  let elo;
  if (rank <= 10) elo = Math.round(1750 + (10 - rank) * (100 / 9));
  else if (rank <= 30) elo = Math.round(1550 + (30 - rank) * (100 / 20));
  else elo = Math.round(1400 + (50 - rank) * (50 / 20));
  
  teams[name] = {
    attackBase: data.attackBase,
    defenseBase: data.defenseBase,
    styleFactor: data.styleFactor,
    style: data.style,
    rank: rank,
    eloRating: elo,  // 初始 Elo
    worldCupTitles: data.worldCupTitles || 0,
    gdpPerCapita: data.gdpPerCapita || 20000,
    population: data.population || 10,
    isHost: data.isHost || false,
    climate: data.climate || '温带',
    avgAltitude: data.avgAltitude || 0,
    top50Scorers: data.top50Scorers || 0,
    shotConversion: data.shotConversion || 0,
    attackThirdPassPct: data.attackThirdPassPct || 0,
  };
}

wcData.teams = teams;

// 保存
wcData.meta.syncedFrom = 'database.mjs';
wcData.meta.syncedAt = new Date().toISOString();
wcData.meta.dataVersion = (wcData.meta.dataVersion || 0) + 1;

fs.writeFileSync(wcPath, JSON.stringify(wcData, null, 2), 'utf8');

console.log(`\n  ✅ 已写入 ${Object.keys(teams).length} 支球队到 worldcup.json`);
console.log(`  📊 Elo 范围: ${Math.min(...Object.values(teams).map(t => t.eloRating))} - ${Math.max(...Object.values(teams).map(t => t.eloRating))}`);
console.log(`  📁 文件: ${wcPath}`);
