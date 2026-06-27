#!/usr/bin/env node

/**
 * ⚽ 世界杯预测 - 后端服务器 v3.0
 * 
 * 融合模型: Elo + 泊松 + 经济学 + 赔率市场
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

// ============================================================
// 数据库
// ============================================================
let dbData = loadDB();
let standingsCache = null;
let statsCache = null;
let eloInitialized = false;

function loadDB() {
  const dbPath = path.join(__dirname, 'db', 'worldcup.json');
  if (!fs.existsSync(dbPath)) {
    console.error('❌ 数据库不存在，请先运行: node db/init.mjs');
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
    const line = JSON.stringify(entry) + '\n';
    fs.appendFileSync(LOG_PATH, line, 'utf8');
  } catch (e) {
    console.error('写入预测日志失败:', e.message);
  }
}

function readPredictionLog(limit = 200) {
  try {
    if (!fs.existsSync(LOG_PATH)) return [];
    const raw = fs.readFileSync(LOG_PATH, 'utf8');
    const lines = raw.trim().split('\n').filter(Boolean);
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
 * 初始化/更新 Elo 等级分
 * 首次: 从排名初始化
 * 之后: 按已完赛结果更新
 */
function ensureElo() {
  if (eloInitialized) return;
  
  // 检查是否已有 Elo
  let hasElo = false;
  for (const t of Object.values(dbData.teams)) {
    if (t.eloRating !== undefined) { hasElo = true; break; }
  }
  
  if (!hasElo) {
    // 首次: 从 rank 初始化
    for (const [name, t] of Object.entries(dbData.teams)) {
      t.eloRating = engine.rankToElo(t.rank || 50);
    }
  }
  
  // 按已完赛结果更新 Elo
  engine.batchUpdateElo(dbData.teams, dbData.completedMatches);
  saveDB();
  eloInitialized = true;
  console.log(`  ⚡ Elo 已初始化: ${Object.keys(dbData.teams).length} 队`);
}

// ============================================================
// HTTP 服务器
// ============================================================
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
// 对比预测日志中的预判与实际赛果, 分析各因素对判断的影响
// ============================================================
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
  factors.push({ name: 'Dixon-Coles \u03c1', value: avgRho.toFixed(3) });
  
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
    factors.push({ name: '平局误判平均概率', value: '主胜' + avgHP.toFixed(1) + '% / 平' + avgDP.toFixed(1) + '%' });
  }
  
  const top1C = logMatched.filter(l => l.topPredictions?.[0]?.score === l.actualScore).length;
  if (logMatched.length > 0) {
    factors.push({ name: 'top1比分精确率', value: top1C + '/' + logMatched.length + ' (' + (top1C/logMatched.length*100).toFixed(1) + '%)' });
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
    // 1. 系统状态
    // ========================================
    if (pathname === '/api/status' && method === 'GET') {
      ensureElo();
      const stats = getStats();
      sendJSON(res, {
        meta: dbData.meta,
        stats,
        teamCount: Object.keys(dbData.teams).length,
        groupCount: Object.keys(dbData.groups).length,
        completedCount: dbData.completedMatches.filter(m => m.score).length,
        upcomingCount: dbData.upcomingMatches.length,
        knockoutCount: dbData.knockoutMatches.length,
        modelVersion: 'v3.0-fusion',
        fusionWeights: dbData.modelConfig?.fusionWeights || {
          elo: 0.25, poisson: 0.30, economic: 0.10, market: 0.35
        }
      });
      return;
    }

    // ========================================
    // 2. 球队列表
    // ========================================
    if (pathname === '/api/teams' && method === 'GET') {
      ensureElo();
      const group = queryParams.group;
      let teams = Object.entries(dbData.teams).map(([name, data]) => ({
        name, ...data, group: dbData.teamGroup[name] || ''
      }));
      if (group) teams = teams.filter(t => t.group === group);
      teams.sort((a, b) => (a.rank || 99) - (b.rank || 99));
      sendJSON(res, teams);
      return;
    }

    // ========================================
    // 3. 单支球队
    // ========================================
    if (pathname.startsWith('/api/teams/') && method === 'GET') {
      const name = decodeURIComponent(pathname.slice(11));
      const team = dbData.teams[name];
      if (!team) return sendError(res, '球队不存在', 404);
      sendJSON(res, { name, ...team, group: dbData.teamGroup[name] || '' });
      return;
    }

    // ========================================
    // 4. 更新球队
    // ========================================
    if (pathname.startsWith('/api/teams/') && method === 'PUT') {
      const name = decodeURIComponent(pathname.slice(11));
      if (!dbData.teams[name]) return sendError(res, '球队不存在', 404);
      const body = await parseBody(req);
      const allowedFields = [
        'attackBase', 'defenseBase', 'style', 'styleFactor', 'rank',
        'attackThirdPassPct', 'shotConversion', 'possessionStyle', 'defenseIntercept',
        'eloRating', 'top50Scorers', 'worldCupTitles'
      ];
      for (const field of allowedFields) {
        if (body[field] !== undefined) dbData.teams[name][field] = body[field];
      }
      saveDB();
      sendJSON(res, { success: true, team: { name, ...dbData.teams[name] } });
      return;
    }

    // ========================================
    // 5. 分组+积分榜
    // ========================================
    if (pathname === '/api/groups' && method === 'GET') {
      const standings = getStandings();
      const groupData = {};
      for (const [g, teams] of Object.entries(dbData.groups)) {
        const gs = teams.map(t => standings[t]).filter(Boolean)
          .sort((a, b) => b.p - a.p || b.gd - a.gd || b.gf - a.gf);
        groupData[g] = { teams: gs };
      }
      sendJSON(res, { groups: dbData.groups, standings: groupData });
      return;
    }

    // ========================================
    // 6. 比赛数据
    // ========================================
    if (pathname === '/api/matches/completed' && method === 'GET') {
      sendJSON(res, dbData.completedMatches);
      return;
    }
    if (pathname === '/api/matches/upcoming' && method === 'GET') {
      sendJSON(res, dbData.upcomingMatches);
      return;
    }
    if (pathname === '/api/matches/knockout' && method === 'GET') {
      sendJSON(res, dbData.knockoutMatches);
      return;
    }

    // ========================================
    // 7. 添加比赛结果 (含 Elo 更新)
    // ========================================
    if (pathname === '/api/matches/result' && method === 'POST') {
      ensureElo();
      const body = await parseBody(req);
      const { date, group, home, away, score, round } = body;
      if (!date || !home || !away || !score) return sendError(res, '缺少必填字段: date, home, away, score');
      if (!/^\d+-\d+$/.test(score)) return sendError(res, '比分格式错误，应为 "x-y"');
      
      const exists = dbData.completedMatches.some(m => m.home === home && m.away === away && m.date === date);
      if (exists) return sendError(res, '该比赛已存在', 409);

      const newMatch = { date, group: group || dbData.teamGroup[home] || '', home, away, score, round: round || 3 };
      dbData.completedMatches.push(newMatch);
      
      // 更新 Elo
      const tHome = dbData.teams[home];
      const tAway = dbData.teams[away];
      if (tHome && tAway) {
        const eloH = tHome.eloRating || engine.rankToElo(tHome.rank || 50);
        const eloA = tAway.eloRating || engine.rankToElo(tAway.rank || 50);
        const [hG, aG] = score.split('-').map(Number);
        const K = round && round.toString().includes('/') ? 40 : 30;
        const updated = engine.updateElo(eloH, eloA, hG, aG, K);
        tHome.eloRating = updated.home;
        tAway.eloRating = updated.away;
      }
      
      saveDB();
      sendJSON(res, { success: true, match: newMatch });
      return;
    }

    // ========================================
    // 8. 删除比赛
    // ========================================
    if (pathname.startsWith('/api/matches/') && method === 'DELETE') {
      const idx = parseInt(pathname.slice(13), 10);
      if (isNaN(idx) || idx < 0 || idx >= dbData.completedMatches.length) return sendError(res, '索引无效', 404);
      dbData.completedMatches.splice(idx, 1);
      // 重置 Elo 并重新计算
      eloInitialized = false;
      ensureElo();
      saveDB();
      sendJSON(res, { success: true });
      return;
    }

    // ========================================
    // 9. 融合预测 (含赔率输入)
    // ========================================
    if (pathname === '/api/predict/match' && method === 'POST') {
      ensureElo();
      const body = await parseBody(req);
      const { home, away, isFinalRound, isKnockout, oddsHome, oddsDraw, oddsAway, handicap, useAI } = body;
      if (!home || !away) return sendError(res, '需要 home 和 away 参数');

      // 计算末轮战意
      const teamUrgency = {};
      if (isFinalRound && dbData.groupStandings) {
        for (const t of [home, away]) {
          const groupKey = dbData.teamGroup[t] || '';
          const gs = dbData.groupStandings[groupKey];
          if (gs) {
            // 根据积分推断战意
            const standings = getStandings();
            const s = standings[t];
            if (s) {
              const maxPts = Math.max(...gs.teams.map(n => standings[n]?.p || 0));
              const pts = s.p;
              const gd = s.gd;
              // 已出线(>=5分或领先4分以上)
              if (pts >= 5) teamUrgency[t] = 5; // 已出线
              else if (pts >= 4 && pts >= maxPts - 2) teamUrgency[t] = 4; // 打平就出线
              else if (pts >= 3) teamUrgency[t] = 3; // 需赢球
              else if (pts >= 1 && gd > -2) teamUrgency[t] = 2; // 还有机会
              else if (pts >= 1) teamUrgency[t] = 1; // 渺茫
              else teamUrgency[t] = 0; // 已出局
            }
          }
        }
      }

      const config = dbData.modelConfig || {};
      const weights = config.fusionWeights || { elo: 0.25, poisson: 0.30, economic: 0.10, market: 0.35 };
      
      const pred = engine.fusionPredict(home, away, dbData.teams, dbData.recentMatches, dbData.headToHead, {
        monteCarloRuns: config.monteCarloRuns || 5000,
        isFinalRound: isFinalRound || false,
        isKnockout: isKnockout || false,
        teamUrgency,
        oddsHome: oddsHome || body.odds_home || null,
        oddsDraw: oddsDraw || body.odds_draw || null,
        oddsAway: oddsAway || body.odds_away || null,
        handicap: handicap || null,
        eloWeight: weights.elo,
        poissonWeight: weights.poisson,
        economicWeight: weights.economic,
        marketWeight: weights.market,
      });

      // 如果要求 AI 推理
      if (useAI && !pred.error) {
        try {
          const aiReport = await runAIReasoning(home, away, pred, body);
          pred.aiReport = aiReport;
        } catch (e) {
          pred.aiReport = { error: `AI推理失败: ${e.message}` };
        }
      }

      // 记录预测历史
      if (!pred.error) {
        dbData.predictionHistory.push({
          timestamp: pred.timestamp,
          home, away,
          fusion: pred.fusion,
          models: {
            elo: pred.models.elo.winPct + '/' + pred.models.elo.drawPct + '/' + pred.models.elo.awayPct,
            poisson: pred.models.poisson.winPct + '/' + pred.models.poisson.drawPct + '/' + pred.models.poisson.awayPct,
          },
          odds: oddsHome ? { home: oddsHome, draw: oddsDraw, away: oddsAway } : null
        });
        if (dbData.predictionHistory.length > 200) {
          dbData.predictionHistory = dbData.predictionHistory.slice(-200);
        }
        saveDB();

        // ---- 写入预测日志 (prediction_log.jsonl) ----
        const logEntry = {
          timestamp: pred.timestamp,
          source: 'custom',
          match: home + ' vs ' + away,
          home, away,
          isFinalRound: isFinalRound || false,
          isKnockout: isKnockout || false,
          hasOdds: !!oddsHome,
          odds: oddsHome ? { home: oddsHome, draw: oddsDraw, away: oddsAway } : null,
          handicap: handicap || null,
          teamUrgency,
          weights: { elo: weights.elo, poisson: weights.poisson, economic: weights.economic, market: weights.market },
          config: { dcRho: config.dcRho, homeAdvantage: config.homeAdvantage, realPerformanceWeight: config.realPerformanceWeight },
          fusionLambda: pred.fusion.lambda,
          topPredictions: pred.fusion.top5,
          fusionProb: { winPct: pred.fusion.winPct, drawPct: pred.fusion.drawPct, awayPct: pred.fusion.awayPct },
          modelProb: {
            elo: { winPct: pred.models.elo.winPct, drawPct: pred.models.elo.drawPct, awayPct: pred.models.elo.awayPct },
            poisson: { winPct: pred.models.poisson.winPct, drawPct: pred.models.poisson.drawPct, awayPct: pred.models.poisson.awayPct },
            economic: { winPct: pred.models.economic.winPct, drawPct: pred.models.economic.drawPct, awayPct: pred.models.economic.awayPct },
            market: pred.models.market ? { winPct: pred.models.market.winPct, drawPct: pred.models.market.drawPct, awayPct: pred.models.market.awayPct } : null
          },
          // AI 推理报告（useAI=true 时才有）
          aiReport: pred.aiReport || null
        };
        appendPredictionLog(logEntry);
      }

      sendJSON(res, pred);
      return;
    }

    // ========================================
    // 10. 预测全部未赛
    // ========================================
    if (pathname === '/api/predict/all' && method === 'POST') {
      ensureElo();
      const config = dbData.modelConfig || {};
      const results = [];
      for (const m of dbData.upcomingMatches) {
        const pred = engine.fusionPredict(m.home, m.away, dbData.teams, dbData.recentMatches, dbData.headToHead, {
          monteCarloRuns: config.monteCarloRuns || 5000,
          isFinalRound: m.round === 3,
          eloWeight: (config.fusionWeights || {}).elo || 0.25,
          poissonWeight: (config.fusionWeights || {}).poisson || 0.30,
          economicWeight: (config.fusionWeights || {}).economic || 0.10,
          marketWeight: 0, // 无赔率时忽略市场模型
        });
        results.push({ ...m, ...pred });

        // ---- 写入预测日志 (prediction_log.jsonl) ----
        if (!pred.error) {
          appendPredictionLog({
            timestamp: pred.timestamp,
            source: 'batch',
            match: m.home + ' vs ' + m.away,
            home: m.home, away: m.away,
            group: m.group, round: m.round,
            date: m.date,
            isFinalRound: m.round === 3,
            isKnockout: false,
            hasOdds: false,
            odds: null,
            handicap: null,
            teamUrgency: {},
            weights: { elo: (config.fusionWeights || {}).elo || 0.25, poisson: (config.fusionWeights || {}).poisson || 0.30, economic: (config.fusionWeights || {}).economic || 0.10, market: 0 },
            config: { dcRho: config.dcRho, homeAdvantage: config.homeAdvantage, realPerformanceWeight: config.realPerformanceWeight },
            fusionLambda: pred.fusion.lambda,
            topPredictions: pred.fusion.top5,
            fusionProb: { winPct: pred.fusion.winPct, drawPct: pred.fusion.drawPct, awayPct: pred.fusion.awayPct },
            modelProb: {
              elo: { winPct: pred.models.elo.winPct, drawPct: pred.models.elo.drawPct, awayPct: pred.models.elo.awayPct },
              poisson: { winPct: pred.models.poisson.winPct, drawPct: pred.models.poisson.drawPct, awayPct: pred.models.poisson.awayPct },
              economic: { winPct: pred.models.economic.winPct, drawPct: pred.models.economic.drawPct, awayPct: pred.models.economic.awayPct },
              market: null
            }
          });
        }
      }
      sendJSON(res, { total: results.length, results, timestamp: new Date().toISOString() });
      return;
    }

    // ========================================
    // 11. 出线形势
    // ========================================
    if (pathname === '/api/predict/advance' && method === 'POST') {
      ensureElo();
      const body = await parseBody(req);
      const N = body.simulations || 10000;
      
      // SSE 流式响应
      res.writeHead(200, {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive',
        'X-Accel-Buffering': 'no'
      });
      
      // 先发一个开始信号
      res.write(`data: ${JSON.stringify({ type: 'start', total: N })}\n\n`);
      
      const result = engine.simulateTournament(dbData, N, (progress) => {
        try {
          res.write(`data: ${JSON.stringify({ type: 'progress', ...progress })}\n\n`);
        } catch(e) {}
      });
      
      // 发结果
      res.write(`data: ${JSON.stringify({ type: 'result', data: result })}\n\n`);
      res.write(`data: ${JSON.stringify({ type: 'done' })}\n\n`);
      res.end();
      return;
    }

    // ========================================
    // 12. 模型分析
    // ========================================
    if (pathname === '/api/analyze' && method === 'GET') {
      ensureElo();
      const result = engine.analyzeModel(dbData.completedMatches, dbData.teams, dbData.recentMatches);
      sendJSON(res, result);
      return;
    }

    // ========================================
    // 13. 配置
    // ========================================
    if (pathname === '/api/config' && method === 'GET') {
      sendJSON(res, dbData.modelConfig || {});
      return;
    }
    if (pathname === '/api/config' && method === 'PUT') {
      const body = await parseBody(req);
      if (!dbData.modelConfig) dbData.modelConfig = {};
      const allowed = ['monteCarloRuns', 'homeAdvantage', 'dcRho', 'realPerformanceWeight', 'preseasonWeight', 'finalRoundFactor'];
      const weightFields = ['elo', 'poisson', 'economic', 'market'];
      for (const field of allowed) {
        if (body[field] !== undefined) dbData.modelConfig[field] = body[field];
      }
      if (body.fusionWeights) {
        dbData.modelConfig.fusionWeights = body.fusionWeights;
      }
      saveDB();
      sendJSON(res, { success: true, config: dbData.modelConfig });
      return;
    }

    // ========================================
    // 14. 预测历史
    // ========================================
    if (pathname === '/api/history' && method === 'GET') {
      sendJSON(res, dbData.predictionHistory?.slice(-50).reverse() || []);
      return;
    }

    // ========================================
    // 14b. 预测日志 (prediction_log.jsonl) — 含 AI 推理报告
    // ========================================
    if (pathname === '/api/prediction/logs' && method === 'GET') {
      const limit = parseInt(queryParams.limit || '200', 10);
      const logs = readPredictionLog(limit);
      // 最新的在前
      sendJSON(res, logs.reverse());
      return;
    }

    // ========================================
    // 15. 统计数据
    // ========================================
    if (pathname === '/api/stats' && method === 'GET') {
      const stats = getStats();
      const standings = getStandings();
      sendJSON(res, { stats, standings });
      return;
    }

    // ========================================
    // 16. Elo 排行榜
    // ========================================
    if (pathname === '/api/elo' && method === 'GET') {
      ensureElo();
      const eloList = Object.entries(dbData.teams)
        .map(([name, data]) => ({
          name,
          elo: data.eloRating || engine.rankToElo(data.rank || 50),
          rank: data.rank,
          group: dbData.teamGroup[name] || ''
        }))
        .sort((a, b) => b.elo - a.elo);
      sendJSON(res, eloList);
      return;
    }

    // ========================================
    // 17. 淘汰赛对阵 + 小组出线形势
    // ========================================
    if (pathname === '/api/knockout' && method === 'GET') {
      const standings = getStandings();
      const groupInfo = {};
      if (dbData.groupStandings) {
        for (const [g, info] of Object.entries(dbData.groupStandings)) {
          const gs = info.teams.map(t => standings[t]).filter(Boolean)
            .sort((a, b) => b.p - a.p || b.gd - a.gd || b.gf - a.gf);
          groupInfo[g] = { ...info, currentRanking: gs };
        }
      }
      sendJSON(res, {
        knockoutTree: dbData.knockoutTree || null,
        groupStandings: dbData.groupStandings || null,
        groupInfo,
        standings: Object.values(standings).sort((a, b) => a.group.localeCompare(b.group) || b.p - a.p)
      });
      return;
    }

    // ========================================
    // 18. 复盘分析
    // ========================================
    if (pathname === '/api/review' && method === 'GET') {
      ensureElo();
      const config = dbData.modelConfig || {};
      const weights = config.fusionWeights || { elo: 0.25, poisson: 0.30, economic: 0.10, market: 0.35 };
      
      const results = [];
      for (const m of (dbData.completedMatches || [])) {
        try {
          const [hScore, aScore] = m.score.split('-').map(Number);
          const actualResult = hScore > aScore ? 'home' : hScore === aScore ? 'draw' : 'away';
          
          const opts = {
            monteCarloRuns: config.monteCarloRuns || 5000,
            isFinalRound: false, isKnockout: false,
            eloWeight: weights.elo, poissonWeight: weights.poisson,
            economicWeight: weights.economic, marketWeight: weights.market,
          };
          if (m.oddsHome) {
            opts.oddsHome = m.oddsHome; opts.oddsDraw = m.oddsDraw; opts.oddsAway = m.oddsAway;
          }
          if (m.handicap) opts.handicap = m.handicap;
          
          const pred = engine.fusionPredict(m.home, m.away, dbData.teams, dbData.recentMatches, dbData.headToHead, opts);
          if (pred.error) continue;
          
          const topResult = pred.fusion.winPct >= pred.fusion.drawPct && pred.fusion.winPct >= pred.fusion.awayPct ? 'home'
            : pred.fusion.drawPct >= pred.fusion.winPct && pred.fusion.drawPct >= pred.fusion.awayPct ? 'draw'
            : 'away';
          const correctDirection = topResult === actualResult;
          const predScore = pred.fusion.top5[0].score;
          const [pH, pA] = predScore.split('-').map(Number);
          const scoreDiff = Math.abs(pH - hScore) + Math.abs(pA - aScore);
          
          results.push({
            home: m.home, away: m.away, score: m.score, group: m.group || '?',
            actualResult, predResult: topResult, correctDirection,
            predTop1: predScore, top1Pct: pred.fusion.top5[0].pct,
            homePct: pred.fusion.winPct, drawPct: pred.fusion.drawPct, awayPct: pred.fusion.awayPct,
            lambdaH: +pred.fusion.lambda.home.toFixed(2), lambdaA: +pred.fusion.lambda.away.toFixed(2),
            scoreDiff, hasOdds: !!m.oddsHome, handicap: m.handicap || 0,
            oddsStr: m.oddsHome ? `${m.oddsHome}/${m.oddsDraw}/${m.oddsAway}` : '无',
            top5: pred.fusion.top5.map(s => `${s.score}(${s.pct}%)`).join(' '),
          });
        } catch(e) {}
      }
      
      const total = results.length;
      const correct = results.filter(r => r.correctDirection).length;
      const withOdds = results.filter(r => r.hasOdds);
      const noOdds = results.filter(r => !r.hasOdds);
      
      const groupStats = {};
      for (const r of results) {
        if (!groupStats[r.group]) groupStats[r.group] = { t:0, c:0 };
        groupStats[r.group].t++;
        if (r.correctDirection) groupStats[r.group].c++;
      }
      
      sendJSON(res, {
        total, correct, correctPct: +((correct/total)*100).toFixed(1),
        withOdds: { count: withOdds.length, correct: withOdds.filter(r=>r.correctDirection).length },
        noOdds: { count: noOdds.length, correct: noOdds.filter(r=>r.correctDirection).length },
        groupStats,
        wrong: results.filter(r => !r.correctDirection),
        exact: results.filter(r => r.scoreDiff === 0),
        scoreBins: {
          '0分(精确)': results.filter(r=>r.scoreDiff===0).length,
          '1-2分': results.filter(r=>r.scoreDiff>=1&&r.scoreDiff<=2).length,
          '3-4分': results.filter(r=>r.scoreDiff>=3&&r.scoreDiff<=4).length,
          '5分+': results.filter(r=>r.scoreDiff>=5).length,
        },
        // ---- 预测日志分析 ----
        logAnalysis: analyzePredictionLog(results),
      });
      return;
    }

  } catch (e) {
    console.error('API 错误:', e);
    sendError(res, e.message || '服务器内部错误', 500);
    return;
  }

  // 静态文件
  const staticPath = pathname === '/' || pathname === '/index.html'
    ? path.join(__dirname, 'public', 'index.html')
    : path.join(__dirname, 'public', pathname);
  serveStatic(res, staticPath);
}

function serveStatic(res, filePath) {
  const ext = path.extname(filePath);
  const mime = MIME[ext] || 'application/octet-stream';
  try {
    const content = fs.readFileSync(filePath);
    res.writeHead(200, { 'Content-Type': mime });
    res.end(content);
  } catch (e) {
    const indexPath = path.join(__dirname, 'public', 'index.html');
    try {
      const content = fs.readFileSync(indexPath, 'utf8');
      res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
      res.end(content);
    } catch (e2) {
      sendError(res, 'Not Found', 404);
    }
  }
}

// ============================================================
// AI 推理裁判 (调用 Python 脚本 + deepseek-v4-flash)
// ============================================================

// 读取 sensenova 配置
const SENSENOVA_CONFIG = getSensenovaConfig();

function getSensenovaConfig() {
  try {
    const configPath = 'E:/OpenClaw/.openclaw/openclaw.json';
    const raw = JSON.parse(fs.readFileSync(configPath, 'utf8'));
    const sn = raw.models?.providers?.sensenova;
    if (sn) return { apiKey: sn.apiKey, baseUrl: sn.baseUrl, model: 'deepseek-v4-flash' };
  } catch (e) {}
  return { apiKey: '', baseUrl: 'https://token.sensenova.cn/v1', model: 'deepseek-v4-flash' };
}

async function runAIReasoning(home, away, pred, body) {
  // 组装因子向量
  const tHome = dbData.teams[home];
  const tAway = dbData.teams[away];
  const standings = getStandings();
  
  // 近10场状态
  function getMomentumStr(name) {
    const m = dbData.recentMatches?.[name];
    if (!m || m.length === 0) return '无数据';
    const wins = m.filter(x => x.result === '胜').length;
    const draws = m.filter(x => x.result === '平').length;
    const losses = m.filter(x => x.result === '负').length;
    return `${wins}胜${draws}平${losses}负 (最近: ${m[0]?.opponent || '?'} ${m[0]?.score || '?'})`;
  }
  
  // 晋级形势
  function getStandingStr(name) {
    const s = standings[name];
    if (!s) return '信息不足';
    return `${s.p}分, ${s.w}胜${s.d}平${s.l}负, 净胜球${s.gd}, 排名待定`;
  }
  
  // 历史交锋
  const h2hKey = [home, away].sort().join('|');
  const h2h = dbData.headToHead?.[h2hKey] || {};
  
  // Top5 比分字符串
  const top5Str = pred.fusion.top5.map(s => `${s.score}:${s.pct}%`).join(', ');
  
  const factors = {
    home,
    away,
    matchType: body.isKnockout ? '世界杯淘汰赛' : '世界杯小组赛',
    matchDate: body.date || '待定',
    elo: {
      home: pred.models.elo.rating.home,
      away: pred.models.elo.rating.away,
      diff: pred.models.elo.rating.home - pred.models.elo.rating.away
    },
    poisson: {
      lambdaHome: pred.models.poisson.lambda.home,
      lambdaAway: pred.models.poisson.lambda.away,
      winPct: pred.models.poisson.winPct,
      drawPct: pred.models.poisson.drawPct,
      awayPct: pred.models.poisson.awayPct,
      top5: top5Str
    },
    economic: {
      gdpHome: tHome?.gdpPerCapita || '?',
      gdpAway: tAway?.gdpPerCapita || '?',
      host: tHome?.isHost ? home : tAway?.isHost ? away : '无'
    },
    odds: {
      home: body.oddsHome || body.odds_home || '未提供',
      draw: body.oddsDraw || body.odds_draw || '未提供',
      away: body.oddsAway || body.odds_away || '未提供',
      handicap: body.handicap || '未提供',
      impliedHome: pred.models.market?.winPct || '?',
      impliedDraw: pred.models.market?.drawPct || '?',
      impliedAway: pred.models.market?.awayPct || '?'
    },
    headToHead: {
      total: h2h.total || 0,
      homeWins: home === h2h.teamA ? h2h.aWins : h2h.bWins || 0,
      draws: h2h.draws || 0,
      awayWins: away === h2h.teamA ? h2h.aWins : h2h.bWins || 0
    },
    standings: {
      home: getStandingStr(home),
      away: getStandingStr(away)
    },
    momentum: {
      home: getMomentumStr(home),
      away: getMomentumStr(away)
    },
    fusionWinPct: pred.fusion.winPct,
    fusionDrawPct: pred.fusion.drawPct,
    fusionAwayPct: pred.fusion.awayPct,
  };

  // 调用 Python 脚本
  const { execSync } = await import('child_process');
  const pythonScript = path.join(__dirname, 'reasoning_agent.py');
  
  const env = {
    ...process.env,
    SENSENOVA_KEY: SENSENOVA_CONFIG.apiKey,
    SENSENOVA_BASE: SENSENOVA_CONFIG.baseUrl,
    REASONING_MODEL: SENSENOVA_CONFIG.model,
  };

  try {
    const result = execSync(
      `python "${pythonScript}"`,
      {
        input: JSON.stringify(factors),
        env,
        encoding: 'utf8',
        timeout: 60000,
        maxBuffer: 50 * 1024 * 1024,
      }
    );
    const parsed = JSON.parse(result.trim());
    return parsed;
  } catch (e) {
    console.error('AI推理失败:', e.message);
    // 尝试直接调用 API（作为 fallback）
    return await callAIReasoningDirect(factors);
  }
}

// Fallback: 直接调用 sensenova API
async function callAIReasoningDirect(factors) {
  const prompt = buildPrompt(factors);
  const url = `${SENSENOVA_CONFIG.baseUrl}/chat/completions`;
  
  try {
    const resp = await fetch(url, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${SENSENOVA_CONFIG.apiKey}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        model: SENSENOVA_CONFIG.model,
        messages: [
          { role: 'system', content: '你是一个专业的足球比赛分析专家，擅长多因子推理分析。' },
          { role: 'user', content: prompt }
        ],
        temperature: 0.3,
        max_tokens: 4096,
        stream: false
      })
    });
    const data = await resp.json();
    return {
      report: data.choices?.[0]?.message?.content || '无输出',
      method: 'direct-api'
    };
  } catch (e) {
    return { error: `AI推理失败: ${e.message}` };
  }
}

function buildPrompt(factors) {
  const h = factors.home, a = factors.away;
  const e = factors.elo, p = factors.poisson, ec = factors.economic;
  const o = factors.odds, h2 = factors.headToHead;
  const s = factors.standings, m = factors.momentum;
  
  return `# 角色设定
你是一名世界顶级的足球比赛分析专家，拥有20年实战研判经验。你的特长是综合多维度信息进行逻辑推演，最终给出有理有据的比赛结论。

# 输入信息

## 1. 基础数据
- 对阵双方：${h} vs ${a}
- 比赛性质：${factors.matchType}
- 比赛时间：${factors.matchDate}

## 2. 数学模型输出
- Elo评分：主队 ${e.home}，客队 ${e.away}，差值 ${e.diff}
- 泊松模型预期进球：主队 ${p.lambdaHome}，客队 ${p.lambdaAway}
- 经济学模型：主队 GDP $${ec.gdpHome}，客队 GDP $${ec.gdpAway}，东道主 ${ec.host}
- **原始比分概率Top5**：${p.top5}
- 融合模型胜率：主胜 ${factors.fusionWinPct}%，平 ${factors.fusionDrawPct}%，客胜 ${factors.fusionAwayPct}%

## 3. 赔率与市场信息
- 胜平负赔率：主胜 ${o.home}，平 ${o.draw}，客胜 ${o.away}
- 让球盘口：${o.handicap}（${o.handicap < 0 ? '主受让' : '主让'}${Math.abs(o.handicap)}）
- 赔率隐含概率：主胜 ${o.impliedHome}%，平 ${o.impliedDraw}%，客胜 ${o.impliedAway}%

## 4. 晋级形势与战意
- 主队：${s.home}
- 客队：${s.away}

## 5. 历史交锋
- 总交手：${h2.total} 次
- 主队胜 ${h2.homeWins}，平 ${h2.draws}，客队胜 ${h2.awayWins}

## 6. 近10场状态
- 主队：${m.home}
- 客队：${m.away}

---

# 推理分析要求

## 第一步：因子重要性排序
评估以上因子中，对本场比赛影响最大的3个因子，说明理由。

## 第二步：进攻/防守效率推演
- 主队最可能的进球方式
- 客队最可能的进球方式
- 双方各自最容易被对手利用的防守漏洞

## 第三步：比赛节奏与进球分布预测
- 全场进球数的合理区间及理由
- 上半场/下半场的进球分布预判
- 是否存在特定时间段进球高发

## 第四步：比分概率重校准
基于推理，对数学模型输出的原始比分概率进行调整，给出：
- **调整后的Top 5比分及概率**
- 每个比分对应的发生场景描述

## 第五步：最终结论
- 最可能比分
- 次可能比分
- 进球数倾向：大/小
- 胜负倾向：胜/平/负

---

# 特别注意
1. 不要和稀泥。如果原始模型输出全是1-0、0-0，要明确指出数学模型过于保守，基于赔率和战意给出修正方向。
2. 比分可以出现2-1、3-1、4-0、5-0等大比分，但要给出合理场景。
3. 如果数据不足，明确指出并给出假设。
4. 以赔率市场作为最高权重参考。如果赔率显示主胜概率>55%，请强制在Top3中至少包含一个主队进2球及以上的比分。
5. **特别注意让球盘口**：如果盘口是主让-2或更深，说明市场预期主队至少赢3球，你的Top1比分必须包含主队进3球及以上的比分（如3-0、4-0、3-1等），并解释为什么数学模型低估了主队的进攻能力。
6. **当赔率+盘口双信号指向大胜时**（如主胜赔<1.30且盘口≥-1.5），你的Top5中至少3个比分是主队进2球及以上。

# 输出格式
用以下结构化格式：

# 🏆 比赛研判报告：${h} vs ${a}

## 一、核心因子分析
...

## 二、战术推演与节奏预判
...

## 三、比分概率重校准
| 排名 | 比分 | 调整后概率 | 发生场景 |
|------|------|-----------|---------|
| 1 | X-X | XX% | ... |

## 四、最终结论
- **推荐比分**：X-X
- **进球数倾向**：
- **胜负倾向**：
- **核心逻辑一句话总结**：
`;
}

const server = http.createServer(handleRequest);
server.listen(PORT, '0.0.0.0', () => {
  console.log('');
  console.log('╔══════════════════════════════════════════════╗');
  console.log('║  ⚽ 世界杯预测系统 v3.0 - 融合模型');
  console.log('╚══════════════════════════════════════════════╝');
  console.log('');
  console.log(`  🌐 本地:   http://localhost:${PORT}`);
  console.log(`  🌐 局域网: http://${getLocalIP()}:${PORT}`);
  console.log('');
  console.log(`  🧠 模型: Elo等级分 + 泊松修正 + 经济学 + 赔率市场`);
  console.log('');
  console.log(`  📊 新增 API:`);
  console.log(`     GET  /api/elo           - Elo 排行榜`);
  console.log(`     POST /api/predict/match - 融合预测 (含赔率)`);
  console.log('');
  console.log(`  按 Ctrl+C 停止`);
});

// 初始化 Elo
ensureElo();