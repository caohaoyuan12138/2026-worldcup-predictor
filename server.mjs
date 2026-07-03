#!/usr/bin/env node

/**
 * �?世界杯预�?- 后端服务�?v3.0
 * 
 * 融合模型: Elo + 泊松 + 经济�?+ 赔率市场
 * 
 * 启动: node server.mjs [端口]
 */

import * as fs from 'fs';
import * as path from 'path';
import * as http from 'http';
import * as url from 'url';
import * as os from 'os';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const engine = await import(new URL('model/engine.mjs', import.meta.url).href);
const db = await import(new URL('database.mjs', import.meta.url).href);

// ============================================================
// 数据�?// ============================================================
let dbData = loadDB();
let standingsCache = null;
let statsCache = null;
let eloInitialized = false;

function loadDB() {
  const dbPath = path.join(__dirname, 'db', 'worldcup.json');
  if (!fs.existsSync(dbPath)) {
    console.error('�?数据库不存在，请先运�? node db/init.mjs');
    process.exit(1);
  }
  return JSON.parse(fs.readFileSync(dbPath, 'utf8'));
}

function saveDB() {
  const dbPath = path.join(__dirname, 'db', 'worldcup.json');
  dbData.meta.updatedAt = new Date().toISOString();
  fs.writeFileSync(dbPath, JSON.stringify(dbData, null, 2), 'utf8');
  invalidateCache();
}

// ============================================================
// 预测日志系统 (prediction_log.jsonl)
// ============================================================
const LOG_PATH = path.join(__dirname, 'prediction_log.jsonl');

function appendPredictionLog(entry) {
  try {
    const line = JSON.stringify(entry) + 'config.monteCarloRuns || 10000n';
    fs.appendFileSync(LOG_PATH, line, 'utf8');
  } catch (e) {
    console.error('写入预测日志失败:', e.message);
  }
}

function readPredictionLog(limit = 200) {
  try {
    if (!fs.existsSync(LOG_PATH)) return [];
    const raw = fs.readFileSync(LOG_PATH, 'utf8');
    const lines = raw.trim().split('config.monteCarloRuns || 10000n').filter(Boolean);
    return lines.slice(-limit).map(line => {
      try { return JSON.parse(line); } catch(e) { return null; }
    }).filter(Boolean);
  } catch (e) {
    return [];
  }
}

function invalidateCache() {
  standingsCache = null;
  statsCache = null;
}

function getStandings() {
  if (!standingsCache) standingsCache = engine.computeStandings(dbData.completedMatches, dbData.groups);
  return standingsCache;
}

function getStats() {
  if (!statsCache) statsCache = engine.getStats(dbData.completedMatches);
  return statsCache;
}

/**
 * 初始�?更新 Elo 等级�? * 首次: 从排名初始化
 * 之后: 按已完赛结果更新
 */
function ensureElo() {
  if (eloInitialized) return;
  
  // 检查是否已�?Elo
  let hasElo = false;
  for (const t of Object.values(dbData.teams)) {
    if (t.eloRating !== undefined) { hasElo = true; break; }
  }
  
  if (!hasElo) {
    // 首次: �?rank 初始�?    for (const [name, t] of Object.entries(dbData.teams)) {
      t.eloRating = engine.rankToElo(t.rank || 50);
    }
  }
  
  // 按已完赛结果更新 Elo
  engine.batchUpdateElo(dbData.teams, dbData.completedMatches);
  saveDB();
  eloInitialized = true;
  console.log(`  �?Elo 已初始化: ${Object.keys(dbData.teams).length} 队`);
}

// ============================================================
// HTTP 服务�?// ============================================================
const PORT = parseInt(process.argv[2] || '3000', 10);

function sendJSON(res, data, status = 200) {
  res.writeHead(status, {
    'Content-Type': 'application/json; charset=utf-8',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type'
  });
  res.end(JSON.stringify(data));
}

function sendError(res, msg, status = 400) {
  sendJSON(res, { error: msg }, status);
}

function parseBody(req) {
  return new Promise((resolve, reject) => {
    let body = '';
    req.on('data', chunk => body += chunk);
    req.on('end', () => {
      try { resolve(body ? JSON.parse(body) : {}); }
      catch (e) { reject(new Error('Invalid JSON')); }
    });
  });
}

// ============================================================
// 预测日志分析引擎
// 对比预测日志中的预判与实际赛�? 分析各因素对判断的影�?// ============================================================
function analyzePredictionLog(currentReviewResults) {
  const logs = readPredictionLog(200).filter(l => l && l.fusionProb);
  if (logs.length === 0) return { message: '暂无有效预测日志记录' };
  
  const customCount = logs.filter(l => l.source === 'custom').length;
  const batchCount = logs.filter(l => l.source === 'batch').length;
  
  const logMatched = [];
  for (const log of logs) {
    const match = currentReviewResults.find(r => r.home === log.home && r.away === log.away);
    if (match) {
      const logTopResult = log.fusionProb.winPct >= log.fusionProb.drawPct && log.fusionProb.winPct >= log.fusionProb.awayPct ? 'home'
        : log.fusionProb.drawPct >= log.fusionProb.winPct && log.fusionProb.drawPct >= log.fusionProb.awayPct ? 'draw'
        : 'away';
      logMatched.push({
        match: log.match, source: log.source,
        topPredictions: log.topPredictions,
        fusionProb: log.fusionProb, modelProb: log.modelProb,
        weights: log.weights, config: log.config,
        teamUrgency: log.teamUrgency, hasOdds: log.hasOdds, handicap: log.handicap,
        actualScore: match.score, actualResult: match.actualResult,
        logPredResult: logTopResult,
        correct: logTopResult === match.actualResult,
      });
    }
  }
  
  const factors = [];
  const avgElo = logs.reduce((s, l) => s + (l.weights?.elo || 0), 0) / logs.length;
  const avgPoisson = logs.reduce((s, l) => s + (l.weights?.poisson || 0), 0) / logs.length;
  const avgMarket = logs.reduce((s, l) => s + (l.weights?.market || 0), 0) / logs.length;
  factors.push({ name: '融合权重', value: 'Elo ' + (avgElo*100).toFixed(0) + '% / Poisson ' + (avgPoisson*100).toFixed(0) + '% / Market ' + (avgMarket*100).toFixed(0) + '%' });
  
  const avgRho = logs.reduce((s, l) => s + (l.config?.dcRho || 0), 0) / logs.length;
  factors.push({ name: 'Dixon-Coles config.monteCarloRuns || 10000u03c1', value: avgRho.toFixed(3) });
  
  const withOddsLogs = logMatched.filter(l => l.hasOdds);
  const noOddsLogs = logMatched.filter(l => !l.hasOdds);
  if (withOddsLogs.length > 0) {
    const woC = withOddsLogs.filter(l => l.correct).length;
    factors.push({ name: '有赔率准确率', value: woC + '/' + withOddsLogs.length + ' (' + (woC/withOddsLogs.length*100).toFixed(0) + '%)' });
  }
  if (noOddsLogs.length > 0) {
    const noC = noOddsLogs.filter(l => l.correct).length;
    factors.push({ name: '无赔率准确率', value: noC + '/' + noOddsLogs.length + ' (' + (noC/noOddsLogs.length*100).toFixed(0) + '%)' });
  }
  
  const wrongDrawLogs = logMatched.filter(l => !l.correct && l.actualResult === 'draw');
  if (wrongDrawLogs.length > 0) {
    const avgDP = wrongDrawLogs.reduce((s, l) => s + l.fusionProb.drawPct, 0) / wrongDrawLogs.length;
    const avgHP = wrongDrawLogs.reduce((s, l) => s + l.fusionProb.winPct, 0) / wrongDrawLogs.length;
    factors.push({ name: '平局误判平均概率', value: '主胜' + avgHP.toFixed(1) + '% / �? + avgDP.toFixed(1) + '%' });
  }
  
  const top1C = logMatched.filter(l => l.topPredictions?.[0]?.score === l.actualScore).length;
  if (logMatched.length > 0) {
    factors.push({ name: 'top1比分精确�?, value: top1C + '/' + logMatched.length + ' (' + (top1C/logMatched.length*100).toFixed(1) + '%)' });
  }
  
  return {
    totalLogs: logs.length, customPredictions: customCount, batchPredictions: batchCount,
    matchedWithResults: logMatched.length,
    matchedCorrect: logMatched.filter(l => l.correct).length,
    matchedCorrectPct: logMatched.length > 0 ? +((logMatched.filter(l => l.correct).length / logMatched.length) * 100).toFixed(1) : 0,
    keyFactors: factors,
    recentLogs: logs.slice(-10).map(l => ({
      timestamp: l.timestamp, match: l.match, source: l.source,
      top1: (l.topPredictions?.[0]?.score || '?') + '(' + (l.topPredictions?.[0]?.pct || '?') + '%)',
      fusion: l.fusionProb.winPct + '/' + l.fusionProb.drawPct + '/' + l.fusionProb.awayPct
    })),
    wrongDrawDetails: wrongDrawLogs.slice(0, 5).map(l => ({
      match: l.match,
      predicted: l.fusionProb.winPct + '/' + l.fusionProb.drawPct + '/' + l.fusionProb.awayPct,
      actual: l.actualScore + '(' + l.actualResult + ')',
      top1: (l.topPredictions?.[0]?.score || '?') + '(' + (l.topPredictions?.[0]?.pct || '?') + '%)'
    }))
  };
}

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'application/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon',
};

function getLocalIP() {
  const nets = os.networkInterfaces();
  for (const name of Object.keys(nets)) {
    for (const net of nets[name]) {
      if (net.family === 'IPv4' && !net.internal) return net.address;
    }
  }
  return '127.0.0.1';
}

// ============================================================
// API 路由
// ============================================================
async function handleRequest(req, res) {
  const parsedUrl = new URL(req.url, 'http://localhost');
  const pathname = parsedUrl.pathname;
  const queryParams = Object.fromEntries(parsedUrl.searchParams.entries());
  const method = req.method;

  if (method === 'OPTIONS') {
    res.writeHead(204, {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type'
    });
    res.end();
    return;
  }

  try {
    // ========================================
    // 1. 系统状�?    // ========================================
    if (pathname === '/api/status' && method === 'GET') {
      ensureElo();
// ============================================================
// 19-25. 新增 Oracle V2 API 端点
// ============================================================
if (pathname === "/api/trends" && method === "GET") {
  const trendsPath = path.join(__dirname, "data_local", "trends.json");
  if (fs.existsSync(trendsPath)) {
    sendJSON(res, JSON.parse(fs.readFileSync(trendsPath, "utf8")));
  } else {
    try { const tg = await import("./trend_generator.mjs"); sendJSON(res, tg.generateTrends()); } catch(e) { sendJSON(res, { error: e.message }); }
  }
  return;
}
if (pathname === "/api/quality" && method === "GET") {
  try { const dq = await import("./data_quality.mjs"); sendJSON(res, dq.assessDataQuality()); } catch(e) { sendJSON(res, { error: e.message }); }
  return;
}
if (pathname === "/api/sync" && method === "POST") {
  try { const ss = await import("./sync_service.mjs"); const r = ss.runSync(); sendJSON(res, { success: true, result: r }); } catch(e) { sendJSON(res, { error: e.message }); }
  return;
}
if (pathname === "/api/update" && method === "POST") {
  try { const au = await import("./auto_update.mjs"); const r = au.autoUpdate(); sendJSON(res, { success: true, result: r }); } catch(e) { sendJSON(res, { error: e.message }); }
  return;
}
if (pathname === "/api/queue" && method === "GET") {
  try { const ss = await import("./sync_service.mjs"); sendJSON(res, ss.getQueue()); } catch(e) { sendJSON(res, []); }
  return;
}
if (pathname === "/api/queue/approve" && method === "POST") {
  try { const ss = await import("./sync_service.mjs"); sendJSON(res, ss.approveFirst()); } catch(e) { sendJSON(res, { error: e.message }); }
  return;
}
if (pathname === "/api/audit" && method === "GET") {
  const auditPath = path.join(__dirname, "data_local", "audit_log.jsonl");
  if (fs.existsSync(auditPath)) {
    const logs = fs.readFileSync(auditPath, "utf8").split("\n").filter(Boolean).slice(-50);
    sendJSON(res, logs.map(l => JSON.parse(l)));
  } else { sendJSON(res, []); }
  return;
}
