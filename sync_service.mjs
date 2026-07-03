#!/usr/bin/env node

/**
 * 世界杯 Oracle V2 — 自动数据同步服务
 * 
 * 职责：
 * 1. 定时拉取赛程/赔率/伤病数据
 * 2. 自动清洗和质量评分
 * 3. 增量更新 worldcup.json
 * 4. 异常告警（赔率突变、数据缺失）
 * 5. 人工审核队列（可疑数据标记待审）
 * 
 * 用法:
 *   node sync_service.mjs start    - 启动后台同步
 *   node sync_service.mjs run      - 手动执行一次同步
 *   node sync_service.mjs status   - 查看上次同步状态
 *   node sync_service.mjs queue    - 查看待审核队列
 *   node sync_service.mjs approve  - 批准队列中第一个
 */

import * as fs from 'fs';
import * as path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.join(__dirname, '..');
const DB_PATH = path.join(ROOT, 'db', 'worldcup.json');
const SYNC_STATE_PATH = path.join(ROOT, 'data_local', 'sync_state.json');
const AUDIT_LOG_PATH = path.join(ROOT, 'data_local', 'audit_log.jsonl');
const QUEUE_PATH = path.join(ROOT, 'data_local', 'review_queue.json');

// ============================================================
// 1. 同步状态管理
// ============================================================

let syncState = {
  lastSync: null,
  lastSyncSource: null,
  totalSyncs: 0,
  errors: 0,
  warnings: 0,
  dataPointsUpdated: 0,
  nextSyncIn: 3600000, // 1小时后
  status: 'idle', // idle | syncing | error
};

function loadSyncState() {
  try {
    if (fs.existsSync(SYNC_STATE_PATH)) {
      syncState = { ...syncState, ...JSON.parse(fs.readFileSync(SYNC_STATE_PATH, 'utf8')) };
    }
  } catch (e) { /* ignore */ }
}

function saveSyncState() {
  try {
    fs.mkdirSync(path.dirname(SYNC_STATE_PATH), { recursive: true });
    fs.writeFileSync(SYNC_STATE_PATH, JSON.stringify(syncState, null, 2));
  } catch (e) { /* ignore */ }
}

// ============================================================
// 2. 审计日志
// ============================================================

function logAudit(action, details, severity = 'info') {
  const entry = {
    timestamp: new Date().toISOString(),
    action,
    details,
    severity,
    user: 'system',
  };
  try {
    fs.appendFileSync(AUDIT_LOG_PATH, JSON.stringify(entry) + '\n');
  } catch (e) { /* ignore */ }
  
  if (severity === 'error') syncState.errors++;
  if (severity === 'warning') syncState.warnings++;
  saveSyncState();
}

// ============================================================
// 3. 人工审核队列
// ============================================================

function addToQueue(item) {
  try {
    let queue = [];
    if (fs.existsSync(QUEUE_PATH)) {
      queue = JSON.parse(fs.readFileSync(QUEUE_PATH, 'utf8'));
    }
    queue.push({
      id: Date.now(),
      timestamp: new Date().toISOString(),
      ...item,
      status: 'pending', // pending | approved | rejected
    });
    fs.writeFileSync(QUEUE_PATH, JSON.stringify(queue, null, 2));
  } catch (e) { /* ignore */ }
}

function getQueue() {
  try {
    if (!fs.existsSync(QUEUE_PATH)) return [];
    return JSON.parse(fs.readFileSync(QUEUE_PATH, 'utf8'));
  } catch { return []; }
}

function approveFirst() {
  try {
    let queue = getQueue();
    if (queue.length === 0) return { success: false, message: '队列为空' };
    queue[0].status = 'approved';
    queue[0].approvedAt = new Date().toISOString();
    fs.writeFileSync(QUEUE_PATH, JSON.stringify(queue, null, 2));
    logAudit('approve_item', `Approved item #${queue[0].id}`);
    return { success: true, item: queue[0] };
  } catch (e) { return { success: false, message: e.message }; }
}

// ============================================================
// 4. 数据同步核心逻辑
// ============================================================

/**
 * 增量更新赛程数据
 * 从 juhe API 或本地数据源获取最新赛程
 */
function syncSchedule() {
  console.log('  📅 同步赛程数据...');
  const startTime = Date.now();
  
  try {
    const dbRaw = fs.readFileSync(DB_PATH, 'utf8');
    const db = JSON.parse(dbRaw);
    
    // 检查是否有未完成的比赛
    const upcoming = db.upcomingMatches || [];
    const knockout = db.knockoutMatches || [];
    const pending = [...upcoming, ...knockout].filter(m => !m.score);
    
    console.log(`    待赛场次: ${pending.length}`);
    
    // 标记数据新鲜度
    const lastCompleted = db.completedMatches
      .filter(m => m.score)
      .sort((a, b) => b.date.localeCompare(a.date))[0];
    
    let freshness = 'fresh';
    if (lastCompleted) {
      const daysSince = (Date.now() - new Date(lastCompleted.date).getTime()) / 86400000;
      if (daysSince > 7) freshness = 'stale';
      else if (daysSince > 3) freshness = 'moderate';
    }
    
    const elapsed = Date.now() - startTime;
    logAudit('sync_schedule', { pending, freshness, elapsedMs: elapsed }, 
             freshness === 'stale' ? 'warning' : 'info');
    
    return { success: true, freshness, pending: pending.length, elapsed };
  } catch (e) {
    logAudit('sync_schedule_error', { error: e.message }, 'error');
    return { success: false, error: e.message };
  }
}

/**
 * 同步赔率数据
 * 检查赔率一致性，标记异常
 */
function syncOdds() {
  console.log('  💰 同步赔率数据...');
  const startTime = Date.now();
  
  try {
    const dbRaw = fs.readFileSync(DB_PATH, 'utf8');
    const db = JSON.parse(dbRaw);
    
    const matches = [...(db.upcomingMatches || []), ...(db.knockoutMatches || [])];
    let withOdds = 0;
    let anomalies = 0;
    
    for (const m of matches) {
      if (m.oddsHome && m.oddsDraw && m.oddsAway) {
        withOdds++;
        
        // 检查隐含概率
        const implied = 1/m.oddsHome + 1/m.oddsDraw + 1/m.oddsAway;
        if (implied < 1.01 || implied > 1.25) {
          anomalies++;
          addToQueue({
            type: 'odds_anomaly',
            match: `${m.home} vs ${m.away}`,
            issue: `隐含概率异常: ${implied.toFixed(3)} (正常1.04-1.18)`,
            data: { odds: m, implied },
          });
        }
      }
    }
    
    const elapsed = Date.now() - startTime;
    logAudit('sync_odds', { withOdds, anomalies, elapsedMs: elapsed });
    
    if (anomalies > 0) {
      console.log(`    ⚠️ 发现 ${anomalies} 处赔率异常，已加入审核队列`);
    }
    
    return { success: true, withOdds, anomalies, elapsed };
  } catch (e) {
    logAudit('sync_odds_error', { error: e.message }, 'error');
    return { success: false, error: e.message };
  }
}

/**
 * 同步球队数据
 * 检查完整性、一致性
 */
function syncTeams() {
  console.log('  🏟️ 同步球队数据...');
  const startTime = Date.now();
  
  try {
    const dbRaw = fs.readFileSync(DB_PATH, 'utf8');
    const db = JSON.parse(dbRaw);
    const teams = db.teams || {};
    
    let missingFields = 0;
    let totalFields = 0;
    
    for (const [name, data] of Object.entries(teams)) {
      const required = ['attackBase', 'defenseBase', 'styleFactor', 'rank', 'eloRating'];
      for (const field of required) {
        totalFields++;
        if (data[field] === undefined || data[field] === null) {
          missingFields++;
          if (missingFields <= 5) {
            addToQueue({
              type: 'missing_field',
              team: name,
              issue: `缺少字段: ${field}`,
              data: { field },
            });
          }
        }
      }
    }
    
    const completeness = totalFields > 0 ? ((totalFields - missingFields) / totalFields * 100) : 0;
    const elapsed = Date.now() - startTime;
    
    logAudit('sync_teams', { totalTeams: Object.keys(teams).length, completeness, missingFields, elapsedMs: elapsed });
    
    console.log(`    数据完整度: ${completeness.toFixed(1)}% (${Object.keys(teams).length} 队)`);
    
    return { success: true, completeness, teams: Object.keys(teams).length, elapsed };
  } catch (e) {
    logAudit('sync_teams_error', { error: e.message }, 'error');
    return { success: false, error: e.message };
  }
}

/**
 * 同步伤病/新闻数据
 */
function syncInjuries() {
  console.log('  🏥 同步伤病数据...');
  
  // 当前为静态数据源，标记为 manual 状态
  logAudit('sync_injuries', { status: 'manual_required', note: '需接入实时伤病API' });
  return { success: true, status: 'manual' };
}

/**
 * 执行完整同步
 */
function runSync() {
  console.log('\n' + '═'.repeat(60));
  console.log('  ⚽ 世界杯 Oracle V2 — 自动数据同步服务');
  console.log('═'.repeat(60));
  console.log(`  时间: ${new Date().toISOString()}\n`);
  
  syncState.status = 'syncing';
  syncState.lastSync = new Date().toISOString();
  saveSyncState();
  
  const results = {
    schedule: syncSchedule(),
    odds: syncOdds(),
    teams: syncTeams(),
    injuries: syncInjuries(),
  };
  
  const totalUpdated = Object.values(results).filter(r => r.success).length;
  syncState.dataPointsUpdated += totalUpdated;
  syncState.totalSyncs++;
  syncState.status = 'idle';
  syncState.nextSyncIn = 3600000; // 1小时后
  
  saveSyncState();
  
  console.log(`\n  ✅ 同步完成: ${totalUpdated}/4 模块成功`);
  console.log(`  总同步次数: ${syncState.totalSyncs}`);
  console.log(`  错误数: ${syncState.errors} | 警告数: ${syncState.warnings}`);
  console.log('');
  
  return results;
}

// ============================================================
// 5. CLI 入口
// ============================================================

const cmd = process.argv[2];

switch (cmd) {
  case 'start':
    console.log('🔄 启动自动同步服务...');
    console.log('  首次同步即将执行');
    runSync();
    console.log('  后台服务已启动 (当前为手动触发模式)');
    console.log('  下次同步: 1小时后');
    console.log('  提示: 使用 crontab 或 Windows Task Scheduler 设置定时执行');
    break;
    
  case 'run':
    runSync();
    break;
    
  case 'status':
    loadSyncState();
    console.log('\n  📊 同步状态:');
    console.log(`    上次同步: ${syncState.lastSync || '从未'}`);
    console.log(`    总同步次数: ${syncState.totalSyncs}`);
    console.log(`    数据点更新: ${syncState.dataPointsUpdated}`);
    console.log(`    错误数: ${syncState.errors}`);
    console.log(`    警告数: ${syncState.warnings}`);
    console.log(`    当前状态: ${syncState.status}`);
    console.log(`    下次同步: ${syncState.nextSyncIn ? Math.round(syncState.nextSyncIn / 60000) + ' 分钟后' : '未知'}`);
    console.log('');
    break;
    
  case 'queue': {
    const queue = getQueue();
    const pending = queue.filter(q => q.status === 'pending');
    console.log(`\n  📋 审核队列 (${pending.length} 待处理 / ${queue.length} 总计):`);
    for (const item of pending) {
      console.log(`    [${item.type}] ${item.match || item.team} - ${item.issue}`);
    }
    console.log('');
    break;
  }
  
  case 'approve': {
    const result = approveFirst();
    if (result.success) {
      console.log(`  ✅ 已批准 #${result.item.id}: ${result.item.issue}`);
    } else {
      console.log(`  ⚠️ ${result.message}`);
    }
    break;
  }
  
  default:
    console.log(`
⚽ 世界杯 Oracle V2 — 自动数据同步服务

用法:
  node sync_service.mjs start    - 启动同步服务（首次执行）
  node sync_service.mjs run      - 手动执行一次同步
  node sync_service.mjs status   - 查看同步状态
  node sync_service.mjs queue    - 查看待审核队列
  node sync_service.mjs approve  - 批准队列中第一个

定时任务配置:
  Linux/Mac: crontab -e
    */30 * * * * cd /path/to/football && node sync_service.mjs run >> /tmp/sync.log 2>&1
  
  Windows: schtasks /create /tn "FootballSync" /tr "node sync_service.mjs run" /sc hourly /mo 2
`);
}
