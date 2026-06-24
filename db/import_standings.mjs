#!/usr/bin/env node

/**
 * ⚽ 导入出线形势 + 淘汰赛对阵数据到数据库
 */

import * as fs from 'fs';
import * as path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const dbPath = path.join(__dirname, 'worldcup.json');

const db = JSON.parse(fs.readFileSync(dbPath, 'utf8'));

// ============================================================
// 1. 小组出线形势
// ============================================================
// standings 已由 completedMatches 动态计算
// 这里补充：末轮战意等级 (0=已出局, 1=渺茫, 2=需赢+看别人脸色, 3=需赢, 4=打平就出线, 5=已出线)

const groupStandings = {
  'A': { teams: ['墨西哥','韩国','捷克','南非'], played: 2, description: '墨西哥已锁定头名, 韩国战平即出线' },
  'B': { teams: ['加拿大','瑞士','波黑','卡塔尔'], played: 2, description: '加瑞打平即携手出线' },
  'C': { teams: ['巴西','摩洛哥','苏格兰','海地'], played: 2, description: '巴摩打平即出线, 苏格兰需赢巴西' },
  'D': { teams: ['美国','澳大利亚','巴拉圭','土耳其'], played: 2, description: '美国已出线, 澳巴争第二' },
  'E': { teams: ['德国','科特迪瓦','厄瓜多尔','库拉索'], played: 2, description: '德国已出线, 科特迪瓦战平即出线' },
  'F': { teams: ['荷兰','日本','瑞典','突尼斯'], played: 2, description: '荷日打平即出线, 瑞典需赢日本' },
  'G': { teams: ['埃及','伊朗','比利时','新西兰'], played: 2, description: '埃及战平即出线, 伊朗比利时争' },
  'H': { teams: ['西班牙','乌拉圭','佛得角','沙特阿拉伯'], played: 2, description: '西班牙战平即出线, 乌拉圭佛得角争' },
  'I': { teams: ['法国','挪威','塞内加尔','伊拉克'], played: 2, description: '法挪已出线, 争头名' },
  'J': { teams: ['阿根廷','奥地利','阿尔及利亚','约旦'], played: 2, description: '阿根廷已出线, 奥地利阿尔及利亚争第二' },
  'K': { teams: ['哥伦比亚','葡萄牙','刚果(金)','乌兹别克斯坦'], played: 2, description: '哥伦比亚已出线, 葡萄牙战平即出线' },
  'L': { teams: ['英格兰','加纳','克罗地亚','巴拿马'], played: 2, description: '英加打平即出线, 克罗地亚需赢加纳' },
};

// ============================================================
// 2. 淘汰赛对阵树
// ============================================================
const knockoutTree = {
  round64: [
    { id: 73, label: '1/16', home: 'A2', away: 'B2', venue: '洛杉矶' },
    { id: 74, label: '1/16', home: 'E1', away: 'T3(AB C D F)', venue: '波士顿' },
    { id: 75, label: '1/16', home: 'F1', away: 'C2', venue: '蒙特雷' },
    { id: 76, label: '1/16', home: 'C1', away: 'F2', venue: '休斯顿' },
    { id: 77, label: '1/16', home: 'I1', away: 'T3(CD F G H)', venue: '纽约/新泽西' },
    { id: 78, label: '1/16', home: 'E2', away: 'I2', venue: '达拉斯' },
    { id: 79, label: '1/16', home: 'A1', away: 'T3(CE F H I)', venue: '墨西哥城' },
    { id: 80, label: '1/16', home: 'L1', away: 'T3(EH I J K)', venue: '亚特兰大' },
    { id: 81, label: '1/16', home: 'D1', away: 'T3(BE F I J)', venue: '旧金山湾区' },
    { id: 82, label: '1/16', home: 'G1', away: 'T3(AE H I J)', venue: '西雅图' },
    { id: 83, label: '1/16', home: 'K2', away: 'L2', venue: '多伦多' },
    { id: 84, label: '1/16', home: 'H1', away: 'J2', venue: '洛杉矶' },
    { id: 85, label: '1/16', home: 'B1', away: 'T3(EF G J)', venue: '温哥华' },
    { id: 86, label: '1/16', home: 'J1', away: 'H2', venue: '迈阿密' },
    { id: 87, label: '1/16', home: 'K1', away: 'T3(DE I J L)', venue: '堪萨斯城' },
    { id: 88, label: '1/16', home: 'D2', away: 'G2', venue: '达拉斯' },
  ],
  round16: [
    { id: 89, label: '1/8', home: 'W74', away: 'W77', venue: '费城' },
    { id: 90, label: '1/8', home: 'W73', away: 'W75', venue: '休斯顿' },
    { id: 91, label: '1/8', home: 'W76', away: 'W78', venue: '纽约/新泽西' },
    { id: 92, label: '1/8', home: 'W79', away: 'W80', venue: '墨西哥城' },
    { id: 93, label: '1/8', home: 'W83', away: 'W84', venue: '达拉斯' },
    { id: 94, label: '1/8', home: 'W81', away: 'W82', venue: '西雅图' },
    { id: 95, label: '1/8', home: 'W86', away: 'W88', venue: '亚特兰大' },
    { id: 96, label: '1/8', home: 'W85', away: 'W87', venue: '温哥华' },
  ],
  round8: [
    { id: 97, label: '1/4', home: 'W91', away: 'W90', venue: '波士顿' },
    { id: 98, label: '1/4', home: 'W93', away: 'W94', venue: '洛杉矶' },
    { id: 99, label: '1/4', home: 'W99', away: 'W92', venue: '迈阿密' },
    { id: 100, label: '1/4', home: 'W95', away: 'W96', venue: '堪萨斯城' },
  ],
  semi: [
    { id: 101, label: '半决赛', home: 'W97', away: 'W98', venue: '达拉斯' },
    { id: 102, label: '半决赛', home: 'W99', away: 'W100', venue: '亚特兰大' },
  ],
  final: [
    { id: 103, label: '季军赛', home: 'L101', away: 'L102', venue: '迈阿密' },
    { id: 104, label: '决赛', home: 'W101', away: 'W102', venue: '纽约/新泽西' },
  ],
};

// ============================================================
// 3. 写入数据库
// ============================================================
db.groupStandings = groupStandings;
db.knockoutTree = knockoutTree;
db.meta.dataVersion = 5;

fs.writeFileSync(dbPath, JSON.stringify(db, null, 2), 'utf8');
console.log('✅ 出线形势 + 淘汰赛对阵已写入数据库');
console.log('   小组数:', Object.keys(groupStandings).length);
console.log('   淘汰赛场次:');
console.log('     1/16:', knockoutTree.round64.length, '场');
console.log('     1/8:', knockoutTree.round16.length, '场');
console.log('     1/4:', knockoutTree.round8.length, '场');
console.log('     半决赛:', knockoutTree.semi.length, '场');
console.log('     决赛轮:', knockoutTree.final.length, '场');