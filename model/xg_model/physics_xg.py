"""
物理/统计 xG 模型

基于经典 xG 研究中的距离-角度衰减关系，结合本地球队数据进行校准。
不依赖 StatsBomb 等外部数据源，完全基于公开研究和本地数据。

核心公式（来自 StatsBomb 等公开 xG 研究）：
  xG = base_rate * distance_factor * angle_factor * body_part_factor * situation_factor
"""

import math
import json
import os
import random

# 球场几何常量（StatsBomb 标准 120x80）
PITCH_LENGTH = 120.0
PITCH_WIDTH = 80.0
GOAL_X = 120.0
GOAL_CENTER_Y = 40.0
GOAL_HALF_WIDTH = 3.66  # 球门半宽（7.32m / 2）


# 经典 xG 参数（使用 2026 世界杯 78 场已完赛数据校准）
class XGCoefficients:
    DISTANCE_LAMBDA = 14.0       # 距离衰减特征长度（米）
    ANGLE_EXPONENT = 0.5         # 角度因子指数（平方根，避免远离球门时过度衰减）
    BASE_RATE = 1.20             # 基础进球率

    BODY_PART_FACTORS = {
        'Right Foot': 1.0,
        'Left Foot': 0.92,
        'Head': 0.55,
        'Other': 0.35,
    }

    SHOT_TYPE_FACTORS = {
        'Open Play': 1.0,
        'Free Kick': 0.35,
        'Corner': 0.25,
        'Penalty': 1.0,
        'Throw-in': 0.10,
    }

    SITUATION_FACTORS = {
        'first_time': 1.15,
        'follows_dribble': 1.10,
        'one_on_one': 1.25,
        'open_goal': 5.0,
        'aerial_won': 1.05,
        'assisted_through_ball': 1.20,
        'assisted_cross': 1.10,
    }

    HEADER_DISTANCE_LAMBDA = 8.0
    PENALTY_XG = 0.76


def calc_distance_to_goal(x, y):
    """射门点到球门中心的距离"""
    return math.sqrt((GOAL_X - x) ** 2 + (GOAL_CENTER_Y - y) ** 2)


def calc_angle_to_goal(x, y):
    """射门点与两立柱的夹角（弧度）"""
    if x >= GOAL_X:
        return math.pi
    angle1 = math.atan2(GOAL_CENTER_Y - GOAL_HALF_WIDTH - y, GOAL_X - x)
    angle2 = math.atan2(GOAL_CENTER_Y + GOAL_HALF_WIDTH - y, GOAL_X - x)
    return abs(angle2 - angle1)


def distance_factor(distance, is_header=False):
    """距离衰减因子"""
    lam = XGCoefficients.HEADER_DISTANCE_LAMBDA if is_header else XGCoefficients.DISTANCE_LAMBDA
    return math.exp(-distance / lam)


def angle_factor(angle_rad):
    """角度因子"""
    normalized = min(1.0, angle_rad / math.pi)
    return normalized ** XGCoefficients.ANGLE_EXPONENT


def calc_shot_xg(x, y, body_part='Right Foot', shot_type='Open Play',
                  first_time=False, one_on_one=False, open_goal=False,
                  follows_dribble=False, through_ball=False, cross=False):
    """
    计算单次射门的 xG 值

    Returns:
        float: xG 值 [0.001, 0.99]
    """
    if shot_type == 'Penalty':
        return XGCoefficients.PENALTY_XG

    distance = calc_distance_to_goal(x, y)
    angle = calc_angle_to_goal(x, y)
    is_header = (body_part == 'Head')

    df_val = distance_factor(distance, is_header)
    af = angle_factor(angle)
    bf = XGCoefficients.BODY_PART_FACTORS.get(body_part, 0.8)
    sf = XGCoefficients.SHOT_TYPE_FACTORS.get(shot_type, 0.3)

    sit_f = 1.0
    if open_goal:
        sit_f *= XGCoefficients.SITUATION_FACTORS['open_goal']
    if first_time:
        sit_f *= XGCoefficients.SITUATION_FACTORS['first_time']
    if one_on_one:
        sit_f *= XGCoefficients.SITUATION_FACTORS['one_on_one']
    if follows_dribble:
        sit_f *= XGCoefficients.SITUATION_FACTORS['follows_dribble']
    if through_ball:
        sit_f *= XGCoefficients.SITUATION_FACTORS['assisted_through_ball']
    if cross:
        sit_f *= XGCoefficients.SITUATION_FACTORS['assisted_cross']

    xg = XGCoefficients.BASE_RATE * df_val * af * bf * sf * sit_f
    return min(0.99, max(0.001, xg))


def calibrate_with_actual_goals(team_stats, actual_goals, n_matches):
    """
    用实际进球数据校准 xG 模型

    Args:
        team_stats: 球队统计数据 dict
        actual_goals: 实际进球数
        n_matches: 比赛场数

    Returns:
        dict: 校准后的 xG 特征
    """
    goals_per_game = actual_goals / max(n_matches, 1)

    shots_per_game = team_stats.get('射门', 10)
    on_target_per_game = team_stats.get('射正', 3)

    # 射正率 -> 射门质量
    shot_accuracy = on_target_per_game / max(shots_per_game, 1)

    # 关键传球 -> 机会创造
    key_passes = team_stats.get('关键传球', 10)
    key_pass_rate = key_passes / max(shots_per_game, 1)

    # 绝佳机会
    big_chances = team_stats.get('创造进球机会', 5)
    big_chance_rate = big_chances / max(shots_per_game, 1)

    # 估算场均 xG
    base_shot_xg = 0.10
    accuracy_bonus = 1.0 + (shot_accuracy - 0.35) * 0.8
    key_pass_bonus = 1.0 + (key_pass_rate - 1.0) * 0.3
    big_chance_bonus = 1.0 + big_chance_rate * 0.5

    estimated_xg = shots_per_game * base_shot_xg * accuracy_bonus * key_pass_bonus * big_chance_bonus

    # 终结效率
    conversion_ratio = goals_per_game / max(estimated_xg, 0.1)
    conversion_ratio = min(2.0, max(0.3, conversion_ratio))

    # 防守 xG
    goals_conceded_per_game = team_stats.get('失球', 3) / max(n_matches, 1)
    saves_per_game = team_stats.get('扑救', 2)
    defensive_xg = goals_conceded_per_game + saves_per_game * 0.3

    # xG 差
    xg_diff = estimated_xg - defensive_xg

    return {
        'offensive_xg': round(estimated_xg, 3),
        'defensive_xg': round(defensive_xg, 3),
        'xg_diff': round(xg_diff, 3),
        'shot_quality': round(base_shot_xg * accuracy_bonus * key_pass_bonus, 4),
        'shot_volume': round(shots_per_game, 1),
        'shot_accuracy': round(shot_accuracy, 3),
        'conversion_ratio': round(conversion_ratio, 3),
        'goals_per_game': round(goals_per_game, 3),
        'big_chance_rate': round(big_chance_rate, 3),
    }


# 典型射门的 xG 参考值
SHOT_XG_REFERENCE = {
    'penalty': 0.76,
    'open_goal_5m': 0.90,
    'one_on_one_10m': 0.45,
    'close_range_8m': 0.35,
    'close_range_header_8m': 0.20,
    'edge_of_box_18m': 0.15,
    'edge_of_box_header_18m': 0.08,
    'long_range_25m': 0.05,
    'long_range_30m': 0.03,
    'free_kick_25m_central': 0.08,
    'free_kick_30m_wide': 0.02,
    'half_chance_15m': 0.10,
    'big_chance': 0.45,
}


def get_reference_xg(scenario):
    """获取典型射门的参考 xG 值"""
    return SHOT_XG_REFERENCE.get(scenario, 0.10)


if __name__ == '__main__':
    # 测试典型射门 xG
    print("典型射门 xG 参考值:")
    print(f"  点球 (Penalty):          {calc_shot_xg(120, 40, shot_type='Penalty'):.3f}")
    print(f"  空门 (118, 40):           {calc_shot_xg(118, 40, open_goal=True):.3f}")
    print(f"  禁区内推射 (112, 40):     {calc_shot_xg(112, 40, first_time=True):.3f}")
    print(f"  禁区内头球 (112, 40):     {calc_shot_xg(112, 40, body_part='Head', cross=True):.3f}")
    print(f"  小角度 (118, 32):         {calc_shot_xg(118, 32, one_on_one=True):.3f}")
    print(f"  远射 (100, 40):           {calc_shot_xg(100, 40):.3f}")
    print(f"  任意球 (100, 40):         {calc_shot_xg(100, 40, shot_type='Free Kick'):.3f}")
    print(f"  传中头球 (112, 38):        {calc_shot_xg(112, 38, body_part='Head', cross=True):.3f}")
    print(f"  直塞一对一 (115, 40):     {calc_shot_xg(115, 40, one_on_one=True, through_ball=True):.3f}")
    print()
    print("参考值对比:")
    for k, v in SHOT_XG_REFERENCE.items():
        print(f"  {k:30s} {v:.3f}")
