#!/usr/bin/env node

/**
 * ⚽ 经济学数据填充脚本
 * 
 * 从公开数据源获取 48 国的 GDP per capita、人口、气候、海拔
 * 写入 worldcup.json
 */

import * as fs from 'fs';
import * as path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const dbPath = path.join(__dirname, 'worldcup.json');

if (!fs.existsSync(dbPath)) {
  console.error('❌ 数据库不存在，请先运行 init.mjs');
  process.exit(1);
}

const db = JSON.parse(fs.readFileSync(dbPath, 'utf8'));

// ============================================================
// 48 国经济学数据
// 来源: IMF 2025-2026, World Bank, 地理常识
// 人口: 百万  |  GDP per capita: 美元(PPP)  |  气候: 热带/温带/寒带/干旱
// 海拔: 主场平均海拔(米)  |  东道主: true/false
// ============================================================

const economicData = {
  '阿根廷': { population: 45.8, gdpPerCapita: 26800, climate: '温带', avgAltitude: 25, isHost: false },
  '法国':   { population: 68.0, gdpPerCapita: 58700, climate: '温带', avgAltitude: 35, isHost: false },
  '巴西':   { population: 216.0, gdpPerCapita: 18200, climate: '热带', avgAltitude: 760, isHost: false },  // 巴西利亚高原
  '英格兰': { population: 57.0, gdpPerCapita: 52500, climate: '温带', avgAltitude: 25, isHost: false },    // 单独算英格兰
  '德国':   { population: 84.6, gdpPerCapita: 61200, climate: '温带', avgAltitude: 35, isHost: false },
  '西班牙': { population: 47.8, gdpPerCapita: 45800, climate: '温带', avgAltitude: 660, isHost: false },   // 马德里高原
  '葡萄牙': { population: 10.3, gdpPerCapita: 41200, climate: '温带', avgAltitude: 100, isHost: false },
  '荷兰':   { population: 17.8, gdpPerCapita: 67700, climate: '温带', avgAltitude: 5, isHost: false },
  '比利时': { population: 11.7, gdpPerCapita: 60500, climate: '温带', avgAltitude: 15, isHost: false },
  '乌拉圭': { population: 3.4, gdpPerCapita: 26500, climate: '温带', avgAltitude: 50, isHost: false },
  '克罗地亚': { population: 3.9, gdpPerCapita: 39500, climate: '温带', avgAltitude: 150, isHost: false },
  '美国':   { population: 349.0, gdpPerCapita: 94400, climate: '温带', avgAltitude: 30, isHost: true },    // 东道主
  '摩洛哥': { population: 37.7, gdpPerCapita: 9800, climate: '干旱', avgAltitude: 250, isHost: false },
  '哥伦比亚': { population: 52.2, gdpPerCapita: 19300, climate: '热带', avgAltitude: 2640, isHost: false }, // 波哥大高海拔
  '墨西哥': { population: 129.0, gdpPerCapita: 24800, climate: '温带', avgAltitude: 2240, isHost: true },  // 东道主，墨西哥城高海拔
  '日本':   { population: 123.0, gdpPerCapita: 45000, climate: '温带', avgAltitude: 40, isHost: false },
  '瑞典':   { population: 10.6, gdpPerCapita: 60800, climate: '寒带', avgAltitude: 15, isHost: false },
  '瑞士':   { population: 8.9, gdpPerCapita: 92000, climate: '温带', avgAltitude: 550, isHost: false },
  '挪威':   { population: 5.5, gdpPerCapita: 93500, climate: '寒带', avgAltitude: 10, isHost: false },
  '加拿大': { population: 40.0, gdpPerCapita: 58000, climate: '寒带', avgAltitude: 110, isHost: true },   // 东道主
  '塞内加尔': { population: 18.0, gdpPerCapita: 4200, climate: '热带', avgAltitude: 15, isHost: false },
  '厄瓜多尔': { population: 18.3, gdpPerCapita: 13800, climate: '热带', avgAltitude: 2850, isHost: false }, // 基多高海拔
  '科特迪瓦': { population: 30.0, gdpPerCapita: 6300, climate: '热带', avgAltitude: 50, isHost: false },
  '奥地利': { population: 9.2, gdpPerCapita: 61500, climate: '温带', avgAltitude: 170, isHost: false },
  '捷克':   { population: 10.8, gdpPerCapita: 49300, climate: '温带', avgAltitude: 200, isHost: false },
  '韩国':   { population: 51.7, gdpPerCapita: 47500, climate: '温带', avgAltitude: 30, isHost: false },
  '澳大利亚': { population: 26.6, gdpPerCapita: 66000, climate: '干旱', avgAltitude: 30, isHost: false },
  '苏格兰': { population: 5.5, gdpPerCapita: 52000, climate: '寒带', avgAltitude: 20, isHost: false },    // 按英国人均
  '埃及':   { population: 116.0, gdpPerCapita: 14200, climate: '干旱', avgAltitude: 20, isHost: false },
  '伊朗':   { population: 89.0, gdpPerCapita: 18700, climate: '干旱', avgAltitude: 1200, isHost: false },  // 德黑兰高原
  '阿尔及利亚': { population: 45.0, gdpPerCapita: 13400, climate: '干旱', avgAltitude: 350, isHost: false },
  '加纳':   { population: 33.5, gdpPerCapita: 6200, climate: '热带', avgAltitude: 30, isHost: false },
  '土耳其': { population: 85.0, gdpPerCapita: 39600, climate: '温带', avgAltitude: 120, isHost: false },
  '巴拉圭': { population: 6.8, gdpPerCapita: 15800, climate: '热带', avgAltitude: 120, isHost: false },
  '波黑':   { population: 3.2, gdpPerCapita: 18500, climate: '温带', avgAltitude: 500, isHost: false },
  '南非':   { population: 60.0, gdpPerCapita: 15600, climate: '温带', avgAltitude: 1750, isHost: false },  // 约翰内斯堡高海拔
  '卡塔尔': { population: 2.8, gdpPerCapita: 112000, climate: '干旱', avgAltitude: 5, isHost: false },
  '刚果(金)': { population: 105.0, gdpPerCapita: 1500, climate: '热带', avgAltitude: 400, isHost: false },
  '巴拿马': { population: 4.5, gdpPerCapita: 35500, climate: '热带', avgAltitude: 30, isHost: false },
  '乌兹别克斯坦': { population: 36.0, gdpPerCapita: 10500, climate: '干旱', avgAltitude: 300, isHost: false },
  '约旦':   { population: 11.5, gdpPerCapita: 12700, climate: '干旱', avgAltitude: 800, isHost: false },
  '海地':   { population: 11.7, gdpPerCapita: 3200, climate: '热带', avgAltitude: 50, isHost: false },
  '伊拉克': { population: 45.0, gdpPerCapita: 12800, climate: '干旱', avgAltitude: 100, isHost: false },
  '突尼斯': { population: 12.5, gdpPerCapita: 13200, climate: '干旱', avgAltitude: 20, isHost: false },
  '沙特阿拉伯': { population: 33.0, gdpPerCapita: 66800, climate: '干旱', avgAltitude: 600, isHost: false },
  '佛得角': { population: 0.52, gdpPerCapita: 8200, climate: '热带', avgAltitude: 100, isHost: false },
  '新西兰': { population: 5.2, gdpPerCapita: 48000, climate: '温带', avgAltitude: 10, isHost: false },
  '库拉索': { population: 0.16, gdpPerCapita: 28000, climate: '热带', avgAltitude: 10, isHost: false },
};

// 验证覆盖
let missing = [];
for (const name of Object.keys(db.teams)) {
  if (!economicData[name]) missing.push(name);
}
if (missing.length > 0) {
  console.error('❌ 缺失以下球队的经济学数据:', missing.join(', '));
  process.exit(1);
}

// 写入数据库
for (const [name, data] of Object.entries(economicData)) {
  if (db.teams[name]) {
    db.teams[name].population = data.population;
    db.teams[name].gdpPerCapita = data.gdpPerCapita;
    db.teams[name].climate = data.climate;
    db.teams[name].avgAltitude = data.avgAltitude;
    db.teams[name].isHost = data.isHost;
  }
}

// 统计
const stats = {
  teamsWithEco: Object.keys(economicData).length,
  avgGdp: Object.values(economicData).reduce((s, d) => s + d.gdpPerCapita, 0) / Object.keys(economicData).length,
  maxGdp: Math.max(...Object.values(economicData).map(d => d.gdpPerCapita)),
  minGdp: Math.min(...Object.values(economicData).map(d => d.gdpPerCapita)),
  hosts: Object.entries(economicData).filter(([_, d]) => d.isHost).map(([n]) => n),
  climates: [...new Set(Object.values(economicData).map(d => d.climate))],
};

fs.writeFileSync(dbPath, JSON.stringify(db, null, 2), 'utf8');
console.log('✅ 经济学数据已写入 worldcup.json');
console.log('');
console.log(`   球队数: ${stats.teamsWithEco}`);
console.log(`   平均GDP: $${Math.round(stats.avgGdp).toLocaleString()}`);
console.log(`   最高GDP: $${stats.maxGdp.toLocaleString()} (卡塔尔)`);
console.log(`   最低GDP: $${stats.minGdp.toLocaleString()} (刚果金)`);
console.log(`   东道主: ${stats.hosts.join(', ')}`);
console.log(`   气候类型: ${stats.climates.join(', ')}`);