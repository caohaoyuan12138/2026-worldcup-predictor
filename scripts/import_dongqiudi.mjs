#!/usr/bin/env node
/**
 * 懂球帝数据导入脚本
 * 解析 世界杯数据完全汇总.md 中的球员榜/球队榜数据
 * 写入 worldcup.json 数据库
 */

import * as fs from 'fs';
import * as path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const MD_PATH = path.join(__dirname, '..', '世界杯数据完全汇总.md');
const DB_PATH = path.join(__dirname, '..', 'db', 'worldcup.json');

// ============================================================
// 1. 读取 MD 并分节
// ============================================================
const md = fs.readFileSync(MD_PATH, 'utf8');
const lines = md.split('\n');

// 找到所有节标题
function findSections() {
  const sections = [];
  for (let i = 0; i < lines.length; i++) {
    const m = lines[i].match(/^## (二|三)、(.+)/);
    if (m) {
      sections.push({ line: i, type: m[1] === '二' ? 'player' : 'team', title: m[2], header: lines[i] });
    }
  }
  return sections;
}

const sections = findSections();
const playerSection = sections.find(s => s.type === 'player');
const teamSection = sections.find(s => s.type === 'team');

// 找到所有 ### 子节
function findSubSections(startLine, endLine) {
  const subs = [];
  for (let i = startLine; i < Math.min(endLine, lines.length); i++) {
    const m = lines[i].match(/^### (\S+)/);
    if (m) {
      subs.push({ line: i, name: m[1], fullName: m[0] });
    }
  }
  return subs;
}

// ============================================================
// 2. 解析表格数据
// ============================================================
function parseTableLines(start, end) {
  const data = [];
  for (let i = start; i < Math.min(end, lines.length); i++) {
    const line = lines[i].trim();
    if (!line || line.startsWith('| 排名') || line.startsWith('|:---') || line.startsWith('*共')) continue;
    if (!line.startsWith('|')) continue;
    
    const cells = line.split('|').map(c => c.trim()).filter(Boolean);
    if (cells.length < 3) continue;
    
    // 判断是球员榜(4列: 排名|球员|球队|数值)还是球队榜(3列: 排名|球队|数值)
    // 规则: 如果第4列能parse为数字, 就是球员榜; 否则是球队榜
    const rank = parseInt(cells[0]);
    const name = cells[1];
    
    if (cells.length >= 4) {
      // 球员榜格式: 排名|球员|球队|数值
      const team = cells[2];
      const valRaw = cells[3];
      const val = parseFloat(valRaw.replace(/[()]/g, ''));
      const hasPenalty = valRaw.includes('(');
      const entry = { rank, name, val, team };
      if (hasPenalty) entry.raw = valRaw;
      data.push(entry);
    } else {
      // 球队榜格式: 排名|球队|数值
      const valRaw = cells[2];
      const val = parseFloat(valRaw.replace(/[()]/g, ''));
      const hasPenalty = valRaw.includes('(');
      const entry = { rank, name, val };
      if (hasPenalty) entry.raw = valRaw;
      data.push(entry);
    }
  }
  return data;
}

// ============================================================
// 3. 解析球员榜
// ============================================================
function parsePlayerBoard() {
  const playerSubs = findSubSections(playerSection.line, teamSection ? teamSection.line : lines.length);
  
  const playerBoards = {};
  for (let i = 0; i < playerSubs.length; i++) {
    const sub = playerSubs[i];
    const nextSub = playerSubs[i + 1];
    const endLine = nextSub ? nextSub.line : (teamSection ? teamSection.line : lines.length);
    
    // 找表头行
    let tableStart = sub.line + 1;
    while (tableStart < endLine && !lines[tableStart].trim().startsWith('| 排名')) tableStart++;
    if (tableStart >= endLine) continue;
    
    // 表头后3行(空行+表头+分隔线)跳过
    let dataStart = tableStart + 2;
    while (dataStart < endLine && !lines[dataStart].trim().startsWith('|')) dataStart++;
    
    const data = parseTableLines(dataStart, endLine);
    
    // 构建 name -> {球队, 数值} 映射
    const boardMap = {};
    for (const entry of data) {
      const teamName = entry.team || '';
      // 从球员榜格式: 排名 | 球员 | 球队 | 数值
      // 有些表是 排名|球员|球队|数值, 有些是 排名|球员|数值(没有球队列)
      // 对于有球队列的, entry.team 已经存在
      boardMap[entry.name] = { team: teamName, val: entry.val, rank: entry.rank };
    }
    
    playerBoards[sub.name] = {
      name: sub.name,
      count: data.length,
      data: boardMap
    };
  }
  
  return playerBoards;
}

// ============================================================
// 4. 解析球队榜
// ============================================================
function parseTeamBoard() {
  const teamSubs = findSubSections(teamSection.line, lines.length);
  
  const teamData = {};
  
  for (let i = 0; i < teamSubs.length; i++) {
    const sub = teamSubs[i];
    const nextSub = teamSubs[i + 1];
    const endLine = nextSub ? nextSub.line : lines.length;
    
    // 找表头
    let tableStart = sub.line + 1;
    while (tableStart < endLine && !lines[tableStart].trim().startsWith('| 排名')) tableStart++;
    if (tableStart >= endLine) continue;
    
    let dataStart = tableStart + 2;
    while (dataStart < endLine && !lines[dataStart].trim().startsWith('|')) dataStart++;
    
    const data = parseTableLines(dataStart, endLine);
    
    // 按球队名聚合
    for (const entry of data) {
      const teamName = entry.name.trim().replace(/\s+$/, '');
      if (!teamData[teamName]) teamData[teamName] = {};
      teamData[teamName][sub.name] = entry.val;
    }
  }
  
  return teamData;
}

// ============================================================
// 5. 解析球员详细信息 (关联到球队)
// ============================================================
function parsePlayersByTeam(playerBoards) {
  // 先收集所有球员
  const allPlayers = {};
  
  for (const [boardName, board] of Object.entries(playerBoards)) {
    for (const [playerName, info] of Object.entries(board.data)) {
      const team = info.team || '未知';
      if (!allPlayers[playerName]) {
        allPlayers[playerName] = { name: playerName, team, stats: {} };
      }
      allPlayers[playerName].stats[boardName] = info.val;
      if (info.team && info.team !== '未知' && info.team !== '') {
        allPlayers[playerName].team = info.team;
      }
    }
  }
  
  // 按球队分组
  const playersByTeam = {};
  for (const [name, info] of Object.entries(allPlayers)) {
    const team = info.team || '未知';
    if (!playersByTeam[team]) playersByTeam[team] = [];
    playersByTeam[team].push(info);
  }
  
  return { allPlayers, playersByTeam };
}

// ============================================================
// 6. 主函数
// ============================================================
console.log('=== 懂球帝数据导入 ===\n');

// 解析
const playerBoards = parsePlayerBoard();
const teamStats = parseTeamBoard();
const { allPlayers, playersByTeam } = parsePlayersByTeam(playerBoards);

console.log('球员榜维度:', Object.keys(playerBoards).length);
for (const [name, board] of Object.entries(playerBoards)) {
  console.log('  ' + name + ': ' + board.count + '人');
}

console.log('\n球队榜维度:', Object.keys(teamStats['法国'] || {}).length);
console.log('球队数:', Object.keys(teamStats).length);

// 读取现有数据库
const db = JSON.parse(fs.readFileSync(DB_PATH, 'utf8'));

// 给每支球队添加懂球帝数据
let updatedCount = 0;
let missingCount = 0;
for (const [teamName, stats] of Object.entries(teamStats)) {
  // 匹配球队名 (数据库可能用 '刚果(金)', 懂球帝用 '刚果民主共和国')
  const dbTeamName = findTeamInDB(teamName, db.teams);
  if (dbTeamName) {
    db.teams[dbTeamName].dongqiudi = db.teams[dbTeamName].dongqiudi || {};
    Object.assign(db.teams[dbTeamName].dongqiudi, stats);
    updatedCount++;
  } else {
    missingCount++;
    console.log('  未匹配球队:', teamName);
  }
}

// 添加球员数据到数据库
db.players = allPlayers;
db.playersByTeam = playersByTeam;

console.log('\n匹配球队:', updatedCount);
console.log('未匹配球队:', missingCount);

// 示例: 查看一支球队的懂球帝数据
console.log('\n巴西懂球帝数据样本:');
const br = db.teams['巴西'];
if (br && br.dongqiudi) {
  const keys = Object.keys(br.dongqiudi);
  console.log('  ' + keys.length + '个维度');
  console.log('  进球:', br.dongqiudi['进球']);
  console.log('  射门:', br.dongqiudi['射门']);
  console.log('  射正:', br.dongqiudi['射正']);
  console.log('  扑救:', br.dongqiudi['扑救']);
  console.log('  评分:', br.dongqiudi['评分']);
  console.log('  身价:', br.dongqiudi['身价']);
  console.log('  传球成功率:', br.dongqiudi['传球成功率']);
}

// 球员数据样本
console.log('\n梅西数据:');
const messi = db.players['梅西'];
if (messi) {
  console.log('  球队:', messi.team);
  console.log('  射手榜:', messi.stats['射手榜']);
  console.log('  射门:', messi.stats['射门']);
  console.log('  射正:', messi.stats['射正']);
  console.log('  关键传球:', messi.stats['关键传球']);
  console.log('  评分:', messi.stats['评分']);
}

// 写入数据库
db.meta.dataSource = '懂球帝数据中心';
db.meta.importDate = new Date().toISOString();
db.meta.playerDimensions = Object.keys(playerBoards);
db.meta.teamDimensions = Object.keys(teamStats['法国'] || {});

fs.writeFileSync(DB_PATH, JSON.stringify(db, null, 2), 'utf8');
console.log('\n✅ 数据已写入 worldcup.json');
console.log('球员总数:', Object.keys(allPlayers).length);
console.log('有球员的球队数:', Object.keys(playersByTeam).length);

// 辅助函数: 匹配球队名
function findTeamInDB(name, teams) {
  // 直接匹配
  if (teams[name]) return name;
  
  // 别名映射
  const aliases = {
    '刚果民主共和国': '刚果(金)',
    '刚果民主共和国 ': '刚果(金)',
    '加拿大': '加拿大',
    '佛得角 ': '佛得角',
    '韩国': '韩国',
    '库拉索': '库拉索',
    '卡塔尔': '卡塔尔',
    '捷克': '捷克',
    '巴拿马': '巴拿马',
    '苏格兰': '苏格兰',
    '南非': '南非',
    '加纳': '加纳',
    '伊朗': '伊朗',
    '克罗地亚': '克罗地亚',
    '日本': '日本',
    '沙特阿拉伯': '沙特阿拉伯',
    '乌兹别克斯坦': '乌兹别克斯坦',
    '突尼斯': '突尼斯',
    '新西兰': '新西兰',
    '伊拉克': '伊拉克',
    '海地': '海地',
    '约旦': '约旦',
    '奥地利': '奥地利',
    '阿尔及利亚': '阿尔及利亚',
    '巴拉圭': '巴拉圭',
    '厄瓜多尔': '厄瓜多尔',
    '澳大利亚': '澳大利亚',
    '土耳其': '土耳其',
    '塞内加尔': '塞内加尔',
    '乌拉圭': '乌拉圭',
    '科特迪瓦': '科特迪瓦',
    '埃及': '埃及',
    '波黑': '波黑',
    '摩洛哥': '摩洛哥',
    '哥伦比亚': '哥伦比亚',
    '葡萄牙': '葡萄牙',
    '英格兰': '英格兰',
    '阿根廷': '阿根廷',
    '法国': '法国',
    '德国': '德国',
    '荷兰': '荷兰',
    '西班牙': '西班牙',
    '巴西': '巴西',
    '比利时': '比利时',
    '墨西哥': '墨西哥',
    '美国': '美国',
    '挪威': '挪威',
    '瑞士': '瑞士',
    '瑞典': '瑞典',
  };
  
  const mapped = aliases[name];
  if (mapped && teams[mapped]) return mapped;
  
  // 模糊匹配
  for (const t of Object.keys(teams)) {
    if (name.includes(t) || t.includes(name)) return t;
  }
  
  return null;
}
