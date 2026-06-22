"""
Elo 评分系统 — 核心引擎

功能：
1. 基础 Elo 公式计算预期胜率
2. K 值动态调整
3. 主场优势加分
4. FIFA 排名对应初始评分
5. 世界杯专项修正（卫冕冠军、首次参赛、洲际加成）
6. 赛后评分更新
"""

import math
from typing import Tuple, Optional, Dict, List
import config


class TeamElo:
    """单个球队的 Elo 评分管理"""

    def __init__(self, team_id: int, name: str, country_code: str,
                 fifa_ranking: Optional[int] = None,
                 is_defending_champion: bool = False,
                 is_previous_semi: bool = False,
                 is_first_time: bool = False,
                 is_host_nation: bool = False,
                 continent: str = ""):
        self.team_id = team_id
        self.name = name
        self.country_code = country_code
        self.fifa_ranking = fifa_ranking
        self.defending_champion = is_defending_champion
        self.previous_semi = is_previous_semi
        self.first_time = is_first_time
        self.host_nation = is_host_nation
        self.continent = continent

        # 初始化评分
        self.rating = self._calc_initial_rating()
        # 近期比赛记录
        self.recent_results: List[Dict] = []

    def _calc_initial_rating(self) -> float:
        """根据 FIFA 排名设定初始 Elo + 专项修正"""
        # 先清除所有修正项，获取基础评分
        base_elo = config.ELO_INITIAL_RATING
        if self.fifa_ranking is not None:
            if self.fifa_ranking <= 10:
                # 排名越高评分越高
                rank_offset = (10 - self.fifa_ranking) / 9
                base_elo = config.ELO_TOP_10_RANGE[0] + rank_offset * (
                    config.ELO_TOP_10_RANGE[1] - config.ELO_TOP_10_RANGE[0]
                )
            elif self.fifa_ranking <= 30:
                rank_offset = (30 - self.fifa_ranking) / 20
                base_elo = config.ELO_MID_RANGE[0] + rank_offset * (
                    config.ELO_MID_RANGE[1] - config.ELO_MID_RANGE[0]
                )
            else:
                rank_offset = min((50 - self.fifa_ranking) / 20, 1.0)
                base_elo = config.ELO_BOTTOM_RANGE[0] + rank_offset * (
                    config.ELO_BOTTOM_RANGE[1] - config.ELO_BOTTOM_RANGE[0]
                )

        return base_elo

    def get_adjusted_rating(self, opponent_elo: Optional['TeamElo'] = None,
                            is_home: bool = None) -> float:
        """获取修正后的评分（包含专项修正 + 主场优势）"""
        adjusted = self.rating

        # 世界杯专项修正
        if self.defending_champion:
            adjusted += config.ELO_CHAMPION_BONUS
        if self.previous_semi:
            adjusted += config.ELO_SEMI_FINAL_BONUS
        if self.first_time:
            adjusted += config.ELO_FIRST_TIME_PENALTY
        if self.continent != "England" and self.continent != "":
            adjusted += config.ELO_CONTINENT_BONUS
        # 东道主身份加成（不影响K值更新，只影响初始评分和对局预期）
        if self.host_nation:
            adjusted += config.ELO_HOST_BONUS

        # 主场优势
        if is_home is True:
            adjusted += config.ELO_HOME_ADVANTAGE

        return adjusted

    def apply_match_result(self, opponent: 'TeamElo', is_home: bool,
                           scored: int, conceded: int, stage: str = "group_stage"):
        """根据比赛结果更新自身评分"""
        result = math.log1p(scored) - math.log1p(conceded)
        s = 1 if scored > conceded else (0.5 if scored == conceded else 0)
        new_rating = self.rating + self._calc_k(opponent, stage) * (s - self._expected(opponent, is_home))
        self.rating = new_rating
        self.recent_results.append({
            "opponent": opponent.name,
            "scored": scored,
            "conceded": conceded,
            "result": s
        })
        # 仅保留最近 10 场
        if len(self.recent_results) > 10:
            self.recent_results = self.recent_results[-10:]

    def _calc_k(self, opponent: Optional['TeamElo'] = None, stage: str = "group_stage") -> float:
        """
        动态 K 值 — 按比赛阶段区分
        大赛阶段 K 值更高（评分变化更敏感）
        """
        stage_k = {
            "group_stage": config.ELO_K_GROUP_STAGE,
            "round_of_16": config.ELO_K_ROUND_OF_16,
            "quarter_final": config.ELO_K_QUARTER_FINAL,
            "semi_final": config.ELO_K_SEMI_FINAL,
            "final": config.ELO_K_FINAL,
        }
        base_k = stage_k.get(stage, config.ELO_K_BASE)

        # 近期比赛少时 K 值更高（新信息权重更大）
        if len(self.recent_results) <= 5:
            return config.ELO_K_MAX
        return min(base_k + 10, config.ELO_K_MAX)

    def _expected(self, opponent: Optional['TeamElo'], is_home: Optional[bool] = None) -> float:
        """Elo 预期胜率公式"""
        ra = self.rating
        rb = opponent.rating if opponent is not None else config.ELO_INITIAL_RATING
        if is_home:
            ra += config.ELO_HOME_ADVANTAGE
        delta = rb - ra
        return 1.0 / (10 ** (delta / 400) + 1)


class EloEngine:
    """Elo 评分系统引擎"""

    def __init__(self):
        self.teams: Dict[int, TeamElo] = {}

    def add_team(self, team: TeamElo):
        """添加球队"""
        self.teams[team.team_id] = team

    def set_team(self, team_id: int, name: str, country: str,
                 fifa_rank: int, is_host_nation: bool = False, **kwargs):
        """设置球队数据并添加"""
        team = TeamElo(team_id, name, country, fifa_rank,
                        is_host_nation=is_host_nation, **kwargs)
        self.teams[team_id] = team
        return team

    def get_expected_score(self, team_a_id: int, team_b_id: int,
                           team_a_home: bool = True) -> float:
        """计算 A 队预期得分"""
        team_a = self.teams.get(team_a_id)
        team_b = self.teams.get(team_b_id)
        if team_a is None:
            return 0.5
        return team_a._expected(team_b, team_a_home)

    def simulate_match(self, team_a_id: int, team_b_id: int,
                       team_a_home: bool = True) -> Dict[str, float]:
        """
        计算两队比赛的预期胜率

        使用 Elo 预期得分公式：
        E_A = 1 / (1 + 10^((R_B - R_A) / 400))
        E_B = 1 - E_A

        然后映射到胜/平/负概率：
        - 使用 Dixon-Coles 方法：draw 概率与 Elo 差距负相关
        - 当两队实力接近时，draw 概率更高
        """
        team_a = self.teams.get(team_a_id)
        team_b = self.teams.get(team_b_id)
        if team_a is None or team_b is None:
            return {"home_win": 0.33, "draw": 0.34, "away_win": 0.33}

        exp_a = team_a._expected(team_b, team_a_home)  # A 的预期得分
        exp_b = 1 - exp_a  # B 的预期得分

        # 将预期得分映射到胜/平/负概率
        # 使用简单映射：draw 概率 ≈ 0.25 - 0.1 * |exp_a - 0.5|
        # 实力差距越大，draw 概率越低
        draw_base = 0.27
        gap = abs(exp_a - 0.5)
        draw_prob = max(0.15, draw_base - 0.2 * gap)

        # 剩余概率按 Elo 比例分配
        remaining = 1 - draw_prob
        if exp_a + exp_b > 0:
            home_win = remaining * (exp_a / (exp_a + exp_b))
            away_win = remaining * (exp_b / (exp_a + exp_b))
        else:
            home_win = remaining * 0.5
            away_win = remaining * 0.5

        return {
            "home_win": round(home_win, 4),
            "draw": round(draw_prob, 4),
            "away_win": round(away_win, 4)
        }

    def update_after_match(self, team_a_id: int, team_b_id: int,
                           home_goals: int, away_goals: int,
                           stage: str = "group_stage"):
        """赛后更新两队评分"""
        team_a = self.teams.get(team_a_id)
        team_b = self.teams.get(team_b_id)
        if team_a is None or team_b is None:
            return

        team_a.apply_match_result(team_b, True, home_goals, away_goals, stage)
        team_b.apply_match_result(team_a, False, away_goals, home_goals, stage)

    def get_rating(self, team_id: int) -> Optional[float]:
        """获取球队当前评分"""
        team = self.teams.get(team_id)
        if team:
            return team.rating
        return None

    def export_ratings(self) -> Dict[int, Dict]:
        """导出所有球队评分"""
        return {
            tid: {
                "name": t.name,
                "rating": round(t.rating, 1),
                "fifa_ranking": t.fifa_ranking,
            }
            for tid, t in self.teams.items()
        }
