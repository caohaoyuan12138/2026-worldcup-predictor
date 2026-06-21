"""
解释层模块 - 核心分析引擎

这不是装饰，而是真正的判断引擎。
所有因素都会影响最终预测结果。

解释层维度：
1. Elo/评分系统 - 球队实力对比
2. 补水时刻战术影响 - 上下半场30分钟后强制补水
3. 主场/天气因素 - 环境影响
4. 伤停/体能 - 球员状态
5. 战术相克 - 阵型对抗
6. 市场信号 - 赔率隐含信息
7. 胜平负概率 - 综合预测
8. 比分池 - 最可能比分
9. 大小球预测 - 进球总数
10. 风险观点 - 多维度风险分析
"""

import math
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass


@dataclass
class ExplanationResult:
    """解释层结果"""
    # 核心输出
    win_draw_lose_probs: Dict[str, float]  # 胜平负概率
    expected_goals: Dict[str, float]  # 预期进球
    total_goals_prediction: Dict[str, any]  # 大小球预测
    top_score: str  # 首选比分
    score_probs: List[Dict]  # 比分概率列表
    
    # 解释层维度
    elo_analysis: Dict  # Elo评分分析
    hydration_impact: Dict  # 补水时刻战术影响
    environment_factors: Dict  # 主场/天气
    injury_fitness: Dict  # 伤停/体能
    tactical_matchup: Dict  # 战术相克
    market_signals: Dict  # 市场信号
    score_pool: Dict  # 比分池
    over_under: Dict  # 大小球
    
    # 风险分析
    risk_analysis: Dict  # 风险观点（拆分）
    
    # 比分矩阵
    score_matrix: List[List[float]]  # 0-8球比分矩阵
    
    # 观点摘要
    summary: str


class ExplanationEngine:
    """
    解释引擎 - 核心分析
    
    所有维度都会影响最终预测，不是装饰。
    """
    
    def __init__(self):
        # 补水时刻影响系数
        self.hydration_effect = {
            "tactical_shift": 0.05,  # 战术调整概率
            "tempo_change": 0.10,  # 节奏变化
            "substitution_likelihood": 0.15,  # 换人概率
        }
        
        # 战术相克矩阵
        self.tactical_matrix = {
            ("4-3-3", "4-4-2"): {"home": 0.05, "away": -0.03},
            ("4-3-3", "5-3-2"): {"home": -0.02, "away": 0.04},
            ("4-4-2", "4-3-3"): {"home": -0.03, "away": 0.05},
            ("4-4-2", "3-5-2"): {"home": 0.02, "away": -0.04},
            ("3-5-2", "4-4-2"): {"home": -0.04, "away": 0.02},
            ("5-3-2", "4-3-3"): {"home": 0.04, "away": -0.02},
        }
        
        # 大小球阈值
        self.over_under_lines = [0.5, 1.5, 2.5, 3.5, 4.5]
    
    def analyze(self, 
                elo_data: Dict,
                poisson_data: Dict,
                mc_data: Dict,
                bayesian_data: Dict,
                environment_data: Dict,
                injury_data: Dict,
                tactical_data: Dict,
                market_data: Dict,
                score_matrix: List[List[float]]) -> ExplanationResult:
        """
        综合分析 - 所有维度进入判断
        
        Args:
            elo_data: Elo评分数据
            poisson_data: 泊松期望进球
            mc_data: 蒙特卡洛模拟结果
            bayesian_data: 贝叶斯融合结果
            environment_data: 环境（主场/天气）
            injury_data: 伤病/体能数据
            tactical_data: 战术数据
            market_data: 市场赔率数据
            score_matrix: 0-8球比分矩阵
        
        Returns:
            ExplanationResult: 完整的解释结果
        """
        
        # 1. Elo评分系统分析
        elo_analysis = self._analyze_elo(elo_data)
        
        # 2. 补水时刻战术影响
        hydration_impact = self._analyze_hydration(tactical_data)
        
        # 3. 主场/天气因素
        environment_factors = self._analyze_environment(environment_data)
        
        # 4. 伤停/体能分析
        injury_fitness = self._analyze_injury_fitness(injury_data)
        
        # 5. 战术相克分析
        tactical_matchup = self._analyze_tactical_matchup(tactical_data)
        
        # 6. 市场信号分析
        market_signals = self._analyze_market_signals(market_data)
        
        # 7. 胜平负概率（综合所有因素）
        win_draw_lose_probs = self._calculate_final_probs(
            elo_analysis, hydration_impact, environment_factors,
            injury_fitness, tactical_matchup, market_signals,
            bayesian_data, mc_data
        )
        
        # 8. 预期进球数
        expected_goals = self._calculate_expected_goals(
            poisson_data, injury_fitness, tactical_matchup
        )
        
        # 9. 大小球预测
        total_goals_prediction = self._predict_over_under(
            expected_goals, mc_data, market_signals
        )
        
        # 10. 比分池分析
        score_pool = self._analyze_score_pool(score_matrix)
        
        # 11. 首选比分和概率
        top_score, score_probs = self._get_top_scores(score_matrix)
        
        # 12. 风险分析（拆分）
        risk_analysis = self._analyze_risks(
            win_draw_lose_probs, expected_goals, injury_data,
            tactical_data, market_data, score_matrix
        )
        
        # 13. 观点摘要
        summary = self._generate_summary(
            elo_analysis, injury_fitness, tactical_matchup,
            win_draw_lose_probs, top_score, risk_analysis
        )
        
        return ExplanationResult(
            win_draw_lose_probs=win_draw_lose_probs,
            expected_goals=expected_goals,
            total_goals_prediction=total_goals_prediction,
            top_score=top_score,
            score_probs=score_probs,
            elo_analysis=elo_analysis,
            hydration_impact=hydration_impact,
            environment_factors=environment_factors,
            injury_fitness=injury_fitness,
            tactical_matchup=tactical_matchup,
            market_signals=market_signals,
            score_pool=score_pool,
            over_under=total_goals_prediction,
            risk_analysis=risk_analysis,
            score_matrix=score_matrix,
            summary=summary
        )
    
    def _analyze_elo(self, elo_data: Dict) -> Dict:
        """Elo评分系统分析"""
        diff = elo_data.get("diff", 0)
        home_rating = elo_data.get("home_rating", 1500)
        away_rating = elo_data.get("away_rating", 1500)
        
        # 评分差距判断
        if diff > 200:
            level = "碾压级优势"
            impact = 0.15
        elif diff > 100:
            level = "明显优势"
            impact = 0.10
        elif diff > 50:
            level = "轻微优势"
            impact = 0.05
        elif diff > -50:
            level = "势均力敌"
            impact = 0.0
        elif diff > -100:
            level = "轻微劣势"
            impact = -0.05
        elif diff > -200:
            level = "明显劣势"
            impact = -0.10
        else:
            level = "碾压级劣势"
            impact = -0.15
        
        return {
            "home_rating": home_rating,
            "away_rating": away_rating,
            "diff": diff,
            "level": level,
            "impact": impact,  # 对胜率的影响
            "fifa_rank_diff": elo_data.get("home_fifa_rank", "?"),
        }
    
    def _analyze_hydration(self, tactical_data: Dict) -> Dict:
        """
        补水时刻战术影响分析
        
        上下半场30分钟后强制补水时刻对战术的影响：
        - 战术调整概率
        - 节奏变化
        - 换人可能性
        """
        home_style = tactical_data.get("home_style", "balanced")
        away_style = tactical_data.get("away_style", "balanced")
        
        # 不同战术风格对补水的反应
        hydration_response = {
            "attacking": {"tactical_shift": 0.08, "tempo_drop": 0.12},
            "balanced": {"tactical_shift": 0.05, "tempo_drop": 0.08},
            "defensive": {"tactical_shift": 0.03, "tempo_drop": 0.05},
            "counter": {"tactical_shift": 0.10, "tempo_drop": 0.06},
        }
        
        home_response = hydration_response.get(home_style, hydration_response["balanced"])
        away_response = hydration_response.get(away_style, hydration_response["balanced"])
        
        # 补水时刻对进球的影响
        # 下半场补水后，防守方通常更稳固，进球概率下降
        goal_impact = -0.05
        
        return {
            "first_half_30min": {
                "home_tactical_shift": home_response["tactical_shift"],
                "away_tactical_shift": away_response["tactical_shift"],
            },
            "second_half_30min": {
                "home_tactical_shift": home_response["tactical_shift"] * 1.2,
                "away_tactical_shift": away_response["tactical_shift"] * 1.2,
            },
            "goal_impact": goal_impact,
            "substitution_likelihood": self.hydration_effect["substitution_likelihood"],
            "summary": f"补水时刻后，{home_style}风格球队战术调整概率{home_response['tactical_shift']*100:.1f}%，进球概率下降约5%",
        }
    
    def _analyze_environment(self, environment_data: Dict) -> Dict:
        """主场/天气因素分析"""
        is_home = environment_data.get("is_home_advantage", True)
        temperature = environment_data.get("temperature", 22)
        is_rain = environment_data.get("is_rain", False)
        altitude = environment_data.get("altitude", 0)
        
        # 主场优势
        home_advantage = 0.10 if is_home else 0
        
        # 温度影响
        temp_impact = 0
        if temperature > 30:
            temp_impact = -0.05  # 高温降低体能
        elif temperature < 10:
            temp_impact = -0.03  # 低温影响发挥
        
        # 雨天影响
        rain_impact = -0.08 if is_rain else 0
        
        # 海拔影响
        altitude_impact = 0
        if altitude > 1500:
            altitude_impact = -0.10  # 高海拔影响客队更多
        
        total_impact = home_advantage + temp_impact + rain_impact + altitude_impact
        
        return {
            "home_advantage": home_advantage,
            "temperature": temperature,
            "temperature_impact": temp_impact,
            "is_rain": is_rain,
            "rain_impact": rain_impact,
            "altitude": altitude,
            "altitude_impact": altitude_impact,
            "total_impact": total_impact,
            "summary": f"主场优势+{home_advantage*100:.1f}%，环境因素总影响{total_impact*100:+.1f}%",
        }
    
    def _analyze_injury_fitness(self, injury_data: Dict) -> Dict:
        """伤停/体能分析"""
        home_injuries = injury_data.get("home_injuries", [])
        away_injuries = injury_data.get("away_injuries", [])
        home_fitness = injury_data.get("home_fitness", 100)
        away_fitness = injury_data.get("away_fitness", 100)
        
        # 伤病影响计算
        # 主力伤病-5%，替补伤病-2%，疑伤-1%
        home_injury_impact = 0
        for injury in home_injuries:
            status = injury.get("status", "injured")
            if status == "injured":
                home_injury_impact -= 0.05
            elif status == "suspended":
                home_injury_impact -= 0.05
            elif status == "doubt":
                home_injury_impact -= 0.02
        
        away_injury_impact = 0
        for injury in away_injuries:
            status = injury.get("status", "injured")
            if status == "injured":
                away_injury_impact -= 0.05
            elif status == "suspended":
                away_injury_impact -= 0.05
            elif status == "doubt":
                away_injury_impact -= 0.02
        
        # 体能影响
        home_fitness_impact = (100 - home_fitness) * -0.01
        away_fitness_impact = (100 - away_fitness) * -0.01
        
        total_home_impact = home_injury_impact + home_fitness_impact
        total_away_impact = away_injury_impact + away_fitness_impact
        
        return {
            "home_injuries": home_injuries,
            "away_injuries": away_injuries,
            "home_injury_count": len(home_injuries),
            "away_injury_count": len(away_injuries),
            "home_injury_impact": home_injury_impact,
            "away_injury_impact": away_injury_impact,
            "home_fitness": home_fitness,
            "away_fitness": away_fitness,
            "home_fitness_impact": home_fitness_impact,
            "away_fitness_impact": away_fitness_impact,
            "total_home_impact": total_home_impact,
            "total_away_impact": total_away_impact,
            "summary": f"主队伤病影响{total_home_impact*100:+.1f}%，客队{total_away_impact*100:+.1f}%",
        }
    
    def _analyze_tactical_matchup(self, tactical_data: Dict) -> Dict:
        """战术相克分析"""
        home_formation = tactical_data.get("home_formation", "4-3-3")
        away_formation = tactical_data.get("away_formation", "4-4-2")
        home_style = tactical_data.get("home_style", "balanced")
        away_style = tactical_data.get("away_style", "balanced")
        
        # 查找战术相克矩阵
        matchup_key = (home_formation, away_formation)
        matchup_effect = self.tactical_matrix.get(matchup_key, {"home": 0, "away": 0})
        
        # 如果没有直接匹配，尝试反向
        reverse_key = (away_formation, home_formation)
        reverse_effect = self.tactical_matrix.get(reverse_key, {"home": 0, "away": 0})
        if reverse_effect and not matchup_effect:
            matchup_effect = {"home": -reverse_effect["away"], "away": -reverse_effect["home"]}
        
        home_tactical_advantage = matchup_effect.get("home", 0)
        away_tactical_advantage = matchup_effect.get("away", 0)
        
        # 战术风格相克
        style_matchup = {
            ("attacking", "defensive"): {"home": -0.03, "away": 0.05},
            ("attacking", "counter"): {"home": 0.02, "away": -0.05},
            ("defensive", "attacking"): {"home": 0.05, "away": -0.03},
            ("defensive", "counter"): {"home": -0.02, "away": 0.03},
            ("counter", "attacking"): {"home": -0.05, "away": 0.02},
            ("counter", "defensive"): {"home": 0.03, "away": -0.02},
        }
        
        style_key = (home_style, away_style)
        style_effect = style_matchup.get(style_key, {"home": 0, "away": 0})
        
        total_home_advantage = home_tactical_advantage + style_effect.get("home", 0)
        total_away_advantage = away_tactical_advantage + style_effect.get("away", 0)
        
        return {
            "home_formation": home_formation,
            "away_formation": away_formation,
            "home_style": home_style,
            "away_style": away_style,
            "formation_matchup": matchup_effect,
            "style_matchup": style_effect,
            "total_home_advantage": total_home_advantage,
            "total_away_advantage": total_away_advantage,
            "summary": f"{home_formation} vs {away_formation}，主队战术优势{total_home_advantage*100:+.1f}%",
        }
    
    def _analyze_market_signals(self, market_data: Dict) -> Dict:
        """市场信号分析"""
        odds_home = market_data.get("odds_home", 0)
        odds_draw = market_data.get("odds_draw", 0)
        odds_away = market_data.get("odds_away", 0)
        
        if not odds_home or not odds_draw or not odds_away:
            return {"signal": "无市场数据", "impact": 0}
        
        # 计算隐含概率
        implied_home = 1 / odds_home
        implied_draw = 1 / odds_draw
        implied_away = 1 / odds_away
        
        # 计算返还率
        payout_rate = implied_home + implied_draw + implied_away
        
        # 正规化概率
        norm_home = implied_home / payout_rate
        norm_draw = implied_draw / payout_rate
        norm_away = implied_away / payout_rate
        
        # 市场信号判断
        if norm_home > 0.6:
            signal = "市场看好主胜"
            confidence = "高"
        elif norm_away > 0.6:
            signal = "市场看好客胜"
            confidence = "高"
        elif norm_draw > 0.35:
            signal = "市场暗示平局"
            confidence = "中"
        elif abs(norm_home - norm_away) < 0.1:
            signal = "市场认为势均力敌"
            confidence = "低"
        else:
            signal = "市场信号中性"
            confidence = "中"
        
        # 赔率变化信号（如果有）
        odds_change = market_data.get("odds_change", {})
        if odds_change:
            home_change = odds_change.get("home", 0)
            if home_change > 0.1:
                signal += "，主胜赔率上升（市场信心下降）"
            elif home_change < -0.1:
                signal += "，主胜赔率下降（市场信心上升）"
        
        return {
            "odds_home": odds_home,
            "odds_draw": odds_draw,
            "odds_away": odds_away,
            "implied_home": norm_home,
            "implied_draw": norm_draw,
            "implied_away": norm_away,
            "signal": signal,
            "confidence": confidence,
            "payout_rate": payout_rate,
            "summary": f"市场隐含概率：主胜{norm_home:.1%} 平{norm_draw:.1%} 客胜{norm_away:.1%}",
        }
    
    def _calculate_final_probs(self, 
                               elo_analysis: Dict,
                               hydration_impact: Dict,
                               environment_factors: Dict,
                               injury_fitness: Dict,
                               tactical_matchup: Dict,
                               market_signals: Dict,
                               bayesian_data: Dict,
                               mc_data: Dict) -> Dict[str, float]:
        """
        计算最终胜平负概率
        
        所有因素都会影响最终概率！
        """
        # 基础概率（从贝叶斯或蒙特卡洛）
        if bayesian_data:
            base_probs = {
                "home_win": bayesian_data.get("home_win", 0.33),
                "draw": bayesian_data.get("draw", 0.34),
                "away_win": bayesian_data.get("away_win", 0.33),
            }
        else:
            base_probs = {
                "home_win": mc_data.get("home_win", 0.33),
                "draw": mc_data.get("draw", 0.34),
                "away_win": mc_data.get("away_win", 0.33),
            }
        
        # 累积所有影响因子
        home_impact = 0
        away_impact = 0
        
        # Elo影响
        home_impact += elo_analysis.get("impact", 0)
        
        # 补水影响
        home_impact += hydration_impact.get("goal_impact", 0)
        
        # 环境影响
        env_total = environment_factors.get("total_impact", 0)
        home_impact += env_total
        
        # 伤病影响
        home_impact += injury_fitness.get("total_home_impact", 0)
        away_impact += injury_fitness.get("total_away_impact", 0)
        
        # 战术相克影响
        home_impact += tactical_matchup.get("total_home_advantage", 0)
        away_impact += tactical_matchup.get("total_away_advantage", 0)
        
        # 调整概率
        adjusted_home = base_probs["home_win"] + home_impact
        adjusted_away = base_probs["away_win"] + away_impact
        adjusted_draw = base_probs["draw"]
        
        # 确保概率在合理范围
        adjusted_home = max(0.05, min(0.85, adjusted_home))
        adjusted_away = max(0.05, min(0.85, adjusted_away))
        
        # 正规化
        total = adjusted_home + adjusted_draw + adjusted_away
        final_home = adjusted_home / total
        final_draw = adjusted_draw / total
        final_away = adjusted_away / total
        
        return {
            "home_win": round(final_home, 3),
            "draw": round(final_draw, 3),
            "away_win": round(final_away, 3),
            "base_probs": base_probs,
            "adjustments": {
                "elo": elo_analysis.get("impact", 0),
                "hydration": hydration_impact.get("goal_impact", 0),
                "environment": env_total,
                "injury_home": injury_fitness.get("total_home_impact", 0),
                "injury_away": injury_fitness.get("total_away_impact", 0),
                "tactical_home": tactical_matchup.get("total_home_advantage", 0),
                "tactical_away": tactical_matchup.get("total_away_advantage", 0),
            },
        }
    
    def _calculate_expected_goals(self, 
                                  poisson_data: Dict,
                                  injury_fitness: Dict,
                                  tactical_matchup: Dict) -> Dict[str, float]:
        """计算预期进球数"""
        base_lambda_home = poisson_data.get("lambda_home", 1.4)
        base_lambda_away = poisson_data.get("lambda_away", 1.4)
        
        # 伤病调整
        injury_home = injury_fitness.get("total_home_impact", 0)
        injury_away = injury_fitness.get("total_away_impact", 0)
        
        # 战术调整
        tactical_home = tactical_matchup.get("total_home_advantage", 0)
        tactical_away = tactical_matchup.get("total_away_advantage", 0)
        
        # 调整lambda
        adjusted_lambda_home = base_lambda_home * (1 + injury_home + tactical_home)
        adjusted_lambda_away = base_lambda_away * (1 + injury_away + tactical_away)
        
        # 确保合理范围
        adjusted_lambda_home = max(0.3, min(3.5, adjusted_lambda_home))
        adjusted_lambda_away = max(0.3, min(3.5, adjusted_lambda_away))
        
        return {
            "lambda_home": round(adjusted_lambda_home, 3),
            "lambda_away": round(adjusted_lambda_away, 3),
            "total_expected": round(adjusted_lambda_home + adjusted_lambda_away, 2),
            "base_lambda_home": base_lambda_home,
            "base_lambda_away": base_lambda_away,
        }
    
    def _predict_over_under(self, 
                            expected_goals: Dict,
                            mc_data: Dict,
                            market_signals: Dict) -> Dict:
        """大小球预测"""
        total_expected = expected_goals.get("total_expected", 2.8)
        
        # 计算各大小球线的概率
        over_under_probs = {}
        for line in self.over_under_lines:
            # 使用泊松分布计算
            prob_over = self._calc_over_prob(total_expected, line)
            over_under_probs[f"over_{line}"] = prob_over
        
        # 推荐
        if total_expected > 3.0:
            recommendation = "大球（2.5球以上）"
            confidence = "高"
        elif total_expected > 2.5:
            recommendation = "大球偏（2.5球）"
            confidence = "中"
        elif total_expected < 1.8:
            recommendation = "小球（2.5球以下）"
            confidence = "高"
        elif total_expected < 2.2:
            recommendation = "小球偏（2.5球）"
            confidence = "中"
        else:
            recommendation = "中性（约2.5球）"
            confidence = "低"
        
        return {
            "total_expected": total_expected,
            "over_under_probs": over_under_probs,
            "recommendation": recommendation,
            "confidence": confidence,
            "most_likely_total": round(total_expected, 1),
        }
    
    def _calc_over_prob(self, total_lambda: float, line: float) -> float:
        """计算大于某线的概率"""
        from scipy.stats import poisson
        # 总进球服从泊松分布
        prob_under = poisson.cdf(int(line), total_lambda)
        return 1 - prob_under
    
    def _analyze_score_pool(self, score_matrix: List[List[float]]) -> Dict:
        """比分池分析"""
        # 提取所有比分概率
        scores = []
        for i in range(len(score_matrix)):
            for j in range(len(score_matrix[i])):
                prob = score_matrix[i][j]
                if prob > 0.01:  # 只保留概率>1%的比分
                    scores.append({
                        "score": f"{i}-{j}",
                        "probability": prob,
                    })
        
        # 按概率排序
        scores.sort(key=lambda x: x["probability"], reverse=True)
        
        # 分类
        home_win_scores = [s for s in scores if int(s["score"].split("-")[0]) > int(s["score"].split("-")[1])]
        draw_scores = [s for s in scores if int(s["score"].split("-")[0]) == int(s["score"].split("-")[1])]
        away_win_scores = [s for s in scores if int(s["score"].split("-")[0]) < int(s["score"].split("-")[1])]
        
        return {
            "all_scores": scores[:10],
            "home_win_pool": home_win_scores[:5],
            "draw_pool": draw_scores[:3],
            "away_win_pool": away_win_scores[:5],
            "total_scores": len(scores),
        }
    
    def _get_top_scores(self, score_matrix: List[List[float]]) -> Tuple[str, List[Dict]]:
        """获取首选比分和比分概率列表"""
        scores = []
        for i in range(len(score_matrix)):
            for j in range(len(score_matrix[i])):
                prob = score_matrix[i][j]
                scores.append({
                    "score": f"{i}-{j}",
                    "probability": prob,
                })
        
        scores.sort(key=lambda x: x["probability"], reverse=True)
        
        top_score = scores[0]["score"] if scores else "未知"
        
        return top_score, scores[:10]
    
    def _analyze_risks(self,
                       win_draw_lose_probs: Dict,
                       expected_goals: Dict,
                       injury_data: Dict,
                       tactical_data: Dict,
                       market_data: Dict,
                       score_matrix: List[List[float]]) -> Dict:
        """
        风险分析（拆分）
        
        包括：
        1. 冷门风险
        2. 角球风险
        3. 红黄牌风险
        4. 双方进球风险
        5. 大小球风险
        6. 关键球员风险
        7. 球员心理压力
        """
        
        # 1. 冷门风险
        upset_risk = self._analyze_upset_risk(win_draw_lose_probs, market_data)
        
        # 2. 角球风险
        corner_risk = self._analyze_corner_risk(tactical_data)
        
        # 3. 红黄牌风险
        card_risk = self._analyze_card_risk(tactical_data, injury_data)
        
        # 4. 双方进球风险
        btts_risk = self._analyze_btts_risk(expected_goals, score_matrix)
        
        # 5. 大小球风险
        over_under_risk = self._analyze_over_under_risk(expected_goals)
        
        # 6. 关键球员风险
        key_player_risk = self._analyze_key_player_risk(injury_data)
        
        # 7. 球员心理压力
        psychology_risk = self._analyze_psychology_risk(win_draw_lose_probs, tactical_data)
        
        # 观点摘要
        risk_summary = self._generate_risk_summary(
            upset_risk, corner_risk, card_risk, btts_risk,
            over_under_risk, key_player_risk, psychology_risk
        )
        
        return {
            "upset": upset_risk,
            "corner": corner_risk,
            "card": card_risk,
            "btts": btts_risk,
            "over_under": over_under_risk,
            "key_player": key_player_risk,
            "psychology": psychology_risk,
            "summary": risk_summary,
        }
    
    def _analyze_upset_risk(self, probs: Dict, market: Dict) -> Dict:
        """冷门风险分析"""
        home_prob = probs.get("home_win", 0.33)
        away_prob = probs.get("away_win", 0.33)
        
        # 如果市场看好一方但概率不高，冷门风险大
        implied_home = market.get("implied_home", 0.33)
        implied_away = market.get("implied_away", 0.33)
        
        # 冷门定义：市场看好一方>60%，但模型预测<50%
        upset_level = "低"
        upset_prob = 0
        
        if implied_home > 0.6 and home_prob < 0.5:
            upset_level = "高"
            upset_prob = away_prob + probs.get("draw", 0.34)
        elif implied_away > 0.6 and away_prob < 0.5:
            upset_level = "高"
            upset_prob = home_prob + probs.get("draw", 0.34)
        elif abs(home_prob - away_prob) < 0.15:
            upset_level = "中"
            upset_prob = max(home_prob, away_prob)
        
        return {
            "level": upset_level,
            "probability": upset_prob,
            "direction": "客胜冷门" if implied_home > 0.6 else "主胜冷门" if implied_away > 0.6 else "无明显冷门",
        }
    
    def _analyze_corner_risk(self, tactical: Dict) -> Dict:
        """角球风险分析"""
        home_style = tactical.get("home_style", "balanced")
        away_style = tactical.get("away_style", "balanced")
        
        # 不同风格预期角球
        corner_expectation = {
            "attacking": {"corners_for": 6, "corners_against": 3},
            "balanced": {"corners_for": 5, "corners_against": 4},
            "defensive": {"corners_for": 3, "corners_against": 6},
            "counter": {"corners_for": 4, "corners_against": 5},
        }
        
        home_corners = corner_expectation.get(home_style, corner_expectation["balanced"])
        away_corners = corner_expectation.get(away_style, corner_expectation["balanced"])
        
        total_corners = home_corners["corners_for"] + away_corners["corners_for"]
        
        return {
            "home_corners_expected": home_corners["corners_for"],
            "away_corners_expected": away_corners["corners_for"],
            "total_corners_expected": total_corners,
            "over_9_5_prob": 0.65 if total_corners > 10 else 0.45,
        }
    
    def _analyze_card_risk(self, tactical: Dict, injury: Dict) -> Dict:
        """红黄牌风险分析"""
        home_style = tactical.get("home_style", "balanced")
        away_style = tactical.get("away_style", "balanced")
        
        # 不同风格预期犯规/黄牌
        card_expectation = {
            "attacking": {"cards": 1.5, "fouls": 12},
            "balanced": {"cards": 2, "fouls": 14},
            "defensive": {"cards": 2.5, "fouls": 16},
            "counter": {"cards": 1.8, "fouls": 13},
        }
        
        home_cards = card_expectation.get(home_style, card_expectation["balanced"])
        away_cards = card_expectation.get(away_style, card_expectation["balanced"])
        
        # 红牌概率（通常较低）
        red_card_prob = 0.05
        
        return {
            "home_cards_expected": home_cards["cards"],
            "away_cards_expected": away_cards["cards"],
            "total_cards_expected": home_cards["cards"] + away_cards["cards"],
            "red_card_probability": red_card_prob,
        }
    
    def _analyze_btts_risk(self, expected_goals: Dict, score_matrix: List[List[float]]) -> Dict:
        """双方进球（BTTS）风险分析"""
        lambda_home = expected_goals.get("lambda_home", 1.4)
        lambda_away = expected_goals.get("lambda_away", 1.4)
        
        # 计算双方都进球的概率
        # P(both score) = 1 - P(home=0) - P(away=0) + P(both=0)
        from scipy.stats import poisson
        
        p_home_zero = poisson.pmf(0, lambda_home)
        p_away_zero = poisson.pmf(0, lambda_away)
        
        btts_prob = 1 - p_home_zero - p_away_zero + p_home_zero * p_away_zero
        
        return {
            "probability": round(btts_prob, 3),
            "recommendation": "是" if btts_prob > 0.55 else "否" if btts_prob < 0.45 else "中性",
        }
    
    def _analyze_over_under_risk(self, expected_goals: Dict) -> Dict:
        """大小球风险分析"""
        total = expected_goals.get("total_expected", 2.8)
        
        # 风险：偏离预期
        if total > 3.5:
            risk_level = "大球风险高"
            risk_value = 0.15
        elif total < 1.5:
            risk_level = "小球风险高"
            risk_value = 0.15
        else:
            risk_level = "大小球风险适中"
            risk_value = 0.05
        
        return {
            "level": risk_level,
            "risk_value": risk_value,
            "expected_total": total,
        }
    
    def _analyze_key_player_risk(self, injury: Dict) -> Dict:
        """关键球员风险分析"""
        home_injuries = injury.get("home_injuries", [])
        away_injuries = injury.get("away_injuries", [])
        
        # 检查是否有关键球员伤病
        key_players_home = [p for p in home_injuries if p.get("is_key", False)]
        key_players_away = [p for p in away_injuries if p.get("is_key", False)]
        
        risk_level = "低"
        if key_players_home or key_players_away:
            risk_level = "高"
        
        return {
            "level": risk_level,
            "home_key_injuries": len(key_players_home),
            "away_key_injuries": len(key_players_away),
            "affected_players": [p.get("name") for p in key_players_home + key_players_away],
        }
    
    def _analyze_psychology_risk(self, probs: Dict, tactical: Dict) -> Dict:
        """球员心理压力分析"""
        home_prob = probs.get("home_win", 0.33)
        away_prob = probs.get("away_win", 0.33)
        
        # 心理压力因素
        # 1. 赛事重要性（世界杯压力高）
        # 2. 实力差距（差距大压力不对称）
        # 3. 主客场（主场压力更大）
        
        pressure_level = "中"
        if abs(home_prob - away_prob) > 0.3:
            pressure_level = "不对称"  # 一方压力大，一方小
        elif home_prob < 0.4 and away_prob < 0.4:
            pressure_level = "高"  # 双方都有压力
        
        return {
            "level": pressure_level,
            "home_pressure": "高" if home_prob < 0.5 else "中",
            "away_pressure": "高" if away_prob < 0.5 else "中",
            "pressure_asymmetry": abs(home_prob - away_prob),
        }
    
    def _generate_risk_summary(self, 
                               upset, corner, card, btts,
                               over_under, key_player, psychology) -> str:
        """生成风险观点摘要"""
        parts = []
        
        if upset["level"] == "高":
            parts.append(f"⚠️ 冷门风险：{upset['direction']}概率{upset['probability']:.1%}")
        
        if key_player["level"] == "高":
            parts.append(f"⚠️ 关键球员：{key_player['affected_players']}")
        
        parts.append(f"📊 角球预期：{corner['total_corners_expected']}个")
        parts.append(f"📋 黄牌预期：{card['total_cards_expected']}张")
        parts.append(f"⚽ 双方进球：{btts['recommendation']}（{btts['probability']:.1%}）")
        parts.append(f"🧠 心理压力：{psychology['level']}")
        
        return "\n".join(parts)
    
    def _generate_summary(self, 
                          elo_analysis, injury_fitness, tactical_matchup,
                          probs, top_score, risk_analysis) -> str:
        """生成观点摘要"""
        parts = []
        
        # Elo
        parts.append(f"【实力对比】{elo_analysis['level']}，Elo差{elo_analysis['diff']:+d}")
        
        # 伤病
        parts.append(f"【伤病影响】主队{injury_fitness['total_home_impact']*100:+.1f}%，客队{injury_fitness['total_away_impact']*100:+.1f}%")
        
        # 战术
        parts.append(f"【战术相克】{tactical_matchup['summary']}")
        
        # 预测
        parts.append(f"【胜平负】主胜{probs['home_win']:.1%} 平{probs['draw']:.1%} 客胜{probs['away_win']:.1%}")
        
        # 比分
        parts.append(f"【首选比分】{top_score}")
        
        # 风险
        parts.append(f"【风险提示】{risk_analysis['summary'][:100]}")
        
        return "\n\n".join(parts)