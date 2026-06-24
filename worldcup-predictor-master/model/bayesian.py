"""
贝叶斯融合层

功能：
1. 多阶段权重融合（小组赛 → 淘汰赛 → 半决赛/决赛）
2. 市场隐含概率与模型概率加权融合
3. 多维度环境修正因子
4. 输出最终预测概率 + 置信区间
"""

from typing import Dict, Tuple, Optional
import math
import config


def calc_market_implied_prob(odds_home: float, odds_draw: float,
                             odds_away: float) -> Dict[str, float]:
    """
    从赔率计算市场隐含概率（去 Vig）

    去 Vig 方法：proportional（按比例分配）
    implied_prob = (1/odds) / sum(1/odds_i)

    Returns:
        {"home_win": float, "draw": float, "away_win": float}
    """
    inv_home = 1.0 / odds_home if odds_home > 0 else 0
    inv_draw = 1.0 / odds_draw if odds_draw > 0 else 0
    inv_away = 1.0 / odds_away if odds_away > 0 else 0

    total_inv = inv_home + inv_draw + inv_away
    if total_inv <= 0:
        return {"home_win": 0.33, "draw": 0.34, "away_win": 0.33}

    return {
        "home_win": round(inv_home / total_inv, 4),
        "draw": round(inv_draw / total_inv, 4),
        "away_win": round(inv_away / total_inv, 4)
    }


def bayesian_fusion(model_probs: Dict[str, float],
                    market_probs: Dict[str, float],
                    stage: str = "group_stage",
                    model_confidence: float = 0.5) -> Dict[str, float]:
    """
    贝叶斯加权融合

    P_final = w_model * P_model + w_market * P_market + corrections

    Args:
        model_probs: 模型预测概率 {"home_win", "draw", "away_win"}
        market_probs: 市场隐含概率 {"home_win", "draw", "away_win"}
        stage: 比赛阶段 ("group_stage", "round_of_16", "quarter_final",
               "semi_final", "final")
        model_confidence: 模型置信度 (0-1)

    Returns:
        融合后的概率 {"home_win", "draw", "away_win", "confidence"}
    """
    weights = config.BAYESIAN_WEIGHTS.get(stage, (0.6, 0.4))
    w_model_base, w_market_base = weights

    # 根据模型置信度动态调整权重
    w_model = w_model_base * model_confidence
    w_market = w_market_base
    total_w = w_model + w_market
    if total_w > 0:
        w_model /= total_w
        w_market /= total_w

    home = (w_model * model_probs.get("home_win", 0.33) +
            w_market * market_probs.get("home_win", 0.33))
    draw = (w_model * model_probs.get("draw", 0.34) +
            w_market * market_probs.get("draw", 0.34))
    away = (w_model * model_probs.get("away_win", 0.33) +
            w_market * market_probs.get("away_win", 0.33))

    # 归一化
    total = home + draw + away
    if total > 0:
        home /= total
        draw /= total
        away /= total

    # 计算融合置信度
    # 模型和市场的预测越一致，置信度越高
    agreement = 1.0 - (
        abs(model_probs.get("home_win", 0) - market_probs.get("home_win", 0)) +
        abs(model_probs.get("draw", 0) - market_probs.get("draw", 0)) +
        abs(model_probs.get("away_win", 0) - market_probs.get("away_win", 0))
    ) / 2
    confidence = round(min(agreement * model_confidence * 2, 1.0), 4)

    return {
        "home_win": round(home, 4),
        "draw": round(draw, 4),
        "away_win": round(away, 4),
        "confidence": confidence,
        "weight_model": round(w_model, 3),
        "weight_market": round(w_market, 3),
        "stage": stage
    }


def calc_confidence_interval(prob: float, n_samples: int = 10000,
                             confidence: float = 0.95) -> Tuple[float, float]:
    """
    计算预测概率的置信区间（Wilson score interval）

    Args:
        prob: 预测概率
        n_samples: 样本量
        confidence: 置信水平

    Returns:
        (lower_bound, upper_bound)
    """
    if n_samples <= 0:
        return (0.0, 1.0)

    z_map = {0.90: 1.645, 0.95: 1.96, 0.99: 2.576}
    z = z_map.get(confidence, 1.96)

    denominator = 1 + z ** 2 / n_samples
    center = (prob + z ** 2 / (2 * n_samples)) / denominator
    spread = z * math.sqrt(
        (prob * (1 - prob) + z ** 2 / (4 * n_samples)) / n_samples
    ) / denominator

    return (max(0, center - spread), min(1, center + spread))


def apply_stage(result: Dict, stage: str) -> Dict:
    """
    应用阶段特定的融合权重重新计算
    """
    if "model_probs" not in result or "market_probs" not in result:
        return result
    mr = bayesian_fusion(
        result["model_probs"], result["market_probs"], stage)
    result["final_probs"] = mr
    return mr


def detect_market_value(model_probs: Dict[str, float],
                        market_probs: Dict[str, float],
                        threshold: float = 0.05) -> Dict[str, Dict]:
    """
    检测市场价值投注机会

    当模型概率 > 市场概率 threshold 时视为有价值

    Returns:
        {"home_win": {"value": bool, "edge": float}, ...}
    """
    results = {}
    for outcome in ["home_win", "draw", "away_win"]:
        m_prob = model_probs.get(outcome, 0)
        mk_prob = market_probs.get(outcome, 0)
        edge = m_prob - mk_prob
        results[outcome] = {
            "value": edge >= threshold,
            "edge": round(edge, 4),
            "model_prob": round(m_prob, 4),
            "market_prob": round(mk_prob, 4)
        }
    return results
