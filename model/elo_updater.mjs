/**
 * 实时Elo更新 + 战力数据反哺系统
 * 
 * 核心功能：
 * 1. 每场比赛后自动更新球队Elo评分
 * 2. 基于比赛结果动态调整 attackBase / defenseBase
 * 3. 大胜过热限制（防止单场极端比分扭曲全局）
 * 4. 淘汰赛阶段K值放大
 * 5. 战意/轮换因子自动推断
 */

import * as fs from 'fs';
import * as path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const DB_PATH = path.join(__dirname, '..', 'db', 'worldcup.json');

// ============================================================
// 1. Elo 实时更新
// ============================================================

/** 将FIFA排名转为Elo评分 */
export function rankToElo(rank) {
  if (!rank || rank < 1 || rank > 50) return 1500;
  if (rank <= 10) return Math.round(1750 + (10 - rank) * (10 / 9));
  if (rank <= 30) return Math.round(1550 + (30 - rank) * (100 / 20));
  return Math.round(1400 + (50 - rank) * (50 / 20));
}

/** Elo期望得分 */
function eloExpected(homeElo, awayElo) {
  return 1 / (1 + Math.pow(10, (awayElo - homeElo) / 400));
}

/**
 * 更新Elo评分
 * @param {number} eloA - 主队Elo
 * @param {number} eloB - 客队Elo
 * @param {number} goalsA - 主队进球
 * @param {number} goalsB - 客队进球
 * @param {string} stage - 比赛阶段
 * @returns {{ home: number, away: number }}
 */
export function updateElo(eloA, eloB, goalsA, goalsB, stage = 'group_stage') {
  const stageK = {
    'group_stage': 20,
    'round_of_16': 30,
    '16强': 30,
    '1/16': 30,
    'round_of_32': 30,
    'quarter_final': 35,
    '1/4': 35,
    '半决赛': 40,
    'semi_final': 40,
    '决赛': 50,
    'final': 50,
    '三四名': 30,
  };
  
  let K = stageK[stage] || 20;
  
  // 淘汰赛K值放大
  if (stage && typeof stage === 'string' && (stage.includes('KO') || stage.includes('强') || stage.includes('决赛') || stage.includes('半决赛'))) {
    K = Math.max(K, 30);
  }
  
  // 点球大战判负也算输球（90分钟平局）
  let resultA;
  if (goalsA > goalsB) resultA = 1;
  else if (goalsA === goalsB) resultA = 0.5;
  else resultA = 0;
  
  // 大胜过热限制：净胜球最多算4球的影响
  const cappedGD = Math.min(Math.abs(goalsA - goalsB), 4);
  const gdFactor = Math.min(Math.log(cappedGD + 1) / Math.LN2, 1.5);
  
  // 大胜额外奖励（不超过50%）
  const bonusScore = resultA === 1 ? gdFactor * 0.3 : 0;
  const scoreA = resultA + bonusScore;
  
  const expectedA = eloExpected(eloA, eloB);
  const homeNew = Math.round(eloA + K * (scoreA - expectedA));
  const awayNew = Math.round(eloB + K * ((1 - scoreA) - (1 - expectedA)));
  
  return { home: homeNew, away: awayNew };
}

// ============================================================
// 2. 战力参数反哺（attackBase / defenseBase 动态更新）
// ============================================================

/**
 * 基于比赛结果更新球队战力参数
 * 使用指数移动平均（EMA），近期比赛权重更高
 * 
 * @param {Object} teams - TEAM_STRENGTHS 对象
 * @param {Object} completedMatches - 已完成比赛列表
 */
export function updateTeamStrengths(teams, completedMatches) {
  if (!teams || !completedMatches) return teams;
  
  // 按日期排序
  const sorted = [...completedMatches].filter(m => m.score).sort((a, b) => a.date.localeCompare(b.date));
  
  // 对每支球队维护一个近期表现记录
  const teamForm = {};
  
  for (const match of sorted) {
    const [hG, aG] = match.score.split('-').map(Number);
    if (isNaN(hG) || isNaN(aG)) continue;
    
    const { home, away } = match;
    if (!home || !away) continue;
    
    // 初始化球队记录
    if (!teamForm[home]) teamForm[home] = { attacks: [], defenses: [], games: 0 };
    if (!teamForm[away]) teamForm[away] = { attacks: [], defenses: [], games: 0 };
    
    // 主队进攻表现（对手防守漏洞 = 主队进球）
    teamForm[home].attacks.push(hG);
    // 主队防守表现（对手进球 = 主队失球）
    teamForm[home].defenses.push(aG);
    // 客队进攻表现
    teamForm[away].attacks.push(aG);
    // 客队防守表现
    teamForm[away].defenses.push(hG);
    
    teamForm[home].games++;
    teamForm[away].games++;
  }
  
  // 计算每支球队的近期表现并更新参数
  for (const [teamName, form] of Object.entries(teamForm)) {
    if (!teams[teamName]) continue;
    
    // 取最近5场（或全部）
    const recentAttacks = form.attacks.slice(-5);
    const recentDefenses = form.defenses.slice(-5);
    
    if (recentAttacks.length < 1) continue;
    
    const avgAttack = recentAttacks.reduce((a, b) => a + b, 0) / recentAttacks.length;
    const avgDefense = recentDefenses.reduce((a, b) => a + b, 0) / recentDefenses.length;
    
    // EMA 混合：70% 原有参数 + 30% 近期表现
    // 将场均进球映射回 attackBase 尺度
    const originalAttack = teams[teamName].attackBase || 1.0;
    const originalDefense = teams[teamName].defenseBase || 1.0;
    
    // 进球 -> attackBase: 场均1.5球 ≈ attackBase 1.2
    // 失球 -> defenseBase: 场均0.8球 ≈ defenseBase 0.85
    const recentAttackBase = 0.8 + avgAttack * 0.4;
    const recentDefenseBase = 1.0 - avgDefense * 0.15;
    
    teams[teamName].attackBase = Math.round(
      (originalAttack * 0.7 + recentAttackBase * 0.3) * 100
    ) / 100;
    
    teams[teamName].defenseBase = Math.round(
      Math.max(0.5, Math.min(1.6, originalDefense * 0.7 + recentDefenseBase * 0.3)) * 100
    ) / 100;
    
    // 更新Elo评分
    if (form.games >= 1) {
      const initialElo = rankToElo(teams[teamName].rank || 50);
      const recentElo = initialElo + (avgAttack - avgDefense) * 50;
      teams[teamName].eloRating = Math.round(recentElo);
    }
  }
  
  return teams;
}

// ============================================================
// 3. 从 worldcup.json 加载并更新
// ============================================================

/**
 * 从 worldcup.json 加载数据，执行Elo更新和战力反哺
 * @returns {{ teams, completedMatches, eloUpdates }}
 */
export function loadAndUpdateTeams() {
  try {
    const raw = fs.readFileSync(DB_PATH, 'utf8');
    const db = JSON.parse(raw);
    
    // 注意: worldcup.json 的 teams 可能为空，需要从 database.mjs 加载
    // 这里只从 worldcup.json 读取 completedMatches
    const completedMatches = db.completedMatches || [];
    
    // 需要从 database.mjs 加载 teams 数据
    // 这部分在 fullUpdate 中通过 integrated_engine 处理
    const teams = db.teams || {};
    
    // 执行Elo更新（仅当teams存在时）
    const eloHistory = [];
    if (Object.keys(teams).length > 0) {
      for (const match of completedMatches) {
        if (!match.score) continue;
        const [hG, aG] = match.score.split('-').map(Number);
        if (isNaN(hG) || isNaN(aG)) continue;
        
        const home = match.home;
        const away = match.away;
        if (!teams[home] || !teams[away]) continue;
        
        const eloH = teams[home].eloRating || rankToElo(teams[home].rank || 50);
        const eloA = teams[away].eloRating || rankToElo(teams[away].rank || 50);
        
        const updated = updateElo(eloH, eloA, hG, aG, match.round || match.group);
        
        if (teams[home]) teams[home].eloRating = updated.home;
        if (teams[away]) teams[away].eloRating = updated.away;
        
        eloHistory.push({
          match: `${home} vs ${away}`,
          score: `${hG}-${aG}`,
          eloBefore: { home: eloH, away: eloA },
          eloAfter: updated,
        });
      }
    }
    
    // 战力反哺
    if (Object.keys(teams).length > 0) {
      updateTeamStrengths(teams, completedMatches);
    }
    
    return { teams, completedMatches, eloHistory };
  } catch (err) {
    console.error('❌ 加载/更新失败:', err.message);
    return { teams: {}, completedMatches: [], eloHistory: [] };
  }
}

// ============================================================
// 4. 持久化更新结果
// ============================================================

/**
 * 将更新后的数据保存回 worldcup.json
 */
export function saveUpdatedTeams(teams) {
  try {
    const raw = fs.readFileSync(DB_PATH, 'utf8');
    const db = JSON.parse(raw);
    db.teams = teams;
    db.meta.updatedAt = new Date().toISOString();
    db.meta.dataVersion = (db.meta.dataVersion || 0) + 1;
    fs.writeFileSync(DB_PATH, JSON.stringify(db, null, 2), 'utf8');
    console.log('✅ 球队数据已更新至 worldcup.json');
  } catch (err) {
    console.error('❌ 保存失败:', err.message);
  }
}

// ============================================================
// 5. 战意/轮换因子自动推断
// ============================================================

/**
 * 基于小组赛积分形势推断各队战意
 * @param {Object} teams - 球队数据
 * @param {Array} completedMatches - 已完成比赛
 * @param {Array} upcomingMatches - 未完成比赛
 * @returns {Object} 战意映射 { teamName: urgencyLevel }
 *   0=已淘汰, 1=渺茫, 2=需赢+看别人, 3=必须赢, 4=打平就出线, 5=已出线
 */
export function inferMotivation(teams, completedMatches, upcomingMatches, groups) {
  // 计算当前积分榜
  const standings = {};
  for (const m of completedMatches) {
    if (!m.score || m.group === 'KO') continue;
    const [hG, aG] = m.score.split('-').map(Number);
    if (isNaN(hG) || isNaN(aG)) continue;
    
    for (const t of [m.home, m.away]) {
      if (!standings[t]) {
        standings[t] = { team: t, group: m.group, played: 0, points: 0, won: 0, drawn: 0, lost: 0, gf: 0, ga: 0 };
      }
      standings[t].played++;
      standings[t].gf += (t === m.home ? hG : aG);
      standings[t].ga += (t === m.home ? aG : hG);
      if (hG > aG) { standings[t].points += 3; standings[t].won++; }
      else if (hG === aG) { standings[t].points += 1; standings[t].drawn++; }
      else { standings[t].lost++; }
    }
  }
  
  // 按小组排序
  const groupTeams = {};
  for (const [g, teamList] of Object.entries(groups || {})) {
    groupTeams[g] = teamList.map(t => standings[t] || { team: t, points: 0, played: 0, gf: 0, ga: 0 }).sort(
      (a, b) => b.points - a.points || (b.gf - b.ga) - (a.gf - a.ga)
    );
  }
  
  // 推断战意（针对小组赛最后1-2轮）
  const motivation = {};
  const maxRound = Math.max(...completedMatches.map(m => m.round || 0));
  
  for (const [g, teamsInGroup] of Object.entries(groupTeams)) {
    const remaining = upcomingMatches.filter(m => m.group === g && !m.score).length;
    
    for (const t of teamsInGroup) {
      const idx = teamsInGroup.indexOf(t);
      const gd = t.gf - t.ga;
      const pts = t.points;
      const maxPossiblePts = pts + (3 - t.played) * 3;
      
      // 理论最大积分
      if (idx === 0 && pts >= 5 && t.played >= 2) {
        // 小组第一且已有5分以上，大概率已出线
        motivation[t.team] = 5; // 已出线
      } else if (idx === teamsInGroup.length - 1 && maxPossiblePts <= 1) {
        motivation[t.team] = 0; // 已淘汰
      } else if (idx === 0 && remaining <= 1) {
        motivation[t.team] = 4; // 打平可能就出线
      } else if (idx >= 2 && maxPossiblePts <= 2) {
        motivation[t.team] = 1; // 渺茫
      } else if (idx <= 1 && remaining === 1 && pts < 4) {
        motivation[t.team] = 3; // 必须赢
      } else {
        motivation[t.team] = 2; // 需赢 + 看别人脸色
      }
    }
  }
  
  return motivation;
}

// ============================================================
// 6. 一键更新入口
// ============================================================

export function fullUpdate() {
  console.log('🔄 开始更新球队数据...\n');
  
  const result = loadAndUpdateTeams();
  
  console.log(`  Elo 更新: ${result.eloHistory.length} 场比赛完成\n`);
  
  // 打印前10支球队的Elo变化
  console.log('  前10强 Elo 排名:');
  const sorted = Object.entries(result.teams)
    .map(([name, data]) => ({ name, elo: data.eloRating || rankToElo(data.rank || 50), attack: data.attackBase, defense: data.defenseBase }))
    .sort((a, b) => b.elo - a.elo)
    .slice(0, 10);
  
  for (const t of sorted) {
    console.log(`    ${t.name.padEnd(12)} Elo: ${t.elo.toString().padStart(5)}  攻击: ${t.attack.toFixed(2)}  防守: ${t.defense.toFixed(2)}`);
  }
  
  // 保存
  saveUpdatedTeams(result.teams);
  
  console.log('\n✅ 更新完成！\n');
}

// CLI 入口
if (import.meta.url === `file://${process.argv[1]}`) {
  fullUpdate();
}
