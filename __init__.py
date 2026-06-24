"""
World Cup Predictor - 2026世界杯比分预测模型

四层融合架构：Elo + Dixon-Coles泊松 + 蒙特卡洛 + 贝叶斯
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from model.elo_engine import EloEngine
from model.poisson import calc_expected_goals
from model.monte_carlo import Simulator, MatchEnvironment
from model.bayesian import calc_market_implied_prob, bayesian_fusion
from model.llm_analyzer import generate_match_analysis, set_llm_enabled, is_llm_enabled, call_llm
from data.bsd_api import set_bsd_api_key, get_best_odds, get_team_injuries
from data.news_api import get_team_news, get_team_injuries_from_wiki


class Predictor:
    """
    预测器类 - 供其他AI工具调用
    
    示例：
        predictor = Predictor()
        result = predictor.predict("西班牙", "沙特阿拉伯", 1.83, 4.00, 3.00)
        print(result.prediction)
    """
    
    def __init__(self, bsd_api_key=None, llm_provider=None, llm_api_key=None, llm_model=None):
        """初始化预测器"""
        if bsd_api_key:
            set_bsd_api_key(bsd_api_key)
        
        if llm_provider and llm_api_key:
            set_llm_config(llm_provider, llm_api_key, llm_model)
        
        self._teams = {
            "西班牙": {"id": 29, "elo": 1840, "fifa_ranking": 4},
            "沙特阿拉伯": {"id": 31, "elo": 1550, "fifa_ranking": 48},
            "比利时": {"id": 25, "elo": 1800, "fifa_ranking": 14},
            "伊朗": {"id": 27, "elo": 1720, "fifa_ranking": 23},
            "乌拉圭": {"id": 32, "elo": 1660, "fifa_ranking": 8},
            "佛得角": {"id": 30, "elo": 1770, "fifa_ranking": 64},
            "新西兰": {"id": 28, "elo": 1540, "fifa_ranking": 56},
            "埃及": {"id": 26, "elo": 1790, "fifa_ranking": 36},
            "巴西": {"id": 33, "elo": 1850, "fifa_ranking": 5},
            "阿根廷": {"id": 34, "elo": 1870, "fifa_ranking": 1},
            "法国": {"id": 35, "elo": 1860, "fifa_ranking": 2},
            "英格兰": {"id": 36, "elo": 1810, "fifa_ranking": 3},
        }
    
    def predict(self, home, away, odds_home=None, odds_draw=None, odds_away=None, use_llm=False):
        """
        预测比赛
        
        Args:
            home: 主队名
            away: 客队名
            odds_home: 主胜赔率（可选）
            odds_draw: 平局赔率（可选）
            odds_away: 客胜赔率（可选）
            use_llm: 是否使用大模型增强
        
        Returns:
            PredictionResult对象
        """
        # 导入cli中的预测函数
        import sys
        import os
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from cli import predict_match
        
        result_dict = predict_match(home, away, odds_home, odds_draw, odds_away, use_llm)
        
        return PredictionResult(result_dict)
    
    def get_odds(self, home, away):
        """获取实时赔率"""
        return get_best_odds(home, away)
    
    def get_injuries(self, team):
        """获取伤病名单"""
        return get_team_injuries_from_wiki(team)
    
    def get_news(self, team, limit=5):
        """获取新闻"""
        return get_team_news(team, limit)
    
    def list_teams(self):
        """列出所有球队"""
        return list(self._teams.keys())


class PredictionResult:
    """预测结果类"""
    
    def __init__(self, data):
        self._data = data
    
    @property
    def match(self):
        return self._data.get("match")
    
    @property
    def prediction(self):
        return self._data.get("prediction")
    
    @property
    def confidence(self):
        return self._data.get("confidence")
    
    @property
    def top_scores(self):
        return self._data.get("top_scores", [])
    
    @property
    def elo_diff(self):
        return self._data.get("elo_diff")
    
    @property
    def lambda_home(self):
        return self._data.get("lambda_home")
    
    @property
    def lambda_away(self):
        return self._data.get("lambda_away")
    
    @property
    def mc_probs(self):
        return self._data.get("mc_probs")
    
    @property
    def posterior_probs(self):
        return self._data.get("posterior_probs")
    
    @property
    def llm_analysis(self):
        return self._data.get("llm_analysis")
    
    def to_dict(self):
        return self._data
    
    def __str__(self):
        return f"{self.match}: {self.prediction} (置信度{self.confidence:.1%})"


__all__ = [
    "Predictor",
    "PredictionResult",
    "EloEngine",
    "calc_expected_goals",
    "Simulator",
    "MatchEnvironment",
    "calc_market_implied_prob",
    "bayesian_fusion",
    "generate_match_analysis",
    "set_llm_enabled",
    "is_llm_enabled",
    "call_llm",
    "set_bsd_api_key",
    "get_best_odds",
    "get_team_injuries",
    "get_team_news",
    "get_team_injuries_from_wiki",
]