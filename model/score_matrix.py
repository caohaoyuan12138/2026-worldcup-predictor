"""
比分矩阵模块 - 0-8球比分概率矩阵

生成完整的比分概率矩阵，用于：
- 比分池分析
- 大小球预测
- 风险评估
"""

import math
from typing import List, Dict, Tuple
from scipy.stats import poisson


def generate_score_matrix(lambda_home: float, lambda_away: float, 
                          max_goals: int = 8) -> List[List[float]]:
    """
    生成0-8球比分概率矩阵
    
    Args:
        lambda_home: 主队期望进球
        lambda_away: 客队期望进球
        max_goals: 最大进球数（默认8）
    
    Returns:
        9x9矩阵，matrix[i][j] = 主队i球、客队j球的概率
    """
    matrix = []
    
    for i in range(max_goals + 1):
        row = []
        for j in range(max_goals + 1):
            # 泊松分布概率
            prob_home = poisson.pmf(i, lambda_home)
            prob_away = poisson.pmf(j, lambda_away)
            
            # 独立事件，联合概率
            prob = prob_home * prob_away * 100  # 转换为百分比
            row.append(round(prob, 2))
        matrix.append(row)
    
    return matrix


def analyze_matrix(matrix: List[List[float]]) -> Dict:
    """
    分析比分矩阵
    
    Returns:
        {
            "home_win_prob": 主胜总概率,
            "draw_prob": 平局总概率,
            "away_win_prob": 客胜总概率,
            "top_scores": 最可能比分列表,
            "over_2_5_prob": 大2.5球概率,
            "under_2_5_prob": 小2.5球概率,
            "btts_prob": 双方进球概率,
            "clean_sheet_home": 主队零封概率,
            "clean_sheet_away": 客队零封概率,
        }
    """
    home_win_prob = 0
    draw_prob = 0
    away_win_prob = 0
    over_2_5_prob = 0
    under_2_5_prob = 0
    btts_prob = 0
    clean_sheet_home = 0
    clean_sheet_away = 0
    
    scores = []
    
    for i in range(len(matrix)):
        for j in range(len(matrix[i])):
            prob = matrix[i][j]
            
            # 胜平负分类
            if i > j:
                home_win_prob += prob
            elif i == j:
                draw_prob += prob
            else:
                away_win_prob += prob
            
            # 大小球分类
            total = i + j
            if total > 2.5:
                over_2_5_prob += prob
            else:
                under_2_5_prob += prob
            
            # 双方进球
            if i > 0 and j > 0:
                btts_prob += prob
            
            # 零封
            if j == 0:
                clean_sheet_home += prob
            if i == 0:
                clean_sheet_away += prob
            
            # 收集比分
            scores.append({"score": f"{i}-{j}", "probability": prob})
    
    # 排序比分
    scores.sort(key=lambda x: x["probability"], reverse=True)
    
    return {
        "home_win_prob": round(home_win_prob, 2),
        "draw_prob": round(draw_prob, 2),
        "away_win_prob": round(away_win_prob, 2),
        "top_scores": scores[:10],
        "over_2_5_prob": round(over_2_5_prob, 2),
        "under_2_5_prob": round(under_2_5_prob, 2),
        "btts_prob": round(btts_prob, 2),
        "clean_sheet_home": round(clean_sheet_home, 2),
        "clean_sheet_away": round(clean_sheet_away, 2),
    }


def format_matrix_display(matrix: List[List[float]]) -> str:
    """
    格式化矩阵显示
    
    Returns:
        表格形式的字符串
    """
    lines = []
    
    # 标题行
    header = "     " + "  ".join([f"{j:>5}" for j in range(len(matrix[0]))])
    lines.append(header)
    lines.append("     " + "-" * (len(matrix[0]) * 6))
    
    # 数据行
    for i in range(len(matrix)):
        row_str = f"{i:>2} | " + "  ".join([f"{p:>5.1f}" for p in matrix[i]])
        lines.append(row_str)
    
    return "\n".join(lines)


def get_score_distribution(matrix: List[List[float]]) -> Dict:
    """
    获取进球分布
    
    Returns:
        {
            "home_goals_distribution": [0球概率, 1球概率, ...],
            "away_goals_distribution": [0球概率, 1球概率, ...],
            "total_goals_distribution": [0球概率, 1球概率, ...],
        }
    """
    n = len(matrix)
    
    # 主队进球分布
    home_dist = []
    for i in range(n):
        prob = sum(matrix[i])
        home_dist.append(round(prob, 2))
    
    # 客队进球分布
    away_dist = []
    for j in range(n):
        prob = sum([matrix[i][j] for i in range(n)])
        away_dist.append(round(prob, 2))
    
    # 总进球分布
    total_dist = []
    for t in range(n * 2):
        prob = 0
        for i in range(n):
            for j in range(n):
                if i + j == t:
                    prob += matrix[i][j]
        total_dist.append(round(prob, 2))
    
    return {
        "home_goals_distribution": home_dist,
        "away_goals_distribution": away_dist,
        "total_goals_distribution": total_dist[:9],  # 只保留0-8球
    }


def calculate_exact_score_prob(matrix: List[List[float]], 
                                home_goals: int, away_goals: int) -> float:
    """
    计算特定比分的概率
    
    Args:
        matrix: 比分矩阵
        home_goals: 主队进球数
        away_goals: 客队进球数
    
    Returns:
        该比分的概率（百分比）
    """
    if home_goals >= len(matrix) or away_goals >= len(matrix[0]):
        return 0.0
    
    return matrix[home_goals][away_goals]


def get_most_likely_score_range(matrix: List[List[float]]) -> Dict:
    """
    获取最可能的比分范围
    
    Returns:
        {
            "home_range": (min, max),
            "away_range": (min, max),
            "total_range": (min, max),
        }
    """
    analysis = analyze_matrix(matrix)
    top_scores = analysis["top_scores"][:5]
    
    home_goals = [int(s["score"].split("-")[0]) for s in top_scores]
    away_goals = [int(s["score"].split("-")[1]) for s in top_scores]
    total_goals = [int(s["score"].split("-")[0]) + int(s["score"].split("-")[1]) for s in top_scores]
    
    return {
        "home_range": (min(home_goals), max(home_goals)),
        "away_range": (min(away_goals), max(away_goals)),
        "total_range": (min(total_goals), max(total_goals)),
    }


# 测试
if __name__ == "__main__":
    # 测试生成矩阵
    lambda_home = 2.13
    lambda_away = 0.82
    
    matrix = generate_score_matrix(lambda_home, lambda_away)
    
    print("=== 0-8球比分矩阵 ===")
    print(format_matrix_display(matrix))
    
    print("\n=== 矩阵分析 ===")
    analysis = analyze_matrix(matrix)
    print(f"主胜概率: {analysis['home_win_prob']}%")
    print(f"平局概率: {analysis['draw_prob']}%")
    print(f"客胜概率: {analysis['away_win_prob']}%")
    print(f"大2.5球: {analysis['over_2_5_prob']}%")
    print(f"小2.5球: {analysis['under_2_5_prob']}%")
    print(f"双方进球: {analysis['btts_prob']}%")
    
    print("\n=== 最可能比分 ===")
    for s in analysis["top_scores"][:5]:
        print(f"{s['score']}: {s['probability']}%")