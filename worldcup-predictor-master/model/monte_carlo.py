"""
蒙特卡洛模拟

功能：
1. 基于泊松分布的 10,000 次比赛模拟
2. 输出胜/平/负概率分布
3. 输出比分概率矩阵
4. 输出进球数分布
5. 支持环境修正因子（天气/海拔/路程/伤停/战术）
6. 淘汰赛阶段：加时赛 + 点球大战模拟
7. 补水机制、时区影响、红牌停赛
"""

import numpy as np
from typing import Dict, Tuple, List, Optional
import random
import config
from model.poisson import (
    calc_expected_goals,
    calc_score_matrix,
    calc_match_probabilities,
    get_favorite_scorelines,
)


class MatchEnvironment:
    """比赛环境因素"""

    def __init__(self, home_team_id: int, away_team_id: int,
                 venue_altitude: float = 0,
                 temperature: float = 20,
                 is_rain: bool = False,
                 home_travel_distance_km: float = 0,
                 home_rest_days: int = 7,
                 home_days_since_last: int = 7,
                 star_players_missing_home: int = 0,
                 star_players_missing_away: int = 0,
                 goalie_missing_home: bool = False,
                 goalie_missing_away: bool = False,
                 home_tactical_style: str = "balanced",
                 away_tactical_style: str = "balanced",
                 is_high_stakes: bool = False,
                 referee_bias: float = 0,
                 political_factor: float = 0,
                 home_red_card: bool = False,
                 away_red_card: bool = False,
                 home_suspensions: int = 0,
                 away_suspensions: int = 0,
                 timezone_diff_hours: float = 0,
                 is_water_break: bool = False,
                 home_bench_depth: float = 1.0,
                 away_bench_depth: float = 1.0):
        self.home_team_id = home_team_id
        self.away_team_id = away_team_id
        self.venue_altitude = venue_altitude
        self.temperature = temperature
        self.is_rain = is_rain
        self.home_travel_distance_km = home_travel_distance_km
        self.home_rest_days = home_rest_days
        self.home_days_since_last = home_days_since_last
        self.star_players_missing_home = star_players_missing_home
        self.star_players_missing_away = star_players_missing_away
        self.goalie_missing_home = goalie_missing_home
        self.goalie_missing_away = goalie_missing_away
        self.home_tactical_style = home_tactical_style
        self.away_tactical_style = away_tactical_style
        self.is_high_stakes = is_high_stakes
        self.referee_bias = referee_bias
        self.political_factor = political_factor
        self.home_red_card = home_red_card
        self.away_red_card = away_red_card
        self.home_suspensions = home_suspensions
        self.away_suspensions = away_suspensions
        self.timezone_diff_hours = timezone_diff_hours
        self.is_water_break = is_water_break
        self.home_bench_depth = home_bench_depth
        self.away_bench_depth = away_bench_depth

    def apply_corrections(self, lambda_home: float,
                          lambda_away: float) -> Tuple[float, float]:
        """
        对环境修正因子应用后返回修正后的 λ

        依次应用：
        1. 跨国转场/休息时间
        2. 天气（高温/雨天）
        3. 高海拔
        4. 补水机制（高温天气赛后半程体能恢复）
        5. 时区跨度
        6. 人员伤停 + 红牌停赛
        7. 战术克制
        8. 裁判执法风格
        9. 政治因素
        10. 比赛重要性
        11. 阵容深度
        """
        lh = lambda_home
        la = lambda_away

        # --- 1. 跨国转场修正 ---
        if (self.home_rest_days < 4 and
                self.home_travel_distance_km > 1000):
            lh *= (1 + config.INTER_NATIONAL_REST_PENALTY)
        elif self.home_travel_distance_km > 3000:
            lh *= (1 + config.DOMESTIC_LONG_DISTANCE_PENALTY)

        # 休息天数影响（连续作战疲劳）
        if self.home_days_since_last >= 3:
            lh *= (1 + config.BENCH_DEPTH_FACTOR * (self.home_bench_depth - 1.0))

        # --- 2. 天气修正 ---
        if self.temperature > config.HIGH_TEMP_THRESHOLD:
            lh_adj = config.HIGH_TEMP_TECH_PENALTY \
                if self.home_tactical_style == "technical" \
                else config.HIGH_TEMP_PHYSICAL_BONUS \
                if self.home_tactical_style == "physical" \
                else 0
            la_adj = config.HIGH_TEMP_TECH_PENALTY \
                if self.away_tactical_style == "technical" \
                else config.HIGH_TEMP_PHYSICAL_BONUS \
                if self.away_tactical_style == "physical" \
                else 0
            lh *= (1 + lh_adj)
            la *= (1 + la_adj)

        if self.is_rain:
            if self.home_tactical_style == "possession":
                lh *= (1 + config.RAIN_SHOT_PENALTY)
            elif self.home_tactical_style == "long_ball":
                lh *= (1 + config.RAIN_LONG_BONUS)
            if self.away_tactical_style == "possession":
                la *= (1 + config.RAIN_SHOT_PENALTY)
            elif self.away_tactical_style == "long_ball":
                la *= (1 + config.RAIN_LONG_BONUS)

        # --- 3. 高海拔修正 ---
        if self.venue_altitude >= config.ALTITUDE_PENALTY_THRESHOLD:
            altitude_factor = 1 + config.ALTITUDE_PENALTY
            # 技术型球队受海拔影响更大
            if self.home_tactical_style != "physical":
                lh *= altitude_factor
                la *= (1 - config.ALTITUDE_TECH_PENALTY)

        # --- 4. 补水机制（2026 世界杯特有）---
        if self.is_water_break:
            lh *= (1 + config.WATER_BREAK_BONUS)
            la *= (1 + config.WATER_BREAK_BONUS)

        # --- 5. 时区跨度修正 ---
        if abs(self.timezone_diff_hours) > config.TIMEZONE_PENALTY_THRESHOLD:
            tz_factor = 1 + config.TIMEZONE_PENALTY
            # 影响双向，但跨时区更大的球队受影响更多
            lh *= tz_factor
            la *= tz_factor

        # --- 6. 人员伤停 + 红牌停赛 ---
        missing_home = self.star_players_missing_home + self.home_suspensions
        missing_away = self.star_players_missing_away + self.away_suspensions
        if missing_home >= 3:
            lh *= (1 + config.MULTIPLE_MISSING)
        elif missing_home > 0:
            lh *= (1 + config.STAR_PLAYER_MISSING * missing_home)
        if self.home_red_card:
            lh *= (1 + config.RED_CARD_PENALTY)  # 少赛一人 → 进球期望降低
        elif missing_home > 0:
            pass  # 已在上面处理
        if self.goalie_missing_home:
            lh *= (1 + config.GOALIE_MISSING * 0.5)  # 门将缺阵增加失球
            la *= (1 + config.GOALIE_MISSING)

        if missing_away >= 3:
            la *= (1 + config.MULTIPLE_MISSING)
        elif missing_away > 0:
            la *= (1 + config.STAR_PLAYER_MISSING * missing_away)
        if self.away_red_card:
            la *= (1 + config.RED_CARD_PENALTY)
        elif missing_away > 0:
            pass
        if self.goalie_missing_away:
            la *= (1 + config.GOALIE_MISSING * 0.5)
            lh *= (1 + config.GOALIE_MISSING)

        # --- 7. 战术克制 ---
        if (self.home_tactical_style == "high_press" and
                self.away_tactical_style == "buildup"):
            lh *= (1 + config.TACTICAL_PRESSURE_WEAK)
        if (self.home_tactical_style == "counter" and
                self.away_tactical_style == "possession"):
            lh *= (1 + config.TACTICAL_COUNTER)
        if (self.home_tactical_style == "set_piece" and
                self.away_tactical_style == "aerial_weak"):
            lh *= (1 + config.TACTICAL_SET_PIECE)

        if (self.away_tactical_style == "high_press" and
                self.home_tactical_style == "buildup"):
            la *= (1 + config.TACTICAL_PRESSURE_WEAK)
        if (self.away_tactical_style == "counter" and
                self.home_tactical_style == "possession"):
            la *= (1 + config.TACTICAL_COUNTER)

        # --- 8. 裁判执法风格 ---
        ref = self.referee_bias
        if ref > 0.02:  # 严格裁判
            lh *= (1 - config.REFEREE_CARD_STRICT)
            la *= (1 - config.REFEREE_CARD_STRICT)
        elif ref < -0.02:  # 宽松裁判
            lh *= (1 - config.REFEREE_CARD_LENIENT)
            la *= (1 - config.REFEREE_CARD_LENIENT)

        # --- 9. 政治因素 ---
        if abs(self.political_factor) > 0.05:
            lh *= (1 + self.political_factor)
            la *= (1 - self.political_factor)

        # --- 10. 比赛重要性（淘汰赛球员更保守） ---
        if self.is_high_stakes:
            # 大赛进球期望略降
            lh *= 0.97
            la *= 0.97

        return max(0.05, lh), max(0.05, la)


class Simulator:
    """蒙特卡洛模拟器"""

    def __init__(self, n_sim: int = None, seed: int = None):
        self.n_sim = n_sim or config.MC_SIMULATIONS
        self.rng = np.random.default_rng(seed or config.MC_SEED)

    def run_match(self, lambda_home: float, lambda_away: float,
                  is_knockout: bool = False) -> Dict:
        """
        运行单次蒙特卡洛模拟
        Args:
            is_knockout: 是否淘汰赛（平局后模拟加时赛+点球）
        Returns:
            {"home_win": float, "draw": float, "away_win": float,
             "score_matrix": {...}, "goal_distribution": {...},
             "extra_time": {...} | None, "penalty_shootout": {...} | None}
        """
        home_goals = self.rng.poisson(lambda_home, self.n_sim)
        away_goals = self.rng.poisson(lambda_away, self.n_sim)

        # 统计胜/平/负（90 分钟）
        hw = int(np.sum(home_goals > away_goals))
        dr = int(np.sum(home_goals == away_goals))
        aw = int(np.sum(home_goals < away_goals))

        total = self.n_sim
        result = {
            "home_win": hw / total,
            "draw": dr / total,
            "away_win": aw / total,
        }

        # 比分矩阵
        score_matrix: Dict[str, int] = {}
        for i in range(self.n_sim):
            key = f"{int(home_goals[i])}-{int(away_goals[i])}"
            score_matrix[key] = score_matrix.get(key, 0) + 1

        result["score_matrix"] = {
            k: round(v / total * 100, 2)
            for k, v in sorted(score_matrix.items(),
                                key=lambda x: -x[1])[:10]
        }

        # 进球数分布
        total_goals = home_goals + away_goals
        goal_dist = {}
        for g in range(0, 10):
            count = int(np.sum(total_goals == g))
            if count > 0:
                goal_dist[str(g)] = round(count / total * 100, 2)
        result["goal_distribution"] = goal_dist

        # 淘汰赛：加时赛 + 点球大战
        if is_knockout:
            result["extra_time"] = self._run_extra_time(
                home_goals, away_goals, lambda_home, lambda_away)
            result["penalty_shootout"] = self._run_penalty_shootout(
                home_goals, away_goals)
            # 最终胜负（含加时/点球）
            final_result = self._determine_knockout_winner(
                home_goals, away_goals, result["penalty_shootout"])
            result["final_home_win"] = final_result["home_win"]
            result["final_draw"] = final_result["draw"]
            result["final_away_win"] = final_result["away_win"]

        return result

    def _run_extra_time(self, home_goals_90: np.ndarray,
                        away_goals_90: np.ndarray,
                        lambda_home: float, lambda_away: float) -> Dict:
        """
        加时赛模拟
        加时赛用降低的 λ（疲劳 + 比赛重要性 → 进球更少）
        """
        # 只对平局进行加时赛
        draw_mask = home_goals_90 == away_goals_90
        n_draw = int(np.sum(draw_mask))
        if n_draw == 0:
            return None

        # 加时赛 λ 约为常规时间的 40%
        lambda_et_home = lambda_home * 0.4
        lambda_et_away = lambda_away * 0.4

        et_home = self.rng.poisson(lambda_et_home, n_draw)
        et_away = self.rng.poisson(lambda_et_away, n_draw)

        hw_et = int(np.sum(et_home > et_away))
        dr_et = int(np.sum(et_home == et_away))
        et_goals_dist = {}
        for g in range(0, 5):
            count = int(np.sum((et_home + et_away) == g))
            if count > 0:
                et_goals_dist[str(g)] = round(count / n_draw * 100, 1)

        return {
            "home_win": round(hw_et / n_draw * 100, 1),
            "draw": round(dr_et / n_draw * 100, 1),  # 进入点球
            "goals_distribution": et_goals_dist,
            "avg_et_goals_home": round(float(np.mean(et_home)), 2),
            "avg_et_goals_away": round(float(np.mean(et_away)), 2),
        }

    def _run_penalty_shootout(self, home_goals_90: np.ndarray,
                              away_goals_90: np.ndarray) -> Dict:
        """
        点球大战模拟
        假设点球命中率约 75%，每队 5 轮
        """
        draw_mask = home_goals_90 == away_goals_90
        n_draw = int(np.sum(draw_mask))
        if n_draw == 0:
            return None

        penalty_rate = 0.75
        home_penalties = self.rng.binomial(5, penalty_rate, n_draw)
        away_penalties = self.rng.binomial(5, penalty_rate, n_draw)

        hw_pen = int(np.sum(home_penalties > away_penalties))
        aw_pen = int(np.sum(home_penalties < away_penalties))
        draw_5 = int(np.sum(home_penalties == away_penalties))

        return {
            "home_win": round(hw_pen / n_draw * 100, 1),
            "away_win": round(aw_pen / n_draw * 100, 1),
            "draw_after_5": round(draw_5 / n_draw * 100, 1),  # 突然死亡
            "avg_home_penalties": round(float(np.mean(home_penalties)), 2),
            "avg_away_penalties": round(float(np.mean(away_penalties)), 2),
        }

    def _determine_knockout_winner(self, home_goals_90, away_goals_90,
                                   penalty_result: Dict) -> Dict:
        """综合 90 分钟 + 加时赛 + 点球，确定最终胜负"""
        n = len(home_goals_90)
        final_hw = 0
        final_aw = 0

        for i in range(n):
            h_total = int(home_goals_90[i])
            a_total = int(away_goals_90[i])

            if h_total > a_total:
                final_hw += 1
            elif h_total < a_total:
                final_aw += 1
            else:
                # 平局 → 看加时赛+点球概率
                # 使用蒙特卡洛结果的概率分布
                if penalty_result and penalty_result.get("home_win", 0) > 50:
                    final_hw += 1
                elif penalty_result and penalty_result.get("away_win", 0) > 50:
                    final_aw += 1
                else:
                    # 50/50 随机
                    if self.rng.random() > 0.5:
                        final_hw += 1
                    else:
                        final_aw += 1

        return {
            "home_win": round(final_hw / n, 4),
            "draw": 0.0,
            "away_win": round(final_aw / n, 4),
        }

    def run_with_environment(self, base_lambda_home: float,
                            base_lambda_away: float,
                            env: MatchEnvironment,
                            is_knockout: bool = False) -> Dict:
        """带环境修正的模拟"""
        lh, la = env.apply_corrections(
            base_lambda_home, base_lambda_away)
        return self.run_match(lh, la, is_knockout=is_knockout)

    def run_detailed(self, base_lambda_home: float,
                     base_lambda_away: float,
                     env: MatchEnvironment = None,
                     is_knockout: bool = False) -> Dict:
        """
        详细模拟：先修正环境，再运行，返回完整结果
        """
        if env:
            lh, la = env.apply_corrections(
                base_lambda_home, base_lambda_away)
        else:
            lh, la = base_lambda_home, base_lambda_away

        result = self.run_match(lh, la, is_knockout=is_knockout)

        # 模型预测（纯概率）
        analytical = calc_score_matrix(lh, la, max_goals=6)
        analytical_probs = calc_match_probabilities(analytical)
        top_scores = get_favorite_scorelines(analytical, top_n=5)

        result["analytical"] = analytical_probs
        result["top_scorelines"] = top_scores
        result["lambda_home"] = round(lh, 3)
        result["lambda_away"] = round(la, 3)
        result["is_knockout"] = is_knockout

        return result


def run_quick_simulation(elo_engine, home_id: int, away_id: int,
                         env: MatchEnvironment = None,
                         is_knockout: bool = False) -> Dict:
    """
    快捷模拟接口：从 Elo 引擎获取 λ → 环境修正 → 蒙特卡洛
    """
    lh, la = calc_expected_goals(home_id, away_id, elo_engine)
    sim = Simulator()
    return sim.run_detailed(lh, la, env, is_knockout=is_knockout)
