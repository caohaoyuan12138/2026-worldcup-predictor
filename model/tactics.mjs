/**
 * ⚽ 战术匹配分析引擎
 * 
 * 基于 1494 场历史数据，分析：
 * - 战术风格匹配 (防反vs传控、强攻vs大巴)
 * - 主客场表现差异
 * - 大赛心理韧性
 */

import * as fs from 'fs';
import * as path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const TACTICS_PATH = path.join(__dirname, '..', 'db', 'tactics.json');

// 缓存
let _tacticsCache = null;

export function loadTactics() {
  if (_tacticsCache) return _tacticsCache;
  try {
    if (fs.existsSync(TACTICS_PATH)) {
      _tacticsCache = JSON.parse(fs.readFileSync(TACTICS_PATH, 'utf8'));
      return _tacticsCache;
    }
  } catch (e) {
    console.error('加载战术数据失败:', e.message);
  }
  return {};
}

export function reloadTactics() {
  _tacticsCache = null;
  return loadTactics();
}

/**
 * 1️⃣ 战术风格匹配度
 * 
 * 两队风格对撞决定比赛走向：
 * - 防反 vs 强攻：防反方如果顶住，反击致命
 * - 传控 vs 大巴：传控方控球率高但可能久攻不下
 * - 小球稳健 vs 大开大合：进球数预期不同
 */
export function styleMatch(home, away, tactics) {
  const h = tactics[home];
  const a = tactics[away];
  if (!h || !a) return { factor: 1.0, description: '数据不足' };
  
  const hStyle = h.style || '平衡';
  const aStyle = a.style || '平衡';
  
  // 风格对抗矩阵: [攻击修正, 防守修正]
  const matrix = {
    '强攻稳固': { '防守反击': [0.85, 1.15], '小球稳健': [0.90, 1.10], '平衡': [1.05, 1.00], '攻势足球': [1.10, 0.90], '大开大合': [1.15, 0.85] },
    '攻势足球': { '防守反击': [0.80, 1.20], '小球稳健': [0.85, 1.15], '平衡': [1.05, 0.95], '强攻稳固': [0.90, 1.10], '大开大合': [1.10, 0.90] },
    '防守反击': { '强攻稳固': [1.20, 0.80], '攻势足球': [1.25, 0.75], '平衡': [1.10, 0.90], '小球稳健': [0.95, 1.05], '大开大合': [0.90, 1.10] },
    '小球稳健': { '攻势足球': [1.15, 0.85], '大开大合': [1.10, 0.90], '平衡': [1.05, 0.95], '强攻稳固': [0.90, 1.10], '防守反击': [0.95, 1.05] },
    '大开大合': { '防守反击': [0.85, 1.15], '小球稳健': [0.90, 1.10], '平衡': [1.05, 0.95], '强攻稳固': [0.90, 1.10], '攻势足球': [1.10, 0.90] },
  };
  
  // 默认
  let attackAdj = 1.0, defenseAdj = 1.0;
  
  // 主队攻击 vs 客队防守
  if (matrix[hStyle] && matrix[hStyle][aStyle]) {
    const [atk, def] = matrix[hStyle][aStyle];
    attackAdj = atk;
    defenseAdj = def;
  }
  
  // 战术描述
  let desc = '';
  const atkDir = attackAdj > 1.05 ? '↑' : attackAdj < 0.95 ? '↓' : '→';
  const defDir = defenseAdj > 1.05 ? '↑' : defenseAdj < 0.95 ? '↓' : '→';
  desc = `${hStyle} vs ${aStyle} (攻${atkDir}防${defDir})`;
  
  return {
    attackFactor: attackAdj,
    defenseFactor: defenseAdj,
    netFactor: attackAdj / defenseAdj,
    description: desc
  };
}

/**
 * 2️⃣ 主客场表现修正
 * 
 * 使用实际主客场数据，而非固定系数
 */
export function homeAwayFactor(home, away, tactics) {
  const h = tactics[home];
  const a = tactics[away];
  if (!h || !a) return { homeFactor: 1.08, awayFactor: 1.0 };
  
  // 主队主场优势 vs 客队客场表现
  const homeWinRate = h.homeWinRate || 50;
  const awayWinRate = a.awayWinRate || 35;
  const awayGames = a.awayGames || 0;
  
  // 主场优势系数: 基于实际主场胜率
  // 基准50% → 系数1.08, 80% → 1.15, 30% → 0.95
  const homeFactor = 0.90 + (homeWinRate / 100) * 0.30;
  
  // 客队客场表现: 基准35% → 1.0, 60% → 1.10, 20% → 0.90
  const awayFactor = 0.80 + (awayWinRate / 100) * 0.50;
  
  // 如果客队客场样本太少(<5场), 用默认值
  const finalAwayFactor = awayGames < 5 ? 1.0 : awayFactor;
  
  return {
    homeFactor: Math.round(homeFactor * 100) / 100,
    awayFactor: Math.round(finalAwayFactor * 100) / 100,
    homeWinRate,
    awayWinRate,
    homeGames: h.homeGames,
    awayGames
  };
}

/**
 * 3️⃣ 大赛心理因素
 * 
 * 评估两队在大赛中的心理韧性：
 * - 大赛胜率 (世界杯/美洲杯/欧洲杯等)
 * - 落后时的表现 (逆转能力)
 * - 零封率 (关键比赛不丢球)
 */
export function bigGameFactor(home, away, tactics) {
  const h = tactics[home];
  const a = tactics[away];
  if (!h || !a) return { homeFactor: 1.0, awayFactor: 1.0 };
  
  // 大赛胜率: 基准40% → 1.0
  const hTournRate = h.tournamentWinRate || 40;
  const aTournRate = a.tournamentWinRate || 40;
  const hTournGames = h.tournamentGames || 0;
  const aTournGames = a.tournamentGames || 0;
  
  // 大赛心理韧性: 基于胜率和样本量
  let hMental = 0.90 + (hTournRate / 100) * 0.30;
  let aMental = 0.90 + (aTournRate / 100) * 0.30;
  
  // 样本量修正: 大赛经验越丰富, 心理韧性越可靠
  if (hTournGames < 5) hMental = Math.min(hMental, 1.05);  // 样本少, 谨慎
  if (aTournGames < 5) aMental = Math.min(aMental, 1.05);
  
  // 防守硬度 (零封率) 修正大赛信心
  const hCS = h.cleanSheetRate || 30;
  const aCS = a.cleanSheetRate || 30;
  hMental *= (0.85 + hCS / 200);
  aMental *= (0.85 + aCS / 200);
  
  // 近期状态 (最近10场胜率) 增强信心
  const hForm = h.recentWins || 5;
  const aForm = a.recentWins || 5;
  hMental *= (0.90 + hForm * 0.02);
  aMental *= (0.90 + aForm * 0.02);
  
  return {
    homeFactor: Math.round(hMental * 100) / 100,
    awayFactor: Math.round(aMental * 100) / 100,
    homeTournamentWinRate: hTournRate,
    awayTournamentWinRate: aTournRate,
    homeRecentForm: h.recentForm || '0-0-0',
    awayRecentForm: a.recentForm || '0-0-0',
  };
}

/**
 * 4️⃣ 比赛进球倾向
 * 
 * 基于两队历史比赛的进球分布，预测本场进球数倾向
 */
export function goalExpectationFactor(home, away, tactics) {
  const h = tactics[home];
  const a = tactics[away];
  if (!h || !a) return { lowScoreFactor: 1.0, highScoreFactor: 1.0 };
  
  // 两队低比分率取均值
  const hLow = h.lowScoringRate || 35;
  const aLow = a.lowScoringRate || 35;
  const avgLow = (hLow + aLow) / 2;
  
  // 两队进球失球综合
  const hGF = h.avgGF || 1.5;
  const hGA = h.avgGA || 1.0;
  const aGF = a.avgGF || 1.5;
  const aGA = a.avgGA || 1.0;
  
  // 预期总进球 = 主队攻 × 客队守 + 客队攻 × 主队守
  const expectedTotal = (hGF * (aGA / 1.2)) + (aGF * (hGA / 1.2));
  
  let totalFactor = 1.0;
  if (expectedTotal < 2.0) totalFactor = 0.90;  // 小球预期
  else if (expectedTotal > 3.5) totalFactor = 1.10;  // 大球预期
  else if (expectedTotal > 2.8) totalFactor = 1.05;
  
  return {
    totalFactor,
    expectedTotal: +expectedTotal.toFixed(2),
    avgLowScoreRate: +avgLow.toFixed(1),
    homeAvgGF: hGF, homeAvgGA: hGA,
    awayAvgGF: aGF, awayAvgGA: aGA,
  };
}

/**
 * 5️⃣ 完整战术分析摘要
 */
export function fullTacticalAnalysis(home, away) {
  const tactics = loadTactics();
  
  const style = styleMatch(home, away, tactics);
  const ha = homeAwayFactor(home, away, tactics);
  const bg = bigGameFactor(home, away, tactics);
  const goal = goalExpectationFactor(home, away, tactics);
  
  return {
    style,
    homeAway: ha,
    bigGame: bg,
    goalExpectation: goal,
  };
}

/**
 * 6️⃣ 战术修正 λ
 * 
 * 将所有战术因素合并为对 λ 的修正值
 */
export function tacticalLambdaAdjust(home, away, isHome, tactics) {
  if (!tactics) tactics = loadTactics();
  
  const style = styleMatch(home, away, tactics);
  const ha = homeAwayFactor(home, away, tactics);
  const bg = bigGameFactor(home, away, tactics);
  const goal = goalExpectationFactor(home, away, tactics);
  
  // 合成修正系数
  let adjust = 1.0;
  
  // 战术匹配: 主队攻击 × 客队防守 综合
  if (isHome) {
    adjust *= style.attackFactor;  // 主队攻击风格
    adjust *= ha.homeFactor / 1.08;  // 实际主场优势 vs 默认1.08
    adjust *= bg.homeFactor;  // 主队大赛心理
  } else {
    adjust *= style.defenseFactor;  // 客队防守风格 (逆)
    adjust *= ha.awayFactor;  // 客队客场表现
    adjust *= bg.awayFactor;  // 客队大赛心理
  }
  
  // 进球倾向修正
  adjust *= goal.totalFactor;
  
  // 如果某队零封率高, 对手 λ 降低
  const h = tactics[home];
  const a = tactics[away];
  if (h && a) {
    if (isHome) {
      const oppCS = a.cleanSheetRate || 30;
      adjust *= (1.0 - (oppCS - 30) * 0.002);  // 零封率每高10%, λ 降2%
    } else {
      const oppCS = h.cleanSheetRate || 30;
      adjust *= (1.0 - (oppCS - 30) * 0.002);
    }
  }
  
  return {
    adjust: Math.round(adjust * 100) / 100,
    style,
    homeAway: ha,
    bigGame: bg,
    goalExpectation: goal
  };
}