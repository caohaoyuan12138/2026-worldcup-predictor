#!/usr/bin/env node

/**
 * �?世界杯预�?- 数据库初始化
 * 
 * �?database.mjs / user_team_data.json 迁移数据�?JSON 文件数据�? * 零依赖，�?JSON 持久�? */

import * as fs from 'fs';
import * as path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const DB_DIR = __dirname;
const DATA_DIR = path.resolve(__dirname, '..');

// ============================================================
// 1. 导入旧数�?// ============================================================

let src;
try {
  src = fs.readFileSync(path.join(DATA_DIR, 'database.mjs'), 'utf8');
} catch (e) {
  console.error('�?找不�?database.mjs');
  process.exit(1);
}

// 解析 database.mjs 中的数据（正则提取）
function extractConst(name) {
  const re = new RegExp(`const\\s+${name}\\s*=\\s*(\\[[\\s\\S]*?\\]);\\s*\\n`, 'm');
  const m = src.match(re);
  if (!m) {
    // try multi-line object
    const re2 = new RegExp(`const\\s+${name}\\s*=\\s*(\\{[\\s\\S]*?\\});\\s*\\n`, 'm');
    const m2 = src.match(re2);
    if (!m2) return null;
    return eval('(' + m2[1] + ')');
  }
  return eval(m[1]);
}

const GROUPS = extractConst('GROUPS');
const COMPLETED_MATCHES = extractConst('COMPLETED_MATCHES');
const TODAY_MATCHES = extractConst('TODAY_MATCHES');
const UPCOMING_MATCHES = extractConst('UPCOMING_MATCHES');
const KNOCKOUT_MATCHES = extractConst('KNOCKOUT_MATCHES');
const TEAM_STRENGTHS = extractConst('TEAM_STRENGTHS');

// 用户覆盖数据
let userTeamData = {};
try {
  userTeamData = JSON.parse(fs.readFileSync(path.join(DATA_DIR, 'user_team_data.json'), 'utf8'));
} catch (e) {
  console.log('⚠️ 没找�?user_team_data.json，用 database.mjs 的默认数�?);
}

// 合并用户数据
for (const [name, data] of Object.entries(userTeamData)) {
  if (TEAM_STRENGTHS[name]) {
    TEAM_STRENGTHS[name].attackBase = data.attackBase;
    TEAM_STRENGTHS[name].defenseBase = data.defenseBase;
    TEAM_STRENGTHS[name].styleFactor = data.styleFactor;
    TEAM_STRENGTHS[name].rank = data.rank;
    TEAM_STRENGTHS[name].style = data.style;
    // 补充字段（可选）
    if (data.attackThirdPassPct !== undefined) TEAM_STRENGTHS[name].attackThirdPassPct = data.attackThirdPassPct;
    if (data.shotConversion !== undefined) TEAM_STRENGTHS[name].shotConversion = data.shotConversion;
    if (data.possessionStyle !== undefined) TEAM_STRENGTHS[name].possessionStyle = data.possessionStyle;
    if (data.defenseIntercept !== undefined) TEAM_STRENGTHS[name].defenseIntercept = data.defenseIntercept;
  }
}

// ============================================================
// 2. 构建小组映射
// ============================================================

const TEAM_GROUP = {};
for (const [g, teams] of Object.entries(GROUPS)) {
  for (const t of teams) TEAM_GROUP[t] = g;
}

// ============================================================
// 3. 写入 JSON 数据库文�?// ============================================================

const db = {
  meta: {
    version: 3,
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
    description: '2026 世界杯预测数据库'
  },
  groups: GROUPS,
  teamGroup: TEAM_GROUP,
  teams: TEAM_STRENGTHS,
  completedMatches: COMPLETED_MATCHES,
  todayMatches: TODAY_MATCHES,
  upcomingMatches: UPCOMING_MATCHES,
  knockoutMatches: KNOCKOUT_MATCHES,
  predictionHistory: [],
  modelConfig: {
    monteCarloRuns: 10000,
    homeAdvantage: 1.08,
    dcRho: 0.12,
    realPerformanceWeight: 0.4,
    preseasonWeight: 0.6,
    finalRoundFactor: 0.92
  }
};

const outPath = path.join(DB_DIR, 'worldcup.json');
fs.writeFileSync(outPath, JSON.stringify(db, null, 2), 'utf8');
console.log(`�?数据库已初始�? db/worldcup.json`);
console.log(`   球队: ${Object.keys(TEAM_STRENGTHS).length} 队`);
console.log(`   分组: ${Object.keys(GROUPS).length} 组`);
console.log(`   已完�? ${COMPLETED_MATCHES.length} 场`);
console.log(`   未赛: ${UPCOMING_MATCHES.length} 场`);
console.log(`   淘汰�? ${KNOCKOUT_MATCHES.length} 场`);

// ============================================================
// 4. 创建 predictions 目录（如果不存在�?// ============================================================

const predDir = path.join(DATA_DIR, 'predictions');
if (!fs.existsSync(predDir)) {
  fs.mkdirSync(predDir, { recursive: true });
}
