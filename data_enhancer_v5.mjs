/**
 * ⚽ 世界杯历史数据增强器 v5
 *
 * 直接从 ESPN 抓取并解析各队赛果表格
 * 
 * 用法: node data_enhancer_v5.mjs
 */

import * as fs from 'fs';
import * as path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const DB_PATH = path.join(__dirname, 'db', 'worldcup.json');

const ESPN_IDS = {
  '阿尔及利亚': 624, '阿根廷': 202, '澳大利亚': 628, '奥地利': 474,
  '比利时': 459, '波黑': 452, '巴西': 205, '加拿大': 206,
  '佛得角': 2597, '哥伦比亚': 208, '刚果(金)': 2850, '克罗地亚': 477,
  '库拉索': 11678, '捷克': 450, '厄瓜多尔': 209, '埃及': 2620,
  '英格兰': 448, '法国': 478, '德国': 481, '加纳': 4469,
  '海地': 2654, '伊朗': 469, '伊拉克': 4375, '科特迪瓦': 4789,
  '日本': 627, '约旦': 2917, '墨西哥': 203, '摩洛哥': 2869,
  '荷兰': 449, '新西兰': 2666, '挪威': 464, '巴拿马': 2659,
  '巴拉圭': 210, '葡萄牙': 482, '卡塔尔': 4398, '沙特阿拉伯': 655,
  '苏格兰': 580, '塞内加尔': 654, '南非': 467, '韩国': 451,
  '西班牙': 164, '瑞典': 466, '瑞士': 475, '突尼斯': 659,
  '土耳其': 465, '美国': 660, '乌拉圭': 212, '乌兹别克斯坦': 2570,
};

const NAME_MAP = {
  'Algeria':'阿尔及利亚','Argentina':'阿根廷','Australia':'澳大利亚',
  'Austria':'奥地利','Belgium':'比利时','Bosnia':'波黑',
  'Bosnia-Herzegovina':'波黑','Brazil':'巴西','Canada':'加拿大',
  'Cape Verde':'佛得角','Colombia':'哥伦比亚','Congo':'刚果(金)',
  'Congo DR':'刚果(金)','Croatia':'克罗地亚','Curacao':'库拉索',
  'Curaçao':'库拉索','Czechia':'捷克','Czech Republic':'捷克',
  'Ecuador':'厄瓜多尔','Egypt':'埃及','England':'英格兰',
  'France':'法国','Germany':'德国','Ghana':'加纳',
  'Haiti':'海地','Iran':'伊朗','Iraq':'伊拉克',
  'Ivory Coast':'科特迪瓦','Japan':'日本','Jordan':'约旦',
  'Mexico':'墨西哥','Morocco':'摩洛哥','Netherlands':'荷兰',
  'New Zealand':'新西兰','Norway':'挪威','Panama':'巴拿马',
  'Paraguay':'巴拉圭','Portugal':'葡萄牙','Qatar':'卡塔尔',
  'Saudi Arabia':'沙特阿拉伯','Scotland':'苏格兰','Senegal':'塞内加尔',
  'South Africa':'南非','South Korea':'韩国','Spain':'西班牙',
  'Sweden':'瑞典','Switzerland':'瑞士','Tunisia':'突尼斯',
  'Turkey':'土耳其','Turkiye':'土耳其','United States':'美国',
  'Uruguay':'乌拉圭','Uzbekistan':'乌兹别克斯坦',
  // 非参赛队
  'Iceland':'冰岛','Honduras':'洪都拉斯','Zambia':'赞比亚',
  'Mauritania':'毛里塔尼亚','Puerto Rico':'波多黎各','Venezuela':'委内瑞拉',
  'Chile':'智利','Peru':'秘鲁','Bolivia':'玻利维亚',
  'Angola':'安哥拉','Serbia':'塞尔维亚','Costa Rica':'哥斯达黎加',
  'Paraguay':'巴拉圭',
};

function cn(name) {
  return NAME_MAP[name] || name;
}

function loadDB() { return JSON.parse(fs.readFileSync(DB_PATH, 'utf8')); }
function saveDB(db) {
  db.meta.updatedAt = new Date().toISOString();
  fs.writeFileSync(DB_PATH, JSON.stringify(db, null, 2), 'utf8');
}

async function fetchESPNResults(espnId, teamCN) {
  const results = [];
  
  const slugs = {
    202:'argentina',205:'brazil',206:'canada',203:'mexico',
    448:'england',478:'france',481:'germany',164:'spain',
    482:'portugal',449:'netherlands',459:'belgium',212:'uruguay',
    477:'croatia',660:'united-states',2869:'morocco',208:'colombia',
    627:'japan',466:'sweden',475:'switzerland',464:'norway',
    654:'senegal',209:'ecuador',4789:'ivory-coast',474:'austria',
    450:'czechia',451:'south-korea',628:'australia',580:'scotland',
    2620:'egypt',469:'iran',624:'algeria',4469:'ghana',
    465:'turkiye',210:'paraguay',452:'bosnia-herzegovina',467:'south-africa',
    4398:'qatar',2850:'congo-dr',2659:'panama',2570:'uzbekistan',
    2917:'jordan',2654:'haiti',4375:'iraq',659:'tunisia',
    655:'saudi-arabia',2597:'cape-verde',2666:'new-zealand',11678:'curacao',
  };
  
  const slug = slugs[espnId] || '';
  const url = `https://www.espn.com/soccer/team/results/_/id/${espnId}/${slug}`;
  
  try {
    const res = await fetch(url, {
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept-Language': 'en-US,en;q=0.9',
      },
      signal: AbortSignal.timeout(15000)
    });
    if (!res.ok) return results;
    
    const html = await res.text();
    
    // 提取所有表格行
    const rows = html.match(/<tr[^>]*>[\s\S]*?<\/tr>/gi) || [];
    
    for (const row of rows) {
      if (row.includes('<th')) continue;
      
      const cells = row.match(/<td[^>]*>([\s\S]*?)<\/td>/gi);
      if (!cells || cells.length < 4) continue;
      
      const strip = (c) => c.replace(/<[^>]+>/g, '').replace(/&nbsp;/g, ' ').replace(/\s+/g, ' ').trim();
      
      // 第1列: 日期 "Mon, Jun 22"
      const dateRaw = strip(cells[0]);
      const monthDay = dateRaw.match(/(\w+\s+\d+)/);
      if (!monthDay) continue;
      
      // 确定年份: 用当前年份，检查月份逻辑
      // 如果月份 > 当前月份，说明是去年的比赛
      const now = new Date();
      let year = now.getFullYear();
      const monthAbbr = monthDay[1].split(' ')[0];
      const monthMap = {'Jan':0,'Feb':1,'Mar':2,'Apr':3,'May':4,'Jun':5,'Jul':6,'Aug':7,'Sep':8,'Oct':9,'Nov':10,'Dec':11};
      const monthIdx = monthMap[monthAbbr];
      if (monthIdx !== undefined && monthIdx > now.getMonth() + 2) {
        // 如果是6月看到10月的比赛，那应该是去年的
        year -= 1;
      }
      
      const d = new Date(`${monthDay[1]} ${year}`);
      if (isNaN(d.getTime())) continue;
      
      // 只保留2024年及之后的比赛
      if (d < new Date('2024-01-01') || d > new Date('2026-12-31')) continue;
      const fullDate = d.toISOString().slice(0, 10);
      
      // 提取比分: 找包含数字-数字的单元格
      let score = null, homeName = '', awayName = '';
      
      for (let i = 1; i < cells.length; i++) {
        const text = strip(cells[i]);
        const sm = text.match(/^(\d+)\s*[-–]\s*(\d+)$/);
        if (sm) {
          score = `${sm[1]}-${sm[2]}`;
          
          // 找主客队名: 比分前后的纯文本
          for (let j = 1; j < cells.length; j++) {
            const t = strip(cells[j]).replace(/^\d+[\.\)]\s*/, '');
            if (/^[A-Za-z][A-Za-z\s.\-']*$/.test(t) && t.length > 2 && !t.match(/^\d/)) {
              if (!homeName) homeName = t;
              else if (t !== homeName && !awayName) awayName = t;
            }
          }
          break;
        }
      }
      
      if (!score || !homeName || !awayName) continue;
      
      const cnHome = cn(homeName);
      const cnAway = cn(awayName);
      const [hG, aG] = score.split('-').map(Number);
      
      results.push({
        date: fullDate,
        home: cnHome, away: cnAway,
        score, homeScore: hG, awayScore: aG,
        venue: cnHome === teamCN ? '主' : (cnAway === teamCN ? '客' : '中'),
      });
    }
    
    return results;
    
  } catch (e) {
    return results;
  }
}

async function enhanceAll() {
  console.log('╔══════════════════════════════════════════════╗');
  console.log('║  ⚽ 世界杯历史数据增强器 v5');
  console.log('╚══════════════════════════════════════════════╝\n');
  
  const db = loadDB();
  const before = Object.values(db.recentMatches).reduce((s, m) => s + m.length, 0);
  console.log(`当前: ${Object.keys(db.teams).length} 队, ${before} 场\n`);
  
  let totalAdded = 0;
  let teamsDone = 0;
  const teams = Object.keys(ESPN_IDS);
  
  for (const teamCN of teams) {
    const espnId = ESPN_IDS[teamCN];
    const existing = db.recentMatches[teamCN] || [];
    const existingKeys = new Set(existing.map(m => m.opponent + '|' + m.date));
    
    process.stdout.write(`[${++teamsDone}/${teams.length}] ${teamCN}... `);
    
    const matches = await fetchESPNResults(espnId, teamCN);
    let added = 0;
    
    for (const m of matches) {
      const opponent = m.home === teamCN ? m.away : m.home;
      if (opponent === teamCN || !opponent) continue;
      
      const key = opponent + '|' + m.date;
      if (existingKeys.has(key)) continue;
      
      const [hG, aG] = m.score.split('-').map(Number);
      existing.push({
        date: m.date, opponent,
        score: m.venue === '主' ? m.score : `${aG}-${hG}`,
        venue: m.venue, competition: '国际赛',
        result: hG > aG ? '胜' : hG === aG ? '平' : '负',
      });
      existingKeys.add(key);
      added++;
    }
    
    if (added > 0) {
      existing.sort((a, b) => b.date.localeCompare(a.date));
      db.recentMatches[teamCN] = existing.slice(0, 50);
      totalAdded += added;
    }
    
    process.stdout.write(added > 0 ? `+${added} (共${db.recentMatches[teamCN].length}场)\n` : '0条\n');
    
    if (teamsDone % 10 === 0) await new Promise(r => setTimeout(r, 500));
  }
  
  console.log(`\n📊 抓取新增: ${totalAdded} 场`);
  
  // 更新 headToHead
  console.log('📊 更新 headToHead...');
  const h2h = {};
  for (const [team, matches] of Object.entries(db.recentMatches)) {
    for (const m of matches) {
      const [a, b] = [team, m.opponent].sort();
      const key = a + '|' + b;
      if (!h2h[key]) h2h[key] = { teamA: a, teamB: b, total: 0, aWins: 0, draws: 0, bWins: 0 };
      h2h[key].total++;
      const [hG, aG] = m.score.split('-').map(Number);
      if (hG > aG) { if (team === a) h2h[key].aWins++; else h2h[key].bWins++; }
      else if (hG === aG) h2h[key].draws++;
      else { if (team === a) h2h[key].bWins++; else h2h[key].aWins++; }
    }
  }
  db.headToHead = h2h;
  
  saveDB(db);
  
  const after = Object.values(db.recentMatches).reduce((s, m) => s + m.length, 0);
  console.log(`\n✅ 增强完成!`);
  console.log(`   比赛: ${before} → ${after} (新增 ${after-before})`);
  console.log(`   每队平均: ${(after/teams.length).toFixed(0)} 场`);
  console.log(`   headToHead: ${Object.keys(h2h).length} 对`);
}

enhanceAll().catch(e => { console.error('❌ 错误:', e); process.exit(1); });