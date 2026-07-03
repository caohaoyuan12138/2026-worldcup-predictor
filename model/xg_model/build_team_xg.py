"""
球队级 xG 特征构建脚本

为每支球队生成完整的 xG 特征，用于接入 engine.mjs 预测引擎。
输出格式与 worldcup.json 中现有字段兼容，直接替换 xgProxy/xgaProxy/shotAccuracy。

输出：data/xg/team_xg_model_data.json（可直接 merge 到 worldcup.json 的 teams 中）
"""

import os
import sys
import json
import math

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from physics_xg import XGCoefficients, calc_shot_xg

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def load_worldcup_data():
    """加载世界杯数据"""
    with open(os.path.join(BASE_DIR, 'db', 'worldcup.json'), 'r', encoding='utf-8') as f:
        return json.load(f)


def compute_team_xg_features(team, dims, n_matches):
    """
    计算球队的完整 xG 特征集

    Args:
        team: 球队数据 dict
        dims: 维度名称列表
        n_matches: 已赛场数

    Returns:
        dict: xG 特征
    """
    dq = team.get('dongqiudi', {})
    is_host = team.get('isHost', False)

    # 解析懂球帝数据
    raw = {}
    if isinstance(dq, dict):
        for dim in dims:
            if dim in dq:
                try:
                    raw[dim] = float(dq[dim])
                except (ValueError, TypeError):
                    raw[dim] = 0

    if n_matches == 0:
        n_matches = 1

    # 百分比维度
    pct_dims = {'传球成功率', '控球率'}
    stats = {}
    for dim, val in raw.items():
        if dim in pct_dims:
            stats[dim] = val / 100.0 if val > 1 else val
        else:
            stats[dim] = val / n_matches

    # ── 基础统计 ──
    shots_pg = stats.get('射门', 10)
    on_target_pg = stats.get('射正', 3)
    goals_pg = stats.get('进球', 0)
    conceded_pg = stats.get('失球', 0)
    key_passes_pg = stats.get('关键传球', 8)
    big_chances_pg = stats.get('创造进球机会', 3)
    big_missed_pg = stats.get('错失绝佳机会', 1)
    corners_pg = stats.get('角球', 4)
    crosses_pg = stats.get('传中', 10)
    dribbles_pg = stats.get('成功过人', 5)
    saves_pg = stats.get('扑救', 2)
    possession = stats.get('传球成功率', 0.75)
    shot_accuracy = on_target_pg / max(shots_pg, 0.1)
    rating = stats.get('评分', 6.5)

    # ── 进攻 xG 模型 ──
    # 基础每次射门 xG
    base_shot_xg = 0.10

    # 射正率修正
    acc_bonus = 1.0 + (shot_accuracy - 0.35) * 0.8

    # 关键传球修正（反映机会创造质量）
    kp_rate = key_passes_pg / max(shots_pg, 0.1)
    kp_bonus = 1.0 + (kp_rate - 1.0) * 0.3

    # 绝佳机会修正
    bc_rate = big_chances_pg / max(shots_pg, 0.1)
    bc_bonus = 1.0 + bc_rate * 0.5

    # 进攻风格修正
    # 传中比例高 → 更多头球射门 → 平均 xG 略降
    cross_rate = crosses_pg / max(shots_pg, 0.1)
    style_adj = 1.0 - cross_rate * 0.1  # 传中型略微降低平均 xG

    # 场均进攻 xG
    offensive_xg = shots_pg * base_shot_xg * acc_bonus * kp_bonus * bc_bonus * style_adj

    # ── 防守 xG 模型 ──
    # 防守 xG ≈ 失球 + 被扑救×0.3（被扑救的射门也有 xG）
    # 同时考虑被射门数（从失球+扑救反推）
    shots_against = conceded_pg + saves_pg
    defensive_xg = conceded_pg + saves_pg * 0.25

    # 扑救率修正（门将能力）
    save_rate = saves_pg / max(shots_against, 0.1)
    gk_bonus = 1.0 - (save_rate - 0.30) * 0.3  # 扑救率高的门将降低防守 xG
    defensive_xg *= gk_bonus

    # ── 细分 xG ──
    # 运动战 xG（约 75%）
    open_play_xg = offensive_xg * 0.75

    # 定位球 xG（角球 + 任意球，约 15%）
    set_piece_xg = offensive_xg * 0.15 + corners_pg * 0.015

    # 头球 xG（传中相关）
    header_xg = offensive_xg * cross_rate * 0.3

    # 重大机会 xG
    big_chance_xg = big_chances_pg * 0.35  # 重大机会平均 xG 约 0.35

    # ── 终结效率 ──
    conversion = goals_pg / max(offensive_xg, 0.1)
    conversion = min(2.0, max(0.3, conversion))

    # ── 射门质量分布 ──
    # 模拟射门位置分布，计算各区域的 xG
    shot_distribution = simulate_shot_distribution(stats, team)

    # ── 趋势（基于已有比赛结果）──
    xg_trend = estimate_xg_trend(team, n_matches)

    return {
        'offensive_xg': round(offensive_xg, 3),
        'defensive_xg': round(defensive_xg, 3),
        'xg_diff': round(offensive_xg - defensive_xg, 3),
        'shot_quality': round(base_shot_xg * acc_bonus * kp_bonus * bc_bonus * style_adj, 4),
        'shot_volume': round(shots_pg, 1),
        'shot_accuracy': round(shot_accuracy, 3),
        'conversion_ratio': round(conversion, 3),
        'goals_per_game': round(goals_pg, 3),
        'big_chance_rate': round(bc_rate, 3),
        'open_play_xg': round(open_play_xg, 3),
        'set_piece_xg': round(set_piece_xg, 3),
        'header_xg': round(header_xg, 3),
        'big_chance_xg': round(big_chance_xg, 3),
        'shot_distribution': shot_distribution,
        'xg_trend': xg_trend,
        'possession_factor': round(possession, 3),
        'rating_factor': round(rating / 6.5, 3),  # 评分修正
    }


def simulate_shot_distribution(stats, team):
    """
    模拟球队射门位置分布

    Returns:
        dict: 各区域射门占比和平均 xG
    """
    shots_pg = stats.get('射门', 10)
    possession = stats.get('传球成功率', 0.75)
    cross_rate = stats.get('传中', 10) / max(shots_pg, 0.1)
    dribble_rate = stats.get('成功过人', 5) / max(shots_pg, 0.1)

    # 根据球队风格确定射门分布
    # 控球型：更多远射，更多禁区外
    # 反击型：更多禁区内，更多一对一
    # 传中型：更多头球

    long_range_pct = 0.20 + 0.25 * possession  # 0.20 ~ 0.45
    close_range_pct = 0.40 - 0.15 * possession  # 0.40 ~ 0.25
    header_pct = min(0.30, cross_rate * 1.2)
    one_on_one_pct = min(0.12, dribble_rate * 0.2)

    # 各区域平均 xG（基于物理模型）
    close_xg = calc_shot_xg(113, 40, first_time=True)
    long_xg = calc_shot_xg(100, 40)
    header_xg_val = calc_shot_xg(112, 40, body_part='Head', cross=True)
    ooo_xg = calc_shot_xg(115, 40, one_on_one=True)

    return {
        'close_range_pct': round(close_range_pct, 3),
        'long_range_pct': round(long_range_pct, 3),
        'header_pct': round(header_pct, 3),
        'one_on_one_pct': round(one_on_one_pct, 3),
        'close_range_xg': round(close_xg, 3),
        'long_range_xg': round(long_xg, 3),
        'header_xg': round(header_xg_val, 3),
        'one_on_one_xg': round(ooo_xg, 3),
    }


def estimate_xg_trend(team, n_matches):
    """
    估算 xG 趋势（近几场的变化方向）

    由于没有逐场数据，用累积数据的二阶差分近似
    """
    # 简化：返回基于已赛场数的趋势因子
    # 实际应用中应逐场跟踪
    recent = team.get('recentWins', 0)
    draws = team.get('recentDrawes', 0)
    losses = team.get('recentLosses', 0)
    total = recent + draws + losses

    if total == 0:
        return [1.0, 1.0, 1.0]

    # 近期状态因子
    form = (recent * 1.0 + draws * 0.5) / total

    # 生成趋势（基于近期状态）
    if form > 0.7:
        return [1.05, 1.10, 1.15]
    elif form > 0.5:
        return [0.98, 1.00, 1.05]
    elif form > 0.3:
        return [0.90, 0.95, 0.98]
    else:
        return [0.80, 0.85, 0.90]


def build_all_team_xg(teams_data, completed_matches, dims):
    """
    为所有球队构建 xG 特征
    """
    # 计算每支球队的比赛场数和进球
    team_matches = {}
    team_goals = {}
    for m in completed_matches:
        home = m['home']
        away = m['away']
        hs, as_ = map(int, m['score'].split('-'))
        team_matches[home] = team_matches.get(home, 0) + 1
        team_matches[away] = team_matches.get(away, 0) + 1
        team_goals[home] = team_goals.get(home, 0) + hs
        team_goals[away] = team_goals.get(away, 0) + as_

    results = {}
    for name, team in teams_data.items():
        n = team_matches.get(name, 0)
        features = compute_team_xg_features(team, dims, n)

        # 添加元信息
        features['matches_played'] = n
        features['goals_scored'] = team_goals.get(name, 0)

        # 计算失球
        conceded = 0
        for m in completed_matches:
            if m['home'] == name:
                conceded += int(m['score'].split('-')[1])
            elif m['away'] == name:
                conceded += int(m['score'].split('-')[0])
        features['goals_conceded'] = conceded

        results[name] = features

    return results


def merge_into_worldcup(team_xg_data, worldcup_path):
    """
    将 xG 特征合并到 worldcup.json 的球队数据中

    找到每支球队，添加 xg_model 字段
    """
    with open(worldcup_path, 'r', encoding='utf-8') as f:
        wc = json.load(f)

    for name, xg_data in team_xg_data.items():
        if name in wc['teams']:
            wc['teams'][name]['xg_model'] = xg_data
            # 同时更新旧的 xgProxy 值（保持兼容）
            wc['teams'][name]['xgProxy'] = xg_data['offensive_xg']
            wc['teams'][name]['xgaProxy'] = xg_data['defensive_xg']

    with open(worldcup_path, 'w', encoding='utf-8') as f:
        json.dump(wc, f, indent=2, ensure_ascii=False)

    print(f"\n已合并到: {worldcup_path}")
    print(f"更新了 {len(team_xg_data)} 支球队的 xg_model 字段")


def main():
    print("=" * 60)
    print("球队级 xG 特征构建")
    print("=" * 60)

    # 加载数据
    wc = load_worldcup_data()
    dims = wc['meta']['teamDimensions']
    teams = wc['teams']
    completed = wc['completedMatches']

    print(f"\n球队数: {len(teams)}")
    print(f"已完赛: {len(completed)}")

    # 构建特征
    team_xg = build_all_team_xg(teams, completed, dims)

    # 打印摘要
    print(f"\n{'球队':<15s} {'进攻xG':>8s} {'防守xG':>8s} {'xG差':>8s} {'转换率':>8s} {'射门/场':>8s}")
    print("-" * 65)

    sorted_teams = sorted(team_xg.items(), key=lambda x: x[1]['offensive_xg'], reverse=True)
    for name, feat in sorted_teams[:15]:
        print(f"  {name:<13s} {feat['offensive_xg']:8.3f} {feat['defensive_xg']:8.3f} "
              f"{feat['xg_diff']:+8.3f} {feat['conversion_ratio']:8.3f} {feat['shot_volume']:8.1f}")

    print("  ...")
    for name, feat in sorted_teams[-5:]:
        print(f"  {name:<13s} {feat['offensive_xg']:8.3f} {feat['defensive_xg']:8.3f} "
              f"{feat['xg_diff']:+8.3f} {feat['conversion_ratio']:8.3f} {feat['shot_volume']:8.1f}")

    # 保存独立文件
    output_dir = os.path.join(BASE_DIR, 'data', 'xg')
    os.makedirs(output_dir, exist_ok=True)

    output_path = os.path.join(output_dir, 'team_xg_model_data.json')
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(team_xg, f, indent=2, ensure_ascii=False)
    print(f"\n保存到: {output_path}")

    # 合并到 worldcup.json
    worldcup_path = os.path.join(BASE_DIR, 'db', 'worldcup.json')
    merge_into_worldcup(team_xg, worldcup_path)

    # 打印东道主球队详情
    print("\n" + "=" * 60)
    print("美加墨东道主 xG 详情")
    print("=" * 60)
    for host in ['美国', '墨西哥', '加拿大']:
        if host in team_xg:
            xg = team_xg[host]
            print(f"\n  {host}:")
            print(f"    进攻xG:     {xg['offensive_xg']}")
            print(f"    防守xG:     {xg['defensive_xg']}")
            print(f"    xG差:       {xg['xg_diff']}")
            print(f"    射门/场:    {xg['shot_volume']}")
            print(f"    射正率:     {xg['shot_accuracy']}")
            print(f"    终结效率:   {xg['conversion_ratio']}")
            print(f"    重大机会率: {xg['big_chance_rate']}")
            sd = xg['shot_distribution']
            print(f"    射门分布: 近距离{sd['close_range_pct']*100:.0f}% / "
                  f"远射{sd['long_range_pct']*100:.0f}% / "
                  f"头球{sd['header_pct']*100:.0f}% / "
                  f"一对一{sd['one_on_one_pct']*100:.0f}%")

    print(f"\n{'='*60}")
    print("球队级 xG 特征构建完成!")
    print(f"{'='*60}")


if __name__ == '__main__':
    main()
