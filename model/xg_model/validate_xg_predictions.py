"""
验证 xG 预测精度

从 match_xg_results.json 加载数据，计算：
- MAE / RMSE（预测 xG vs 实际进球）
- 校准曲线（分桶 xG vs 实际进球率）
- 球队级超/低预期排名

用法：python model/xg_model/validate_xg_predictions.py
"""

import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def load_data():
    """加载比赛 xG 结果和 worldcup 数据"""
    with open(os.path.join(BASE_DIR, 'data', 'xg', 'match_xg_results.json'), 'r', encoding='utf-8') as f:
        match_xg = json.load(f)
    with open(os.path.join(BASE_DIR, 'db', 'worldcup.json'), 'r', encoding='utf-8') as f:
        wc = json.load(f)
    return match_xg, wc


def compute_mae_rmse(match_xg):
    """计算 MAE 和 RMSE"""
    n = len(match_xg)
    total_ae = 0
    total_se = 0
    total_xg = 0
    total_goals = 0

    for m in match_xg:
        # 主队
        home_diff = abs(m['home_goals'] - m['home_xg'])
        total_ae += home_diff
        total_se += home_diff ** 2
        total_xg += m['home_xg']
        total_goals += m['home_goals']

        # 客队
        away_diff = abs(m['away_goals'] - m['away_xg'])
        total_ae += away_diff
        total_se += away_diff ** 2
        total_xg += m['away_xg']
        total_goals += m['away_goals']

    mae = total_ae / (2 * n)
    rmse = math.sqrt(total_se / (2 * n))
    return mae, rmse, total_xg, total_goals, n


def compute_calibration_curve(match_xg, bins=10):
    """
    校准曲线：将 xG 值分桶，计算每个桶的实际进球率

    Returns:
        list of dict: {bin_label, bin_center, n_shots, n_goals, actual_rate, expected_rate}
    """
    # 收集所有射门的 xG 和 is_goal
    all_shots = []
    for m in match_xg:
        for s in m.get('shots', []):
            all_shots.append({'xg': s['xg'], 'is_goal': s['is_goal']})

    if not all_shots:
        return []

    # 按 xG 值排序
    all_shots.sort(key=lambda x: x['xg'])

    n = len(all_shots)
    bin_size = n // bins

    calibration = []
    for i in range(bins):
        start = i * bin_size
        end = start + bin_size if i < bins - 1 else n
        bucket = all_shots[start:end]
        avg_xg = sum(s['xg'] for s in bucket) / max(len(bucket), 1)
        n_goals = sum(1 for s in bucket if s['is_goal'])
        actual_rate = n_goals / max(len(bucket), 1)

        calibration.append({
            'bin_label': f'{avg_xg:.3f}',
            'bin_center': round(avg_xg, 4),
            'n_shots': len(bucket),
            'n_goals': n_goals,
            'actual_rate': round(actual_rate, 4),
            'expected_rate': round(avg_xg, 4),
        })

    return calibration


def compute_team_xg_accuracy(match_xg):
    """计算每支球队的 xG 准确度指标"""
    team_data = {}

    for m in match_xg:
        for side, team_key in [('home', 'home_team'), ('away', 'away_team')]:
            team = m[team_key]
            xg = m[f'{side}_xg']
            goals = m[f'{side}_goals']

            if team not in team_data:
                team_data[team] = {'matches': 0, 'total_xg': 0, 'total_goals': 0, 'abs_errors': []}

            td = team_data[team]
            td['matches'] += 1
            td['total_xg'] += xg
            td['total_goals'] += goals
            td['abs_errors'].append(abs(goals - xg))

    results = []
    for name, td in team_data.items():
        m = td['matches']
        results.append({
            'team': name,
            'matches': m,
            'total_xg': round(td['total_xg'], 3),
            'total_goals': td['total_goals'],
            'xg_vs_actual': round(td['total_goals'] - td['total_xg'], 3),
            'mae': round(sum(td['abs_errors']) / len(td['abs_errors']), 4),
            'goals_per_game': round(td['total_goals'] / m, 3),
            'xg_per_game': round(td['total_xg'] / m, 3),
        })

    return results


def compute_match_level_error_distribution(match_xg):
    """计算比赛级误差分布"""
    errors = []
    for m in match_xg:
        total_xg = m['home_xg'] + m['away_xg']
        total_goals = m['home_goals'] + m['away_goals']
        errors.append({
            'match_id': m['match_id'],
            'home_team': m['home_team'],
            'away_team': m['away_team'],
            'total_xg': round(total_xg, 3),
            'total_goals': total_goals,
            'error': round(total_goals - total_xg, 3),
            'abs_error': round(abs(total_goals - total_xg), 3),
        })

    errors.sort(key=lambda x: x['abs_error'], reverse=True)
    return errors


def print_validation_report(match_xg):
    """打印完整的验证报告"""
    print("=" * 70)
    print("xG 模型验证报告")
    print("=" * 70)

    # 1. 全局指标
    mae, rmse, total_xg, total_goals, n = compute_mae_rmse(match_xg)
    print(f"\n1. 全局精度指标")
    print(f"  {'比赛数:':20s} {n}")
    print(f"  {'总 xG:':20s} {total_xg:.1f}")
    print(f"  {'总进球:':20s} {total_goals}")
    print(f"  {'xG/场:':20s} {total_xg / (2 * n):.3f}")
    print(f"  {'进球/场:':20s} {total_goals / (2 * n):.3f}")
    print(f"  {'MAE (每队每场):':20s} {mae:.4f}")
    print(f"  {'RMSE (每队每场):':20s} {rmse:.4f}")
    print(f"  {'总 xG / 总进球:':20s} {total_xg / max(total_goals, 1):.3f}")
    print(f"  {'进球 - xG:':20s} {total_goals - total_xg:.1f}")

    # 2. 校准曲线
    print(f"\n2. 校准曲线 (xG 分桶)")
    calibration = compute_calibration_curve(match_xg)
    if calibration:
        print(f"  {'桶中心':>8s} {'射门数':>7s} {'进球':>5s} {'实际率':>8s} {'预期率':>8s} {'偏差':>8s}")
        print("  " + "-" * 48)
        total_bias = 0
        for b in calibration:
            bias = b['actual_rate'] - b['expected_rate']
            total_bias += abs(bias)
            marker = ' ↑' if bias > 0.02 else (' ↓' if bias < -0.02 else '  ')
            print(f"  {b['bin_center']:8.4f} {b['n_shots']:7d} {b['n_goals']:5d} "
                  f"{b['actual_rate']:8.4f} {b['expected_rate']:8.4f} {bias:+8.4f}{marker}")
        print(f"\n  平均绝对校准偏差: {total_bias / max(len(calibration), 1):.4f}")

    # 3. 球队 xG 准确度
    print(f"\n3. 球队 xG 准确度")
    team_results = compute_team_xg_accuracy(match_xg)
    team_results.sort(key=lambda x: x['xg_vs_actual'], reverse=True)

    print(f"  {'球队':<12s} {'场次':>4s} {'xG':>7s} {'进球':>5s} {'差值':>7s} {'MAE':>7s}")
    print("  " + "-" * 46)
    for t in team_results[:10]:
        print(f"  {t['team']:<10s} {t['matches']:4d} {t['total_xg']:7.3f} "
              f"{t['total_goals']:5d} {t['xg_vs_actual']:+7.3f} {t['mae']:7.4f}")
    print("  ...")
    for t in team_results[-5:]:
        print(f"  {t['team']:<10s} {t['matches']:4d} {t['total_xg']:7.3f} "
              f"{t['total_goals']:5d} {t['xg_vs_actual']:+7.3f} {t['mae']:7.4f}")

    # 4. 比赛级误差分布
    print(f"\n4. 比赛级误差 (最大误差 Top 10)")
    match_errors = compute_match_level_error_distribution(match_xg)
    print(f"  {'比赛':<24s} {'总 xG':>7s} {'总进球':>6s} {'误差':>7s}")
    print("  " + "-" * 46)
    for e in match_errors[:10]:
        label = f"{e['home_team']} vs {e['away_team']}"
        print(f"  {label:<22s} {e['total_xg']:7.3f} {e['total_goals']:6d} {e['error']:+7.3f}")

    return {
        'mae': mae,
        'rmse': rmse,
        'total_xg': round(total_xg, 3),
        'total_goals': total_goals,
        'n_matches': n,
        'xg_goal_ratio': round(total_xg / max(total_goals, 1), 3),
        'calibration': calibration,
        'team_results': team_results,
        'match_errors': match_errors[:20],
    }


def save_validation_report(report):
    """保存验证报告到 JSON"""
    output_dir = os.path.join(BASE_DIR, 'data', 'xg')
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, 'validation_report.json')

    # Convert to serializable dict
    serializable = {
        'mae': report['mae'],
        'rmse': report['rmse'],
        'total_xg': report['total_xg'],
        'total_goals': report['total_goals'],
        'n_matches': report['n_matches'],
        'xg_goal_ratio': report['xg_goal_ratio'],
        'calibration': report['calibration'],
        'team_results': report['team_results'],
        'match_errors': report['match_errors'],
    }

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(serializable, f, indent=2, ensure_ascii=False)
    print(f"\n验证报告已保存: {output_path}")


def main():
    match_xg, wc = load_data()
    report = print_validation_report(match_xg)
    save_validation_report(report)


if __name__ == '__main__':
    main()
