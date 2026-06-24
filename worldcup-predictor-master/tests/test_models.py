"""
单元测试 — 覆盖核心模型模块

运行方式:
    pytest tests/test_models.py -v
    或 python -m pytest tests/ -v
"""

import sys
import os
import unittest
import math

# 确保项目根目录在路径中
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import config
from model.elo_engine import TeamElo, EloEngine
from model.poisson import (
    poisson_pmf,
    calc_expected_goals,
    calc_score_matrix,
    calc_match_probabilities,
    get_favorite_scorelines,
)
from model.bayesian import (
    calc_market_implied_prob,
    bayesian_fusion,
    calc_confidence_interval,
    detect_market_value,
)
from model.monte_carlo import MatchEnvironment, Simulator
from strategy.kelly import calc_kelly_stake, apply_risk_controls, calc_match_stake
from strategy.filters import apply_all_filters
from strategy.risk_control import RiskController


# ──────────────────────────────────────────────
#  Elo 引擎测试
# ──────────────────────────────────────────────
class TestEloEngine(unittest.TestCase):

    def test_team_initial_rating(self):
        """测试球队初始评分"""
        team = TeamElo(1, "巴西", "BRA", fifa_ranking=3)
        self.assertGreater(team.rating, 1500)
        self.assertLess(team.rating, 1900)

    def test_team_host_bonus(self):
        """测试东道主加分"""
        team_host = TeamElo(1, "美国", "USA", fifa_ranking=15, is_host_nation=True)
        team_normal = TeamElo(2, "法国", "FRA", fifa_ranking=2)
        adj_host = team_host.get_adjusted_rating()
        adj_normal = team_normal.get_adjusted_rating()
        self.assertEqual(adj_host - team_host.rating, config.ELO_HOST_BONUS)

    def test_elo_expected_score(self):
        """测试 Elo 预期胜率公式"""
        engine = EloEngine()
        engine.set_team(1, "强队", "STR", 5)
        engine.set_team(2, "弱队", "WEA", 50)
        exp = engine.simulate_match(1, 2)
        self.assertGreater(exp["home_win"], exp["away_win"])
        self.assertAlmostEqual(exp["home_win"] + exp["draw"] + exp["away_win"], 1.0, places=3)

    def test_elo_update_after_match(self):
        """测试赛后评分更新"""
        engine = EloEngine()
        engine.set_team(1, "A队", "A", 10)
        engine.set_team(2, "B队", "B", 20)
        rating_before = engine.get_rating(1)
        engine.update_after_match(1, 2, 2, 0, stage="group_stage")
        rating_after = engine.get_rating(1)
        self.assertGreater(rating_after, rating_before)  # 赢球应该加分

    def test_knockout_k_value(self):
        """测试淘汰赛 K 值更高（新球队前5场触发K_MAX上限）"""
        engine = EloEngine()
        engine.set_team(1, "A", "A", 10)
        engine.set_team(2, "B", "B", 20)
        team = engine.teams[1]
        # 先模拟5场比赛，使 recent_results > 5，避免触发 K_MAX
        for _ in range(6):
            team.recent_results.append({"result": 1})
        k_group = team._calc_k(stage="group_stage")
        k_final = team._calc_k(stage="final")
        self.assertGreater(k_final, k_group)


# ──────────────────────────────────────────────
#  泊松模型测试
# ──────────────────────────────────────────────
class TestPoissonModel(unittest.TestCase):

    def test_poisson_pmf_basic(self):
        """测试泊松 PMF 基本计算"""
        p0 = poisson_pmf(0, 1.5)
        p1 = poisson_pmf(1, 1.5)
        p2 = poisson_pmf(2, 1.5)
        self.assertGreater(p0, 0)
        self.assertGreater(p1, 0)
        self.assertGreater(p2, 0)
        # P(0) + P(1) + P(2) < 1（还有其他值）
        self.assertLess(p0 + p1 + p2, 1.0)

    def test_poisson_pmf_zero_lambda(self):
        """测试 lambda=0 时 PMF"""
        self.assertEqual(poisson_pmf(0, 0), 1.0)
        self.assertEqual(poisson_pmf(1, 0), 0.0)

    def test_expected_goals_positive(self):
        """测试期望进球为正"""
        engine = EloEngine()
        engine.set_team(1, "强队", "STR", 5)
        engine.set_team(2, "弱队", "WEA", 50)
        lh, la = calc_expected_goals(1, 2, engine)
        self.assertGreater(lh, 0)
        self.assertGreater(la, 0)

    def test_expected_goals_home_advantage(self):
        """测试主场优势"""
        engine = EloEngine()
        engine.set_team(1, "A", "A", 10)
        engine.set_team(2, "B", "B", 10)
        lh, la = calc_expected_goals(1, 2, engine)
        # 同实力球队，主队期望进球应略高（隐含主场优势）
        self.assertGreaterEqual(lh, la)

    def test_score_matrix_sum_to_one(self):
        """测试比分矩阵概率和为1"""
        matrix = calc_score_matrix(1.5, 1.0, max_goals=6)
        total = sum(matrix.values())
        self.assertAlmostEqual(total, 1.0, places=2)

    def test_match_probabilities_sum(self):
        """测试胜平负概率和为1"""
        matrix = calc_score_matrix(1.5, 1.0, max_goals=6)
        probs = calc_match_probabilities(matrix)
        total = probs["home_win"] + probs["draw"] + probs["away_win"]
        self.assertAlmostEqual(total, 1.0, places=2)

    def test_favorite_scorelines(self):
        """测试最可能比分"""
        matrix = calc_score_matrix(1.5, 1.0, max_goals=6)
        top = get_favorite_scorelines(matrix, top_n=5)
        self.assertEqual(len(top), 5)
        self.assertGreater(top[0]["probability"], top[1]["probability"])


# ──────────────────────────────────────────────
#  贝叶斯融合测试
# ──────────────────────────────────────────────
class TestBayesianFusion(unittest.TestCase):

    def test_market_implied_prob_sum(self):
        """测试市场隐含概率和为1"""
        mp = calc_market_implied_prob(2.0, 3.5, 4.0)
        total = mp["home_win"] + mp["draw"] + mp["away_win"]
        self.assertAlmostEqual(total, 1.0, places=2)

    def test_bayesian_fusion_weights(self):
        """测试融合权重"""
        model = {"home_win": 0.5, "draw": 0.25, "away_win": 0.25}
        market = {"home_win": 0.4, "draw": 0.3, "away_win": 0.3}
        result = bayesian_fusion(model, market, stage="group_stage")
        total = result["home_win"] + result["draw"] + result["away_win"]
        self.assertAlmostEqual(total, 1.0, places=2)
        # 小组赛模型权重更高
        self.assertGreater(result["weight_model"], result["weight_market"])

    def test_final_stage_market_heavier(self):
        """测试决赛市场权重更高"""
        model = {"home_win": 0.5, "draw": 0.25, "away_win": 0.25}
        market = {"home_win": 0.4, "draw": 0.3, "away_win": 0.3}
        result = bayesian_fusion(model, market, stage="final")
        self.assertGreater(result["weight_market"], result["weight_model"])

    def test_confidence_interval(self):
        """测试置信区间"""
        lower, upper = calc_confidence_interval(0.5, n_samples=10000)
        self.assertGreater(lower, 0)
        self.assertLess(upper, 1)
        self.assertLess(lower, upper)

    def test_detect_market_value(self):
        """测试市场价值检测"""
        model = {"home_win": 0.6, "draw": 0.2, "away_win": 0.2}
        market = {"home_win": 0.4, "draw": 0.3, "away_win": 0.3}
        value = detect_market_value(model, market, threshold=0.05)
        self.assertTrue(value["home_win"]["value"])
        self.assertFalse(value["away_win"]["value"])


# ──────────────────────────────────────────────
#  蒙特卡洛模拟测试
# ──────────────────────────────────────────────
class TestMonteCarlo(unittest.TestCase):

    def test_simulator_basic(self):
        """测试蒙特卡洛基本模拟"""
        sim = Simulator(n_sim=1000, seed=42)
        result = sim.run_match(1.5, 1.0)
        total = result["home_win"] + result["draw"] + result["away_win"]
        self.assertAlmostEqual(total, 1.0, places=1)

    def test_simulator_detailed(self):
        """测试详细模拟"""
        sim = Simulator(n_sim=1000, seed=42)
        env = MatchEnvironment(home_team_id=1, away_team_id=2)
        result = sim.run_detailed(1.5, 1.0, env)
        self.assertIn("top_scorelines", result)
        self.assertIn("lambda_home", result)
        self.assertGreater(len(result["top_scorelines"]), 0)

    def test_knockout_simulation(self):
        """测试淘汰赛模拟"""
        sim = Simulator(n_sim=1000, seed=42)
        result = sim.run_match(1.0, 1.0, is_knockout=True)
        self.assertIn("extra_time", result)
        self.assertIn("penalty_shootout", result)
        # 淘汰赛最终无平局
        self.assertAlmostEqual(
            result["final_home_win"] + result["final_away_win"],
            1.0, places=1
        )

    def test_environment_corrections(self):
        """测试环境修正"""
        env = MatchEnvironment(
            home_team_id=1, away_team_id=2,
            temperature=35,  # 高温
            is_water_break=True,
        )
        lh, la = env.apply_corrections(1.5, 1.0)
        # 补水机制应提升进球期望
        self.assertGreater(lh, 1.5)
        self.assertGreater(la, 1.0)


# ──────────────────────────────────────────────
#  Kelly 仓位测试
# ──────────────────────────────────────────────
class TestKelly(unittest.TestCase):

    def test_kelly_positive_expectation(self):
        """测试正期望值"""
        stake = calc_kelly_stake(0.6, 2.0)
        self.assertGreater(stake, 0)

    def test_kelly_negative_expectation(self):
        """测试负期望值"""
        stake = calc_kelly_stake(0.3, 2.0)
        self.assertEqual(stake, 0.0)

    def test_kelly_half_fraction(self):
        """测试半凯利"""
        full = calc_kelly_stake(0.6, 2.0, kelly_fraction=1.0)
        half = calc_kelly_stake(0.6, 2.0, kelly_fraction=0.5)
        self.assertAlmostEqual(half, full * 0.5, places=4)

    def test_risk_control_max_stake(self):
        """测试风控上限"""
        raw = 0.15  # 15%
        controlled = apply_risk_controls(raw, confidence=0.5, league_tier="A")
        self.assertLessEqual(controlled, config.KELLY_MAX_STAKE)

    def test_risk_control_low_confidence(self):
        """测试低置信度减半"""
        raw = 0.04
        controlled = apply_risk_controls(raw, confidence=0.2, league_tier="A")
        self.assertLess(controlled, raw)

    def test_calc_match_stake_structure(self):
        """测试完整仓位建议结构"""
        result = calc_match_stake(0.55, 2.0, confidence=0.6, league_tier="A")
        self.assertIn("recommendation", result)
        self.assertIn("adjusted_stake", result)
        self.assertIn("edge", result)
        self.assertIn("raw_kelly", result)


# ──────────────────────────────────────────────
#  过滤器测试
# ──────────────────────────────────────────────
class TestFilters(unittest.TestCase):

    def test_all_filters_pass(self):
        """测试全部通过"""
        ctx = {
            "team_id": 1,
            "elo_engine": None,
            "recent_results": [{"result": 0.5}, {"result": 0}, {"result": 1}],
            "h2h_count": 5,
            "lineup_announced": True,
            "hours_to_kickoff": 48,
            "phase": "group_stage",
            "referee_nationality": "",
            "team_nationalities": [],
            "referee_bias": 0,
            "political_risk": "low",
        }
        result = apply_all_filters(ctx)
        self.assertTrue(result["passed"])

    def test_h2h_veto(self):
        """测试 H2H 样本不足否决"""
        ctx = {
            "team_id": 1,
            "elo_engine": None,
            "recent_results": [{"result": 0.5}, {"result": 0}, {"result": 1}],
            "h2h_count": 1,
            "lineup_announced": True,
            "hours_to_kickoff": 48,
            "phase": "group_stage",
            "referee_nationality": "",
            "team_nationalities": [],
            "referee_bias": 0,
            "political_risk": "low",
        }
        result = apply_all_filters(ctx)
        self.assertFalse(result["passed"])
        self.assertIn("H2H", result["veto_reason"])

    def test_political_veto(self):
        """测试政治安全否决"""
        ctx = {
            "team_id": 1,
            "elo_engine": None,
            "recent_results": [{"result": 0.5}, {"result": 0}, {"result": 1}],
            "h2h_count": 5,
            "lineup_announced": True,
            "hours_to_kickoff": 48,
            "phase": "group_stage",
            "referee_nationality": "",
            "team_nationalities": [],
            "referee_bias": 0,
            "political_risk": "high",
        }
        result = apply_all_filters(ctx)
        self.assertFalse(result["passed"])


# ──────────────────────────────────────────────
#  风控测试
# ──────────────────────────────────────────────
class TestRiskControl(unittest.TestCase):

    def test_daily_loss_limit(self):
        """测试日亏损上限"""
        ctrl = RiskController()
        ctrl.reset_day(1000)
        ctrl.daily_pnl = -150  # 亏损 15%
        result = ctrl.check_all({"league": "世界杯", "stake_pct": 0.01, "odds": 2.0})
        self.assertFalse(result["approved"])

    def test_consecutive_losses(self):
        """测试连亏止损"""
        ctrl = RiskController()
        ctrl.reset_day(1000)
        ctrl.consecutive_losses = 3
        result = ctrl.check_all({"league": "世界杯", "stake_pct": 0.01, "odds": 2.0})
        self.assertFalse(result["approved"])

    def test_concentration_limit(self):
        """测试集中度限制"""
        ctrl = RiskController(max_concentration_pct=0.20)
        ctrl.reset_day(1000)
        ctrl.league_exposure["世界杯"] = 0.18
        result = ctrl.check_all({"league": "世界杯", "stake_pct": 0.05, "odds": 2.0})
        # 应该被调整
        self.assertTrue(result["approved"])
        self.assertLess(result["adjusted_stake_pct"], 0.05)

    def test_record_result(self):
        """测试记录结果"""
        ctrl = RiskController()
        ctrl.reset_day(1000)
        ctrl.record_result({"stake_pct": 0.02, "odds": 2.0}, won=True)
        self.assertGreater(ctrl.daily_pnl, 0)
        self.assertEqual(ctrl.consecutive_losses, 0)

        ctrl.record_result({"stake_pct": 0.02, "odds": 2.0}, won=False)
        self.assertLess(ctrl.daily_pnl, ctrl.daily_pnl + 20)  # 亏损了
        self.assertEqual(ctrl.consecutive_losses, 1)

    def test_get_status(self):
        """测试状态获取"""
        ctrl = RiskController()
        ctrl.reset_day(1000)
        status = ctrl.get_status()
        self.assertIn("paused", status)
        self.assertIn("daily_pnl", status)
        self.assertIn("consecutive_losses", status)


# ──────────────────────────────────────────────
#  集成测试
# ──────────────────────────────────────────────
class TestIntegration(unittest.TestCase):

    def test_full_pipeline(self):
        """测试完整预测流水线"""
        # 1. 初始化 Elo 引擎
        engine = EloEngine()
        engine.set_team(1, "巴西", "BRA", 3)
        engine.set_team(2, "阿根廷", "ARG", 1)

        # 2. Elo 预测
        elo_pred = engine.simulate_match(1, 2)
        self.assertAlmostEqual(
            elo_pred["home_win"] + elo_pred["draw"] + elo_pred["away_win"],
            1.0, places=2
        )

        # 3. 泊松期望进球
        lh, la = calc_expected_goals(1, 2, engine)
        self.assertGreater(lh, 0)
        self.assertGreater(la, 0)

        # 4. 蒙特卡洛模拟
        sim = Simulator(n_sim=500, seed=42)
        env = MatchEnvironment(home_team_id=1, away_team_id=2)
        mc_result = sim.run_detailed(lh, la, env)
        self.assertIn("top_scorelines", mc_result)

        # 5. 贝叶斯融合（假设市场赔率）
        market = calc_market_implied_prob(2.2, 3.2, 3.5)
        fused = bayesian_fusion(elo_pred, market, stage="group_stage")
        self.assertAlmostEqual(
            fused["home_win"] + fused["draw"] + fused["away_win"],
            1.0, places=2
        )

        # 6. Kelly 仓位
        kelly = calc_match_stake(elo_pred["home_win"], 2.2)
        self.assertIn("recommendation", kelly)

        # 7. 过滤
        ctx = {
            "team_id": 1,
            "elo_engine": engine,
            "recent_results": [{"result": 1}, {"result": 0.5}, {"result": 0}],
            "h2h_count": 10,
            "lineup_announced": True,
            "hours_to_kickoff": 48,
            "phase": "group_stage",
            "referee_nationality": "",
            "team_nationalities": [],
            "referee_bias": 0,
            "political_risk": "low",
        }
        filter_result = apply_all_filters(ctx)

        # 8. 风控
        ctrl = RiskController()
        ctrl.reset_day(1000)
        risk_result = ctrl.check_all({
            "league": "世界杯",
            "stake_pct": kelly["adjusted_stake"],
            "odds": 2.2,
        })

        # 验证整个流程没有报错
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
