#!/usr/bin/env python3
"""
批量复盘分析脚本 - 对已完赛比赛进行复盘
独立运行，不依赖 Streamlit
"""

import json
import os
import sys
from datetime import datetime

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from model.elo_engine import EloEngine
from model.review import ReviewEngine

# 球队元数据（中文名 -> ID, FIFA代码, 洲际, 排名）
TEAM = {
    "墨西哥": (1, "MEX", "CONCACAF", 12), "捷克": (2, "CZE", "UEFA", 35),
    "南非": (3, "RSA", "CAF", 60), "韩国": (4, "KOR", "AFC", 28),
    "加拿大": (5, "CAN", "CONCACAF", 45), "波黑": (6, "BIH", "UEFA", 70),
    "卡塔尔": (7, "QAT", "AFC", 55), "瑞士": (8, "SUI", "UEFA", 25),
    "巴西": (9, "BRA", "CONMEBOL", 3), "摩洛哥": (10, "MAR", "CAF", 18),
    "海地": (11, "HAI", "CONCACAF", 80), "苏格兰": (12, "SCO", "UEFA", 30),
    "美国": (13, "USA", "CONCACAF", 15), "土耳其": (14, "TUR", "UEFA", 24),
    "巴拉圭": (15, "PAR", "CONMEBOL", 22), "澳大利亚": (16, "AUS", "AFC", 38),
    "德国": (17, "GER", "UEFA", 6), "库拉索": (18, "CUW", "CONCACAF", 99),
    "科特迪瓦": (19, "CIV", "CAF", 42), "厄瓜多尔": (20, "ECU", "CONMEBOL", 44),
    "荷兰": (21, "NED", "UEFA", 7), "瑞典": (22, "SWE", "UEFA", 27),
    "日本": (23, "JPN", "AFC", 20), "突尼斯": (24, "TUN", "CAF", 75),
    "比利时": (25, "BEL", "UEFA", 14), "埃及": (26, "EGY", "CAF", 36),
    "伊朗": (27, "IRN", "AFC", 23), "新西兰": (28, "NZL", "OFC", 56),
    "西班牙": (29, "ESP", "UEFA", 4), "佛得角": (30, "CPV", "CAF", 64),
    "沙特阿拉伯": (31, "KSA", "AFC", 48), "乌拉圭": (32, "URU", "CONMEBOL", 8),
    "法国": (33, "FRA", "UEFA", 2), "伊拉克": (34, "IRQ", "AFC", 72),
    "塞内加尔": (35, "SEN", "CAF", 16), "挪威": (36, "NOR", "UEFA", 41),
    "阿根廷": (37, "ARG", "CONMEBOL", 1), "阿尔及利亚": (38, "ALG", "CAF", 58),
    "奥地利": (39, "AUT", "UEFA", 29), "约旦": (40, "JOR", "AFC", 68),
    "葡萄牙": (41, "POR", "UEFA", 5), "刚果民主共和国": (42, "COD", "CAF", 67),
    "乌兹别克斯坦": (43, "UZB", "AFC", 88), "哥伦比亚": (44, "COL", "CONMEBOL", 21),
    "英格兰": (45, "ENG", "UEFA", 9), "克罗地亚": (46, "CRO", "UEFA", 10),
    "加纳": (47, "GHA", "CAF", 65), "巴拿马": (48, "PAN", "CONCACAF", 49),
}

# 东道主
HOST_TEAM_IDS = [1, 13, 5]
# 卫冕冠军
DEFENDING_CHAMPION_CODE = "FRA"


def build_elo_engine(schedule):
    """根据赛程构建 Elo 引擎"""
    engine = EloEngine()
    for cn_, (tid, code, cont, rank) in TEAM.items():
        is_host = tid in HOST_TEAM_IDS
        engine.set_team(tid, cn_, "", fifa_rank=rank, continent=cont,
                        is_defending_champion=(code == DEFENDING_CHAMPION_CODE),
                        is_host_nation=is_host)

    # 更新已完赛比赛
    for m in schedule:
        if m.get("match_des") != "完赛":
            continue
        hg = m.get("host_team_score")
        ag = m.get("guest_team_score")
        if hg is None or ag is None:
            continue
        try:
            hg, ag = int(hg), int(ag)
        except (ValueError, TypeError):
            continue
        hid = m.get("host_team_id")
        aid = m.get("guest_team_id")
        if hid and aid:
            try:
                stage = "group_stage"
                engine.update_after_match(int(hid), int(aid), hg, ag, stage=stage)
            except Exception:
                pass
    return engine


def detect_stage_and_knockout(match):
    """检测比赛阶段"""
    match_type = match.get("match_type_name", "")
    if "小组赛" in match_type:
        return "group_stage", False
    elif "1/16" in match_type:
        return "round_of_16", True
    elif "1/8" in match_type:
        return "quarter_final", True
    elif "1/4" in match_type:
        return "quarter_final", True
    elif "半决赛" in match_type:
        return "semi_final", True
    elif "决赛" in match_type:
        return "final", True
    return "group_stage", False


def do_analysis_simple(hid, aid, engine, hn, an, stage):
    """简化的分析函数 - 只获取核心数据用于复盘"""
    result = {
        "_home_name": hn,
        "_away_name": an,
    }

    # Elo
    eh = engine.get_rating(hid) if hid in engine.teams else 1500
    ea = engine.get_rating(aid) if aid in engine.teams else 1500
    if hid in engine.teams:
        eh_adj = engine.teams[hid].get_adjusted_rating(engine.teams.get(aid), True)
    else:
        eh_adj = eh
    if aid in engine.teams:
        ea_adj = engine.teams[aid].get_adjusted_rating(engine.teams.get(hid), False)
    else:
        ea_adj = ea

    if hid and aid and hid in engine.teams and aid in engine.teams:
        exp = engine.simulate_match(hid, aid)
    else:
        exp = {"home_win": 0.33, "draw": 0.34, "away_win": 0.33}

    result["elo"] = {
        "home_rating": round(eh, 0),
        "away_rating": round(ea, 0),
        "diff": int(round(eh - ea)),
        "home_win": exp["home_win"],
        "draw": exp["draw"],
        "away_win": exp["away_win"],
    }

    # 简化的泊松
    result["poisson"] = {
        "lambda_home": 1.3,
        "lambda_away": 1.0,
    }

    # 简化的蒙特卡洛
    result["monte_carlo"] = {
        "home_win": exp["home_win"],
        "draw": exp["draw"],
        "away_win": exp["away_win"],
        "top_scorelines": [{"score": "1-0", "probability": 15.0}],
    }

    result["prediction"] = "分析完成"
    result["prediction_reasoning"] = ""
    result["environment"] = {"temperature": 22, "altitude": 0}
    result["bayesian"] = None
    result["bsd_odds"] = None
    result["extra"] = None
    result["explanation"] = None

    return result


def main():
    # 加载数据
    data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data_local")

    with open(os.path.join(data_dir, "schedule.json"), "r", encoding="utf-8") as f:
        schedule = json.load(f)

    # 加载已有复盘结果
    review_file = os.path.join(data_dir, "review_results.json")
    if os.path.exists(review_file):
        with open(review_file, "r", encoding="utf-8") as f:
            existing_reviews = json.load(f)
        done_ids = {r["match_id"] for r in existing_reviews}
    else:
        existing_reviews = []
        done_ids = set()

    # 筛选已完赛比赛
    finished = [m for m in schedule if m.get("match_des") == "完赛"]
    todo = [m for m in finished if m.get("id") not in done_ids]

    print(f"已完赛比赛: {len(finished)}, 已完成复盘: {len(done_ids)}, 待复盘: {len(todo)}")

    if not todo:
        print("所有已完赛比赛已完成复盘！")
        return

    # 构建 Elo 引擎
    engine = build_elo_engine(schedule)

    # 初始化复盘引擎
    review_engine = ReviewEngine()

    # 批量复盘
    results = list(existing_reviews)
    errors = 0

    for i, m in enumerate(todo, 1):
        mid = m.get("id", "")
        hn = m.get("host_team_name", "?")
        an = m.get("guest_team_name", "?")
        hs = m.get("host_team_score", "")
        gs = m.get("guest_team_score", "")

        try:
            hg = int(hs)
            ag = int(gs)
        except (ValueError, TypeError):
            print(f"  [{i}/{len(todo)}] 跳过 {hn} vs {an} - 比分无效")
            errors += 1
            continue

        hid = m.get("host_team_id")
        aid = m.get("guest_team_id")

        if not hid or not aid:
            print(f"  [{i}/{len(todo)}] 跳过 {hn} vs {an} - ID缺失")
            errors += 1
            continue

        try:
            hid, aid = int(hid), int(aid)
        except (ValueError, TypeError):
            print(f"  [{i}/{len(todo)}] 跳过 {hn} vs {an} - ID无效")
            errors += 1
            continue

        # 获取预测数据
        stage, is_ko = detect_stage_and_knockout(m)
        prediction = do_analysis_simple(hid, aid, engine, hn, an, stage)

        # 复盘
        review = review_engine.review_match(
            f"{hn} vs {an}",
            hg, ag,
            prediction
        )

        # 保存结果
        result_dict = {
            "match_id": mid,
            "match_name": f"{hn} vs {an}",
            "actual_score": f"{hg}-{ag}",
            "actual_result": review.actual_result,
            "predicted_top_score": review.predicted_top_score,
            "predicted_result": review.predicted_result,
            "first_choice_hit": review.first_choice_hit,
            "second_choice_hit": review.second_choice_hit,
            "result_hit": review.result_hit,
            "over_under_hit": review.over_under_hit,
            "total_range_hit": review.total_range_hit,
            "upset_hit": review.upset_hit,
            "elo_hit": review.elo_hit,
            "poisson_hit": review.poisson_hit,
            "mc_hit": review.mc_hit,
            "bayesian_hit": review.bayesian_hit,
            "score_deviation": review.score_deviation,
            "total_goals_deviation": review.total_goals_deviation,
            "deviation_reasons": review.deviation_reasons,
            "reviewed_at": datetime.now().isoformat(),
        }
        results.append(result_dict)

        status = "[OK]" if review.result_hit else "[FAIL]"
        print(f"  [{i}/{len(todo)}] {status} {hn} {hg}:{ag} {an} | 预测: {review.predicted_result}")

        # 每10场保存一次
        if i % 10 == 0:
            with open(review_file, "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            print(f"  --- saved {len(results)} results ---")

    # 最终保存
    with open(review_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    # 统计
    total = len(results)
    result_hits = sum(1 for r in results if r["result_hit"])
    first_hits = sum(1 for r in results if r["first_choice_hit"])
    elo_hits = sum(1 for r in results if r["elo_hit"])
    mc_hits = sum(1 for r in results if r["mc_hit"])

    print(f"\n=== 复盘完成 ===")
    print(f"Total: {total}")
    print(f"Direction: {result_hits}/{total} ({result_hits/total*100:.1f}%)")
    print(f"1st choice: {first_hits}/{total} ({first_hits/total*100:.1f}%)")
    print(f"Elo: {elo_hits}/{total} ({elo_hits/total*100:.1f}%)")
    print(f"MC: {mc_hits}/{total} ({mc_hits/total*100:.1f}%)")
    print(f"Errors: {errors}")
    print(f"Saved to: {review_file}")


if __name__ == "__main__":
    main()
