/**
 * ⚽ 世界杯 2026 数据库
 *
 * 数据来源: 曹昊源提供的Excel + 懂球帝世界杯数据中心
 * 更新日期: 2026-07-01 (第3轮结束 + 1/16决赛4场完成)
 *
 * 赛制: 48队/12组 → 每组前2+8个最佳第3 → 1/16(32强)→1/8→1/4→半决赛→决赛
 * 总场次: 104场 (小组赛72 + 淘汰赛32)
 * 已完赛: 78场 (第1轮24场 + 第2轮22场 + 第3轮24场 + 1/16决赛4场)
 * 淘汰赛: 6月28日-7月19日 32场
 * 主数据源: db/worldcup.json (server.mjs 使用)
 * database.mjs 已同步至 78场
 *
 * 懂球帝数据: 球员榜(射手/助攻/关键传球/传球成功率/评分/防守) + 球队榜(进球/失球/助攻/射门/射正/角球/越位/犯规/传球/抢断/拦截/解围/争顶/地面争抢/扑救/评分/身价)
 */

import * as fs from 'fs';
import * as path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// ============================================================
// 1. 分组
// ============================================================
const GROUPS = {
  A: ['墨西哥', '韩国', '捷克', '南非'],
  B: ['加拿大', '瑞士', '波黑', '卡塔尔'],
  C: ['巴西', '摩洛哥', '苏格兰', '海地'],
  D: ['美国', '澳大利亚', '巴拉圭', '土耳其'],
  E: ['德国', '科特迪瓦', '厄瓜多尔', '库拉索'],
  F: ['荷兰', '日本', '瑞典', '突尼斯'],
  G: ['比利时', '埃及', '伊朗', '新西兰'],
  H: ['西班牙', '佛得角', '沙特阿拉伯', '乌拉圭'],
  I: ['法国', '挪威', '伊拉克', '塞内加尔'],
  J: ['阿根廷', '奥地利', '阿尔及利亚', '约旦'],
  K: ['葡萄牙', '哥伦比亚', '刚果(金)', '乌兹别克斯坦'],
  L: ['英格兰', '克罗地亚', '加纳', '巴拿马'],
};

const TEAM_GROUP = {};
for (const [g, teams] of Object.entries(GROUPS)) {
  for (const t of teams) TEAM_GROUP[t] = g;
}

// ============================================================
// 2. 已完赛 46场 (第1轮24场 + 第2轮22场)
// ============================================================
const COMPLETED_MATCHES = [
  // ═══ 第1轮 (6月11-18日, 24场) ═══
  // 6月11日 - 1场
  { date: '2026-06-11', group: 'A', home: '墨西哥', away: '南非', score: '2-0', round: 1 },
  // 6月12日 - 2场
  { date: '2026-06-12', group: 'A', home: '韩国', away: '捷克', score: '2-1', round: 1 },
  { date: '2026-06-12', group: 'B', home: '加拿大', away: '波黑', score: '1-1', round: 1 },
  // 6月13日 - 3场
  { date: '2026-06-13', group: 'D', home: '美国', away: '巴拉圭', score: '4-1', round: 1 },
  { date: '2026-06-13', group: 'B', home: '卡塔尔', away: '瑞士', score: '1-1', round: 1 },
  { date: '2026-06-13', group: 'C', home: '巴西', away: '摩洛哥', score: '1-1', round: 1 },
  // 6月14日 - 3场
  { date: '2026-06-14', group: 'C', home: '海地', away: '苏格兰', score: '0-1', round: 1 },
  { date: '2026-06-14', group: 'D', home: '澳大利亚', away: '土耳其', score: '2-0', round: 1 },
  { date: '2026-06-14', group: 'E', home: '德国', away: '库拉索', score: '7-1', round: 1 },
  // 6月15日 - 4场
  { date: '2026-06-15', group: 'F', home: '荷兰', away: '日本', score: '2-2', round: 1 },
  { date: '2026-06-15', group: 'E', home: '科特迪瓦', away: '厄瓜多尔', score: '1-0', round: 1 },
  { date: '2026-06-15', group: 'F', home: '瑞典', away: '突尼斯', score: '5-1', round: 1 },
  { date: '2026-06-15', group: 'H', home: '西班牙', away: '佛得角', score: '0-0', round: 1 },
  // 6月16日 - 4场
  { date: '2026-06-16', group: 'G', home: '比利时', away: '埃及', score: '1-1', round: 1 },
  { date: '2026-06-16', group: 'H', home: '沙特阿拉伯', away: '乌拉圭', score: '1-1', round: 1 },
  { date: '2026-06-16', group: 'G', home: '伊朗', away: '新西兰', score: '2-2', round: 1 },
  { date: '2026-06-16', group: 'I', home: '法国', away: '塞内加尔', score: '3-1', round: 1 },
  // 6月17日 - 4场
  { date: '2026-06-17', group: 'I', home: '伊拉克', away: '挪威', score: '1-4', round: 1 },
  { date: '2026-06-17', group: 'J', home: '阿根廷', away: '阿尔及利亚', score: '3-0', round: 1 },
  { date: '2026-06-17', group: 'J', home: '奥地利', away: '约旦', score: '3-1', round: 1 },
  { date: '2026-06-17', group: 'K', home: '葡萄牙', away: '刚果(金)', score: '1-1', round: 1 },
  // 6月18日 - 3场
  { date: '2026-06-18', group: 'L', home: '英格兰', away: '克罗地亚', score: '4-2', round: 1 },
  { date: '2026-06-18', group: 'L', home: '加纳', away: '巴拿马', score: '1-0', round: 1 },
  { date: '2026-06-18', group: 'K', home: '乌兹别克斯坦', away: '哥伦比亚', score: '1-3', round: 1 },

  // ═══ 第2轮 (6月18-24日, 22场) ═══
  // 6月18日 - 1场
  { date: '2026-06-18', group: 'A', home: '捷克', away: '南非', score: '1-1', round: 2 },
  // 6月19日 - 3场
  { date: '2026-06-19', group: 'B', home: '瑞士', away: '波黑', score: '4-1', round: 2 },
  { date: '2026-06-19', group: 'B', home: '加拿大', away: '卡塔尔', score: '6-0', round: 2 },
  { date: '2026-06-19', group: 'A', home: '墨西哥', away: '韩国', score: '1-0', round: 2 },
  // 6月20日 - 4场
  { date: '2026-06-20', group: 'D', home: '美国', away: '澳大利亚', score: '2-0', round: 2 },
  { date: '2026-06-20', group: 'C', home: '苏格兰', away: '摩洛哥', score: '0-1', round: 2 },
  { date: '2026-06-20', group: 'C', home: '巴西', away: '海地', score: '3-0', round: 2 },
  { date: '2026-06-20', group: 'D', home: '土耳其', away: '巴拉圭', score: '0-1', round: 2 },
  // 6月21日 - 4场
  { date: '2026-06-21', group: 'E', home: '德国', away: '科特迪瓦', score: '2-1', round: 2 },
  { date: '2026-06-21', group: 'F', home: '荷兰', away: '瑞典', score: '5-1', round: 2 },
  { date: '2026-06-21', group: 'E', home: '厄瓜多尔', away: '库拉索', score: '0-0', round: 2 },
  { date: '2026-06-21', group: 'F', home: '突尼斯', away: '日本', score: '0-4', round: 2 },
  // 6月22日 - 4场
  { date: '2026-06-22', group: 'H', home: '西班牙', away: '沙特阿拉伯', score: '4-0', round: 2 },
  { date: '2026-06-22', group: 'G', home: '比利时', away: '伊朗', score: '0-0', round: 2 },
  { date: '2026-06-22', group: 'H', home: '乌拉圭', away: '佛得角', score: '2-2', round: 2 },
  { date: '2026-06-22', group: 'G', home: '新西兰', away: '埃及', score: '1-3', round: 2 },
  // 6月23日 - 4场
  { date: '2026-06-23', group: 'J', home: '阿根廷', away: '奥地利', score: '2-0', round: 2 },
  { date: '2026-06-23', group: 'I', home: '法国', away: '伊拉克', score: '3-0', round: 2 },
  { date: '2026-06-23', group: 'I', home: '挪威', away: '塞内加尔', score: '3-2', round: 2 },
  { date: '2026-06-23', group: 'J', home: '约旦', away: '阿尔及利亚', score: '1-2', round: 2 },
  // 6月24日 - 2场
  { date: '2026-06-24', group: 'K', home: '葡萄牙', away: '乌兹别克斯坦', score: '5-0', round: 2 },
  { date: '2026-06-24', group: 'L', home: '英格兰', away: '加纳', score: '0-0', round: 2 },

  // ═══ 第3轮 (6月24-28日, 24场) ═══
  // 6月24日 - 2场 (B组+C组补赛)
  { date: '2026-06-24', group: 'L', home: '巴拿马', away: '克罗地亚', score: '0-1', round: 2 },
  { date: '2026-06-24', group: 'K', home: '哥伦比亚', away: '刚果(金)', score: '1-0', round: 2 },
  // 6月25日 - 6场
  { date: '2026-06-25', group: 'B', home: '瑞士', away: '加拿大', score: '2-1', round: 3 },
  { date: '2026-06-25', group: 'B', home: '波黑', away: '卡塔尔', score: '3-1', round: 3 },
  { date: '2026-06-25', group: 'C', home: '苏格兰', away: '巴西', score: '0-3', round: 3 },
  { date: '2026-06-25', group: 'C', home: '摩洛哥', away: '海地', score: '4-2', round: 3 },
  { date: '2026-06-25', group: 'A', home: '南非', away: '韩国', score: '1-0', round: 3 },
  { date: '2026-06-25', group: 'A', home: '捷克', away: '墨西哥', score: '0-3', round: 3 },
  // 6月26日 - 6场
  { date: '2026-06-26', group: 'E', home: '厄瓜多尔', away: '德国', score: '2-1', round: 3 },
  { date: '2026-06-26', group: 'E', home: '库拉索', away: '科特迪瓦', score: '0-2', round: 3 },
  { date: '2026-06-26', group: 'F', home: '突尼斯', away: '荷兰', score: '1-3', round: 3 },
  { date: '2026-06-26', group: 'F', home: '日本', away: '瑞典', score: '1-1', round: 3 },
  { date: '2026-06-26', group: 'D', home: '巴拉圭', away: '澳大利亚', score: '0-0', round: 3 },
  { date: '2026-06-26', group: 'D', home: '土耳其', away: '美国', score: '3-2', round: 3 },
  // 6月27日 - 6场
  { date: '2026-06-27', group: 'I', home: '挪威', away: '法国', score: '1-4', round: 3 },
  { date: '2026-06-27', group: 'I', home: '塞内加尔', away: '伊拉克', score: '5-0', round: 3 },
  { date: '2026-06-27', group: 'H', home: '佛得角', away: '沙特阿拉伯', score: '0-0', round: 3 },
  { date: '2026-06-27', group: 'H', home: '乌拉圭', away: '西班牙', score: '0-1', round: 3 },
  { date: '2026-06-27', group: 'G', home: '埃及', away: '伊朗', score: '1-1', round: 3 },
  { date: '2026-06-27', group: 'G', home: '新西兰', away: '比利时', score: '1-5', round: 3 },
  // 6月27日 - 4场 (K组+L组补赛)
  { date: '2026-06-27', group: 'K', home: '哥伦比亚', away: '葡萄牙', score: '0-0', round: 3 },
  { date: '2026-06-27', group: 'K', home: '刚果(金)', away: '乌兹别克斯坦', score: '3-1', round: 3 },
  { date: '2026-06-27', group: 'L', home: '克罗地亚', away: '加纳', score: '2-1', round: 3 },
  { date: '2026-06-27', group: 'L', home: '巴拿马', away: '英格兰', score: '0-2', round: 3 },
  // 6月28日 - 4场 (J组补赛)
  { date: '2026-06-28', group: 'J', home: '阿尔及利亚', away: '奥地利', score: '3-3', round: 3 },
  { date: '2026-06-28', group: 'J', home: '约旦', away: '阿根廷', score: '1-3', round: 3 },

  // ═══ 1/16决赛 (6月28日起) ═══
  { date: '2026-06-28', group: 'KO', home: '南非', away: '加拿大', score: '0-1', round: '16强' },
  { date: '2026-06-28', group: 'KO', home: '巴西', away: '日本', score: '2-1', round: '16强' },
  { date: '2026-06-29', group: 'KO', home: '德国', away: '巴拉圭', score: '1-1', penalty: '3-4', round: '16强' },
  { date: '2026-07-01', group: 'KO', home: '科特迪瓦', away: '挪威', score: '1-2', round: '16强' },
  { date: '2026-07-01', group: 'KO', home: '法国', away: '瑞典', score: '3-0', round: '16强' },
];

// ============================================================
// 3. 今日比赛 (当前无)
// ============================================================
const TODAY_MATCHES = [];

// ============================================================
// 4. 已完赛第3轮 (已移至 COMPLETED_MATCHES)
// ============================================================
const UPCOMING_MATCHES = [];

// ============================================================
// 5. 淘汰赛 (6月28日-7月19日, 32场) — 实际对阵
//    来源: worldcup.json 的 knockoutMatches
// ============================================================
const KNOCKOUT_MATCHES = [
  // 1/16决赛 (6月28日-7月3日, 16场)
  { date: '2026-06-28', round: '1/16', home: '南非', away: '加拿大', score: '0-1', label: '1/16 #1' },
  { date: '2026-06-28', round: '1/16', home: '巴西', away: '日本', score: '2-1', label: '1/16 #2' },
  { date: '2026-06-29', round: '1/16', home: '德国', away: '巴拉圭', score: '1-1', penalty: '3-4', label: '1/16 #3' },
  { date: '2026-06-29', round: '1/16', home: '荷兰', away: '摩洛哥', score: '1-1', penalty: '2-3', label: '1/16 #4' },
  { date: '2026-06-30', round: '1/16', home: '科特迪瓦', away: '挪威', score: '1-2', label: '1/16 #5' },
  { date: '2026-06-30', round: '1/16', home: '法国', away: '瑞典', score: '3-0', label: '1/16 #6' },
  { date: '2026-06-30', round: '1/16', home: '墨西哥', away: '厄瓜多尔', score: null, label: '1/16 #7' },
  { date: '2026-07-01', round: '1/16', home: '英格兰', away: '刚果(金)', score: null, label: '1/16 #8' },
  { date: '2026-07-01', round: '1/16', home: '比利时', away: '塞内加尔', score: null, label: '1/16 #9' },
  { date: '2026-07-01', round: '1/16', home: '美国', away: '波黑', score: null, label: '1/16 #10' },
  { date: '2026-07-02', round: '1/16', home: '西班牙', away: '奥地利', score: null, label: '1/16 #11' },
  { date: '2026-07-02', round: '1/16', home: '葡萄牙', away: '克罗地亚', score: null, label: '1/16 #12' },
  { date: '2026-07-02', round: '1/16', home: '瑞士', away: '阿尔及利亚', score: null, label: '1/16 #13' },
  { date: '2026-07-03', round: '1/16', home: '澳大利亚', away: '埃及', score: null, label: '1/16 #14' },
  { date: '2026-07-03', round: '1/16', home: '阿根廷', away: '佛得角', score: null, label: '1/16 #15' },
  { date: '2026-07-03', round: '1/16', home: '哥伦比亚', away: '加纳', score: null, label: '1/16 #16' },
  // 1/8决赛 (待定)
  { date: '2026-07-05', round: '1/8', home: '#1胜者', away: '#14胜者', label: '1/8 #17' },
  { date: '2026-07-05', round: '1/8', home: '#3胜者', away: '#12胜者', label: '1/8 #18' },
  { date: '2026-07-06', round: '1/8', home: '#6胜者', away: '#13胜者', label: '1/8 #19' },
  { date: '2026-07-06', round: '1/8', home: '#5胜者', away: '#16胜者', label: '1/8 #20' },
  { date: '2026-07-07', round: '1/8', home: '#7胜者', away: '#15胜者', label: '1/8 #21' },
  { date: '2026-07-07', round: '1/8', home: '#9胜者', away: '#11胜者', label: '1/8 #22' },
  { date: '2026-07-08', round: '1/8', home: '#8胜者', away: '#2胜者', label: '1/8 #23' },
  { date: '2026-07-08', round: '1/8', home: '#10胜者', away: '#4胜者', label: '1/8 #24' },
  // 1/4决赛 (待定)
  { date: '2026-07-10', round: '1/4', home: '#17胜者', away: '#20胜者', label: '1/4 #25' },
  { date: '2026-07-11', round: '1/4', home: '#18胜者', away: '#23胜者', label: '1/4 #26' },
  { date: '2026-07-12', round: '1/4', home: '#19胜者', away: '#22胜者', label: '1/4 #27' },
  { date: '2026-07-12', round: '1/4', home: '#21胜者', away: '#24胜者', label: '1/4 #28' },
  // 半决赛 (待定)
  { date: '2026-07-15', round: '半决赛', home: '#25胜者', away: '#26胜者', label: '半决赛 #29' },
  { date: '2026-07-16', round: '半决赛', home: '#27胜者', away: '#28胜者', label: '半决赛 #30' },
  // 三四名 & 决赛
  { date: '2026-07-19', round: '三四名', home: '#29负者', away: '#30负者', label: '三四名 #31' },
  { date: '2026-07-20', round: '决赛', home: '#29胜者', away: '#30胜者', label: '决赛 #32' },
];

// ============================================================
// 6. 积分榜 (自动计算)
// ============================================================
function computeStandings() {
  const standings = {};

  for (const m of COMPLETED_MATCHES) {
    const [hG, aG] = m.score.split('-').map(Number);
    for (const t of [m.home, m.away]) {
      if (!standings[t]) standings[t] = { team: t, group: m.group, p: 0, w: 0, d: 0, l: 0, gf: 0, ga: 0, gd: 0, played: 0 };
    }
    const h = standings[m.home], a = standings[m.away];
    h.played++; a.played++;
    h.gf += hG; h.ga += aG;
    a.gf += aG; a.ga += hG;
    if (hG > aG) { h.w++; h.p += 3; a.l++; }
    else if (hG === aG) { h.d++; h.p += 1; a.d++; a.p += 1; }
    else { h.l++; a.w++; a.p += 3; }
  }

  for (const s of Object.values(standings)) s.gd = s.gf - s.ga;
  return standings;
}

// ============================================================
// 7. 球队特征数据 (基于你的Excel积分榜反推)
// ============================================================
const TEAM_STRENGTHS = {
  '阿根廷': { attackBase: 1.6, defenseBase: 0.7, style: '控球渗透', styleFactor: 1.10, rank: 1 },
  '法国':   { attackBase: 1.7, defenseBase: 0.6, style: '全能攻防', styleFactor: 1.15, rank: 2 },
  '巴西':   { attackBase: 1.5, defenseBase: 0.7, style: '个人突破', styleFactor: 1.15, rank: 3 },
  '英格兰': { attackBase: 1.6, defenseBase: 0.6, style: '快速转换', styleFactor: 1.10, rank: 4 },
  '德国':   { attackBase: 1.7, defenseBase: 0.7, style: '高压控球', styleFactor: 1.10, rank: 5 },
  '西班牙': { attackBase: 1.5, defenseBase: 0.7, style: '传控', styleFactor: 1.05, rank: 6 },
  '葡萄牙': { attackBase: 1.5, defenseBase: 0.8, style: '边路进攻', styleFactor: 1.10, rank: 7 },
  '荷兰':   { attackBase: 1.4, defenseBase: 0.8, style: '全攻全守', styleFactor: 1.10, rank: 8 },
  '比利时': { attackBase: 1.3, defenseBase: 0.8, style: '中场控制', styleFactor: 1.05, rank: 9 },
  '乌拉圭': { attackBase: 1.3, defenseBase: 0.9, style: '强硬防守', styleFactor: 0.95, rank: 10 },
  '克罗地亚': { attackBase: 1.2, defenseBase: 0.9, style: '中场绞杀', styleFactor: 0.95, rank: 11 },
  '美国':   { attackBase: 1.3, defenseBase: 0.9, style: '体能压制', styleFactor: 1.10, rank: 12 },
  '摩洛哥': { attackBase: 1.2, defenseBase: 0.9, style: '防守反击', styleFactor: 0.90, rank: 13 },
  '哥伦比亚': { attackBase: 1.2, defenseBase: 1.0, style: '技术流派', styleFactor: 1.00, rank: 14 },
  '墨西哥': { attackBase: 1.1, defenseBase: 1.0, style: '快速反击', styleFactor: 1.00, rank: 15 },
  '日本':   { attackBase: 1.1, defenseBase: 1.0, style: '团队配合', styleFactor: 1.00, rank: 16 },
  '瑞典':   { attackBase: 1.2, defenseBase: 1.0, style: '身体对抗', styleFactor: 1.00, rank: 17 },
  '瑞士':   { attackBase: 1.1, defenseBase: 1.0, style: '防守稳固', styleFactor: 0.95, rank: 18 },
  '挪威':   { attackBase: 1.2, defenseBase: 1.1, style: '长传冲吊', styleFactor: 1.05, rank: 19 },
  '加拿大': { attackBase: 1.1, defenseBase: 1.0, style: '速度突破', styleFactor: 1.05, rank: 20 },
  '塞内加尔': { attackBase: 1.1, defenseBase: 1.1, style: '身体+速度', styleFactor: 1.05, rank: 21 },
  '厄瓜多尔': { attackBase: 1.0, defenseBase: 1.0, style: '防守反击', styleFactor: 0.95, rank: 22 },
  '科特迪瓦': { attackBase: 1.0, defenseBase: 1.1, style: '身体对抗', styleFactor: 1.00, rank: 23 },
  '奥地利': { attackBase: 1.0, defenseBase: 1.1, style: '高压逼抢', styleFactor: 1.05, rank: 24 },
  '捷克':   { attackBase: 0.9, defenseBase: 1.1, style: '身体对抗', styleFactor: 1.00, rank: 25 },
  '韩国':   { attackBase: 1.0, defenseBase: 1.2, style: '体能奔跑', styleFactor: 1.05, rank: 26 },
  '澳大利亚': { attackBase: 0.9, defenseBase: 1.1, style: '身体对抗', styleFactor: 1.00, rank: 27 },
  '苏格兰': { attackBase: 0.9, defenseBase: 1.1, style: '强硬拼抢', styleFactor: 1.00, rank: 28 },
  '埃及':   { attackBase: 0.9, defenseBase: 1.1, style: '防守反击', styleFactor: 0.95, rank: 29 },
  '伊朗':   { attackBase: 0.8, defenseBase: 1.0, style: '铁桶防守', styleFactor: 0.85, rank: 30 },
  '阿尔及利亚': { attackBase: 0.9, defenseBase: 1.2, style: '技术+速度', styleFactor: 1.00, rank: 31 },
  '加纳':   { attackBase: 0.9, defenseBase: 1.2, style: '身体+速度', styleFactor: 1.00, rank: 32 },
  '土耳其': { attackBase: 0.9, defenseBase: 1.2, style: '情绪化进攻', styleFactor: 1.10, rank: 33 },
  '巴拉圭': { attackBase: 0.8, defenseBase: 1.1, style: '铁桶防守', styleFactor: 0.85, rank: 34 },
  '波黑':   { attackBase: 0.8, defenseBase: 1.3, style: '身体对抗', styleFactor: 1.00, rank: 35 },
  '南非':   { attackBase: 0.7, defenseBase: 1.2, style: '防守反击', styleFactor: 0.95, rank: 36 },
  '卡塔尔': { attackBase: 0.7, defenseBase: 1.3, style: '传控', styleFactor: 0.95, rank: 37 },
  '刚果(金)': { attackBase: 0.7, defenseBase: 1.3, style: '身体对抗', styleFactor: 1.00, rank: 38 },
  '巴拿马': { attackBase: 0.6, defenseBase: 1.3, style: '防守反击', styleFactor: 0.90, rank: 39 },
  '乌兹别克斯坦': { attackBase: 0.7, defenseBase: 1.4, style: '技术流派', styleFactor: 0.95, rank: 40 },
  '约旦':   { attackBase: 0.6, defenseBase: 1.4, style: '防守反击', styleFactor: 0.90, rank: 41 },
  '海地':   { attackBase: 0.5, defenseBase: 1.5, style: '身体对抗', styleFactor: 1.00, rank: 42 },
  '伊拉克': { attackBase: 0.6, defenseBase: 1.4, style: '防守反击', styleFactor: 0.90, rank: 43 },
  '突尼斯': { attackBase: 0.6, defenseBase: 1.4, style: '铁桶防守', styleFactor: 0.85, rank: 44 },
  '沙特阿拉伯': { attackBase: 0.5, defenseBase: 1.5, style: '技术不足', styleFactor: 0.90, rank: 45 },
  '佛得角': { attackBase: 0.6, defenseBase: 1.5, style: '技术流派', styleFactor: 0.95, rank: 46 },
  '新西兰': { attackBase: 0.6, defenseBase: 1.4, style: '身体对抗', styleFactor: 1.00, rank: 47 },
  '库拉索': { attackBase: 0.4, defenseBase: 1.6, style: '技术流派', styleFactor: 0.95, rank: 48 },
};

// ============================================================
// 9. 懂球帝完整数据 (从 dongqiudi_full.json 导入)
// ============================================================

// 导入完整数据
const DONGQIUDI_DATA = JSON.parse(fs.readFileSync(path.join(__dirname, 'dongqiudi_full.json'), 'utf8'));

// 解析数值（处理括号注释如 "3(1)" → 3，百分比 "87%" → 0.87）
function parseValue(val) {
  if (typeof val === 'number') return val;
  if (!val) return 0;
  const str = String(val);
  // 处理百分比
  if (str.includes('%')) {
    const match = str.match(/([\d.]+)/);
    return match ? parseFloat(match[1]) / 100 : 0;
  }
  // 处理括号注释如 "3(1)" → 3
  const match = str.match(/^([\d.]+)/);
  return match ? parseFloat(match[1]) : 0;
}

// 球员数据快捷访问
const PLAYER_GOALS = DONGQIUDI_DATA.player['射手榜'] || [];
const PLAYER_ASSISTS = DONGQIUDI_DATA.player['助攻榜'] || [];
const PLAYER_KEY_PASSES = DONGQIUDI_DATA.player['关键传球'] || [];
const PLAYER_RATINGS = DONGQIUDI_DATA.player['评分'] || [];
const PLAYER_DEFENSE_RAW = DONGQIUDI_DATA.player || {};

// 球队数据
const TEAM_DONGQIUDI = {};
for (const [category, items] of Object.entries(DONGQIUDI_DATA.team)) {
  for (const item of items) {
    if (!TEAM_DONGQIUDI[item.team]) TEAM_DONGQIUDI[item.team] = {};
    TEAM_DONGQIUDI[item.team][category] = item.value;
  }
}

// 积分榜
const STANDINGS = DONGQIUDI_DATA.standings || {};

// ============================================================
// 10. 懂球帝球队汇总数据（基于 dongqiudi_full.json 动态生成）
// ============================================================
// TEAM_DONGQIUDI 在下方通过 JSON 数据动态生成

// ============================================================
// 8. 工具函数
// ============================================================
function getStats() {
  const total = COMPLETED_MATCHES.length;
  let homeW = 0, draw = 0, awayW = 0, totalG = 0;
  const scoreDist = {};
  for (const m of COMPLETED_MATCHES) {
    const [h, a] = m.score.split('-').map(Number);
    if (h > a) homeW++; else if (h === a) draw++; else awayW++;
    totalG += h + a;
    scoreDist[`${h}-${a}`] = (scoreDist[`${h}-${a}`] || 0) + 1;
  }
  return {
    total, homeWinPct: (homeW / total * 100).toFixed(1),
    drawPct: (draw / total * 100).toFixed(1), awayWinPct: (awayW / total * 100).toFixed(1),
    avgGoals: (totalG / total).toFixed(2),
    avgHomeGoals: (COMPLETED_MATCHES.reduce((s, m) => s + Number(m.score.split('-')[0]), 0) / total).toFixed(2),
    avgAwayGoals: (COMPLETED_MATCHES.reduce((s, m) => s + Number(m.score.split('-')[1]), 0) / total).toFixed(2),
    scoreDist: Object.fromEntries(Object.entries(scoreDist).sort((a, b) => b[1] - a[1])),
  };
}

function getTeamByName(name) { return TEAM_STRENGTHS[name] || null; }
function getStandings() { return computeStandings(); }
function getMatches() { return { completed: COMPLETED_MATCHES, today: TODAY_MATCHES, upcoming: UPCOMING_MATCHES, knockout: KNOCKOUT_MATCHES }; }
function getGroups() { return GROUPS; }
function getTeamGroup(team) { return TEAM_GROUP[team] || null; }

// ============================================================
// 11. 懂球帝数据查询函数
// ============================================================

/** 获取球队懂球帝统计数据 */
function getTeamDongqiudi(team) {
  return TEAM_DONGQIUDI[team] || null;
}

/** 获取球员在指定类别的排名数据（跳过表头行） */
function getPlayerStat(category, playerName) {
  const list = DONGQIUDI_DATA.player[category];
  if (!list) return null;
  const found = list.find(p => p.name === playerName && p.rank !== ':---:');
  if (!found) return null;
  return parseValue(found.value);
}

/** 获取球员进球数 */
function getPlayerGoals(player) {
  return getPlayerStat('射手榜', player);
}

/** 获取球员助攻数 */
function getPlayerAssists(player) {
  return getPlayerStat('助攻榜', player);
}

/** 获取球员关键传球数 */
function getPlayerKeyPasses(player) {
  return getPlayerStat('关键传球', player);
}

/** 获取球员射门数 */
function getPlayerShots(player) {
  return getPlayerStat('射门', player);
}

/** 获取球员射正数 */
function getPlayerOnTarget(player) {
  return getPlayerStat('射正', player);
}

/** 获取球员评分 */
function getPlayerRating(player) {
  return getPlayerStat('评分', player);
}

/** 获取球队进攻强度（基于懂球帝数据） */
function getTeamAttackStrength(team) {
  const dq = TEAM_DONGQIUDI[team];
  const ts = TEAM_STRENGTHS[team];
  if (!dq || !ts) return ts?.attackBase || 1.0;
  // 基于进球和射正率计算进攻强度
  const goals = parseValue(dq['进球']) || 0;
  const shots = parseValue(dq['射门']) || 1;
  const onTarget = parseValue(dq['射正']) || 0;
  const shotAccuracy = shots > 0 ? onTarget / shots : 0.3;
  const attackBonus = shotAccuracy > 0.4 ? 1.1 : shotAccuracy > 0.3 ? 1.05 : 1.0;
  return ts.attackBase * attackBonus;
}

/** 获取球队防守强度（基于懂球帝数据） */
function getTeamDefenseStrength(team) {
  const dq = TEAM_DONGQIUDI[team];
  const ts = TEAM_STRENGTHS[team];
  if (!dq || !ts) return ts?.defenseBase || 1.0;
  // 基于抢断/拦截/解围计算防守强度
  const tackles = parseValue(dq['抢断']) || 0;
  const interceptions = parseValue(dq['拦截']) || 0;
  const clearances = parseValue(dq['解围']) || 0;
  const defActions = tackles + interceptions + clearances;
  const defBonus = defActions > 150 ? 1.15 : defActions > 100 ? 1.1 : defActions > 50 ? 1.05 : 1.0;
  return ts.defenseBase * defBonus;
}

/** 获取球队射正率 */
function getTeamShotAccuracy(team) {
  const dq = TEAM_DONGQIUDI[team];
  if (!dq) return 0.3;
  const shots = parseValue(dq['射门']) || 0;
  const onTarget = parseValue(dq['射正']) || 0;
  return shots > 0 ? onTarget / shots : 0.3;
}

/** 获取球队传球成功率 */
function getTeamPassAccuracy(team) {
  const dq = TEAM_DONGQIUDI[team];
  if (!dq) return 0.85;
  return parseValue(dq['传球成功率']) || 0.85;
}

/** 获取球队控球评分 */
function getTeamRating(team) {
  const dq = TEAM_DONGQIUDI[team];
  if (!dq) return 6.5;
  return parseValue(dq['评分']) || 6.5;
}

/** 获取完整数据 */
function getDongqiudiData() {
  return DONGQIUDI_DATA;
}

/** 获取积分榜数据 */
function getDongqiudiStandings() {
  return STANDINGS;
}

export {
  GROUPS, COMPLETED_MATCHES, TODAY_MATCHES, UPCOMING_MATCHES, KNOCKOUT_MATCHES,
  TEAM_STRENGTHS, TEAM_GROUP,
  DONGQIUDI_DATA, TEAM_DONGQIUDI, STANDINGS,
  computeStandings, getStats, getTeamByName, getStandings,
  getMatches, getGroups, getTeamGroup,
  getTeamDongqiudi, getTeamAttackStrength, getTeamDefenseStrength,
  getTeamShotAccuracy, getTeamPassAccuracy, getTeamRating,
  getPlayerGoals, getPlayerAssists, getPlayerKeyPasses,
  getPlayerShots, getPlayerOnTarget, getPlayerRating,
  getDongqiudiData, getDongqiudiStandings,
};
