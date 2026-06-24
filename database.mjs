/**
 * ⚽ 世界杯 2026 数据库
 * 
 * 数据来源: 曹昊源提供的Excel (2026美加墨世界杯赛程结果.xlsx)
 * 更新日期: 2026-06-24 (第2轮结束)
 * 
 * 赛制: 48队/12组 → 每组前2+8个最佳第3 → 1/16(32强)→1/8→1/4→半决赛→决赛
 * 总场次: 104场 (小组赛72 + 淘汰赛32)
 * 已完赛: 46场 (第1轮24场 + 第2轮22场)
 * 进行中: 6月24日剩余4场
 * 未赛: 6月25-27日 22场 (第3轮)
 * 淘汰赛: 6月28日-7月19日 32场
 */

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
];

// ============================================================
// 3. 今日未赛 (6月24日剩余4场)
// ============================================================
const TODAY_MATCHES = [
  { date: '2026-06-24', group: 'L', home: '巴拿马', away: '克罗地亚', round: 2 },
  { date: '2026-06-24', group: 'K', home: '哥伦比亚', away: '刚果(金)', round: 2 },
  { date: '2026-06-24', group: 'B', home: '瑞士', away: '加拿大', round: 2 },
  { date: '2026-06-24', group: 'B', home: '波黑', away: '卡塔尔', round: 2 },
  { date: '2026-06-24', group: 'C', home: '苏格兰', away: '巴西', round: 2 },
  { date: '2026-06-24', group: 'C', home: '摩洛哥', away: '海地', round: 2 },
];

// ============================================================
// 4. 第3轮 (6月25-27日, 24场)
// ============================================================
const UPCOMING_MATCHES = [
  // 6月25日 - 8场
  { date: '2026-06-25', group: 'A', home: '捷克', away: '墨西哥', round: 3 },
  { date: '2026-06-25', group: 'A', home: '南非', away: '韩国', round: 3 },
  { date: '2026-06-25', group: 'E', home: '厄瓜多尔', away: '德国', round: 3 },
  { date: '2026-06-25', group: 'E', home: '库拉索', away: '科特迪瓦', round: 3 },
  { date: '2026-06-25', group: 'F', home: '日本', away: '瑞典', round: 3 },
  { date: '2026-06-25', group: 'F', home: '突尼斯', away: '荷兰', round: 3 },
  { date: '2026-06-25', group: 'D', home: '土耳其', away: '美国', round: 3 },
  { date: '2026-06-25', group: 'D', home: '巴拉圭', away: '澳大利亚', round: 3 },
  // 6月26日 - 6场
  { date: '2026-06-26', group: 'I', home: '挪威', away: '法国', round: 3 },
  { date: '2026-06-26', group: 'I', home: '塞内加尔', away: '伊拉克', round: 3 },
  { date: '2026-06-26', group: 'H', home: '佛得角', away: '沙特阿拉伯', round: 3 },
  { date: '2026-06-26', group: 'H', home: '乌拉圭', away: '西班牙', round: 3 },
  { date: '2026-06-26', group: 'G', home: '埃及', away: '伊朗', round: 3 },
  { date: '2026-06-26', group: 'G', home: '新西兰', away: '比利时', round: 3 },
  // 6月27日 - 6场
  { date: '2026-06-27', group: 'L', home: '巴拿马', away: '英格兰', round: 3 },
  { date: '2026-06-27', group: 'L', home: '克罗地亚', away: '加纳', round: 3 },
  { date: '2026-06-27', group: 'K', home: '哥伦比亚', away: '葡萄牙', round: 3 },
  { date: '2026-06-27', group: 'K', home: '刚果(金)', away: '乌兹别克斯坦', round: 3 },
  { date: '2026-06-27', group: 'J', home: '阿尔及利亚', away: '奥地利', round: 3 },
  { date: '2026-06-27', group: 'J', home: '约旦', away: '阿根廷', round: 3 },
];

// ============================================================
// 5. 淘汰赛 (6月28日-7月19日, 32场)
// ============================================================
const KNOCKOUT_MATCHES = [
  // 1/16决赛 (6月28日-7月3日, 16场)
  { date: '2026-06-28', round: '1/16', home: 'A组第2', away: 'B组第2', label: '1/16 #73' },
  { date: '2026-06-29', round: '1/16', home: 'C组第1', away: 'F组第2', label: '1/16 #74' },
  { date: '2026-06-29', round: '1/16', home: 'E组第1', away: '最佳第3', label: '1/16 #75' },
  { date: '2026-06-29', round: '1/16', home: 'F组第1', away: 'C组第2', label: '1/16 #76' },
  { date: '2026-06-30', round: '1/16', home: 'E组第2', away: 'I组第2', label: '1/16 #77' },
  { date: '2026-06-30', round: '1/16', home: 'I组第1', away: '最佳第3', label: '1/16 #78' },
  { date: '2026-06-30', round: '1/16', home: 'A组第1', away: '最佳第3', label: '1/16 #79' },
  { date: '2026-07-01', round: '1/16', home: 'L组第1', away: '最佳第3', label: '1/16 #80' },
  { date: '2026-07-01', round: '1/16', home: 'G组第1', away: '最佳第3', label: '1/16 #81' },
  { date: '2026-07-01', round: '1/16', home: 'D组第1', away: '最佳第3', label: '1/16 #82' },
  { date: '2026-07-02', round: '1/16', home: 'H组第1', away: 'J组第2', label: '1/16 #83' },
  { date: '2026-07-02', round: '1/16', home: 'K组第2', away: 'L组第2', label: '1/16 #84' },
  { date: '2026-07-02', round: '1/16', home: 'B组第1', away: '最佳第3', label: '1/16 #85' },
  { date: '2026-07-03', round: '1/16', home: 'D组第2', away: 'G组第2', label: '1/16 #86' },
  { date: '2026-07-03', round: '1/16', home: 'J组第1', away: 'H组第2', label: '1/16 #87' },
  { date: '2026-07-03', round: '1/16', home: 'K组第1', away: '最佳第3', label: '1/16 #88' },
  // 1/8决赛 (7月4-7日, 8场)
  { date: '2026-07-04', round: '1/8', home: '#73胜者', away: '#86胜者', label: '1/8 #89' },
  { date: '2026-07-04', round: '1/8', home: '#75胜者', away: '#84胜者', label: '1/8 #90' },
  { date: '2026-07-05', round: '1/8', home: '#78胜者', away: '#85胜者', label: '1/8 #91' },
  { date: '2026-07-05', round: '1/8', home: '#77胜者', away: '#88胜者', label: '1/8 #92' },
  { date: '2026-07-06', round: '1/8', home: '#79胜者', away: '#87胜者', label: '1/8 #93' },
  { date: '2026-07-06', round: '1/8', home: '#81胜者', away: '#83胜者', label: '1/8 #94' },
  { date: '2026-07-07', round: '1/8', home: '#80胜者', away: '#74胜者', label: '1/8 #95' },
  { date: '2026-07-07', round: '1/8', home: '#82胜者', away: '#76胜者', label: '1/8 #96' },
  // 1/4决赛 (7月9-11日, 4场)
  { date: '2026-07-09', round: '1/4', home: '#89胜者', away: '#92胜者', label: '1/4 #97' },
  { date: '2026-07-10', round: '1/4', home: '#90胜者', away: '#95胜者', label: '1/4 #98' },
  { date: '2026-07-11', round: '1/4', home: '#91胜者', away: '#94胜者', label: '1/4 #99' },
  { date: '2026-07-11', round: '1/4', home: '#93胜者', away: '#96胜者', label: '1/4 #100' },
  // 半决赛 (7月14-15日, 2场)
  { date: '2026-07-14', round: '半决赛', home: '#97胜者', away: '#98胜者', label: '半决赛 #101' },
  { date: '2026-07-15', round: '半决赛', home: '#99胜者', away: '#100胜者', label: '半决赛 #102' },
  // 三四名 & 决赛 (7月18-19日, 2场)
  { date: '2026-07-18', round: '三四名', home: '#101负者', away: '#102负者', label: '三四名 #103' },
  { date: '2026-07-19', round: '决赛', home: '#101胜者', away: '#102胜者', label: '决赛 #104' },
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

export {
  GROUPS, COMPLETED_MATCHES, TODAY_MATCHES, UPCOMING_MATCHES, KNOCKOUT_MATCHES,
  TEAM_STRENGTHS, TEAM_GROUP,
  computeStandings, getStats, getTeamByName, getStandings,
  getMatches, getGroups, getTeamGroup,
};
