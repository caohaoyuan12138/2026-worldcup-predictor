/**
 * ⚽ 懂球帝数据完整解析脚本
 * 读取 世界杯数据完全汇总.md 并生成完整的 JSON 数据文件
 */

import * as fs from 'fs';
import * as path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const inputFile = path.join(__dirname, '世界杯数据完全汇总.md');
const outputFile = path.join(__dirname, 'dongqiudi_full.json');

console.log('📖 读取文件:', inputFile);
const content = fs.readFileSync(inputFile, 'utf-8');
const lines = content.split('\n');
console.log(`📊 总行数: ${lines.length}`);

const data = {
  player: {},
  team: {},
  standings: {}
};

let currentSection = ''; // 'player', 'team', 'standings'
let currentSubsection = '';

function parseTableRow(line) {
  const cells = line.split('|').map(c => c.trim()).filter(c => c);
  return cells;
}

function parsePercent(val) {
  return parseFloat(val.replace('%', '')) / 100;
}

function parseValue(val) {
  const match = val.match(/^([\d.]+)/);
  return match ? parseFloat(match[1]) : 0;
}

// 主解析循环
for (let i = 0; i < lines.length; i++) {
  const line = lines[i].trim();

  // 检测主要章节
  if (line === '## 一、积分榜（A-L组）') {
    currentSection = 'standings';
    currentSubsection = '';
    continue;
  } else if (line === '## 二、球员榜') {
    currentSection = 'player';
    currentSubsection = '';
    continue;
  } else if (line === '## 三、球队榜') {
    currentSection = 'team';
    currentSubsection = '';
    continue;
  }

  // 检测子标题 (### 开头)
  if (line.startsWith('### ')) {
    currentSubsection = line.replace('### ', '').trim();
    continue;
  }

  // 跳过空行和标题行
  if (!line || line.startsWith('#') || line.startsWith('---') || line.startsWith('|---') || line.startsWith('*共') || line.startsWith('| 排名')) {
    continue;
  }

  // 解析表格行
  if (line.startsWith('|') && currentSection && currentSubsection) {
    const cells = parseTableRow(line);

    if (currentSection === 'standings') {
      // 积分榜: 排名 | 球队 | 场次 | 胜 | 平 | 负 | 进球 | 失球 | 积分
      if (cells.length >= 9 && cells[0] && !cells[0].includes('排名')) {
        if (!data.standings[currentSubsection]) data.standings[currentSubsection] = [];
        data.standings[currentSubsection].push({
          rank: cells[0],
          team: cells[1],
          played: cells[2],
          wins: cells[3],
          draws: cells[4],
          losses: cells[5],
          gf: cells[6],
          ga: cells[7],
          points: cells[8]
        });
      }
    } else if (currentSection === 'player') {
      // 球员榜: 排名 | 球员 | 球队 | 数值
      if (cells.length >= 4 && cells[0] && !cells[0].includes('排名')) {
        if (!data.player[currentSubsection]) data.player[currentSubsection] = [];
        data.player[currentSubsection].push({
          rank: cells[0],
          name: cells[1],
          team: cells[2],
          value: cells[3]
        });
      }
    } else if (currentSection === 'team') {
      // 球队榜: 排名 | 球队 | 数值
      if (cells.length >= 3 && cells[0] && !cells[0].includes('排名')) {
        if (!data.team[currentSubsection]) data.team[currentSubsection] = [];
        data.team[currentSubsection].push({
          rank: cells[0],
          team: cells[1],
          value: cells[2]
        });
      }
    }
  }
}

// 输出统计
console.log('\n📊 解析结果:');
console.log('积分榜:', Object.keys(data.standings).length, '组');
console.log('球员榜:', Object.keys(data.player).length, '个类别');
console.log('球队榜:', Object.keys(data.team).length, '个类别');

// 详细统计
console.log('\n── 球员榜详情 ──');
var playerTotal = 0;
for (const [key, arr] of Object.entries(data.player)) {
  console.log(`  ${key}: ${arr.length} 条`);
  playerTotal += arr.length;
}
console.log(`  球员榜总计: ${playerTotal} 条`);

console.log('\n── 球队榜详情 ──');
var teamTotal = 0;
for (const [key, arr] of Object.entries(data.team)) {
  console.log(`  ${key}: ${arr.length} 条`);
  teamTotal += arr.length;
}
console.log(`  球队榜总计: ${teamTotal} 条`);

// 保存 JSON
fs.writeFileSync(outputFile, JSON.stringify(data, null, 2), 'utf-8');
console.log('\n✅ 已保存到:', outputFile);
