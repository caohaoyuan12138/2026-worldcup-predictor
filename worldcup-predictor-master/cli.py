"""
World Cup Predictor CLI

命令行工具，供其他AI工具调用

命令：
- predict: 预测单场比赛
- batch: 批量预测多场比赛
- odds: 获取实时赔率
- injuries: 获取伤病名单
- news: 获取新闻
- team: 查看球队信息
- serve: 启动Web服务
- api: 启动HTTP API服务
"""

import argparse
import json
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
import model.elo_engine as elo
import model.poisson as poisson
import model.monte_carlo as mc
import model.bayesian as bayesian
import model.llm_analyzer as llm_analyzer
import data.local_data as ld
import data.bsd_api as bsd
import data.news_api as news


# 球队数据
TEAMS = {
    "西班牙": {"id": 29, "elo": 1840, "fifa_ranking": 4, "eng": "Spain"},
    "沙特阿拉伯": {"id": 31, "elo": 1550, "fifa_ranking": 48, "eng": "Saudi Arabia"},
    "沙特": {"id": 31, "elo": 1550, "fifa_ranking": 48, "eng": "Saudi Arabia"},
    "比利时": {"id": 25, "elo": 1800, "fifa_ranking": 14, "eng": "Belgium"},
    "伊朗": {"id": 27, "elo": 1720, "fifa_ranking": 23, "eng": "Iran"},
    "乌拉圭": {"id": 32, "elo": 1660, "fifa_ranking": 8, "eng": "Uruguay"},
    "佛得角": {"id": 30, "elo": 1770, "fifa_ranking": 64, "eng": "Cape Verde"},
    "新西兰": {"id": 28, "elo": 1540, "fifa_ranking": 56, "eng": "New Zealand"},
    "埃及": {"id": 26, "elo": 1790, "fifa_ranking": 36, "eng": "Egypt"},
    "巴西": {"id": 33, "elo": 1850, "fifa_ranking": 5, "eng": "Brazil"},
    "阿根廷": {"id": 34, "elo": 1870, "fifa_ranking": 1, "eng": "Argentina"},
    "法国": {"id": 35, "elo": 1860, "fifa_ranking": 2, "eng": "France"},
    "英格兰": {"id": 36, "elo": 1810, "fifa_ranking": 3, "eng": "England"},
    "德国": {"id": 37, "elo": 1780, "fifa_ranking": 12, "eng": "Germany"},
    "荷兰": {"id": 38, "elo": 1795, "fifa_ranking": 7, "eng": "Netherlands"},
    "葡萄牙": {"id": 39, "elo": 1820, "fifa_ranking": 6, "eng": "Portugal"},
    "日本": {"id": 40, "elo": 1700, "fifa_ranking": 18, "eng": "Japan"},
    "韩国": {"id": 41, "elo": 1680, "fifa_ranking": 22, "eng": "South Korea"},
    "墨西哥": {"id": 42, "elo": 1650, "fifa_ranking": 15, "eng": "Mexico"},
    "美国": {"id": 43, "elo": 1690, "fifa_ranking": 13, "eng": "USA"},
    "加拿大": {"id": 44, "elo": 1600, "fifa_ranking": 41, "eng": "Canada"},
    "澳大利亚": {"id": 45, "elo": 1620, "fifa_ranking": 32, "eng": "Australia"},
    "克罗地亚": {"id": 46, "elo": 1750, "fifa_ranking": 10, "eng": "Croatia"},
    "瑞士": {"id": 47, "elo": 1730, "fifa_ranking": 11, "eng": "Switzerland"},
    "塞内加尔": {"id": 48, "elo": 1710, "fifa_ranking": 17, "eng": "Senegal"},
}


def elo_predict(home_elo, away_elo):
    """基于Elo评分计算胜率"""
    diff = home_elo - away_elo
    home_advantage = 100
    adjusted_diff = diff + home_advantage
    
    home_win = 1 / (1 + 10**(-adjusted_diff/400))
    away_win = 1 / (1 + 10**(adjusted_diff/400))
    draw = 1 - home_win - away_win
    
    if draw < 0.15:
        draw = 0.15
        total = home_win + away_win + draw
        home_win = home_win / total
        away_win = away_win / total
        draw = draw / total
    
    return {"home_win": home_win, "draw": draw, "away_win": away_win}


def calc_lambda_from_elo(home_elo, away_elo):
    """根据Elo评分计算期望进球"""
    diff = home_elo - away_elo
    base_lambda = 1.4
    elo_effect = diff / 500
    home_bonus = 0.15
    
    lambda_home = base_lambda + elo_effect + home_bonus
    lambda_away = base_lambda - elo_effect
    
    lambda_home = max(0.5, min(3.0, lambda_home))
    lambda_away = max(0.3, min(2.5, lambda_away))
    
    return lambda_home, lambda_away


def predict_match(home, away, odds_home=None, odds_draw=None, odds_away=None, use_llm=False):
    """预测单场比赛"""
    
    # 查找球队
    home_data = TEAMS.get(home) or TEAMS.get(home.replace("阿拉伯", ""))
    away_data = TEAMS.get(away) or TEAMS.get(away.replace("阿拉伯", ""))
    
    if not home_data:
        return {"error": f"球队 '{home}' 未找到"}
    if not away_data:
        return {"error": f"球队 '{away}' 未找到"}
    
    home_elo = home_data["elo"]
    away_elo = away_data["elo"]
    elo_diff = home_elo - away_elo
    
    # Elo预测
    elo_probs = elo_predict(home_elo, away_elo)
    
    # 期望进球
    lh, la = calc_lambda_from_elo(home_elo, away_elo)
    
    # 蒙特卡洛模拟
    env = mc.MatchEnvironment(
        home_team_id=home_data["id"],
        away_team_id=away_data["id"],
        temperature=22, venue_altitude=0, is_rain=False,
        timezone_diff_hours=0, is_water_break=False, is_high_stakes=True,
        home_tactical_style="balanced", away_tactical_style="balanced"
    )
    
    sim = mc.Simulator(n_sim=50000).run_detailed(lh, la, env, is_knockout=False)
    
    mc_probs = {
        "home_win": sim["home_win"],
        "draw": sim["draw"],
        "away_win": sim["away_win"],
    }
    
    # 市场赔率
    market_probs = None
    posterior_probs = None
    
    if odds_home and odds_draw and odds_away:
        market_probs = bayesian.calc_market_implied_prob(odds_home, odds_draw, odds_away)
        prior = elo_probs
        posterior_probs = bayesian.bayesian_fusion(prior, market_probs)
    
    # 综合预测
    if posterior_probs:
        final_hw = (posterior_probs["home_win"] + mc_probs["home_win"] + elo_probs["home_win"]) / 3
        final_dr = (posterior_probs["draw"] + mc_probs["draw"] + elo_probs["draw"]) / 3
        final_aw = (posterior_probs["away_win"] + mc_probs["away_win"] + elo_probs["away_win"]) / 3
    else:
        final_hw = (mc_probs["home_win"] + elo_probs["home_win"]) / 2
        final_dr = (mc_probs["draw"] + elo_probs["draw"]) / 2
        final_aw = (mc_probs["away_win"] + elo_probs["away_win"]) / 2
    
    # 判断胜负
    if final_hw > 0.50:
        prediction = f"主胜（{home}）"
        confidence = final_hw
    elif final_aw > 0.50:
        prediction = f"客胜（{away}）"
        confidence = final_aw
    elif final_hw > final_aw + 0.10:
        prediction = f"主胜偏（{home}）"
        confidence = final_hw
    elif final_aw > final_hw + 0.10:
        prediction = f"客胜偏（{away}）"
        confidence = final_aw
    else:
        prediction = "平局"
        confidence = final_dr
    
    # 最可能比分
    top_scores = sim.get("top_scorelines", [])[:5]
    
    result = {
        "match": f"{home} vs {away}",
        "elo_diff": elo_diff,
        "elo_probs": elo_probs,
        "lambda_home": round(lh, 3),
        "lambda_away": round(la, 3),
        "mc_probs": mc_probs,
        "market_probs": market_probs,
        "posterior_probs": posterior_probs,
        "top_scores": top_scores,
        "prediction": prediction,
        "confidence": round(confidence, 3),
    }
    
    # 大模型增强（可选）
    if use_llm and llm_analyzer.LLM_CONFIG.get("api_key"):
        elo_data = {
            "home_rating": home_elo,
            "away_rating": away_elo,
            "diff": elo_diff,
            "home_fifa_rank": home_data["fifa_ranking"],
            "away_fifa_rank": away_data["fifa_ranking"],
        }
        
        odds_data = {
            "average_home": odds_home or "?",
            "average_draw": odds_draw or "?",
            "average_away": odds_away or "?",
        }
        
        injury_data = {"home_summary": "", "away_summary": ""}
        news_data = []
        report_data = {"home_report": "", "away_report": ""}
        
        llm_analysis = llm_analyzer.generate_match_analysis(
            home, away, elo_data, odds_data, injury_data, news_data, report_data
        )
        result["llm_analysis"] = llm_analysis
    
    return result


def cmd_predict(args):
    """predict命令"""
    result = predict_match(
        args.home,
        args.away,
        args.odds_home,
        args.odds_draw,
        args.odds_away,
        args.use_llm
    )
    
    print(json.dumps(result, indent=2, ensure_ascii=False))


def cmd_odds(args):
    """odds命令"""
    if not bsd.is_bsd_available():
        print(json.dumps({"error": "未配置BSD API Key"}, ensure_ascii=False))
        return
    
    home = args.home
    away = args.away
    
    # 转换为英文
    home_eng = TEAMS.get(home, {}).get("eng", home)
    away_eng = TEAMS.get(away, {}).get("eng", away)
    
    odds = bsd.get_best_odds(home_eng, away_eng)
    print(json.dumps(odds, indent=2, ensure_ascii=False))


def cmd_injuries(args):
    """injuries命令"""
    team = args.team
    injuries = news.get_team_injuries_from_wiki(team)
    print(json.dumps(injuries, indent=2, ensure_ascii=False))


def cmd_news(args):
    """news命令"""
    team = args.team
    team_news = news.get_team_news(team, limit=args.limit)
    
    result = {
        "team": team,
        "news": team_news,
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))


def cmd_team(args):
    """team命令"""
    team = args.name
    team_data = TEAMS.get(team) or TEAMS.get(team.replace("阿拉伯", ""))
    
    if not team_data:
        print(json.dumps({"error": f"球队 '{team}' 未找到"}, ensure_ascii=False))
        return
    
    # 获取伤病信息
    injuries = news.get_team_injuries_from_wiki(team)
    
    result = {
        "name": team,
        "elo": team_data["elo"],
        "fifa_ranking": team_data["fifa_ranking"],
        "injuries": injuries,
    }
    
    print(json.dumps(result, indent=2, ensure_ascii=False))


def cmd_teams(args):
    """teams命令"""
    result = {
        "teams": [{"name": k, "elo": v["elo"], "fifa_ranking": v["fifa_ranking"]} 
                  for k, v in TEAMS.items()],
        "total": len(TEAMS),
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description="World Cup Predictor CLI")
    subparsers = parser.add_subparsers(dest="command")
    
    # predict命令
    predict_parser = subparsers.add_parser("predict", help="预测比赛")
    predict_parser.add_argument("--home", required=True, help="主队名")
    predict_parser.add_argument("--away", required=True, help="客队名")
    predict_parser.add_argument("--odds-home", type=float, help="主胜赔率")
    predict_parser.add_argument("--odds-draw", type=float, help="平局赔率")
    predict_parser.add_argument("--odds-away", type=float, help="客胜赔率")
    predict_parser.add_argument("--use-llm", action="store_true", help="使用大模型增强")
    predict_parser.set_defaults(func=cmd_predict)
    
    # odds命令
    odds_parser = subparsers.add_parser("odds", help="获取实时赔率")
    odds_parser.add_argument("--home", required=True, help="主队名")
    odds_parser.add_argument("--away", required=True, help="客队名")
    odds_parser.set_defaults(func=cmd_odds)
    
    # injuries命令
    injuries_parser = subparsers.add_parser("injuries", help="获取伤病名单")
    injuries_parser.add_argument("--team", required=True, help="球队名")
    injuries_parser.set_defaults(func=cmd_injuries)
    
    # news命令
    news_parser = subparsers.add_parser("news", help="获取新闻")
    news_parser.add_argument("--team", required=True, help="球队名")
    news_parser.add_argument("--limit", type=int, default=5, help="新闻数量")
    news_parser.set_defaults(func=cmd_news)
    
    # team命令
    team_parser = subparsers.add_parser("team", help="查看球队信息")
    team_parser.add_argument("--name", required=True, help="球队名")
    team_parser.set_defaults(func=cmd_team)
    
    # teams命令
    teams_parser = subparsers.add_parser("teams", help="查看所有球队")
    teams_parser.set_defaults(func=cmd_teams)
    
    args = parser.parse_args()
    
    if args.command:
        args.func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()