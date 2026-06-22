"""
复盘模块 - 比赛结束后分析预测准确性

功能：
1. 根据真实赛果分析预测命中情况
2. 检查各口径命中：一选二选、胜平负、大小球、总进球区间、冷门
3. 生成单场复盘报告，分析偏差原因
4. 统计总命中率，为模型校正提供数据

口径定义：
- 一选命中：首选比分与真实比分完全一致
- 二选命中：二选比分与真实比分一致
- 胜平负命中：预测方向与真实结果一致
- 大小球命中：大小球推荐与真实总进球一致
- 总进球区间命中：预测区间与真实总进球一致
- 冷门命中：是否正确预测冷门
"""

import json
from typing import Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime


@dataclass
class ReviewResult:
    """复盘结果"""
    match: str
    actual_score: str
    actual_result: str  # home_win / draw / away_win
    actual_total_goals: int
    
    # 预测数据
    predicted_top_score: str
    predicted_second_score: str
    predicted_result: str
    predicted_over_under: str
    predicted_total_range: tuple
    
    # 命中情况
    first_choice_hit: bool
    second_choice_hit: bool
    result_hit: bool
    over_under_hit: bool
    total_range_hit: bool
    upset_hit: bool
    
    # 各模型预测准确性（新增）
    elo_hit: bool  # Elo模型预测是否命中
    poisson_hit: bool  # 泊松模型预测是否命中
    mc_hit: bool  # 蒙特卡洛预测是否命中
    bayesian_hit: bool  # 贝叶斯融合预测是否命中
    
    # 各模型预测详情（新增）
    elo_prediction: Dict  # Elo模型预测详情
    poisson_prediction: Dict  # 泊松模型预测详情
    mc_prediction: Dict  # 蒙特卡洛预测详情
    bayesian_prediction: Dict  # 贝叶斯融合预测详情
    
    # 偏差分析
    score_deviation: int
    result_deviation: str
    total_goals_deviation: int
    deviation_reasons: List[str]
    
    # 深度复盘分析（新增）
    model_analysis: Dict  # 各模型偏差深度分析
    
    # 报告
    report: str


class ReviewEngine:
    """复盘引擎"""
    
    def __init__(self):
        self.history = []  # 复盘历史记录
    
    def review_match(self,
                     match_name: str,
                     actual_home_goals: int,
                     actual_away_goals: int,
                     prediction_data: Dict) -> ReviewResult:
        """
        复盘单场比赛
        
        Args:
            match_name: 比赛名称（如"西班牙 vs 沙特"）
            actual_home_goals: 实际主队进球
            actual_away_goals: 实际客队进球
            prediction_data: 预测数据（从_do_analysis返回）
        
        Returns:
            ReviewResult: 复盘结果
        """
        
        # 实际结果
        actual_score = f"{actual_home_goals}-{actual_away_goals}"
        actual_total_goals = actual_home_goals + actual_away_goals
        
        if actual_home_goals > actual_away_goals:
            actual_result = "home_win"
        elif actual_home_goals < actual_away_goals:
            actual_result = "away_win"
        else:
            actual_result = "draw"
        
        # 获取预测数据
        explanation = prediction_data.get("explanation")
        
        if explanation:
            predicted_top_score = explanation.top_score
            predicted_result_probs = explanation.win_draw_lose_probs
            predicted_over_under = explanation.total_goals_prediction.get("recommendation", "")
            predicted_total = explanation.total_goals_prediction.get("most_likely_total", 2.5)
            
            # 获取二选比分
            score_probs = explanation.score_probs
            predicted_second_score = score_probs[1]["score"] if len(score_probs) > 1 else ""
            
            # 预测结果方向
            hw = predicted_result_probs.get("home_win", 0.33)
            aw = predicted_result_probs.get("away_win", 0.33)
            if hw > aw + 0.15:
                predicted_result = "home_win"
            elif aw > hw + 0.15:
                predicted_result = "away_win"
            else:
                predicted_result = "draw"
            
            # 总进球区间
            predicted_total_range = (int(predicted_total - 0.5), int(predicted_total + 1.5))
        else:
            # 从蒙特卡洛数据获取
            mc_data = prediction_data.get("monte_carlo", {})
            top_scores = mc_data.get("top_scorelines", [])
            predicted_top_score = top_scores[0]["score"] if top_scores else "未知"
            predicted_second_score = top_scores[1]["score"] if len(top_scores) > 1 else ""
            
            # 胜平负方向
            hw = mc_data.get("home_win", 0.33)
            aw = mc_data.get("away_win", 0.33)
            if hw > aw + 0.15:
                predicted_result = "home_win"
            elif aw > hw + 0.15:
                predicted_result = "away_win"
            else:
                predicted_result = "draw"
            
            predicted_over_under = "未知"
            predicted_total_range = (0, 8)
        
        # 命中判断
        first_choice_hit = predicted_top_score == actual_score
        second_choice_hit = predicted_second_score == actual_score
        result_hit = predicted_result == actual_result
        
        # ── 各模型预测准确性检查（新增）──
        # Elo模型预测
        elo_data = prediction_data.get("elo", {})
        elo_hw = elo_data.get("home_win", 0.33)
        elo_aw = elo_data.get("away_win", 0.33)
        elo_pred = "home_win" if elo_hw > elo_aw + 0.10 else "away_win" if elo_aw > elo_hw + 0.10 else "draw"
        elo_hit = elo_pred == actual_result
        elo_prediction = {
            "predicted": elo_pred,
            "home_win_prob": elo_hw,
            "draw_prob": elo_data.get("draw", 0.34),
            "away_win_prob": elo_aw,
            "elo_diff": elo_data.get("diff", 0),
            "hit": elo_hit,
        }
        
        # 泊松模型预测
        poisson_data = prediction_data.get("poisson", {})
        poisson_lambda_home = poisson_data.get("lambda_home", 1.4)
        poisson_lambda_away = poisson_data.get("lambda_away", 1.4)
        # 泊松预测：期望进球差值判断
        poisson_pred = "home_win" if poisson_lambda_home > poisson_lambda_away + 0.3 else "away_win" if poisson_lambda_away > poisson_lambda_home + 0.3 else "draw"
        poisson_hit = poisson_pred == actual_result
        poisson_prediction = {
            "predicted": poisson_pred,
            "lambda_home": poisson_lambda_home,
            "lambda_away": poisson_lambda_away,
            "expected_total": poisson_lambda_home + poisson_lambda_away,
            "actual_total": actual_total_goals,
            "hit": poisson_hit,
        }
        
        # 蒙特卡洛预测
        mc_data = prediction_data.get("monte_carlo", {})
        mc_hw = mc_data.get("home_win", 0.33)
        mc_aw = mc_data.get("away_win", 0.33)
        mc_pred = "home_win" if mc_hw > mc_aw + 0.10 else "away_win" if mc_aw > mc_hw + 0.10 else "draw"
        mc_hit = mc_pred == actual_result
        mc_top_scores = mc_data.get("top_scorelines", [])
        mc_prediction = {
            "predicted": mc_pred,
            "home_win_prob": mc_hw,
            "draw_prob": mc_data.get("draw", 0.34),
            "away_win_prob": mc_aw,
            "top_score": mc_top_scores[0]["score"] if mc_top_scores else "未知",
            "hit": mc_hit,
        }
        
        # 贝叶斯融合预测
        bayesian_data = prediction_data.get("bayesian", {})
        bayesian_hw = bayesian_data.get("home_win", 0.33)
        bayesian_aw = bayesian_data.get("away_win", 0.33)
        bayesian_pred = "home_win" if bayesian_hw > bayesian_aw + 0.10 else "away_win" if bayesian_aw > bayesian_hw + 0.10 else "draw"
        bayesian_hit = bayesian_pred == actual_result
        bayesian_prediction = {
            "predicted": bayesian_pred,
            "home_win_prob": bayesian_hw,
            "draw_prob": bayesian_data.get("draw", 0.34),
            "away_win_prob": bayesian_aw,
            "confidence": bayesian_data.get("confidence", 0),
            "hit": bayesian_hit,
        }
        
        # ── 深度复盘分析（新增）──
        model_analysis = self._analyze_model_deviation(
            elo_prediction, poisson_prediction, mc_prediction, bayesian_prediction,
            actual_result, actual_home_goals, actual_away_goals, prediction_data
        )
        
        # 大小球命中
        if "大球" in predicted_over_under and actual_total_goals > 2.5:
            over_under_hit = True
        elif "小球" in predicted_over_under and actual_total_goals < 2.5:
            over_under_hit = True
        elif "中性" in predicted_over_under and 2 <= actual_total_goals <= 3:
            over_under_hit = True
        else:
            over_under_hit = False
        
        # 总进球区间命中
        total_range_hit = predicted_total_range[0] <= actual_total_goals <= predicted_total_range[1]
        
        # 冷门判断（市场看好一方但实际相反）
        market_data = prediction_data.get("bsd_odds", {})
        upset_hit = False
        if market_data:
            implied_home = 1 / market_data.get("average_home", 10)
            if implied_home > 0.6 and actual_result != "home_win":
                upset_hit = True  # 正确预测了冷门
        
        # 偏差分析
        score_deviation = self._calc_score_deviation(predicted_top_score, actual_score)
        result_deviation = self._calc_result_deviation(predicted_result, actual_result)
        total_goals_deviation = abs(predicted_total - actual_total_goals) if explanation else 0
        
        # 偏差原因分析
        deviation_reasons = self._analyze_deviation_reasons(
            prediction_data, actual_home_goals, actual_away_goals
        )
        
        # 生成报告
        report = self._generate_report(
            match_name, actual_score, actual_result, actual_total_goals,
            predicted_top_score, predicted_result, predicted_over_under,
            first_choice_hit, result_hit, over_under_hit,
            deviation_reasons
        )
        
        result = ReviewResult(
            match=match_name,
            actual_score=actual_score,
            actual_result=actual_result,
            actual_total_goals=actual_total_goals,
            predicted_top_score=predicted_top_score,
            predicted_second_score=predicted_second_score,
            predicted_result=predicted_result,
            predicted_over_under=predicted_over_under,
            predicted_total_range=predicted_total_range,
            first_choice_hit=first_choice_hit,
            second_choice_hit=second_choice_hit,
            result_hit=result_hit,
            over_under_hit=over_under_hit,
            total_range_hit=total_range_hit,
            upset_hit=upset_hit,
            elo_hit=elo_hit,
            poisson_hit=poisson_hit,
            mc_hit=mc_hit,
            bayesian_hit=bayesian_hit,
            elo_prediction=elo_prediction,
            poisson_prediction=poisson_prediction,
            mc_prediction=mc_prediction,
            bayesian_prediction=bayesian_prediction,
            score_deviation=score_deviation,
            result_deviation=result_deviation,
            total_goals_deviation=total_goals_deviation,
            deviation_reasons=deviation_reasons,
            model_analysis=model_analysis,
            report=report
        )
        
        # 保存到历史
        self.history.append(result)
        
        return result
    
    def _calc_score_deviation(self, predicted: str, actual: str) -> int:
        """计算比分偏差"""
        try:
            pred_h, pred_a = map(int, predicted.split("-"))
            act_h, act_a = map(int, actual.split("-"))
            return abs(pred_h - act_h) + abs(pred_a - act_a)
        except:
            return 999
    
    def _calc_result_deviation(self, predicted: str, actual: str) -> str:
        """计算结果偏差"""
        if predicted == actual:
            return "无偏差"
        
        if predicted == "home_win" and actual == "draw":
            return "主胜→平局（偏差小）"
        elif predicted == "home_win" and actual == "away_win":
            return "主胜→客胜（偏差大）"
        elif predicted == "away_win" and actual == "draw":
            return "客胜→平局（偏差小）"
        elif predicted == "away_win" and actual == "home_win":
            return "客胜→主胜（偏差大）"
        elif predicted == "draw" and actual in ["home_win", "away_win"]:
            return "平局→有胜负（偏差中）"
        else:
            return "未知偏差"
    
    def _analyze_deviation_reasons(self,
                                   prediction_data: Dict,
                                   actual_home: int,
                                   actual_away: int) -> List[str]:
        """分析偏差原因"""
        reasons = []
        
        # 获取解释层分析
        explanation = prediction_data.get("explanation")
        if not explanation:
            return ["无解释层数据，无法分析偏差原因"]
        
        # 兼容处理：explanation可能是对象或字典
        def _get_attr_or_key(obj, key):
            """兼容获取属性或字典键"""
            if hasattr(obj, key):
                return getattr(obj, key)
            elif isinstance(obj, dict):
                return obj.get(key, {})
            return {}
        
        # Elo偏差
        elo_analysis = _get_attr_or_key(explanation, "elo_analysis")
        elo_impact = elo_analysis.get("impact", 0) if isinstance(elo_analysis, dict) else 0
        if abs(elo_impact) > 0.10:
            reasons.append(f"Elo影响过大（{elo_impact*100:+.1f}%），可能导致过度偏向一方")
        
        # 伤病偏差
        injury_fitness = _get_attr_or_key(explanation, "injury_fitness")
        if injury_fitness.get("home_injury_count", 0) > 2:
            reasons.append(f"主队伤病人数{injury_fitness['home_injury_count']}，可能低估了主队韧性")
        if injury_fitness.get("away_injury_count", 0) > 2:
            reasons.append(f"客队伤病人数{injury_fitness['away_injury_count']}，可能低估了客队韧性")
        
        # 战术偏差
        tactical = _get_attr_or_key(explanation, "tactical_matchup")
        if abs(tactical.get("total_home_advantage", 0)) > 0.05:
            reasons.append(f"战术相克影响{tactical['total_home_advantage']*100:+.1f}%，实际比赛战术可能调整")
        
        # 补水时刻偏差
        hydration = _get_attr_or_key(explanation, "hydration_impact")
        if actual_home + actual_away < 2:
            reasons.append(f"补水时刻进球影响-5%，实际进球偏少，符合预期")
        elif actual_home + actual_away > 3:
            reasons.append(f"补水时刻进球影响-5%，但实际进球偏多，可能比赛节奏未受补水影响")
        
        # 大小球偏差
        expected_goals = _get_attr_or_key(explanation, "expected_goals")
        expected_total = expected_goals.get("total_expected", 2.8) if isinstance(expected_goals, dict) else 2.8
        actual_total = actual_home + actual_away
        if abs(expected_total - actual_total) > 1:
            reasons.append(f"预期总进球{expected_total:.1f}，实际{actual_total}，偏差{abs(expected_total-actual_total):.1f}球")
        
        # 市场信号偏差
        market = _get_attr_or_key(explanation, "market_signals")
        risk_analysis = _get_attr_or_key(explanation, "risk_analysis")
        if market.get("confidence") == "高" and not (risk_analysis.get("upset", {}) if isinstance(risk_analysis, dict) else {}).get("level") == "高":
            reasons.append("市场信号置信度高，但模型可能忽略了市场隐含信息")
        
        if not reasons:
            reasons.append("无明显偏差因素，预测偏差可能来自随机性")
        
        return reasons
    
    def _analyze_model_deviation(self,
                                  elo_pred: Dict,
                                  poisson_pred: Dict,
                                  mc_pred: Dict,
                                  bayesian_pred: Dict,
                                  actual_result: str,
                                  actual_home: int,
                                  actual_away: int,
                                  prediction_data: Dict) -> Dict:
        """
        深度复盘分析 - 各模型偏差分析
        
        分析每个模型的预测准确性，找出偏差原因
        """
        analysis = {}
        
        # Elo模型分析
        analysis["elo"] = {
            "summary": f"Elo预测: {elo_pred['predicted']} (主胜{elo_pred['home_win_prob']:.1%} 平{elo_pred['draw_prob']:.1%} 客胜{elo_pred['away_win_prob']:.1%})",
            "hit": elo_pred["hit"],
            "deviation": "命中" if elo_pred["hit"] else f"预测{elo_pred['predicted']}，实际{actual_result}",
            "suggestion": "Elo模型表现正常" if elo_pred["hit"] else "建议检查Elo评分更新频率和K值参数",
        }
        
        # 泊松模型分析
        expected_total = poisson_pred["expected_total"]
        actual_total = actual_home + actual_away
        total_deviation = abs(expected_total - actual_total)
        analysis["poisson"] = {
            "summary": f"泊松预测: λ主{poisson_pred['lambda_home']:.2f} λ客{poisson_pred['lambda_away']:.2f} (预期{expected_total:.1f}球)",
            "hit": poisson_pred["hit"],
            "deviation": "命中" if poisson_pred["hit"] else f"预测{poisson_pred['predicted']}，实际{actual_result}",
            "total_deviation": f"预期总进球{expected_total:.1f}，实际{actual_total}，偏差{total_deviation:.1f}球",
            "suggestion": "泊松模型表现正常" if poisson_pred["hit"] and total_deviation < 1 else "建议检查Dixon-Coles参数和动机因子",
        }
        
        # 蒙特卡洛分析
        analysis["mc"] = {
            "summary": f"MC预测: {mc_pred['predicted']} (主胜{mc_pred['home_win_prob']:.1%} 平{mc_pred['draw_prob']:.1%} 客胜{mc_pred['away_win_prob']:.1%})",
            "hit": mc_pred["hit"],
            "deviation": "命中" if mc_pred["hit"] else f"预测{mc_pred['predicted']}，实际{actual_result}",
            "top_score": mc_pred["top_score"],
            "suggestion": "MC模型表现正常" if mc_pred["hit"] else "建议检查模拟次数和泊松参数",
        }
        
        # 贝叶斯融合分析
        analysis["bayesian"] = {
            "summary": f"贝叶斯预测: {bayesian_pred['predicted']} (主胜{bayesian_pred['home_win_prob']:.1%} 平{bayesian_pred['draw_prob']:.1%} 客胜{bayesian_pred['away_win_prob']:.1%})",
            "hit": bayesian_pred["hit"],
            "deviation": "命中" if bayesian_pred["hit"] else f"预测{bayesian_pred['predicted']}，实际{actual_result}",
            "confidence": f"置信度{bayesian_pred['confidence']:.0%}",
            "suggestion": "贝叶斯融合表现正常" if bayesian_pred["hit"] else "建议检查市场赔率权重和模型权重配置",
        }
        
        # 综合分析
        hits = [elo_pred["hit"], poisson_pred["hit"], mc_pred["hit"], bayesian_pred["hit"]]
        hit_count = sum(hits)
        
        if hit_count == 4:
            analysis["overall"] = "所有模型预测一致且命中，模型表现优秀"
        elif hit_count >= 2:
            analysis["overall"] = f"{hit_count}/4模型命中，部分模型预测准确"
        elif hit_count == 1:
            analysis["overall"] = "仅1个模型命中，模型预测存在分歧"
        else:
            analysis["overall"] = "所有模型均未命中，可能存在系统性偏差"
        
        # 异常检测
        anomalies = []
        
        # 检查模型分歧
        predictions = [elo_pred["predicted"], poisson_pred["predicted"], mc_pred["predicted"], bayesian_pred["predicted"]]
        if len(set(predictions)) > 2:
            anomalies.append(f"⚠️ 模型预测分歧：Elo预测{elo_pred['predicted']}，泊松预测{poisson_pred['predicted']}，MC预测{mc_pred['predicted']}，贝叶斯预测{bayesian_pred['predicted']}")
        
        # 检查概率异常
        if abs(elo_pred["home_win_prob"] - mc_pred["home_win_prob"]) > 0.15:
            anomalies.append(f"⚠️ Elo与MC概率差异大：Elo主胜{elo_pred['home_win_prob']:.1%}，MC主胜{mc_pred['home_win_prob']:.1%}")
        
        # 检查置信度异常
        if bayesian_pred["confidence"] < 0.4:
            anomalies.append(f"⚠️ 贝叶斯置信度低（{bayesian_pred['confidence']:.0%}），模型与市场分歧大")
        
        # 检查总进球偏差
        if total_deviation > 1.5:
            anomalies.append(f"⚠️ 总进球偏差大：预期{expected_total:.1f}球，实际{actual_total}球，偏差{total_deviation:.1f}")
        
        analysis["anomalies"] = anomalies
        
        return analysis
    
    def _generate_report(self,
                         match_name: str,
                         actual_score: str,
                         actual_result: str,
                         actual_total: int,
                         predicted_score: str,
                         predicted_result: str,
                         predicted_over_under: str,
                         first_hit: bool,
                         result_hit: bool,
                         over_under_hit: bool,
                         deviation_reasons: List[str]) -> str:
        """生成复盘报告"""
        
        lines = []
        lines.append(f"# {match_name} 复盘报告")
        lines.append(f"\n## 实际结果")
        lines.append(f"- 比分: {actual_score}")
        lines.append(f"- 结果: {actual_result}")
        lines.append(f"- 总进球: {actual_total}")
        
        lines.append(f"\n## 预测结果")
        lines.append(f"- 首选比分: {predicted_score}")
        lines.append(f"- 胜平负方向: {predicted_result}")
        lines.append(f"- 大小球推荐: {predicted_over_under}")
        
        lines.append(f"\n## 命中情况")
        lines.append(f"- 一选命中: {'✅' if first_hit else '❌'}")
        lines.append(f"- 胜平负命中: {'✅' if result_hit else '❌'}")
        lines.append(f"- 大小球命中: {'✅' if over_under_hit else '❌'}")
        
        lines.append(f"\n## 偏差分析")
        for reason in deviation_reasons:
            lines.append(f"- {reason}")
        
        lines.append(f"\n## 模型校正建议")
        if not result_hit:
            lines.append("- 建议检查Elo评分是否需要调整")
            lines.append("- 建议检查伤病影响系数是否合理")
        if not over_under_hit:
            lines.append("- 建议检查λ计算是否需要调整")
            lines.append("- 建议检查补水时刻影响系数")
        
        return "\n".join(lines)
    
    def get_statistics(self) -> Dict:
        """获取统计数据"""
        if not self.history:
            return {"total": 0}
        
        total = len(self.history)
        first_hit_count = sum(1 for r in self.history if r.first_choice_hit)
        second_hit_count = sum(1 for r in self.history if r.second_choice_hit)
        result_hit_count = sum(1 for r in self.history if r.result_hit)
        over_under_hit_count = sum(1 for r in self.history if r.over_under_hit)
        upset_hit_count = sum(1 for r in self.history if r.upset_hit)
        
        # 总进球区间命中
        total_range_hit_count = sum(1 for r in self.history if r.total_range_hit)
        
        # 平均偏差
        avg_score_deviation = sum(r.score_deviation for r in self.history) / total
        avg_total_deviation = sum(r.total_goals_deviation for r in self.history) / total
        
        return {
            "total": total,
            "first_choice_hit_rate": round(first_hit_count / total * 100, 2),
            "second_choice_hit_rate": round(second_hit_count / total * 100, 2),
            "result_hit_rate": round(result_hit_count / total * 100, 2),
            "over_under_hit_rate": round(over_under_hit_count / total * 100, 2),
            "total_range_hit_rate": round(total_range_hit_count / total * 100, 2),
            "upset_hit_rate": round(upset_hit_count / total * 100, 2),
            "avg_score_deviation": round(avg_score_deviation, 2),
            "avg_total_deviation": round(avg_total_deviation, 2),
        }
    
    def save_history(self, filepath: str):
        """保存复盘历史"""
        data = {
            "history": [
                {
                    "match": r.match,
                    "actual_score": r.actual_score,
                    "actual_result": r.actual_result,
                    "actual_total_goals": r.actual_total_goals,
                    "predicted_top_score": r.predicted_top_score,
                    "predicted_result": r.predicted_result,
                    "first_choice_hit": r.first_choice_hit,
                    "result_hit": r.result_hit,
                    "over_under_hit": r.over_under_hit,
                    "deviation_reasons": r.deviation_reasons,
                    "report": r.report,
                }
                for r in self.history
            ],
            "statistics": self.get_statistics(),
            "timestamp": datetime.now().isoformat(),
        }
        
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def load_history(self, filepath: str):
        """加载复盘历史"""
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # 恢复历史记录
            for item in data.get("history", []):
                # 简化恢复（不完整）
                self.history.append(ReviewResult(
                    match=item["match"],
                    actual_score=item["actual_score"],
                    actual_result=item["actual_result"],
                    actual_total_goals=item["actual_total_goals"],
                    predicted_top_score=item["predicted_top_score"],
                    predicted_second_score="",
                    predicted_result=item["predicted_result"],
                    predicted_over_under="",
                    predicted_total_range=(0, 8),
                    first_choice_hit=item["first_choice_hit"],
                    second_choice_hit=False,
                    result_hit=item["result_hit"],
                    over_under_hit=item["over_under_hit"],
                    total_range_hit=False,
                    upset_hit=False,
                    score_deviation=0,
                    result_deviation="",
                    total_goals_deviation=0,
                    deviation_reasons=item.get("deviation_reasons", []),
                    report=item.get("report", ""),
                ))
            
            return True
        except:
            return False