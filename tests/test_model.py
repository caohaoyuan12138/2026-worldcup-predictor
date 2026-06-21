"""模型单元测试"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import model.elo_engine as elo
import model.poisson as poisson
import model.monte_carlo as mc
import model.bayesian as bayesian


def test_elo_basic():
    engine = elo.EloEngine()
    t1 = elo.TeamElo(1, "Brazil", "BR", 1)
    t2 = elo.TeamElo(2, "Japan", "JP", 20)
    engine.add_team(t1)
    engine.add_team(t2)
    r = engine.simulate_match(1, 2)
    assert "home_win" in r
    assert r["home_win"] > r["away_win"]  # 巴西应该赢面更大
    print(f"✅ Elo 基础: BR={t1.rating:.0f} vs JP={t2.rating:.0f} → {r}")


def test_poisson_basic():
    engine = elo.EloEngine()
    engine.set_team(1, "TestA", "TA", 10)
    engine.set_team(2, "TestB", "TB", 20)
    lh, la = poisson.calc_expected_goals(1, 2, engine)
    assert lh > 0 and la > 0
    matrix = poisson.calc_score_matrix(lh, la)
    total = sum(matrix.values())
    assert 0.95 < total < 1.05  # 归一化后应接近 1
    probs = poisson.calc_match_probabilities(matrix)
    assert abs(probs["home_win"] + probs["draw"] + probs["away_win"] - 1.0) < 0.01
    print(f"✅ 泊松: λ_home={lh:.2f}, λ_away={la:.2f} → probs={probs}")


def test_monte_carlo_basic():
    sim = mc.Simulator(n_sim=1000)
    result = sim.run_match(1.5, 1.0)
    assert abs(result["home_win"] + result["draw"] + result["away_win"] - 1.0) < 0.01
    print(f"✅ 蒙特卡洛: {result['home_win']:.2f}/{result['draw']:.2f}/{result['away_win']:.2f}")


def test_bayesian_basic():
    model_p = {"home_win": 0.6, "draw": 0.2, "away_win": 0.2}
    market_p = {"home_win": 0.5, "draw": 0.3, "away_win": 0.2}
    result = bayesian.bayesian_fusion(model_p, market_p, "group_stage")
    assert abs(result["home_win"] + result["draw"] + result["away_win"] - 1.0) < 0.01
    print(f"✅ 贝叶斯融合: {result}")


def test_market_implied():
    result = bayesian.calc_market_implied_prob(2.0, 3.5, 4.0)
    total = result["home_win"] + result["draw"] + result["away_win"]
    assert abs(total - 1.0) < 0.01
    print(f"✅ 市场隐含概率: {result}")


def test_kelly():
    import strategy.kelly as kelly
    result = kelly.calc_match_stake(0.6, 2.0, 0.5, "A")
    assert result["adjusted_stake"] >= 0
    assert result["adjusted_stake"] <= 0.05
    print(f"✅ Kelly: {result}")


def test_filters():
    import strategy.filters as filters
    ctx = {
        "team_id": 1, "elo_engine": None, "recent_results": [],
        "h2h_count": 5, "lineup_announced": True, "hours_to_kickoff": 48,
        "phase": "group_stage", "referee_nationality": "",
        "team_nationalities": ["BR"], "referee_bias": 0, "political_risk": "low"
    }
    result = filters.apply_all_filters(ctx)
    assert result["passed"] is True
    print(f"✅ 否决过滤: {len(result['checks'])} 项检查通过")


if __name__ == "__main__":
    test_elo_basic()
    test_poisson_basic()
    test_monte_carlo_basic()
    test_bayesian_basic()
    test_market_implied()
    test_kelly()
    test_filters()
    print("\n🎉 全部 7 个测试通过！")
