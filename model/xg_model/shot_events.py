"""
射门事件数据模型

定义 2026 世界杯射门事件的数据结构，用于从懂球帝数据和比赛结果中
提取射门信息，并通过 physics_xg.py 计算实际 xG。
"""

from dataclasses import dataclass, field, asdict
from typing import List, Optional


@dataclass
class ShotEvent:
    """单次射门事件"""
    match_id: str
    team_id: str
    player_id: str = ''
    minute: int = 0
    x: float = 0.0      # 球场坐标 0-120
    y: float = 0.0      # 球场坐标 0-80
    body_part: str = 'Right Foot'  # RightFoot, LeftFoot, Head, Other
    situation: str = 'Open Play'   # OpenPlay, SetPiece, Penalty, FreeKick, Corner
    shot_type: str = 'Open Play'   # RegularShot, OneOnOne, OpenGoal, Penalty
    is_goal: bool = False
    xg: float = 0.0     # 由 physics_xg.py 计算


@dataclass
class MatchXGResult:
    """单场比赛的 xG 结果"""
    match_id: str
    home_team: str
    away_team: str
    home_goals: int = 0
    away_goals: int = 0
    home_xg: float = 0.0
    away_xg: float = 0.0
    home_shots: int = 0
    away_shots: int = 0
    home_sot: int = 0   # shots on target
    away_sot: int = 0
    shots: List[dict] = field(default_factory=list)

    def to_dict(self):
        return asdict(self)


@dataclass
class TeamXGActual:
    """球队实际 xG 特征（从比赛数据计算）"""
    team_name: str
    matches_played: int = 0
    total_xg_for: float = 0.0
    total_xg_against: float = 0.0
    total_goals_for: int = 0
    total_goals_against: int = 0
    total_shots: int = 0
    total_sot: int = 0
    offensive_xg: float = 0.0
    defensive_xg: float = 0.0
    xg_diff: float = 0.0
    goals_per_game: float = 0.0
    xg_per_game: float = 0.0
    conversion_ratio: float = 0.0
    shot_quality: float = 0.0
    xg_vs_actual: float = 0.0        # goals - xG (正=超预期)
    xg_variance: float = 0.0         # variance of (goals - xG) per match

    def to_dict(self):
        return asdict(self)