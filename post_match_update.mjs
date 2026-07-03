#!/usr/bin/env node

/**
 * ⚽ 赛后数据更新器 — 自动更新球队战力参数
 * 
 * 功能:
 * 1. 每场比赛后自动更新 Elo 评分
 * 2. 用滑动窗口更新 attackBase / defenseBase
 * 3. 标记已确定淘汰/出线的球队 (战意修正)
 * 4. 输出更新报告
 * 
 * 用法: node post_match_update.mjs
 */

import * as fs from 'fs';
import * as path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const DB_DIR = path.join(__dirname, 'db');

// ============================================================
// 加载数据
// ============================================================

const dbModule = await import('./database.mjs');
const TEAM_STRENGTHS = dbModule.TEAM_STRENGTHS;
const COMPLETED_MATCHES = dbModule.COMPLETED_MATCHES;
const GROUPS = dbModule.GROUPS;
const TEAM_GROUP = dbModule.TEAM_GROUP;
const computeStandings = dbModule.computeStandings;

const worldcupData = JSON.parse(fs.readFileSync(path.join(DB_DIR, 'worldcup.json'), 'utf8'));

// ============================================================
// 1. Elo 评分系统
// ============================================================

const ELO_INITIAL_RATING = 1500;
const ELO_HOME_ADVANTAGE = 60;
const ELO_K_GROUP = 20;
const ELO_K_KO = 30;

function rankToElo(rank) {
  return Math.round(2100 - (rank - 1) * (900 / 47));
}

function eloExpected(ratingA, ratingB) {
  return 1 / (1 + Math.pow(10, (ratingB - ratingA) / 400));
}

function updateElo(eloA, eloB, goalA, goalB, K = 20) {
  const expectedA = eloExpected(eloA, eloB);
  const gd = goalA - goalB;
  let scoreA;
  if (gd > 0) {
    const cappedGd = Math.min(Math.abs(gd), 5);
    const gdFactor = Math.min(Math.log(cappedGd + 1) / Math.LN2, 1.8);
    scoreA = 1 + gdFactor * 0.3;
  } else if (gd === 0) {
    scoreA = 0.5;
  } else {
    scoreA = 0;
  }
  return {
    home: Math.round(eloA + K * (scoreA - expectedA)),
    away: Math.round(eloB + K * ((1 - scoreA) - (1 - expectedA)))
  };
}

// ============================================================
// 2. 计算小组赛出线形势
// ============================================================

function computeGroupStandings() {
  const standings = computeStandings();
  const groupResults = {};
  
  for (const [g, teams] of Object.entries(GROUPS)) {
    const teamStats = teams.map(t => {
      const s = standings[t];
      return { team: t, ...s, group: g };
    }).sort((a, b) => b.p - a.p || b.gd - a.gd || b.gf - a.gf);
    
    // 确定出线/淘汰状态
    const advanced = [];
    const eliminated = [];
    
    if (teamStats.length >= 2) {
      // 前2名出线
      advanced.push(teamStats[0].team, teamStats[1].team);
    }
    if (teamStats.length >= 3) {
      // 第3名看积分
      const thirdPoints = teamStats[2].p;
      const fourthPoints = teamStats[3].p;
      if (thirdPoints > fourthPoints) {
        advanced.push(teamStats[2].team);
      } else if (thirdPoints < fourthPoints) {
        eliminated.push(teamStats[3].team);
      }
      // 同分时需要比较净胜球等, 简化处理
    }
    if (teamStats.length >= 4) {
      eliminated.push(teamStats[3].team);
    }
    
    groupResults[g] = {
      standings: teamStats,
      advanced: advanced,
      eliminated: eliminated,
    };
  }
  
  return groupResults;
}

// ============================================================
// 3. 赛后更新
// ============================================================

function postMatchUpdate() {
  console.log('╔═══════════════════════════════════════════════════════════╗');
  console.log('║  🔧 赛后数据更新器 v2.0                                  ║');
  console.log('╚═══════════════════════════════════════════════════════════╝');
  console.log('');
  
  // --- 3.1 初始化 Elo 评分 ---
  console.log('📊 初始化 Elo 评分...');
  let totalUpdates = 0;
  let totalEloChanges = 0;
  
  for (const [teamName, team] of Object.entries(TEAM_STRENGTHS)) {
    if (!team.eloRating) {
      team.eloRating = rankToElo(team.rank || 50);
      team.eloHistory = [];
    }
  }
  
  // --- 3.2 按比赛顺序更新 Elo ---
  console.log('📊 按比赛顺序更新 Elo...');
  const sortedMatches = [...COMPLETED_MATCHES].sort((a, b) => new Date(a.date) - new Date(b.date));
  
  for (const match of sortedMatches) {
    if (!match.score || !match.score.includes('-')) continue;
    const [hG, aG] = match.score.split('-').map(Number);
    if (isNaN(hG) || isNaN(aG)) continue;
    
    const home = match.home;
    const away = match.away;
    
    const homeElo = TEAM_STRENGTHS[home]?.eloRating || rankToElo(50);
    const awayElo = TEAM_STRENGTHS[away]?.eloRating || rankToElo(50);
    
    const K = match.round === 'KO' || match.round === '1/16' || match.round === '1/8' || match.round === '1/4' || match.round === '半决赛' || match.round === '决赛' || match.round === '三四名' ? ELO_K_KO : ELO_K_GROUP;
    
    const result = updateElo(homeElo + ELO_HOME_ADVANTAGE, awayElo, hG, aG, K);
    
    if (TEAM_STRENGTHS[home]) {
      TEAM_STRENGTHS[home].eloRating = result.home - ELO_HOME_ADVANTAGE;
      TEAM_STRENGTHS[home].eloHistory.push({
        date: match.date,
        opponent: away,
        goalFor: hG,
        goalAgainst: aG,
        eloBefore: homeElo,
        eloAfter: result.home - ELO_HOME_ADVANTAGE,
      });
    }
    if (TEAM_STRENGTHS[away]) {
      TEAM_STRENGTHS[away].eloRating = result.away;
      TEAM_STRENGTHS[away].eloHistory.push({
        date: match.date,
        opponent: home,
        goalFor: aG,
        goalAgainst: hG,
        eloBefore: awayElo,
        eloAfter: result.away,
      });
    }
    
    totalEloChanges += Math.abs(result.home - homeElo) + Math.abs(result.away - awayElo);
    totalUpdates++;
  }
  
  console.log(`   更新了 ${totalUpdates} 场比赛的 Elo`);
  console.log(`   总 Elo 变化: ${totalEloChanges.toFixed(0)} 分`);
  
  // --- 3.3 用滑动窗口更新 attackBase / defenseBase ---
  console.log('\n📊 用滑动窗口更新 attackBase / defenseBase...');
  
  // 按球队聚合比赛结果
  const teamMatches = {};
  for (const match of sortedMatches) {
    if (!match.score || !match.score.includes('-')) continue;
    const [hG, aG] = match.score.split('-').map(Number);
    if (isNaN(hG) || isNaN(aG)) continue;
    
    if (!teamMatches[match.home]) teamMatches[match.home] = [];
    if (!teamMatches[match.away]) teamMatches[match.away] = [];
    
    teamMatches[match.home].push({
      date: match.date,
      opponent: match.away,
      isHome: true,
      gf: hG, ga: aG,
    });
    teamMatches[match.away].push({
      date: match.date,
      opponent: match.home,
      isHome: false,
      gf: aG, ga: hG,
    });
  }
  
  // 用最近 5 场比赛更新 attackBase / defenseBase
  const WINDOW = 5;
  for (const [teamName, matches] of Object.entries(teamMatches)) {
    if (!TEAM_STRENGTHS[teamName]) continue;
    
    const recent = matches.slice(-WINDOW);
    if (recent.length < 2) continue;
    
    const avgGF = recent.reduce((s, m) => s + m.gf, 0) / recent.length;
    const avgGA = recent.reduce((s, m) => s + m.ga, 0) / recent.length;
    
    // 原始 attackBase 基于历史数据, 现在用近期表现加权更新
    const oldAttack = TEAM_STRENGTHS[teamName].attackBase;
    const oldDefense = TEAM_STRENGTHS[teamName].defenseBase;
    
    // 新 attackBase = 0.3 * 近期场均进球 + 0.7 * 原有值
    // 新 defenseBase = 0.3 * 近期场均失球 + 0.7 * 原有值
    const newAttack = oldAttack * 0.7 + avgGF * 0.3;
    const newDefense = oldDefense * 0.7 + avgGA * 0.3;
    
    const attackChange = Math.abs(newAttack - oldAttack);
    const defenseChange = Math.abs(newDefense - oldDefense);
    
    if (attackChange > 0.01 || defenseChange > 0.01) {
      TEAM_STRENGTHS[teamName].attackBase = Math.round(newAttack * 100) / 100;
      TEAM_STRENGTHS[teamName].defenseBase = Math.round(newDefense * 100) / 100;
      totalUpdates++;
    }
  }
  
  console.log(`   更新了 ${totalUpdates} 支球队的参数`);
  
  // --- 3.4 输出 Top 10 变化最大的球队 ---
  console.log('\n📊 变化最大的球队 (Elo):');
  const eloChanges = Object.entries(TEAM_STRENGTHS)
    .filter(([, t]) => t.eloHistory && t.eloHistory.length > 0)
    .map(([name, t]) => ({
      name,
      elo: t.eloRating,
      rank: t.rank,
      change: t.eloHistory[t.eloHistory.length - 1].eloAfter - (t.eloHistory[t.eloHistory.length - 1].eloBefore),
      games: t.eloHistory.length,
    }))
    .sort((a, b) => Math.abs(b.change) - Math.abs(a.change))
    .slice(0, 10);
  
  for (const ec of eloChanges) {
    const arrow = ec.change > 0 ? '↑' : ec.change < 0 ? '↓' : '→';
    console.log(`   ${arrow} ${ec.name}: Elo ${ec.elo.toFixed(0)} (${arrow} ${Math.abs(ec.change).toFixed(0)}, ${ec.games}场)`);
  }
  
  // --- 3.5 小组赛出线形势 ---
  console.log('\n📊 小组赛出线形势:');
  const groupResults = computeGroupStandings();
  for (const [g, result] of Object.entries(groupResults)) {
    const qualified = result.advanced.length > 0 ? result.advanced.join(', ') : '-';
    const eliminated_str = result.eliminated.length > 0 ? result.eliminated.join(', ') : '-';
    console.log(`   Group ${g}: 出线[${qualified}] 淘汰[${eliminated_str}]`);
  }
  
  // --- 3.6 保存更新后的数据 ---
  console.log('\n💾 保存更新数据...');
  
  // 保存 TEAM_STRENGTHS (带 Elo)
  const exportTeams = {};
  for (const [name, t] of Object.entries(TEAM_STRENGTHS)) {
    exportTeams[name] = {
      attackBase: t.attackBase,
      defenseBase: t.defenseBase,
      style: t.style,
      styleFactor: t.styleFactor,
      rank: t.rank,
      eloRating: Math.round(t.eloRating),
    };
  }
  
  // 保存为 JSON 供后续使用
  fs.writeFileSync(
    path.join(__dirname, 'data_local', 'updated_teams.json'),
    JSON.stringify(exportTeams, null, 2),
    'utf8'
  );
  
  // 保存 Elo 历史
  const eloHistory = {};
  for (const [name, t] of Object.entries(TEAM_STRENGTHS)) {
    if (t.eloHistory) {
      eloHistory[name] = t.eloHistory;
    }
  }
  fs.writeFileSync(
    path.join(__dirname, 'data_local', 'elo_history.json'),
    JSON.stringify(eloHistory, null, 2),
    'utf8'
  );
  
  console.log('✅ 数据更新完成!');
  console.log('');
}

postMatchUpdate();
