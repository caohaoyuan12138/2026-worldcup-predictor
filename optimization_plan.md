# ⚽ Football 预测模型诊断与优化方案

> 诊断日期: 2026-07-02
> 诊断目标: 提升比分预测准确率，降低系统性偏差

---

## 一、核心问题诊断

### 1.1 数据时效性问题 — ⚠️ 最严重

**问题：球队战力数据停留在小组赛阶段，淘汰赛表现未更新**

- `database.mjs` 中的 `TEAM_STRENGTHS` 是基于 Excel 手动录入的静态数据
- 淘汰赛已经打了 4 场（加纳0-1加拿大、巴西2-1日本、德国点球负巴拉圭、科特迪瓦1-2挪威）
- 但这些结果**没有反哺**到模型参数中
- 厄瓜多尔 3-1 德国（小组赛强队翻车）后，德国仍被标为 attackBase: 1.7, rank: 5

**影响：所有淘汰赛预测的基础数据都是错的**

### 1.2 赔率数据混乱

**问题：同一场比赛出现矛盾的赔率**

- 科特迪瓦 vs 挪威：
  - 第一次预测 odds: `{home: 3.6, draw: 3.38, away: 1.8}` — 挪威客胜 1.8
  - 第三次预测 odds: `{home: 1.78, draw: 3.45, away: 3.6}` — 科特迪瓦主胜 1.78
  - **赔率完全颠倒了！**

- 厄瓜多尔 vs 德国：
  - 第一次 odds: `{home: 5.2, draw: 4.95, away: 1.36}` — 德国远强
  - 第二次 odds: `{home: 2.65, draw: 3.72, away: 2.07}` — 德国变弱了？
  - **同一场比赛赔率变了60%+**

**原因：赔率可能来自不同时间点的快照，或手动输入错误，或数据源切换**

### 1.3 模型融合权重不合理

**问题：economic 权重只有 0.1，但实际是重要的基本面信号**

- `weights: { elo: 0.28, poisson: 0.32, economic: 0.1, market: 0.3 }`
- economic 只有 10% 权重，但身价差距、阵容深度、比赛战意等基本面信息被严重低估
- 小组赛末轮"已确定淘汰"的比赛，双方 λ 仍然一样计算，没有充分反映战意差异

### 1.4 贝叶斯融合过度依赖 Elo

**问题：Elo 模型经常与其他模型严重冲突**

- 科特迪瓦 vs 挪威：Elo 显示客胜 70.1%，但 Poisson 显示客胜仅 34.6%
- 厄瓜多尔 vs 德国：Elo 显示客胜 79.5%，但 Poisson 显示 68.8%
- Elo 和 Poisson 的冲突说明 Elo 评分没有及时反映近期比赛结果

### 1.5 环境修正系数过于粗糙

**问题：硬编码系数没有经过统计验证**

- `starPlayerMissing: 0.93` — 核心缺阵就乘以 0.93？没有区分核心是谁、缺阵多久
- `altitudePenalty: 0.94` — 固定系数，但不同球队适应力不同
- 补水/时区/天气等因子只在少数比赛中有数据，大部分比赛用默认值

### 1.6 蒙特卡洛模拟次数不一致

- `config.py`: `MC_SIMULATIONS = 50000`
- `engine.mjs`: `N = 5000`
- `predict.mjs`: `N = 5000`
- **实际只跑了 5000 次，配置写 50000 没用上**

### 1.7 AI Report 过度自信

**问题：生成的比赛研判报告篇幅过长，分析过度解读**

- 同一场比赛跑了 3-4 次 AI Report，每次都给出不同的"推荐比分"
- 报告的"核心因子分析"很多是事后合理化（hindsight bias）
- 例如科特迪瓦 vs 挪威，AI 报告说"哈兰德效应"是关键，但这是基于结果倒推

---

## 二、优化方案（按优先级排序）

### P0 — 必须立即修复

#### 2.1 实时 Elo 更新 + 战力数据反哺

**目标：** 每场比赛结束后，自动更新球队战力参数

```javascript
// 在 engine.mjs 中添加赛后更新
function updateTeamStrengthsAfterMatch(match) {
  const [hG, aG] = match.score.split('-').map(Number);
  const home = TEAM_STRENGTHS[match.home];
  const away = TEAM_STRENGTHS[match.away];
  
  // Elo 更新
  const K = match.round === 'KO' ? 30 : 20;
  const E_home = 1 / (1 + Math.pow(10, (away.elo - home.elo) / 400));
  const E_away = 1 - E_home;
  home.elo += K * (result - E_home);
  away.elo += K * (result - E_away);
  
  // 进攻/防守 λ 回归更新
  home.attackBase = home.attackBase * 0.7 + (hG / match.played) * 0.3;
  home.defenseBase = home.defenseBase * 0.7 + (hGa / match.played) * 0.3;
}
```

**具体改动：**
1. 给每个球队加 `elo` 字段（初始从 rank 反推）
2. 每场比赛后自动更新 Elo
3. 用 Elo 差值动态调整 `attackBase` 和 `defenseBase`
4. 小组赛末轮已确定出线的比赛，自动降低战意系数

#### 2.2 赔率数据清洗与一致性检查

**目标：** 确保输入模型的赔率是一致的、最新的

```javascript
// 添加赔率质量评分
function assessOddsQuality(odds) {
  if (!odds) return { quality: 0, reason: 'no_odds' };
  
  // 检查隐含概率是否合理（应接近 1.05-1.15，含抽水）
  const implied = 1/odds.home + 1/odds.draw + 1/odds.away;
  if (implied < 1.0 || implied > 1.2) {
    return { quality: 0.3, reason: 'implied_prob_outlier' };
  }
  
  // 检查赔率是否合理（不应有负数或 0）
  if (odds.home <= 0 || odds.draw <= 0 || odds.away <= 0) {
    return { quality: 0, reason: 'invalid_odds' };
  }
  
  return { quality: 1.0, impliedMargin: implied };
}
```

**具体改动：**
1. 预测前自动检查赔率合理性
2. 如果赔率异常，标记为 `hasOdds: false`，只用模型预测
3. 记录每次使用的赔率时间点，避免混用不同快照

#### 2.3 统一模拟次数

将 `engine.mjs` 和 `predict.mjs` 中的 `N` 从 5000 提升到 10000-20000（淘汰赛建议 20000）

### P1 — 显著提升

#### 2.4 动态模型融合权重

**目标：** 根据各模型近期表现自动调整权重

```javascript
// 基于过去 N 场比赛的准确率动态调整权重
function getDynamicWeights(recentAccuracy) {
  // elo: 小组赛稳定，淘汰赛波动大 → 近期 Elo 差权重降低
  // poisson: 比分预测好，但 WDL 概率一般
  // market: 强队 vs 弱队时最准，势均力敌时偏差大
  
  const weights = {
    elo: 0.25,
    poisson: 0.30,
    economic: 0.15,  // 从 0.1 提升到 0.15
    market: 0.30,
    xg: 0.00         // 预留 xG 模型接口
  };
  
  // 淘汰赛阶段：降低 elo 权重，提高 market 权重
  if (isKnockout) {
    weights.elo *= 0.8;
    weights.market *= 1.2;
  }
  
  // 归一化
  const sum = Object.values(weights).reduce((a,b) => a+b, 0);
  for (const k in weights) weights[k] /= sum;
  
  return weights;
}
```

#### 2.5 比分预测准确率评估体系

**目标：** 建立可量化的预测评估，知道什么准、什么不准

```javascript
function evaluatePredictions(predictions, actualResults) {
  // 1. 胜平负准确率 (WDL Accuracy)
  // 2. 比分准确率 (Exact Score Accuracy)
  // 3. 大小球准确率 (Over/Under Accuracy)
  // 4. 期望进球误差 (Goal Difference MAE)
  // 5. Log Loss / Brier Score
  // 6. 冷门命中率 (Upset Detection Rate)
  
  return {
    wdlAccuracy: 0.0,
    exactScoreAccuracy: 0.0,
    overUnderAccuracy: 0.0,
    meanGoalError: 0.0,
    logLoss: 0.0,
    brierScore: 0.0,
    upsetHitRate: 0.0
  };
}
```

**关键指标目标：**
- WDL 准确率：小组赛 > 55%，淘汰赛 > 50%
- 热门（高概率预测）准确率 > 70%
- Log Loss < 0.8
- 冷门检测命中率 > 60%

#### 2.6 淘汰赛特殊处理

**目标：** 淘汰赛和小组赛用完全不同的策略

```javascript
// 淘汰赛特殊规则
const KNOCKOUT_RULES = {
  lowerScoring: true,           // 淘汰赛进球更少
  higherDrawRate: true,         // 平局率更高（加时/点球）
  penaltyFactor: 0.15,          // 15% 概率进入点球
  conservativeLambda: 0.85,     // λ 整体下调 15%
  upsetProbability: 0.12,       // 冷门概率基线 12%
};
```

### P2 — 持续优化

#### 2.7 引入 xG 数据作为独立模型

目前 xG 数据只做了简单叠加，应该作为一个独立的预测模型：
- 用 xG 差值作为 λ 的核心输入
- 用 xG 趋势（最近3场上升/下降）做方向性调整
- 与 Poisson 模型做交叉验证

#### 2.8 AI Report 精简

- 当前 AI Report 太长（2000+字），很多内容是重复的
- 改为结构化输出：3个核心因子 + 1句话结论 + 推荐比分
- 避免事后合理化分析

#### 2.9 置信度校准

- 当前置信度（高/中/低）没有经过校准
- 应该用可靠性曲线（Reliability Diagram）验证：标称 70% 置信度的预测，实际命中率应该接近 70%

---

## 三、实施计划

| 阶段 | 内容 | 预计工作量 | 优先级 |
|------|------|-----------|--------|
| Phase 1 | 赛后 Elo 自动更新 + 战力反哺 | 2-3 小时 | P0 |
| Phase 2 | 赔率数据清洗 + 一致性检查 | 1-2 小时 | P0 |
| Phase 3 | 统一模拟次数 + 淘汰赛特殊处理 | 1-2 小时 | P0 |
| Phase 4 | 动态模型融合权重 | 3-4 小时 | P1 |
| Phase 5 | 预测评估体系（回测） | 2-3 小时 | P1 |
| Phase 6 | xG 独立模型整合 | 4-5 小时 | P2 |
| Phase 7 | AI Report 精简 + 置信度校准 | 2-3 小时 | P2 |

**总计：约 15-22 小时**

---

## 四、预期效果

| 指标 | 当前估计 | 优化后目标 |
|------|---------|-----------|
| WDL 准确率 | ~45% | 55-60% |
| Top3 比分命中率 | ~15% | 20-25% |
| 冷门检测 | 不稳定 | >60% |
| 模型一致性 | 低 | 高 |
| 数据时效性 | 过时 | 实时更新 |
