/**
 * xG 数据更新脚本
 *
 * 用途：每场比赛日后更新球队的 xG 模型数据
 * 数据源：懂球帝（dongqiudi_full.json）+ 已完赛比赛结果 + 实际 xG 计算数据
 *
 * 用法：node scripts/update_xg_data.mjs
 *
 * 工作流程：
 * 1. 加载 worldcup.json 和 dongqiudi_full.json
 * 2. 重新计算每支已赛球队的 xG 特征
 * 3. 加载实际 xG 数据（来自 compute_match_xg.py）
 * 4. 更新 worldcup.json 中的 xg_model 和 xg_actual 字段
 * 5. 更新完成比赛中的 match_xg 数据
 * 6. 保存更新摘要
 */

import fs from 'fs';
import path from 'path';
import { createRequire } from 'module';

const require = createRequire(import.meta.url);
const BASE_URL = new URL('..', import.meta.url);
const DB_PATH = new URL('db/worldcup.json', BASE_URL);
const DONGQIUDI_PATH = new URL('dongqiudi_full.json', BASE_URL);
const OUTPUT_PATH = new URL('data/xg/update_log.jsonl', BASE_URL);

// ── 加载数据 ──
function loadJSON(url) {
  try {
    return JSON.parse(fs.readFileSync(url, 'utf-8'));
  } catch (e) {
    console.error(`加载失败: ${url.pathname} - ${e.message}`);
    return null;
  }
}

// ── 球队 xG 特征计算（与 model/xg_model/build_team_xg.py 同步）──
function computeTeamXG(team, dims, nMatches, goalsScored, goalsConceded) {
  const dq = team?.dongqiudi || {};
  const raw = {};

  if (typeof dq === 'object') {
    for (const dim of dims) {
      if (dim in dq) {
        try {
          raw[dim] = parseFloat(dq[dim]);
        } catch {
          raw[dim] = 0;
        }
      }
    }
  }

  if (nMatches === 0) nMatches = 1;

  const pctDims = new Set(['传球成功率', '控球率']);
  const stats = {};
  for (const [dim, val] of Object.entries(raw)) {
    if (pctDims.has(dim)) {
      stats[dim] = val > 1 ? val / 100 : val;
    } else {
      stats[dim] = val / nMatches;
    }
  }

  const shotsPg = stats['射门'] || 10;
  const onTargetPg = stats['射正'] || 3;
  const keyPassesPg = stats['关键传球'] || 8;
  const bigChancesPg = stats['创造进球机会'] || 3;
  const cornersPg = stats['角球'] || 4;
  const crossesPg = stats['传中'] || 10;
  const savesPg = stats['扑救'] || 2;
  const possession = stats['传球成功率'] || 0.75;
  const shotAccuracy = onTargetPg / Math.max(shotsPg, 0.1);
  const rating = stats['评分'] || 6.5;

  // 进攻 xG
  const baseShotXG = 0.10;
  const accBonus = 1.0 + (shotAccuracy - 0.35) * 0.8;
  const kpRate = keyPassesPg / Math.max(shotsPg, 0.1);
  const kpBonus = 1.0 + (kpRate - 1.0) * 0.3;
  const bcRate = bigChancesPg / Math.max(shotsPg, 0.1);
  const bcBonus = 1.0 + bcRate * 0.5;
  const crossRate = crossesPg / Math.max(shotsPg, 0.1);
  const styleAdj = 1.0 - crossRate * 0.1;
  const offensiveXG = shotsPg * baseShotXG * accBonus * kpBonus * bcBonus * styleAdj;

  // 防守 xG
  const concededPg = goalsConceded / nMatches;
  const shotsAgainst = concededPg + savesPg;
  const saveRate = savesPg / Math.max(shotsAgainst, 0.1);
  const gkBonus = 1.0 - (saveRate - 0.30) * 0.3;
  const defensiveXG = (concededPg + savesPg * 0.25) * gkBonus;

  // 终结效率
  const goalsPg = goalsScored / nMatches;
  const conversion = goalsPg / Math.max(offensiveXG, 0.1);
  const conversionClamped = Math.min(2.0, Math.max(0.3, conversion));

  // 趋势
  const recent = team?.recentWins || 0;
  const draws = team?.recentDrawes || 0;
  const losses = team?.recentLosses || 0;
  const total = recent + draws + losses;
  const form = total > 0 ? (recent * 1.0 + draws * 0.5) / total : 0.5;
  let xgTrend;
  if (form > 0.7) xgTrend = [1.05, 1.10, 1.15];
  else if (form > 0.5) xgTrend = [0.98, 1.00, 1.05];
  else if (form > 0.3) xgTrend = [0.90, 0.95, 0.98];
  else xgTrend = [0.80, 0.85, 0.90];

  return {
    offensive_xg: Math.round(offensiveXG * 1000) / 1000,
    defensive_xg: Math.round(defensiveXG * 1000) / 1000,
    xg_diff: Math.round((offensiveXG - defensiveXG) * 1000) / 1000,
    shot_quality: Math.round(baseShotXG * accBonus * kpBonus * bcBonus * styleAdj * 10000) / 10000,
    shot_volume: Math.round(shotsPg * 10) / 10,
    shot_accuracy: Math.round(shotAccuracy * 1000) / 1000,
    conversion_ratio: Math.round(conversionClamped * 1000) / 1000,
    goals_per_game: Math.round(goalsPg * 1000) / 1000,
    big_chance_rate: Math.round(bcRate * 1000) / 1000,
    open_play_xg: Math.round(offensiveXG * 0.75 * 1000) / 1000,
    set_piece_xg: Math.round((offensiveXG * 0.15 + cornersPg * 0.015) * 1000) / 1000,
    header_xg: Math.round(offensiveXG * crossRate * 0.3 * 1000) / 1000,
    big_chance_xg: Math.round(bigChancesPg * 0.35 * 1000) / 1000,
    xg_trend: xgTrend,
    possession_factor: Math.round(possession * 1000) / 1000,
    rating_factor: Math.round((rating / 6.5) * 1000) / 1000,
    matches_played: nMatches,
    goals_scored: goalsScored,
    goals_conceded: goalsConceded,
    last_updated: new Date().toISOString(),
  };
}

// ── 加载实际 xG 数据（来自 compute_match_xg.py）──
function loadActualXG() {
  const actualTeamPath = new URL('data/xg/actual_team_xg.json', BASE_URL);
  const matchResultsPath = new URL('data/xg/match_xg_results.json', BASE_URL);

  let actualTeamXG = null;
  let matchXGResults = null;

  if (fs.existsSync(actualTeamPath)) {
    try {
      actualTeamXG = JSON.parse(fs.readFileSync(actualTeamPath, 'utf-8'));
    } catch (e) {
      console.warn(`[警告] 无法加载 actual_team_xg.json: ${e.message}`);
    }
  }

  if (fs.existsSync(matchResultsPath)) {
    try {
      matchXGResults = JSON.parse(fs.readFileSync(matchResultsPath, 'utf-8'));
    } catch (e) {
      console.warn(`[警告] 无法加载 match_xg_results.json: ${e.message}`);
    }
  }

  return { actualTeamXG, matchXGResults };
}

// ── 主函数 ──
function main() {
  console.log('='.repeat(60));
  console.log('xG 数据更新');
  console.log('='.repeat(60));

  // 加载数据
  const wc = loadJSON(DB_PATH);
  if (!wc) process.exit(1);

  const dongqiudi = loadJSON(DONGQIUDI_PATH); // 可选

  const dims = wc.meta?.teamDimensions || [];
  const teams = wc.teams || {};
  const completed = wc.completedMatches || [];

  console.log(`\n球队数: ${Object.keys(teams).length}`);
  console.log(`已完赛: ${completed.length}`);

  // 统计每支球队的比赛和进球
  const teamStats = {};
  for (const [name, team] of Object.entries(teams)) {
    teamStats[name] = { matches: 0, goalsFor: 0, goalsAgainst: 0 };
  }

  for (const m of completed) {
    const home = m.home;
    const away = m.away;
    if (!m.score) continue;
    const [hG, aG] = m.score.split('-').map(Number);
    if (isNaN(hG) || isNaN(aG)) continue;

    if (teamStats[home]) {
      teamStats[home].matches++;
      teamStats[home].goalsFor += hG;
      teamStats[home].goalsAgainst += aG;
    }
    if (teamStats[away]) {
      teamStats[away].matches++;
      teamStats[away].goalsFor += aG;
      teamStats[away].goalsAgainst += hG;
    }
  }

  // 更新每支球队的 xg_model
  const updateLog = {
    timestamp: new Date().toISOString(),
    totalTeams: Object.keys(teams).length,
    updatedTeams: 0,
    changes: [],
  };

  for (const [name, team] of Object.entries(teams)) {
    const ts = teamStats[name] || { matches: 0, goalsFor: 0, goalsAgainst: 0 };
    const oldXG = team.xg_model?.offensive_xg;

    const newXG = computeTeamXG(team, dims, ts.matches, ts.goalsFor, ts.goalsAgainst);
    team.xg_model = newXG;

    // 同时更新旧的 xgProxy（兼容）
    team.xgProxy = newXG.offensive_xg;
    team.xgaProxy = newXG.defensive_xg;

    if (oldXG !== undefined && Math.abs(oldXG - newXG.offensive_xg) > 0.01) {
      updateLog.changes.push({
        team: name,
        old_offensive_xg: oldXG,
        new_offensive_xg: newXG.offensive_xg,
        delta: Math.round((newXG.offensive_xg - oldXG) * 1000) / 1000,
      });
    }

    updateLog.updatedTeams++;
  }

  // 保存 worldcup.json
  fs.writeFileSync(DB_PATH, JSON.stringify(wc, null, 2), 'utf-8');
  console.log(`\n已更新: ${DB_PATH.pathname}`);

  // ── 合并实际 xG 数据（如果存在）──
  const { actualTeamXG, matchXGResults } = loadActualXG();

  if (actualTeamXG) {
    let actualXGCount = 0;
    for (const [name, team] of Object.entries(teams)) {
      if (actualTeamXG[name]) {
        team.xg_actual = actualTeamXG[name];
        actualXGCount++;
      }
    }
    console.log(`已合并实际 xG 数据: ${actualXGCount} 支球队`);
    updateLog.actualXGTeams = actualXGCount;
  }

  if (matchXGResults) {
    // 建立 match_id → match_xg 的映射
    const xgMap = {};
    for (const r of matchXGResults) {
      xgMap[r.match_id] = r;
    }

    let matchXGCount = 0;
    for (const m of completed) {
      const mid = m.id || `${m.home}-${m.away}`;
      if (xgMap[mid]) {
        m.match_xg = {
          home_xg: xgMap[mid].home_xg,
          away_xg: xgMap[mid].away_xg,
          home_shots: xgMap[mid].home_shots,
          away_shots: xgMap[mid].away_shots,
          home_sot: xgMap[mid].home_sot,
          away_sot: xgMap[mid].away_sot,
          shots: xgMap[mid].shots,
        };
        matchXGCount++;
      }
    }
    console.log(`已添加比赛 xG 数据: ${matchXGCount} 场`);
    updateLog.matchXGAdded = matchXGCount;
  }

  // 重新保存（包含实际 xG 数据）
  fs.writeFileSync(DB_PATH, JSON.stringify(wc, null, 2), 'utf-8');

  // 保存更新日志
  const logDir = new URL('data/xg/', BASE_URL);
  if (!fs.existsSync(logDir)) fs.mkdirSync(logDir, { recursive: true });
  const logPath = new URL('data/xg/update_log.jsonl', BASE_URL);
  fs.appendFileSync(logPath, JSON.stringify(updateLog) + '\n', 'utf-8');

  // 打印摘要
  console.log(`\n更新摘要:`);
  console.log(`  更新球队: ${updateLog.updatedTeams}`);
  console.log(`  有变化的: ${updateLog.changes.length}`);

  if (updateLog.changes.length > 0) {
    console.log(`\n  变化详情:`);
    for (const c of updateLog.changes.slice(0, 10)) {
      console.log(`    ${c.team}: ${c.old_offensive_xg} -> ${c.new_offensive_xg} (${c.delta > 0 ? '+' : ''}${c.delta})`);
    }
    if (updateLog.changes.length > 10) {
      console.log(`    ... 共 ${updateLog.changes.length} 支球队有变化`);
    }
  }

  // 打印美加墨东道主
  console.log(`\n美加墨东道主 xG:`);
  for (const host of ['美国', '墨西哥', '加拿大']) {
    const xg = teams[host]?.xg_model;
    if (xg) {
      console.log(`  ${host}: 进攻=${xg.offensive_xg} 防守=${xg.defensive_xg} 差=${xg.xg_diff} (已赛${xg.matches_played}场)`);
    }
  }

  console.log(`\n${'='.repeat(60)}`);
  console.log('更新完成!');
  console.log('='.repeat(60));
}

main();
