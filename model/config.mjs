#!/usr/bin/env node

/**
 * 统一配置中心 — 所有引擎共享
 * 
 * 解决 M1: MC_SIMULATIONS 不一致 (config.py=50000, engine.mjs=5000-10000)
 * 解决 C2/L6: Elo 评分持久化
 * 
 * 用法: 
 *   import config from './config.mjs';
 *   config.MC_SIMULATIONS  // 10000
 *   config.MC_KNOCKOUT     // 20000
 */

export default {
  // ==================== 蒙特卡洛 ====================
  MC_SIMULATIONS: 10000,        // 小组赛默认
  MC_KNOCKOUT: 20000,           // 淘汰赛默认
  MC_MIN: 5000,                 // 最低模拟次数
  MC_MAX: 50000,                // 最高模拟次数
  
  // ==================== Elo ====================
  ELO_INITIAL: 1500,
  ELO_HOME_ADVANTAGE: 60,
  ELO_K_GROUP: 20,
  ELO_K_ROUND_OF_16: 30,
  ELO_K_QUARTER: 35,
  ELO_K_SEMI: 40,
  ELO_K_FINAL: 50,
  ELO_BIG_WIN_CAP: 4,           // 大胜过热限制（净胜4球封顶）
  
  // ==================== Dixon-Coles ====================
  DC_RHO_DEFAULT: 0.04,
  DC_RHO_KNOCKOUT: 0.06,
  DC_RHO_LOW_LAMBDA: 0.08,      // 低λ场景
  
  // ==================== 阶段调整 ====================
  KNOCKOUT_LAMBDA_MULT: 0.85,   // 淘汰赛进球下调15%
  KNOCKOUT_DRAW_BOOST: 1.15,    // 淘汰赛平率提升15%
  KNOCKOUT_PENALTY_BASE: 0.15,  // 点球大战基线15%
  
  // ==================== 贝叶斯权重 ====================
  BAYESIAN_WEIGHTS: {
    'group_stage':    { model: 0.70, market: 0.30 },
    'round_of_16':    { model: 0.55, market: 0.45 },
    'quarter_final':  { model: 0.50, market: 0.50 },
    'semi_final':     { model: 0.40, market: 0.60 },
    'final':          { model: 0.35, market: 0.65 },
  },
  
  // ==================== 模型融合权重 ====================
  DEFAULT_WEIGHTS: {
    elo: 0.22,
    poisson: 0.28,
    economic: 0.10,
    market: 0.40,
  },
  
  // ==================== 冷门检测阈值 ====================
  UPSET_RISK_THRESHOLDS: {
    low: 2,
    medium: 3,
    high: 5,
  },
  
  // ==================== 模拟次数获取 ====================
  getMCRuns(isKnockout = false) {
    return isKnockout 
      ? Math.max(this.MC_KNOCKOUT, this.MC_MIN)
      : Math.max(this.MC_SIMULATIONS, this.MC_MIN);
  },
};
