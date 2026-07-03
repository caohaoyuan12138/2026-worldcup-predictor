"""
xG 模型参数校准

用已知的典型射门 xG 参考值（来自 StatsBomb 等公开研究）校准物理模型参数。
目标：使模型输出尽可能接近已知的参考值。

同时用本地 75 场已完赛数据校准球队级特征。
"""

import os
import sys
import json
import math
import random

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from physics_xg import (
    calc_shot_xg, calibrate_with_actual_goals,
    XGCoefficients, GOAL_X, GOAL_CENTER_Y
)

random.seed(42)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ── 参考数据点（射门位置 → 已知 xG）──
# 来自 StatsBomb 公开研究和历史数据
REFERENCE_POINTS = [
    # (x, y, body_part, shot_type, situation_flags, expected_xg, description)
    (120, 40, 'Right Foot', 'Penalty', {}, 0.76, '点球'),

    # 空门
    (118, 40, 'Right Foot', 'Open Play', {'open_goal': True}, 0.92, '空门5m'),

    # 一对一（禁区内）
    (115, 40, 'Right Foot', 'Open Play', {'one_on_one': True}, 0.42, '一对一正面'),
    (115, 38, 'Right Foot', 'Open Play', {'one_on_one': True}, 0.38, '一对一偏左'),
    (115, 42, 'Right Foot', 'Open Play', {'one_on_one': True}, 0.38, '一对一偏右'),

    # 禁区内推射（约8-12m）
    (112, 40, 'Right Foot', 'Open Play', {'first_time': True}, 0.28, '禁区内推射正中'),
    (112, 38, 'Right Foot', 'Open Play', {'first_time': True}, 0.22, '禁区内推射偏左'),
    (112, 42, 'Right Foot', 'Open Play', {'first_time': True}, 0.22, '禁区内推射偏右'),
    (110, 40, 'Right Foot', 'Open Play', {}, 0.20, '禁区线推射'),
    (108, 40, 'Right Foot', 'Open Play', {}, 0.15, '禁区边缘推射'),

    # 头球
    (112, 40, 'Head', 'Open Play', {'cross': True}, 0.15, '禁区内头球'),
    (110, 38, 'Head', 'Open Play', {'cross': True}, 0.10, '禁区线头球'),

    # 远射
    (100, 40, 'Right Foot', 'Open Play', {}, 0.06, '远射正面'),
    (100, 35, 'Right Foot', 'Open Play', {}, 0.04, '远射偏左'),
    (95, 40, 'Right Foot', 'Open Play', {}, 0.04, '超远射'),
    (90, 40, 'Right Foot', 'Open Play', {}, 0.02, '超远射30m'),

    # 任意球
    (100, 40, 'Right Foot', 'Free Kick', {}, 0.07, '任意球正面25m'),
    (100, 35, 'Right Foot', 'Free Kick', {}, 0.04, '任意球偏左'),
    (105, 40, 'Right Foot', 'Free Kick', {}, 0.05, '任意球20m'),

    # 直塞助攻
    (114, 40, 'Right Foot', 'Open Play', {'one_on_one': True, 'through_ball': True}, 0.45, '直塞一对一'),
    (112, 38, 'Right Foot', 'Open Play', {'first_time': True, 'through_ball': True}, 0.30, '直塞推射'),

    # 盘带后射门
    (112, 40, 'Right Foot', 'Open Play', {'follows_dribble': True}, 0.20, '盘带后射门'),

    # 小角度
    (118, 30, 'Right Foot', 'Open Play', {}, 0.06, '小角度右侧'),
    (118, 50, 'Right Foot', 'Open Play', {}, 0.06, '小角度左侧'),
]


def error_for_params(base_rate, dist_lambda, angle_exp, header_lambda):
    """
    计算给定参数下的总误差

    Returns:
        float: 均方根误差 (RMSE)
    """
    # 临时修改系数
    orig = {
        'br': XGCoefficients.BASE_RATE,
        'dl': XGCoefficients.DISTANCE_LAMBDA,
        'ae': XGCoefficients.ANGLE_EXPONENT,
        'hl': XGCoefficients.HEADER_DISTANCE_LAMBDA,
    }
    XGCoefficients.BASE_RATE = base_rate
    XGCoefficients.DISTANCE_LAMBDA = dist_lambda
    XGCoefficients.ANGLE_EXPONENT = angle_exp
    XGCoefficients.HEADER_DISTANCE_LAMBDA = header_lambda

    errors = []
    for x, y, bp, st, sit, expected, desc in REFERENCE_POINTS:
        pred = calc_shot_xg(x, y, body_part=bp, shot_type=st, **sit)
        errors.append((pred - expected) ** 2)

    # 恢复
    XGCoefficients.BASE_RATE = orig['br']
    XGCoefficients.DISTANCE_LAMBDA = orig['dl']
    XGCoefficients.ANGLE_EXPONENT = orig['ae']
    XGCoefficients.HEADER_DISTANCE_LAMBDA = orig['hl']

    return (sum(errors) / len(errors)) ** 0.5


def grid_search_params():
    """网格搜索最优参数"""
    print("=" * 60)
    print("参数校准：网格搜索")
    print("=" * 60)

    best_rmse = 999
    best_params = None

    # 搜索范围
    base_rates = [0.85, 0.90, 0.95, 1.0, 1.05, 1.1]
    dist_lambdas = [10, 11, 12, 13, 14, 15, 16]
    angle_exps = [1.0, 1.1, 1.2, 1.3, 1.4, 1.5]
    header_lambdas = [6, 7, 8, 9, 10]

    total = len(base_rates) * len(dist_lambdas) * len(angle_exps) * len(header_lambdas)
    tested = 0

    for br in base_rates:
        for dl in dist_lambdas:
            for ae in angle_exps:
                for hl in header_lambdas:
                    rmse = error_for_params(br, dl, ae, hl)
                    tested += 1
                    if rmse < best_rmse:
                        best_rmse = rmse
                        best_params = (br, dl, ae, hl)

    print(f"\n搜索完成: 测试了 {total} 组参数")
    print(f"\n最优参数:")
    print(f"  BASE_RATE:            {best_params[0]}")
    print(f"  DISTANCE_LAMBDA:      {best_params[1]}")
    print(f"  ANGLE_EXPONENT:       {best_params[2]}")
    print(f"  HEADER_DISTANCE_LAMBDA: {best_params[3]}")
    print(f"  RMSE:                 {best_rmse:.4f}")

    return best_params, best_rmse


def fine_tune_params(coarse_params):
    """精细搜索"""
    print("\n" + "=" * 60)
    print("参数校准：精细搜索")
    print("=" * 60)

    best_rmse = 999
    best_params = coarse_params

    br_c, dl_c, ae_c, hl_c = coarse_params

    for br in [br_c - 0.04 + i * 0.02 for i in range(5)]:
        for dl in [dl_c - 2 + i for i in range(5)]:
            for ae in [ae_c - 0.2 + i * 0.1 for i in range(5)]:
                for hl in [hl_c - 2 + i for i in range(5)]:
                    if br <= 0 or dl <= 0 or ae <= 0 or hl <= 0:
                        continue
                    rmse = error_for_params(br, dl, ae, hl)
                    if rmse < best_rmse:
                        best_rmse = rmse
                        best_params = (br, dl, ae, hl)

    print(f"\n精细搜索完成:")
    print(f"  BASE_RATE:            {best_params[0]:.3f}")
    print(f"  DISTANCE_LAMBDA:      {best_params[1]:.1f}")
    print(f"  ANGLE_EXPONENT:       {best_params[2]:.2f}")
    print(f"  HEADER_DISTANCE_LAMBDA: {best_params[3]:.1f}")
    print(f"  RMSE:                 {best_rmse:.4f}")

    return best_params, best_rmse


def evaluate_model(params):
    """评估模型输出"""
    br, dl, ae, hl = params
    XGCoefficients.BASE_RATE = br
    XGCoefficients.DISTANCE_LAMBDA = dl
    XGCoefficients.ANGLE_EXPONENT = ae
    XGCoefficients.HEADER_DISTANCE_LAMBDA = hl

    print("\n" + "=" * 60)
    print("模型评估")
    print("=" * 60)
    print(f"{'场景':<20s} {'预测':>8s} {'参考':>8s} {'误差':>8s}")
    print("-" * 50)

    errors = []
    for x, y, bp, st, sit, expected, desc in REFERENCE_POINTS:
        pred = calc_shot_xg(x, y, body_part=bp, shot_type=st, **sit)
        err = pred - expected
        errors.append(err ** 2)
        marker = "[OK]" if abs(err) < 0.05 else "[XX]"
        print(f"  {desc:<18s} {pred:8.3f} {expected:8.3f} {err:+8.3f} {marker}")

    rmse = (sum(errors) / len(errors)) ** 0.5
    mae = sum(abs(e ** 0.5) for e in errors) / len(errors)
    print(f"\nRMSE: {rmse:.4f}")
    print(f"MAE:  {mae:.4f}")

    return rmse


def calibrate_team_xg_from_local_data():
    """
    用本地 75 场已完赛数据 + 懂球帝统计校准球队级 xG
    """
    print("\n" + "=" * 60)
    print("球队级 xG 校准（本地数据）")
    print("=" * 60)

    with open(os.path.join(BASE_DIR, 'db', 'worldcup.json'), 'r', encoding='utf-8') as f:
        wc = json.load(f)

    dims = wc['meta']['teamDimensions']
    teams_data = wc['teams']
    completed = wc['completedMatches']

    # 计算每支球队的实际比赛场数和进球
    team_goals = {}
    team_matches = {}
    for m in completed:
        home = m['home']
        away = m['away']
        hs, as_ = map(int, m['score'].split('-'))
        team_goals[home] = team_goals.get(home, 0) + hs
        team_goals[away] = team_goals.get(away, 0) + as_
        team_matches[home] = team_matches.get(home, 0) + 1
        team_matches[away] = team_matches.get(away, 0) + 1

    # 百分比型维度（值 > 1 时需要除以 100）
    percentage_dims = {'传球成功率', '控球率'}

    # 对每支球队计算 xG 特征
    team_xg_features = {}
    for name, team in teams_data.items():
        dq = team.get('dongqiudi', {})
        # 将懂球帝数据转为 dict（维度名 -> 值）
        raw_stats = {}
        if isinstance(dq, dict):
            for i, dim in enumerate(dims):
                if dim in dq:
                    val = dq[dim]
                    # 尝试转为数值
                    try:
                        val = float(val)
                    except (ValueError, TypeError):
                        val = 0
                    raw_stats[dim] = val

        n_matches = team_matches.get(name, 0)
        if n_matches == 0:
            n_matches = 1  # 避免除零

        # 将累积值转为场均值
        stats = {}
        for dim, val in raw_stats.items():
            if dim in percentage_dims:
                # 百分比：直接除以 100 转为小数
                stats[dim] = val / 100.0 if val > 1 else val
            else:
                # 计数型：除以比赛场数得到场均值
                stats[dim] = val / n_matches

        actual_goals = team_goals.get(name, 0)
        features = calibrate_with_actual_goals(stats, actual_goals, n_matches)
        team_xg_features[name] = features

    # 打印结果
    print(f"\n{'球队':<15s} {'进攻xG':>8s} {'防守xG':>8s} {'xG差':>8s} {'进球/场':>8s} {'射门':>6s} {'射正率':>8s}")
    print("-" * 75)

    sorted_teams = sorted(team_xg_features.items(), key=lambda x: x[1]['offensive_xg'], reverse=True)

    for name, feat in sorted_teams:
        matches = team_matches.get(name, 0)
        gpg = feat['goals_per_game']
        print(f"  {name:<13s} {feat['offensive_xg']:8.3f} {feat['defensive_xg']:8.3f} "
              f"{feat['xg_diff']:+8.3f} {gpg:8.3f} {feat['shot_volume']:6.1f} {feat['shot_accuracy']:8.3f}")

    return team_xg_features


def main():
    # 1. 网格搜索 + 精细校准
    coarse_params, _ = grid_search_params()
    best_params, best_rmse = fine_tune_params(coarse_params)

    # 2. 评估
    evaluate_model(best_params)

    # 3. 应用最优参数
    br, dl, ae, hl = best_params
    XGCoefficients.BASE_RATE = br
    XGCoefficients.DISTANCE_LAMBDA = dl
    XGCoefficients.ANGLE_EXPONENT = ae
    XGCoefficients.HEADER_DISTANCE_LAMBDA = hl

    # 4. 球队级校准
    team_xg = calibrate_team_xg_from_local_data()

    # 5. 保存结果
    output_dir = os.path.join(BASE_DIR, 'model', 'xg_model')
    os.makedirs(output_dir, exist_ok=True)

    # 保存校准后的参数
    params_path = os.path.join(output_dir, 'xg_coefficients.json')
    coeffs = {
        'BASE_RATE': br,
        'DISTANCE_LAMBDA': dl,
        'ANGLE_EXPONENT': ae,
        'HEADER_DISTANCE_LAMBDA': hl,
        'PENALTY_XG': 0.76,
        'RMSE': round(best_rmse, 4),
        'n_reference_points': len(REFERENCE_POINTS),
    }
    with open(params_path, 'w') as f:
        json.dump(coeffs, f, indent=2)
    print(f"\n参数保存到: {params_path}")

    # 保存球队 xG 特征
    team_xg_path = os.path.join(BASE_DIR, 'data', 'xg', 'team_xg_features.json')
    os.makedirs(os.path.dirname(team_xg_path), exist_ok=True)
    with open(team_xg_path, 'w', encoding='utf-8') as f:
        json.dump(team_xg, f, indent=2, ensure_ascii=False)
    print(f"球队xG特征保存到: {team_xg_path}")

    print(f"\n{'='*60}")
    print("校准完成!")
    print(f"{'='*60}")


if __name__ == '__main__':
    main()
