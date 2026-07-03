"""
xG 模型特征工程
从 StatsBomb 射门事件中提取特征，用于训练进球概率预测模型
"""

import math
import json

# 球场尺寸（StatsBomb 标准：120 x 80）
PITCH_LENGTH = 120.0
PITCH_WIDTH = 80.0
GOAL_CENTER_Y = 40.0
GOAL_X = 120.0


def calc_distance_to_goal(x, y):
    """计算射门点到球门中心（120, 40）的欧氏距离"""
    return math.sqrt((GOAL_X - x) ** 2 + (GOAL_CENTER_Y - y) ** 2)


def calc_angle_to_goal(x, y):
    """
    计算射门点与两立柱形成的夹角（弧度）
    立柱位置：(120, 36) 和 (120, 44)
    """
    if x >= GOAL_X:
        return 0.0

    # 两立柱相对于射门点的角度
    post1_angle = math.atan2(36.0 - y, GOAL_X - x)
    post2_angle = math.atan2(44.0 - y, GOAL_X - x)

    angle = abs(post2_angle - post1_angle)
    return angle


def calc_visible_goal_angle(x, y, freeze_frame):
    """
    计算可见球门角度（考虑门将和防守球员遮挡）
    简化版：基于 freeze_frame 中球员位置估算遮挡
    """
    total_angle = calc_angle_to_goal(x, y)
    if total_angle == 0 or not freeze_frame:
        return total_angle

    blocked_rays = 0
    for player in freeze_frame:
        if player.get('teammate', False):
            continue
        px, py = player['location']
        # 检查球员是否在射门线和球门之间
        if x < px < GOAL_X:
            # 计算该球员遮挡的角度
            angle_to_player = abs(math.atan2(py - y, px - x))
            player_width = 0.5  # 球员有效遮挡宽度（米）
            dist_to_player = math.sqrt((px - x) ** 2 + (py - y) ** 2)
            if dist_to_player > 0:
                block_angle = math.atan2(player_width, dist_to_player)
                blocked_rays += block_angle

    visible = max(0, total_angle - blocked_rays * 0.3)  # 遮挡系数
    return visible


def count_defenders_between(x, y, freeze_frame):
    """统计射门点与球门之间的防守球员数量"""
    if not freeze_frame:
        return 0
    count = 0
    for player in freeze_frame:
        if player.get('teammate', False):
            continue
        px, py = player['location']
        # 球员在射门线和球门之间（x 方向）
        if x < px <= GOAL_X:
            # 粗略：球员在射门方向附近
            count += 1
    return count


def extract_shot_features(shot, competition="unknown", stage="group"):
    """
    从单个 StatsBomb 射门事件提取完整特征集

    Args:
        shot: StatsBomb 射门事件 dict
        competition: 赛事名称
        stage: 比赛阶段 (group / knockout / final)

    Returns:
        dict: 特征字典
    """
    x = shot.get('location', [0, 0])[0]
    y = shot.get('location', [0, 0])[1]

    # ── 几何特征 ──
    distance = calc_distance_to_goal(x, y)
    angle = calc_angle_to_goal(y, x)  # 注意：angle 用 y, x 顺序
    angle = calc_angle_to_goal(x, y)  # 正确顺序

    # ── 射门类型 ──
    body_part = shot.get('shot_body_part', {}).get('name', 'Unknown')
    technique = shot.get('shot_technique', {}).get('name', 'Unknown')
    shot_type = shot.get('shot_type', {}).get('name', 'Open Play')
    outcome = shot.get('outcome', {}).get('name', 'Unknown')

    # ── 进攻情境 ──
    first_time = shot.get('shot_first_time', False) or False
    follows_dribble = shot.get('shot_follows_dribble', False) or False
    aerial_won = shot.get('shot_aerial_won', False) or False
    one_on_one = shot.get('shot_one_on_one', False) or False
    open_goal = shot.get('shot_open_goal', False) or False
    deflect = shot.get('shot_deflect', False) or False

    # ── 关键传球类型（助攻方式）──
    key_pass_id = shot.get('key_pass_id', None)
    key_pass_type = 'Unknown'
    if key_pass_id:
        # 这里简化处理，实际应从事件中查找对应传球
        key_pass_type = 'known'

    # ── 360° freeze-frame 特征 ──
    freeze_frame = shot.get('shot_freeze_frame', [])
    defenders_between = count_defenders_between(x, y, freeze_frame)

    # 门将位置
    gk_distance = 0
    gk_angle_coverage = 0
    for player in freeze_frame or []:
        if player.get('position', {}).get('name', '') in ['Goalkeeper']:
            px, py = player['location']
            gk_distance = math.sqrt((px - x) ** 2 + (py - y) ** 2)
            # 门将覆盖角度
            if distance > 0 and gk_distance > 0:
                gk_angle_coverage = math.atan2(3.66, gk_distance)  # 球门宽 7.32m 的一半
            break

    visible_angle = calc_visible_goal_angle(x, y, freeze_frame)

    # ── 比赛时间 ──
    minute = shot.get('minute', 0)
    period = shot.get('period', 1)

    # ── 编码分类变量 ──
    is_header = 1 if body_part == 'Head' else 0
    is_foot = 1 if body_part in ['Left Foot', 'Right Foot'] else 0
    is_foot_preferred = 0  # 需要额外信息
    is_free_kick = 1 if shot_type == 'Free Kick' else 0
    is_corner = 1 if shot_type == 'Corner' else 0
    is_penalty = 1 if shot_type == 'Penalty' else 0
    is_open_play = 1 if shot_type == 'Open Play' else 0

    # 射门部位编码
    is_left_foot = 1 if body_part == 'Left Foot' else 0
    is_right_foot = 1 if body_part == 'Right Foot' else 0

    features = {
        # 几何
        'x': x,
        'y': y,
        'distance_to_goal': round(distance, 2),
        'angle_to_goal': round(angle, 4),
        'angle_degrees': round(math.degrees(angle), 2),
        'visible_goal_angle': round(visible_angle, 4),

        # 射门类型
        'is_header': is_header,
        'is_foot': is_foot,
        'is_left_foot': is_left_foot,
        'is_right_foot': is_right_foot,
        'is_free_kick': is_free_kick,
        'is_corner': is_corner,
        'is_penalty': is_penalty,
        'is_open_play': is_open_play,

        # 技术动作
        'first_time': int(bool(first_time)),
        'follows_dribble': int(bool(follows_dribble)),
        'aerial_won': int(bool(aerial_won)),
        'one_on_one': int(bool(one_on_one)),
        'open_goal': int(bool(open_goal)),
        'deflect': int(bool(deflect)),

        # 360° 防守压力
        'defenders_between': defenders_between,
        'gk_distance': round(gk_distance, 2),
        'gk_angle_coverage': round(gk_angle_coverage, 4),

        # 比赛情境
        'minute': minute,
        'period': period,
        'is_knockout': 1 if stage in ['knockout', 'round_16', 'quarter', 'semi', 'final'] else 0,
        'is_final': 1 if stage == 'final' else 0,

        # 标签
        'is_goal': 1 if outcome == 'Goal' else 0,
        'statsbomb_xg': shot.get('shot_statsbomb_xg', 0) or 0,
    }

    return features


def extract_from_events(events_df, competition="unknown", stage="group"):
    """
    从 StatsBomb 事件 DataFrame 中提取所有射门特征

    Args:
        events_df: StatsBomb events DataFrame
        competition: 赛事名称
        stage: 比赛阶段

    Returns:
        list[dict]: 特征列表
    """
    shots = events_df[events_df['type'] == 'Shot']
    features_list = []

    for _, shot in shots.iterrows():
        feat = extract_shot_features(shot.to_dict(), competition, stage)
        features_list.append(feat)

    return features_list
