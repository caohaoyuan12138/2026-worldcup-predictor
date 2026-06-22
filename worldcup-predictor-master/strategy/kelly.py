"""
Kelly 仓位管理

功能：
1. Kelly 公式计算最优仓位
2. 半凯利策略（降低波动）
3. 风控红线（单场最大 5%，低置信度 1.5%）
4. 输出每场比赛的建议仓位
"""

from typing import Dict, Optional
import config


def calc_kelly_stake(model_prob: float, decimal_odds: float,
                     kelly_fraction: float = None) -> float:
    """
    Kelly 仓位公式

    f* = (bp - q) / b
    其中：
    - b = decimal_odds - 1（净赔率）
    - p = 模型预测胜率
    - q = 1 - p

    半凯利：actual_stake = f* * 0.5

    Args:
        model_prob: 模型预测胜率 (0-1)
        decimal_odds: 小数赔率（如 2.50）
        kelly_fraction: Kelly 分数（默认 0.5 = 半凯利）

    Returns:
        建议仓位比例（0-1），0 表示不建议投注
    """
    if kelly_fraction is None:
        kelly_fraction = config.KELLY_FRACTION

    if decimal_odds <= 1.0:
        return 0.0
    if model_prob <= 0 or model_prob >= 1:
        return 0.0

    b = decimal_odds - 1  # 净赔率
    p = model_prob
    q = 1 - p

    # Kelly 公式
    full_kelly = (b * p - q) / b

    # 如果 Kelly 值为负，表示没有正期望值
    if full_kelly <= 0:
        return 0.0

    # 半凯利策略
    actual_kelly = full_kelly * kelly_fraction

    return actual_kelly


def apply_risk_controls(kelly_stake: float, confidence: float = 0.5,
                        league_tier: str = "A") -> float:
    """
    应用风控红线

    规则：
    1. 单场不超过总资金 5%
    2. C 级联赛/数据不足：上限 1.5%
    3. 低置信度（< 0.3）：减半
    4. 高置信度（> 0.8）：可适当增加，但不超过上限

    Args:
        kelly_stake: Kelly 计算出的原始仓位
        confidence: 预测置信度 (0-1)
        league_tier: 联赛等级 "A" / "B" / "C"

    Returns:
        风控调整后的仓位
    """
    stake = kelly_stake

    # 单场上限
    max_stake = config.KELLY_MAX_STAKE  # 5%

    # C 级联赛上限
    if league_tier == "C":
        max_stake = min(max_stake, config.KELLY_LOW_CONFIDENCE_MAX)  # 1.5%

    # 低置信度减半
    if confidence < 0.3:
        stake *= 0.5
    elif confidence < 0.5:
        stake *= 0.75

    # 应用上限
    stake = min(stake, max_stake)

    return round(stake, 4)


def calc_match_stake(model_prob: float, market_odds: float,
                     confidence: float = 0.5,
                     league_tier: str = "A") -> Dict:
    """
    计算单场比赛的完整仓位建议

    Args:
        model_prob: 模型预测胜率
        market_odds: 市场赔率（小数）
        confidence: 预测置信度
        league_tier: 联赛等级

    Returns:
        {raw_kelly, adjusted_stake, max_stake, recommendation, edge}
    """
    raw = calc_kelly_stake(model_prob, market_odds)
    adjusted = apply_risk_controls(raw, confidence, league_tier)

    # 计算 edge（模型概率 vs 市场隐含概率）
    market_prob = 1.0 / market_odds if market_odds > 0 else 0
    edge = model_prob - market_prob

    # 建议等级
    if adjusted <= 0:
        recommendation = "跳过"
    elif adjusted < 0.01:
        recommendation = "观望"
    elif adjusted < 0.02:
        recommendation = "轻仓"
    elif adjusted < 0.03:
        recommendation = "中仓"
    else:
        recommendation = "重仓"

    return {
        "raw_kelly": round(raw, 4),
        "adjusted_stake": adjusted,
        "max_stake": config.KELLY_MAX_STAKE,
        "edge": round(edge, 4),
        "recommendation": recommendation,
        "model_prob": round(model_prob, 4),
        "market_prob": round(market_prob, 4),
    }


def calc_portfolio_allocation(matches: list,
                              total_bankroll: float = 1000) -> list:
    """
    计算整个投资组合的仓位分配

    Args:
        matches: [{model_prob, market_odds, confidence, league_tier}, ...]
        total_bankroll: 总资金

    Returns:
        [{match, stake_pct, stake_amount, recommendation}, ...]
    """
    results = []
    total_allocated = 0

    for m in matches:
        stake_info = calc_match_stake(
            m.get("model_prob", 0.5),
            m.get("market_odds", 2.0),
            m.get("confidence", 0.5),
            m.get("league_tier", "A")
        )

        stake_pct = stake_info["adjusted_stake"]
        stake_amount = round(total_bankroll * stake_pct, 2)

        # 确保总仓位不超过 30%（分散风险）
        if total_allocated + stake_pct > 0.30:
            stake_pct = max(0, 0.30 - total_allocated)
            stake_amount = round(total_bankroll * stake_pct, 2)

        total_allocated += stake_pct

        results.append({
            "match": m.get("match", "Unknown"),
            "home_team": m.get("home_team", ""),
            "away_team": m.get("away_team", ""),
            "stake_pct": round(stake_pct * 100, 2),
            "stake_amount": stake_amount,
            "recommendation": stake_info["recommendation"],
            "edge": stake_info["edge"],
            "model_prob": stake_info["model_prob"],
            "market_prob": stake_info["market_prob"],
        })

    return results
