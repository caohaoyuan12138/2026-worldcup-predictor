"""
Dixon-Coles 修正泊松模型

功能：
1. 计算主队/客队进球期望参数（λ）
2. Dixon-Coles 低比分修正因子（ρ）
3. 计算单场比分概率矩阵
4. 计算胜/平/负概率
"""

import math
from typing import Dict, Tuple, Optional, List
from functools import lru_cache
import config


def poisson_pmf(k: int, lam: float) -> float:
    """泊松分布概率质量函数 P(X=k) = λ^k * e^(-λ) / k!"""
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    if k < 0:
        return 0.0
    return (lam ** k) * math.exp(-lam) / math.factorial(k)


def _attack_strength(team_id: int, elo_engine, is_home: bool) -> float:
    """
    计算球队进攻强度
    进攻强度 = 近期场均进球 / 联赛均值（此处简化为基于 Elo 的估算）
    """
    rating = elo_engine.get_rating(team_id)
    if rating is None:
        return 1.0
    base = 1.3  # 基准场均进球
    elo_factor = (rating - 1500) / 400 * config.ELO_TO_GOAL_DIFF * 10
    return max(0.3, base + elo_factor)


def _defense_strength(team_id: int, elo_engine, is_home: bool) -> float:
    """
    计算球队防守强度
    防守强度 = 近期场均失球 / 联赛均值
    """
    rating = elo_engine.get_rating(team_id)
    if rating is None:
        return 1.0
    base = 1.0  # 基准场均失球
    elo_factor = (1500 - rating) / 400 * config.ELO_TO_GOAL_DIFF * 5
    return max(0.2, base + elo_factor)


def calc_expected_goals(home_team_id: int, away_team_id: int,
                        elo_engine, home_attack: float = None,
                        home_defense: float = None,
                        away_attack: float = None,
                        away_defense: float = None,
                        stage: str = "group_stage",
                        motivation_home: float = 1.0,
                        motivation_away: float = 1.0) -> Tuple[float, float]:
    """
    计算主客队期望进球数

    λ_home = home_attack * away_defense * avg_goals * elo_factor * motivation
    λ_away = away_attack * home_defense * avg_goals * elo_factor * motivation

    Args:
        stage: 比赛阶段 ("group_stage", "round_of_16", "quarter_final", "semi_final", "final")
        motivation_home/away: 动机因子（小组赛末轮已出线=0.85, 关键战=1.2）

    Returns:
        (lambda_home, lambda_away)
    """
    # 使用传入的强度参数，或从 Elo 引擎估算
    if home_attack is None:
        home_attack = _attack_strength(home_team_id, elo_engine, True)
    if home_defense is None:
        home_defense = _defense_strength(home_team_id, elo_engine, True)
    if away_attack is None:
        away_attack = _attack_strength(away_team_id, elo_engine, False)
    if away_defense is None:
        away_defense = _defense_strength(away_team_id, elo_engine, False)

    # 按阶段调整基准进球数
    stage_avg = {
        "group_stage": config.AVG_GOALS_GROUP_STAGE,
        "round_of_16": config.AVG_GOALS_KNOCKOUT,
        "quarter_final": config.AVG_GOALS_KNOCKOUT,
        "semi_final": config.AVG_GOALS_KNOCKOUT,
        "final": config.AVG_GOALS_FINAL,
    }
    avg_goals = stage_avg.get(stage, config.AVG_GOALS_GROUP_STAGE)

    # Elo 分差修正
    home_rating = elo_engine.get_rating(home_team_id) or 1500
    away_rating = elo_engine.get_rating(away_team_id) or 1500
    elo_diff = (home_rating - away_rating) / 100
    home_elo_factor = 1 + config.DC_ALPHA * elo_diff
    away_elo_factor = 1 - config.DC_BETA * elo_diff

    # 环境修正（动机因子：已出线球队轮换→进球期望降低）
    home_adj = motivation_home
    away_adj = motivation_away

    lambda_home = max(0.1, home_attack * away_defense * avg_goals * home_elo_factor * home_adj)
    lambda_away = max(0.1, away_attack * home_defense * avg_goals * away_elo_factor * away_adj)

    return lambda_home, lambda_away


def _dixon_coles_rho(lambda_home: float, lambda_away: float,
                    score_matrix: Dict) -> float:
    """
    Dixon-Coles 低比分修正参数

    修正 0-0, 1-0, 0-1, 1-1 的概率：
    τ(x,y) = 1 - λ_home*λ_y*ρ   if x=y=0
    τ(x,y) = 1 + λ_home*ρ        if x=0, y=1
    τ(x,y) = 1 + λ_away*ρ        if x=1, y=0
    τ(x,y) = 1 - ρ               if x=y=1
    τ(x,y) = 1                   otherwise

    典型值 ρ ≈ -0.12（负相关表示低比分更集中）
    """
    return config.DC_RHO_DEFAULT


def calc_score_matrix(lambda_home: float, lambda_away: float,
                      max_goals: int = 6,
                      rho: float = None) -> Dict[Tuple[int, int], float]:
    """
    计算比分概率矩阵 P(home_goals=x, away_goals=y)

    Args:
        lambda_home: 主队期望进球
        lambda_away: 客队期望进球
        max_goals: 最大计算进球数
        rho: Dixon-Coles 修正参数，None 则使用默认值

    Returns:
        {(x,y): probability} 比分概率矩阵
    """
    if rho is None:
        rho = _dixon_coles_rho(lambda_home, lambda_away, {})

    matrix = {}
    for i in range(max_goals + 1):
        for j in range(max_goals + 1):
            # 基础泊松概率
            p = poisson_pmf(i, lambda_home) * poisson_pmf(j, lambda_away)

            # Dixon-Coles 修正
            tau = 1.0
            if i == 0 and j == 0:
                tau = 1 - lambda_home * lambda_away * rho
            elif i == 0 and j == 1:
                tau = 1 + lambda_home * rho
            elif i == 1 and j == 0:
                tau = 1 + lambda_away * rho
            elif i == 1 and j == 1:
                tau = 1 - rho

            matrix[(i, j)] = max(0, p * tau)

    # 归一化
    total = sum(matrix.values())
    if total > 0:
        for key in matrix:
            matrix[key] /= total

    return matrix


def calc_match_probabilities(score_matrix: Dict[Tuple[int, int], float]) -> Dict[str, float]:
    """
    从比分矩阵计算胜/平/负概率

    Returns:
        {"home_win": float, "draw": float, "away_win": float}
    """
    home_win = 0.0
    draw = 0.0
    away_win = 0.0

    for (hg, ag), prob in score_matrix.items():
        if hg > ag:
            home_win += prob
        elif hg == ag:
            draw += prob
        else:
            away_win += prob

    total = home_win + draw + away_win
    if total > 0:
        home_win /= total
        draw /= total
        away_win /= total

    return {
        "home_win": round(home_win, 4),
        "draw": round(draw, 4),
        "away_win": round(away_win, 4)
    }


def get_favorite_scorelines(score_matrix: Dict[Tuple[int, int], float],
                            top_n: int = 5) -> List[Dict]:
    """返回概率最高的 N 个比分"""
    sorted_scores = sorted(score_matrix.items(), key=lambda x: -x[1])
    results = []
    for (hg, ag), prob in sorted_scores[:top_n]:
        results.append({
            "score": f"{hg}-{ag}",
            "probability": round(prob * 100, 2)
        })
    return results
