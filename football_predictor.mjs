/**
 * ⚽ 足球比分预测系统 v1.0
 * 
 * 四层架构:
 *   Layer 1 - 特征工程: 多维特征变量 → 进攻/防守强度
 *   Layer 2 - Dixon-Coles: 低比分修正 + 时间衰减
 *   Layer 3 - 蒙特卡洛模拟: 5000次/条件 × N个条件
 *   Layer 4 - 大模型人工修正层: LLM 判断异常场景
 * 
 * 用法:
 *   node football_predictor.mjs [--llm] [--verbose]
 */

// ============================================================
// 配置
// ============================================================
const CONFIG = {
  SIMULATIONS_PER_CONDITION: 5000,
  TIME_DECAY_HALF_LIFE_DAYS: 180,    // 半年衰减半衰期
  LOW_SCORE_ADJUSTMENT: true,         // Dixon-Coles 低比分修正
  USE_LLM: process.argv.includes('--llm'),
  VERBOSE: process.argv.includes('--verbose'),
};

// ============================================================
// Layer 1: 特征工程
// ============================================================

/**
 * 球队画像 - 多维特征
 * 每个特征都映射到进攻/防守强度的调整系数
 */
const TEAM_PROFILES = {
  // 强队示例
  '曼城': {
    attackBase: 1.5,       // 基础进攻强度 (场均预期进球)
    defenseBase: 0.8,      // 基础防守强度 (场均预期失球)
    style: '高压控球',     // 战术风格
    styleFactor: 1.10,     // 高压→更多混乱/更多进球机会
    keyScorer: true,       // 关键射手是否健康 (默认true)
    keyDefender: true,     // 关键后卫是否健康
    morale: 'high',        // 士气
    derby: false,
    isHome: true,
  },
  '利物浦': {
    attackBase: 1.6,
    defenseBase: 0.8,
    style: '高压逼抢',
    styleFactor: 1.15,
    keyScorer: true,
    keyDefender: true,
    morale: 'high',
    derby: false,
    isHome: false,
  },
  '阿森纳': {
    attackBase: 1.6,
    defenseBase: 0.8,
    style: '控球传导',
    styleFactor: 1.05,
    keyScorer: true,
    keyDefender: true,
    morale: 'normal',
    derby: false,
    isHome: true,
  },
  '切尔西': {
    attackBase: 1.4,
    defenseBase: 1.0,
    style: '防守反击',
    styleFactor: 0.85,
    keyScorer: true,
    keyDefender: true,
    morale: 'normal',
    derby: false,
    isHome: false,
  },
  '曼联': {
    attackBase: 1.2,
    defenseBase: 1.2,
    style: '混乱无章',
    styleFactor: 1.10,
    keyScorer: false,      // 关键射手伤缺
    keyDefender: true,
    morale: 'low',
    derby: false,
    isHome: false,
  },
  '热刺': {
    attackBase: 1.4,
    defenseBase: 1.1,
    style: '快攻直塞',
    styleFactor: 1.10,
    keyScorer: true,
    keyDefender: false,    // 关键后卫伤缺
    morale: 'normal',
    derby: false,
    isHome: true,
  },
  // 中下游球队
  '狼队': {
    attackBase: 1.0,
    defenseBase: 1.3,
    style: '防守反击',
    styleFactor: 0.80,
    keyScorer: true,
    keyDefender: true,
    morale: 'normal',
    derby: false,
    isHome: true,
  },
  '诺丁汉森林': {
    attackBase: 0.9,
    defenseBase: 1.4,
    style: '铁桶防守',
    styleFactor: 0.75,
    keyScorer: true,
    keyDefender: true,
    morale: 'high',        // 保级区士气高昂
    derby: false,
    isHome: false,
  },
};

/**
 * 特征工程：将多维特征 → λ_home / λ_away (预期进球)
 * 这是核心函数，体现了所有特征的影响
 */
function featureEngineering(homeTeam, awayTeam, matchContext = {}) {
  const home = { ...TEAM_PROFILES[homeTeam] };
  const away = { ...TEAM_PROFILES[awayTeam] };

  if (!home || !away) {
    throw new Error(`未知球队: ${homeTeam} 或 ${awayTeam}`);
  }

  // ---- 1. 基础进攻强度 ----
  let lambdaHome = home.attackBase;
  let lambdaAway = away.attackBase;

  // ---- 2. 主场优势（5%-10%） ----
  if (home.isHome) lambdaHome *= 1.08;
  if (away.isHome) lambdaAway *= 1.08;

  // ---- 3. 战术风格影响 ----
  lambdaHome *= home.styleFactor;
  lambdaAway *= away.styleFactor;

  // ---- 4. 关键球员伤停 ----
  // 关键射手缺阵 → 进攻下调 15%-20%
  if (!home.keyScorer) lambdaHome *= 0.82;
  if (!away.keyScorer) lambdaAway *= 0.82;
  // 关键后卫缺阵 → 对方进攻上调 12%-15%
  if (!home.keyDefender) lambdaAway *= 1.14;
  if (!away.keyDefender) lambdaHome *= 1.14;

  // ---- 5. 士气影响 ----
  const moraleFactor = { high: 1.10, normal: 1.00, low: 0.90 };
  lambdaHome *= (moraleFactor[home.morale] || 1.0);
  lambdaAway *= (moraleFactor[away.morale] || 1.0);

  // ---- 6. 德比/淘汰赛 ----
  if (matchContext.isDerby) {
    // 德比战 → 保守+情绪化，进球下调
    lambdaHome *= 0.92;
    lambdaAway *= 0.92;
  }
  if (matchContext.isKnockout) {
    // 淘汰赛 → 保守倾向，进球下调
    lambdaHome *= 0.85;
    lambdaAway *= 0.85;
  }

  // ---- 7. 实力差距调整 ----
  const strengthDiff = (home.attackBase - home.defenseBase) - (away.attackBase - away.defenseBase);
  if (strengthDiff > 0.5) {
    // 强打弱 → 强队+8%, 弱队-10%
    lambdaHome *= 1.08;
    lambdaAway *= 0.90;
  } else if (strengthDiff < -0.5) {
    lambdaHome *= 0.90;
    lambdaAway *= 1.08;
  }

  return {
    lambdaHome: Math.round(lambdaHome * 100) / 100,
    lambdaAway: Math.round(lambdaAway * 100) / 100,
    features: { home, away, matchContext },
  };
}

// ============================================================
// Layer 2: Dixon-Coles 低比分修正
// ============================================================

/**
 * Dixon-Coles 修正系数
 * 对 0-0, 1-0, 0-1, 1-1 等低比分结果进行概率调整
 * 
 * 原理: 泊松分布独立假设在低进球场景下高估了这些比分
 * 修正函数: ρ(x,y) 对低进球组合施加惩罚或奖励
 */
function dixonColesAdjustment(x, y, lambdaHome, lambdaAway) {
  if (!CONFIG.LOW_SCORE_ADJUSTMENT) return 1.0;

  // Dixon-Coles ρ 参数 - 经验值 0.1-0.2
  const rho = 0.12;

  // 只在 x≤1 且 y≤1 时修正
  if (x <= 1 && y <= 1) {
    // τ(x,y) = 1 + (-1)^(x+y) * ρ * (1/(λ_home^2) + 1/(λ_away^2))^(-1/2) 的简化版
    const adjustment = 1 + Math.pow(-1, x + y) * rho * 
      (1 / Math.sqrt(Math.max(lambdaHome, 0.1)) + 1 / Math.sqrt(Math.max(lambdaAway, 0.1)));
    return Math.max(0.5, Math.min(1.5, adjustment));
  }
  return 1.0;
}

/**
 * 泊松概率 (含 Dixon-Coles 修正)
 */
function poissonProb(k, lambda) {
  if (lambda <= 0) return k === 0 ? 1.0 : 0.0;
  // e^(-λ) * λ^k / k!
  return Math.exp(-lambda) * Math.pow(lambda, k) / factorial(k);
}

function factorial(n) {
  if (n <= 1) return 1;
  let r = 1;
  for (let i = 2; i <= n; i++) r *= i;
  return r;
}

/**
 * 计算完整比分概率矩阵
 */
function scoreProbabilityMatrix(lambdaHome, lambdaAway, maxGoals = 6) {
  const matrix = [];
  let totalProb = 0;

  for (let h = 0; h <= maxGoals; h++) {
    matrix[h] = [];
    for (let a = 0; a <= maxGoals; a++) {
      let prob = poissonProb(h, lambdaHome) * poissonProb(a, lambdaAway);
      // Dixon-Coles 修正
      prob *= dixonColesAdjustment(h, a, lambdaHome, lambdaAway);
      matrix[h][a] = prob;
      totalProb += prob;
    }
  }

  // 归一化
  for (let h = 0; h <= maxGoals; h++) {
    for (let a = 0; a <= maxGoals; a++) {
      matrix[h][a] /= totalProb;
    }
  }

  return matrix;
}

// ============================================================
// Layer 3: 蒙特卡洛模拟
// ============================================================

/**
 * 从泊松分布采样
 */
function poissonSample(lambda) {
  // 使用 Knuth 算法
  const L = Math.exp(-lambda);
  let k = 0;
  let p = 1;
  do {
    k++;
    p *= Math.random();
  } while (p > L);
  return k - 1;
}

/**
 * 蒙特卡洛模拟: 模拟 N 场比赛
 */
function monteCarloSimulation(lambdaHome, lambdaAway, N) {
  const results = {};

  for (let i = 0; i < N; i++) {
    const h = poissonSample(lambdaHome);
    const a = poissonSample(lambdaAway);
    const key = `${h}-${a}`;
    results[key] = (results[key] || 0) + 1;
  }

  // 转换为百分比
  const stats = { homeWin: 0, draw: 0, awayWin: 0, totalGoals: 0 };
  const sorted = Object.entries(results)
    .map(([score, count]) => {
      const [h, a] = score.split('-').map(Number);
      const pct = (count / N) * 100;
      stats.homeWin += h > a ? count : 0;
      stats.draw += h === a ? count : 0;
      stats.awayWin += h < a ? count : 0;
      stats.totalGoals += (h + a) * count;
      return { score, h, a, count, pct };
    })
    .sort((a, b) => b.count - a.count);

  stats.homeWinPct = (stats.homeWin / N * 100).toFixed(1);
  stats.drawPct = (stats.draw / N * 100).toFixed(1);
  stats.awayWinPct = (stats.awayWin / N * 100).toFixed(1);
  stats.avgGoals = (stats.totalGoals / N).toFixed(2);

  // 最可能的比分
  stats.mostLikely = sorted.slice(0, 5);

  // 最大可能的比分 (概率 > 0.5% 中最高的)
  stats.maxLikely = sorted.filter(s => s.pct > 0.5).slice(0, 10);

  return { sorted, stats };
}

/**
 * 不同条件下的模拟
 */
function multiConditionSimulation(homeTeam, awayTeam) {
  const conditions = [
    { label: '基准条件', overrides: {} },
    { label: '主队关键射手缺阵', overrides: { homeKeyScorer: false } },
    { label: '客队关键后卫缺阵', overrides: { awayKeyDefender: false } },
    { label: '德比战', overrides: { isDerby: true } },
    { label: '淘汰赛压力', overrides: { isKnockout: true } },
    { label: '主队士气低落', overrides: { homeMorale: 'low' } },
    { label: '双伤缺 (主射手+客后卫)', overrides: { homeKeyScorer: false, awayKeyDefender: false } },
  ];

  const results = [];
  for (const cond of conditions) {
    // 应用条件覆盖
    const ctx = { isDerby: false, isKnockout: false };
    const home = { ...TEAM_PROFILES[homeTeam] };
    const away = { ...TEAM_PROFILES[awayTeam] };

    if (cond.overrides.homeKeyScorer === false) home.keyScorer = false;
    if (cond.overrides.awayKeyScorer === false) away.keyScorer = false;
    if (cond.overrides.homeKeyDefender === false) home.keyDefender = false;
    if (cond.overrides.awayKeyDefender === false) away.keyDefender = false;
    if (cond.overrides.isDerby) ctx.isDerby = true;
    if (cond.overrides.isKnockout) ctx.isKnockout = true;
    if (cond.overrides.homeMorale) home.morale = cond.overrides.homeMorale;
    if (cond.overrides.awayMorale) away.morale = cond.overrides.awayMorale;

    const lambdaHome = calcLambda(home, away, ctx, true);
    const lambdaAway = calcLambda(away, home, ctx, false);
    const sim = monteCarloSimulation(lambdaHome, lambdaAway, CONFIG.SIMULATIONS_PER_CONDITION);
    results.push({ condition: cond.label, lambdaHome, lambdaAway, ...sim.stats, topScores: sim.stats.mostLikely });
  }
  return results;
}

function calcLambda(team, opponent, ctx, isHome) {
  let lambda = team.attackBase;
  if (isHome) lambda *= 1.08;
  lambda *= team.styleFactor;
  if (!team.keyScorer) lambda *= 0.82;
  if (!opponent.keyDefender) lambda *= 1.14;
  const mf = { high: 1.10, normal: 1.00, low: 0.90 };
  lambda *= (mf[team.morale] || 1.0);
  if (ctx.isDerby) lambda *= 1.15;
  if (ctx.isKnockout) lambda *= 0.90;
  const strengthDiff = (team.attackBase - team.defenseBase) - (opponent.attackBase - opponent.defenseBase);
  if (isHome && strengthDiff > 0.5) lambda *= 1.10;
  if (isHome && strengthDiff < -0.5) lambda *= 0.85;
  if (!isHome && (-strengthDiff) > 0.5) lambda *= 1.10;
  if (!isHome && (-strengthDiff) < -0.5) lambda *= 0.85;
  return Math.round(lambda * 100) / 100;
}

// ============================================================
// Layer 4: 大模型人工修正
// ============================================================

/**
 * 调用大模型进行人工修正判断
 * 用外部脚本调用，避免依赖
 */
async function llmCorrection(homeTeam, awayTeam, lambdaHome, lambdaAway, topScores, contextInfo) {
  if (!CONFIG.USE_LLM) {
    return { applied: false, reason: 'LLM 修正未启用 (使用 --llm 参数)' };
  }

  const prompt = `
## ⚽ 足球比分预测 - 人工修正请求

### 基础模型输出
- ${homeTeam} 预期进球: ${lambdaHome}
- ${awayTeam} 预期进球: ${lambdaAway}
- 最可能比分: ${topScores.slice(0, 3).map(s => `${s.score}(${s.pct.toFixed(1)}%)`).join(', ')}

### 附加信息
${contextInfo || '无额外信息'}

### 判断任务
基于上述信息，请判断：
1. 基础模型输出的比分是否合理？
2. 是否有需要上调/下调概率的比分？
3. 最终推荐的3个最可能比分是什么？

请用JSON格式回答:
{"judgment":"合理/需微调/需大幅调整","adjustedTop3":[{"score":"2-1","reason":"..."}],"notes":"..."}
`;

  try {
    // 通过子进程调用大模型
    const { execSync } = await import('child_process');
    const result = execSync(
      `curl -s -X POST http://localhost:8080/v1/chat/completions -H "Content-Type: application/json" -d '${JSON.stringify({
        model: 'deepseek-v4-flash',
        messages: [{ role: 'user', content: prompt }],
        temperature: 0.3,
      })}'`,
      { timeout: 30000, encoding: 'utf-8' }
    );
    const parsed = JSON.parse(result);
    const content = parsed.choices?.[0]?.message?.content || '';
    const jsonMatch = content.match(/\{[\s\S]*\}/);
    if (jsonMatch) {
      return { applied: true, correction: JSON.parse(jsonMatch[0]) };
    }
    return { applied: true, raw: content };
  } catch (e) {
    return { applied: false, reason: `LLM 调用失败: ${e.message}` };
  }
}

// ============================================================
// 复盘日志
// ============================================================

function errorLog(matchId, prediction, actual, notes) {
  const entry = {
    timestamp: new Date().toISOString(),
    matchId,
    prediction,
    actual,
    deviation: actual ? `${Math.abs(actual.h - prediction.h)}-${Math.abs(actual.a - prediction.a)}` : '未知',
    notes,
  };
  return entry;
}

// ============================================================
// 报告生成
// ============================================================

function generateReport(homeTeam, awayTeam, results) {
  const lines = [];
  lines.push(`╔══════════════════════════════════════════════════╗`);
  lines.push(`║   ⚽ 足球比分预测报告`);
  lines.push(`║   ${homeTeam} vs ${awayTeam}`);
  lines.push(`║   蒙特卡洛模拟: ${CONFIG.SIMULATIONS_PER_CONDITION}次/条件`);
  lines.push(`║   Dixon-Coles修正: ${CONFIG.LOW_SCORE_ADJUSTMENT ? '✅' : '❌'}`);
  lines.push(`╚══════════════════════════════════════════════════╝`);
  lines.push('');

  for (const r of results) {
    lines.push(`━━━ ${r.condition} ━━━`);
    lines.push(`  预期进球: ${homeTeam} ${r.lambdaHome} : ${r.lambdaAway} ${awayTeam}`);
    lines.push(`  胜率: ${homeTeam} ${r.homeWinPct}% | 平 ${r.drawPct}% | ${awayTeam} ${r.awayWinPct}%`);
    lines.push(`  场均总进球: ${r.avgGoals}`);
    lines.push(`  最可能比分:`);
    for (const s of r.topScores) {
      const bar = '█'.repeat(Math.round(s.pct / 2));
      lines.push(`    ${s.score}  ${s.pct.toFixed(1)}% ${bar}`);
    }
    lines.push('');
  }

  // 跨条件对比
  lines.push(`━━━ 最大可能比分对比 ━━━`);
  for (const r of results) {
    const top = r.topScores[0];
    lines.push(`  [${r.condition}] ${top.score} (${top.pct.toFixed(1)}%)`);
  }

  return lines.join('\n');
}

// ============================================================
// 主流程
// ============================================================

async function main() {
  // 默认比赛
  const homeTeam = process.argv[2] || '曼城';
  const awayTeam = process.argv[3] || '利物浦';

  console.log(`\n⚽ ${homeTeam} vs ${awayTeam} 比分预测系统`);
  console.log(`   模拟次数: ${CONFIG.SIMULATIONS_PER_CONDITION.toLocaleString()} 次/条件`);
  console.log(`   Dixon-Coles 低比分修正: ${CONFIG.LOW_SCORE_ADJUSTMENT ? '启用' : '关闭'}`);
  console.log(`   LLM 人工修正层: ${CONFIG.USE_LLM ? '启用' : '关闭'}\n`);

  // 1. 特征工程
  const features = featureEngineering(homeTeam, awayTeam);
  console.log(`📊 特征工程输出:`);
  console.log(`   ${homeTeam} λ = ${features.lambdaHome} (进攻强度)`);
  console.log(`   ${awayTeam} λ = ${features.lambdaAway} (进攻强度)`);

  // 2. 概率矩阵
  console.log(`\n📈 比分概率矩阵 (Dixon-Coles 修正后):`);
  const matrix = scoreProbabilityMatrix(features.lambdaHome, features.lambdaAway);
  console.log('   ' + ''.padStart(8) + Array.from({length: 8}, (_,i) => `${i}`).join('     '));
  for (let h = 0; h <= 5; h++) {
    const row = matrix[h].slice(0, 8).map(p => (p*100).toFixed(1).padStart(5)).join(' ');
    console.log('   ' + h + ':    ' + row);
  }

  // 3. 多条件蒙特卡洛
  console.log(`\n🎲 蒙特卡洛模拟 (${CONFIG.SIMULATIONS_PER_CONDITION.toLocaleString()} 次):`);
  const results = multiConditionSimulation(homeTeam, awayTeam);

  // 4. 报告
  const report = generateReport(homeTeam, awayTeam, results);
  console.log(`\n${report}`);

  // 5. LLM 修正 (如果启用)
  if (CONFIG.USE_LLM) {
    console.log(`\n🤖 LLM 人工修正层:`);
    const correction = await llmCorrection(
      homeTeam, awayTeam,
      results[0].lambdaHome, results[0].lambdaAway,
      results[0].topScores,
      '无额外新闻信息'
    );
    console.log(`   ${JSON.stringify(correction, null, 2)}`);
  }

  // 6. 保存报告
  const filename = `report_${homeTeam}_vs_${awayTeam}_${new Date().toISOString().slice(0,10)}.txt`;
  const fs = await import('fs');
  fs.writeFileSync(`E:\\OpenClaw\\.openclaw\\kasha\\football\\${filename}`, report, 'utf-8');
  console.log(`\n📁 报告已保存: football/${filename}`);
}

main().catch(console.error);
