"""
数据清洗管道

功能：
1. 原始数据清洗和标准化
2. 赔率数据格式化
3. 数据整合（worldcup2026 API + 赔率数据 + 天气数据）
4. 数据质量检查
"""

from typing import Dict, List, Optional, Any
from datetime import datetime
import model.elo_engine as elo_engine
import model.poisson as poisson
import model.monte_carlo as monte_carlo
import model.bayesian as bayesian


def clean_odds_data(raw_odds: List[Dict]) -> List[Dict]:
    """
    清洗赔率数据

    - 去除赔率异常（< 1.0 或 > 100）
    - 标准化队名
    - 去除重复
    - 补充隐含概率

    Returns:
        清洗后的赔率列表
    """
    cleaned = []
    seen = set()

    for item in raw_odds:
        home = item.get("home_team", "").strip()
        away = item.get("away_team", "").strip()
        o1 = item.get("odds_home")
        ox = item.get("odds_draw")
        o2 = item.get("odds_away")

        if not home or not away:
            continue
        if o1 is None or ox is None or o2 is None:
            continue

        try:
            o1, ox, o2 = float(o1), float(ox), float(o2)
        except (TypeError, ValueError):
            continue

        # 赔率范围检查
        if not all(1.0 <= o <= 100.0 for o in [o1, ox, o2]):
            continue

        # 去重
        key = (home.lower(), away.lower())
        if key in seen:
            # 保留赔率更精确的那个（有更多市场的）
            existing = next(
                (c for c in cleaned
                 if (c["home_team"].lower(), c["away_team"].lower()) == key), None)
            if existing and item.get("markets") and not existing.get("markets"):
                cleaned.remove(existing)
                seen.discard(key)
            else:
                continue
        seen.add(key)

        # 计算隐含概率
        market_probs = bayesian.calc_market_implied_prob(o1, ox, o2)

        cleaned.append({
            "home_team": home,
            "away_team": away,
            "odds_home": round(o1, 2),
            "odds_draw": round(ox, 2),
            "odds_away": round(o2, 2),
            "market_home": market_probs["home_win"],
            "market_draw": market_probs["draw"],
            "market_away": market_probs["away_win"],
            "source": item.get("source", "unknown"),
            "confidence": item.get("confidence"),
            "markets": item.get("markets", {})
        })

    return cleaned


def format_schedule(api_matches: List[Dict]) -> List[Dict]:
    """
    格式化 API 赛程数据

    Returns:
        [{match_id, home_team, away_team, date, group, venue,
          home_score, away_score, status}, ...]
    """
    formatted = []
    for m in api_matches:
        formatted.append({
            "match_id": m.get("id") or m.get("match_id", ""),
            "home_team": (m.get("homeTeam", {}).get("name", "")
                         if isinstance(m.get("homeTeam"), dict)
                         else m.get("home_team", "")),
            "away_team": (m.get("awayTeam", {}).get("name", "")
                         if isinstance(m.get("awayTeam"), dict)
                         else m.get("away_team", "")),
            "date": m.get("startAt") or m.get("date", ""),
            "group": m.get("group", ""),
            "venue": m.get("venue", {}),
            "home_score": m.get("homeScore", m.get("home_score")),
            "away_score": m.get("awayScore", m.get("away_score")),
            "status": m.get("status", "scheduled"),
        })
    return formatted


def merge_data(api_data: Dict, odds_data: List[Dict],
               elo_engine: elo_engine.EloEngine = None) -> List[Dict]:
    """
    整合所有数据源

    将 API 赛程 + Elo 评分 + 赔率数据 + 模型预测 合并为完整记录

    Args:
        api_data: {teams, matches, standings}
        odds_data: 清洗后的赔率列表
        elo_engine: EloEngine 实例

    Returns:
        完整的比赛预测记录列表
    """
    results = []
    matches = api_data.get("matches", [])
    teams = api_data.get("teams", [])

    # 构建赔率索引
    odds_index = {}
    for o in odds_data:
        key = (o["home_team"].lower(), o["away_team"].lower())
        odds_index[key] = o

    for m in matches:
        home = m.get("home_team", "")
        away = m.get("away_team", "")
        key = (home.lower(), away.lower())

        record = {
            "match_id": m.get("match_id", ""),
            "home_team": home,
            "away_team": away,
            "date": m.get("date", ""),
            "group": m.get("group", ""),
            "stage": _determine_stage(m),
            "status": m.get("status", "scheduled"),
            "home_score": m.get("home_score"),
            "away_score": m.get("away_score"),
        }

        # 赔率数据
        odds = odds_index.get(key)
        if odds:
            record["odds_home"] = odds["odds_home"]
            record["odds_draw"] = odds["odds_draw"]
            record["odds_away"] = odds["odds_away"]
            record["market_probs"] = {
                "home_win": odds["market_home"],
                "draw": odds["market_draw"],
                "away_win": odds["market_away"],
            }
            record["odds_source"] = odds["source"]

        # Elo 评分
        if elo_engine:
            home_id = m.get("home_team_id")
            away_id = m.get("away_team_id")
            home_rating = elo_engine.get_rating(home_id) if home_id else None
            away_rating = elo_engine.get_rating(away_id) if away_id else None
            if home_rating and away_rating:
                record["elo_home"] = round(home_rating, 1)
                record["elo_away"] = round(away_rating, 1)
                exp = elo_engine.simulate_match(home_id, away_id)
                record["model_probs"] = exp

        results.append(record)

    return results


def _determine_stage(match: Dict) -> str:
    """判断比赛阶段"""
    status = match.get("status", "")
    group = match.get("group", "")

    if group and status in ("scheduled", "live") and not match.get("knockout"):
        return "group_stage"
    if match.get("round"):
        r = match["round"].lower()
        if "16" in r or "1/16" in r:
            return "round_of_16"
        if "8" in r or "quarter" in r:
            return "quarter_final"
        if "4" in r or "semi" in r:
            return "semi_final"
        if "final" in r:
            return "final"

    return "group_stage"


def quality_check(data: List[Dict]) -> Dict[str, Any]:
    """
    数据质量检查

    Returns:
        {"total": int, "with_odds": int, "with_elo": int,
         "issues": [...]}
    """
    total = len(data)
    with_odds = sum(1 for d in data if d.get("odds_home"))
    with_elo = sum(1 for d in data if d.get("elo_home"))
    issues = []

    if total == 0:
        issues.append("没有比赛数据")
    if with_odds < total * 0.5:
        issues.append(f"赔率覆盖不足：{with_odds}/{total}")

    return {
        "total": total,
        "with_odds": with_odds,
        "with_elo": with_elo,
        "odds_coverage": f"{with_odds / total * 100:.1f}%" if total else "0%",
        "issues": issues,
        "healthy": len(issues) == 0
    }
