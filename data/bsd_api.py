"""
Bzzoiro Sports Data (BSD) API 客户端

免费足球实时数据API，提供：
- 伤病/停赛/疑伤球员列表 (unavailable_players)
- 官方阵容 (赛前1小时自动获取)
- 教练战术信息 (阵型、胜率、xG)
- 多博彩公司赔率对比 (17+ bookmakers)
- ML预测 (CatBoost ensemble)
- 实时比分 (30秒刷新)

API文档: https://sports.bzzoiro.com/docs/football/
"""

import requests
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import time

# 尝试导入streamlit（如果可用则使用缓存）
try:
    import streamlit as st
    HAS_STREAMLIT = True
except ImportError:
    HAS_STREAMLIT = False

# 缓存装饰器（兼容非Streamlit环境）
def cache_data(ttl=300, show_spinner=False):
    def decorator(func):
        if HAS_STREAMLIT:
            return st.cache_data(ttl=ttl, show_spinner=show_spinner)(func)
        else:
            # 简单的内存缓存
            cache = {}
            last_call = {}
            def wrapper(*args, **kwargs):
                key = str(args) + str(kwargs)
                now = datetime.now()
                if key in cache and key in last_call:
                    if (now - last_call[key]).total_seconds() < ttl:
                        return cache[key]
                result = func(*args, **kwargs)
                cache[key] = result
                last_call[key] = now
                return result
            return wrapper
    return decorator

# BSD API配置
BSD_API_BASE = "https://sports.bzzoiro.com/api"
BSD_API_KEY = "e26606d78375f28b58a121ba421d1682ebe27d0d"  # 已配置的API Key


@cache_data(ttl=300, show_spinner=False)
def get_bsd_events(team_name: str = None, date: str = None, limit: int = 20) -> List[Dict]:
    """
    获取比赛事件列表
    
    Args:
        team_name: 球队名称（可选，用于筛选）
        date: 日期 YYYY-MM-DD（可选）
        limit: 返回数量限制
    
    Returns:
        比赛事件列表，每个事件包含：
        - home_team, away_team: 球队名
        - odds_home, odds_draw, odds_away: 赔率
        - unavailable_players: 伤病/停赛球员
        - home_coach, away_coach: 教练信息
        - lineups: 阵容（赛前1小时）
        - ml_predictions: ML预测
    """
    if not BSD_API_KEY:
        return []
    
    headers = {"Authorization": f"Token {BSD_API_KEY}"}
    
    try:
        params = {"limit": limit}
        if date:
            params["date"] = date
        
        r = requests.get(f"{BSD_API_BASE}/events/", headers=headers, params=params, timeout=10)
        
        if r.status_code != 200:
            st.warning(f"BSD API返回状态码: {r.status_code}")
            return []
        
        data = r.json()
        events = data.get("results", [])
        
        # 如果指定球队名，筛选相关比赛
        if team_name:
            events = [e for e in events if 
                      team_name.lower() in e.get("home_team", "").lower() or 
                      team_name.lower() in e.get("away_team", "").lower()]
        
        return events
        
    except requests.exceptions.Timeout:
        st.warning("BSD API请求超时")
        return []
    except requests.exceptions.ConnectionError:
        st.warning("BSD API连接失败")
        return []
    except Exception as e:
        st.warning(f"BSD API错误: {str(e)[:50]}")
        return []


@cache_data(ttl=300, show_spinner=False)
def get_team_injuries(team_name: str) -> Dict:
    """
    获取球队伤病/停赛信息
    
    Args:
        team_name: 球队名称
    
    Returns:
        {
            "injured": [{"name": "梅西", "reason": "膝盖伤病", "status": "out"}, ...],
            "suspended": [{"name": "罗霍", "reason": "红牌停赛", "status": "suspended"}, ...],
            "doubtful": [{"name": "阿圭罗", "reason": "轻伤", "status": "doubtful"}, ...],
            "summary": "伤病情况摘要"
        }
    """
    if not BSD_API_KEY:
        return {"injured": [], "suspended": [], "doubtful": [], "summary": "未配置BSD API Key"}
    
    # 获取该球队最近的比赛事件
    events = get_bsd_events(team_name=team_name, limit=5)
    
    if not events:
        return {"injured": [], "suspended": [], "doubtful": [], 
                "summary": f"未找到 {team_name} 的比赛数据"}
    
    # 从最近的比赛中提取 unavailable_players
    result = {"injured": [], "suspended": [], "doubtful": [], "summary": ""}
    
    for event in events:
        unavailable = event.get("unavailable_players", {})
        
        # 主队伤病
        if team_name.lower() in event.get("home_team", "").lower():
            home_unavail = unavailable.get("home", [])
            for p in home_unavail:
                status = p.get("status", "unknown")
                if status == "injured":
                    result["injured"].append(p)
                elif status == "suspended":
                    result["suspended"].append(p)
                elif status == "doubtful":
                    result["doubtful"].append(p)
        
        # 客队伤病
        if team_name.lower() in event.get("away_team", "").lower():
            away_unavail = unavailable.get("away", [])
            for p in away_unavail:
                status = p.get("status", "unknown")
                if status == "injured":
                    result["injured"].append(p)
                elif status == "suspended":
                    result["suspended"].append(p)
                elif status == "doubtful":
                    result["doubtful"].append(p)
    
    # 生成摘要
    injured_count = len(result["injured"])
    suspended_count = len(result["suspended"])
    doubtful_count = len(result["doubtful"])
    
    if injured_count + suspended_count + doubtful_count == 0:
        result["summary"] = f"✅ {team_name} 无重大伤病/停赛"
    else:
        parts = []
        if injured_count > 0:
            names = ", ".join([p.get("name", "?") for p in result["injured"][:3]])
            parts.append(f"❌ 伤病{injured_count}人({names})")
        if suspended_count > 0:
            names = ", ".join([p.get("name", "?") for p in result["suspended"][:3]])
            parts.append(f"🚫 停赛{suspended_count}人({names})")
        if doubtful_count > 0:
            names = ", ".join([p.get("name", "?") for p in result["doubtful"][:3]])
            parts.append(f"⚠️ 疑伤{doubtful_count}人({names})")
        result["summary"] = f"📋 {team_name}: " + " | ".join(parts)
    
    return result


@cache_data(ttl=300, show_spinner=False)
def get_match_lineups(home_team: str, away_team: str) -> Dict:
    """
    获取比赛阵容信息（赛前1小时可用）
    
    Args:
        home_team: 主队名
        away_team: 客队名
    
    Returns:
        {
            "home_lineup": ["梅西", "阿圭罗", ...],  # 或 None（未公布）
            "away_lineup": ["内马尔", "苏亚雷斯", ...],
            "home Formation": "4-3-3",
            "away_formation": "4-4-2",
            "status": "confirmed" | "expected" | "not_available",
            "summary": "阵容摘要"
        }
    """
    if not BSD_API_KEY:
        return {"status": "not_available", "summary": "未配置BSD API Key"}
    
    # 查找这场比赛
    events = get_bsd_events(limit=50)
    
    target_event = None
    for e in events:
        if (home_team.lower() in e.get("home_team", "").lower() and 
            away_team.lower() in e.get("away_team", "").lower()):
            target_event = e
            break
    
    if not target_event:
        return {"status": "not_available", 
                "summary": f"未找到 {home_team} vs {away_team} 的比赛"}
    
    lineups = target_event.get("lineups", {})
    
    result = {
        "home_lineup": None,
        "away_lineup": None,
        "home_formation": None,
        "away_formation": None,
        "status": "not_available",
        "summary": ""
    }
    
    if lineups:
        home_lineup = lineups.get("home", {})
        away_lineup = lineups.get("away", {})
        
        if home_lineup:
            result["home_lineup"] = [p.get("name") for p in home_lineup.get("players", [])]
            result["home_formation"] = home_lineup.get("formation")
        
        if away_lineup:
            result["away_lineup"] = [p.get("name") for p in away_lineup.get("players", [])]
            result["away_formation"] = away_lineup.get("formation")
        
        if result["home_lineup"] and result["away_lineup"]:
            result["status"] = "confirmed"
            result["summary"] = f"✅ 阵容已确认: {home_team}({result['home_formation']}) vs {away_team}({result['away_formation']})"
        else:
            result["status"] = "expected"
            result["summary"] = "⏳ 阵容尚未公布（通常赛前1小时）"
    else:
        result["summary"] = "⏳ 阵容数据暂未可用"
    
    return result


@cache_data(ttl=300, show_spinner=False)
def get_coach_info(team_name: str) -> Dict:
    """
    获取教练战术信息
    
    Args:
        team_name: 球队名
    
    Returns:
        {
            "name": "斯卡洛尼",
            "profile": "防守反击型",
            "preferred_formation": "4-4-2",
            "win_rate": 0.65,
            "avg_goals": 1.8,
            "avg_xg": 1.6,
            "discipline": 2.1,  # 场均黄牌
            "summary": "教练信息摘要"
        }
    """
    if not BSD_API_KEY:
        return {"summary": "未配置BSD API Key"}
    
    events = get_bsd_events(team_name=team_name, limit=10)
    
    if not events:
        return {"summary": f"未找到 {team_name} 的比赛数据"}
    
    coach_info = None
    
    for event in events:
        # 主队教练
        if team_name.lower() in event.get("home_team", "").lower():
            coach_info = event.get("home_coach", {})
            break
        # 客队教练
        if team_name.lower() in event.get("away_team", "").lower():
            coach_info = event.get("away_coach", {})
            break
    
    if not coach_info:
        return {"summary": f"未找到 {team_name} 的教练信息"}
    
    result = {
        "name": coach_info.get("name", "?"),
        "profile": coach_info.get("profile", "?"),
        "preferred_formation": coach_info.get("preferred_formation", "?"),
        "win_rate": coach_info.get("win_rate", 0),
        "avg_goals": coach_info.get("avg_goals", 0),
        "avg_xg": coach_info.get("avg_xg", 0),
        "discipline": coach_info.get("discipline", 0),
        "summary": ""
    }
    
    # 生成摘要
    result["summary"] = (
        f"👤 {result['name']} ({result['profile']}) | "
        f"阵型: {result['preferred_formation']} | "
        f"胜率: {result['win_rate']:.1%} | "
        f"场均xG: {result['avg_xg']:.2f}"
    )
    
    return result


@cache_data(ttl=300, show_spinner=False)
def get_best_odds(home_team: str, away_team: str) -> Dict:
    """
    获取最佳赔率对比（17+博彩公司）
    
    Args:
        home_team: 主队名（中文或英文）
        away_team: 客队名（中文或英文）
    
    Returns:
        {
            "best_home": {"odds": 1.85, "bookmaker": "Bet365"},
            "best_draw": {"odds": 3.50, "bookmaker": "Pinnacle"},
            "best_away": {"odds": 4.20, "bookmaker": "Betfair"},
            "average_home": 1.90,
            "average_draw": 3.45,
            "average_away": 4.15,
            "odds_range": "主胜1.80-2.00 | 平3.30-3.70 | 客胜4.00-4.50",
            "summary": "赔率摘要"
        }
    """
    # 中文队名到英文队名映射
    TEAM_NAME_MAP = {
        "西班牙": "Spain", "沙特阿拉伯": "Saudi Arabia", "沙特": "Saudi Arabia",
        "比利时": "Belgium", "伊朗": "Iran",
        "乌拉圭": "Uruguay", "佛得角": "Cape Verde", "Cabo Verde": "Cape Verde",
        "新西兰": "New Zealand", "埃及": "Egypt",
        "巴西": "Brazil", "阿根廷": "Argentina", "法国": "France",
        "英格兰": "England", "德国": "Germany", "荷兰": "Netherlands",
        "葡萄牙": "Portugal", "日本": "Japan", "韩国": "South Korea",
        "墨西哥": "Mexico", "美国": "USA", "加拿大": "Canada",
        "澳大利亚": "Australia", "克罗地亚": "Croatia", "瑞士": "Switzerland",
        "塞内加尔": "Senegal", "挪威": "Norway", "阿尔及利亚": "Algeria",
        "约旦": "Jordan", "巴拿马": "Panama", "哥伦比亚": "Colombia",
        "奥地利": "Austria", "伊拉克": "Iraq", "乌兹别克斯坦": "Uzbekistan",
        "加纳": "Ghana", "刚果": "DR Congo",
    }
    
    # 转换队名
    home_eng = TEAM_NAME_MAP.get(home_team, home_team)
    away_eng = TEAM_NAME_MAP.get(away_team, away_team)
    
    if not BSD_API_KEY:
        return {"summary": "未配置BSD API Key"}
    
    events = get_bsd_events(limit=100)
    
    target_event = None
    for e in events:
        event_home = e.get("home_team", "").lower()
        event_away = e.get("away_team", "").lower()
        
        # 匹配（支持中文和英文）
        if ((home_team.lower() in event_home or home_eng.lower() in event_home) and 
            (away_team.lower() in event_away or away_eng.lower() in event_away)):
            target_event = e
            break
        # 反向匹配
        if ((away_team.lower() in event_home or away_eng.lower() in event_home) and 
            (home_team.lower() in event_away or home_eng.lower() in event_away)):
            target_event = e
            break
    
    if not target_event:
        return {"summary": f"未找到 {home_team} vs {away_team} 的赔率", "average_home": 0, "average_draw": 0, "average_away": 0}
    
    # 获取赔率数据
    odds_data = target_event.get("odds", {})
    
    result = {
        "best_home": None,
        "best_draw": None,
        "best_away": None,
        "average_home": target_event.get("odds_home", 0),
        "average_draw": target_event.get("odds_draw", 0),
        "average_away": target_event.get("odds_away", 0),
        "summary": ""
    }
    
    # 如果有详细赔率对比
    if odds_data:
        # 找最佳赔率
        home_odds_list = odds_data.get("home", [])
        draw_odds_list = odds_data.get("draw", [])
        away_odds_list = odds_data.get("away", [])
        
        if home_odds_list:
            best = max(home_odds_list, key=lambda x: x.get("odds", 0))
            result["best_home"] = best
        if draw_odds_list:
            best = max(draw_odds_list, key=lambda x: x.get("odds", 0))
            result["best_draw"] = best
        if away_odds_list:
            best = max(away_odds_list, key=lambda x: x.get("odds", 0))
            result["best_away"] = best
    
    # 生成摘要
    avg_h = result["average_home"]
    avg_d = result["average_draw"]
    avg_a = result["average_away"]
    
    if avg_h and avg_d and avg_a:
        result["summary"] = f"💰 平均赔率: 主胜{avg_h:.2f} | 平{avg_d:.2f} | 客胜{avg_a:.2f}"
        
        if result["best_home"]:
            result["summary"] += f" | 最佳主胜{result['best_home']['odds']:.2f}({result['best_home']['bookmaker']})"
    else:
        result["summary"] = "赔率数据暂未可用"
    
    return result


def set_bsd_api_key(api_key: str):
    """设置BSD API Key（全局）"""
    global BSD_API_KEY
    BSD_API_KEY = api_key


def is_bsd_available() -> bool:
    """检查BSD API是否可用"""
    return BSD_API_KEY is not None and len(BSD_API_KEY) > 0


# ──────────────────────────────────────────────
#  集成到预测分析的辅助函数
# ──────────────────────────────────────────────

def get_realtime_match_data(home_team: str, away_team: str) -> Dict:
    """
    获取比赛实时数据（整合伤病、阵容、教练、赔率）
    
    Returns:
        {
            "injuries": {...},
            "lineups": {...},
            "coach_home": {...},
            "coach_away": {...},
            "odds": {...},
            "summary": "综合摘要"
        }
    """
    if not is_bsd_available():
        return {"summary": "⚠️ 未配置BSD API Key，无法获取实时数据"}
    
    result = {
        "injuries_home": get_team_injuries(home_team),
        "injuries_away": get_team_injuries(away_team),
        "lineups": get_match_lineups(home_team, away_team),
        "coach_home": get_coach_info(home_team),
        "coach_away": get_coach_info(away_team),
        "odds": get_best_odds(home_team, away_team),
        "summary": ""
    }
    
    # 生成综合摘要
    parts = []
    
    # 伤病摘要
    inj_h = result["injuries_home"].get("summary", "")
    inj_a = result["injuries_away"].get("summary", "")
    if inj_h and "无重大" not in inj_h:
        parts.append(inj_h)
    if inj_a and "无重大" not in inj_a:
        parts.append(inj_a)
    
    # 阵容摘要
    lineup_sum = result["lineups"].get("summary", "")
    if lineup_sum and "暂未" not in lineup_sum:
        parts.append(lineup_sum)
    
    # 教练摘要
    coach_h = result["coach_home"].get("summary", "")
    coach_a = result["coach_away"].get("summary", "")
    if coach_h and "未找到" not in coach_h:
        parts.append(coach_h)
    
    # 赔率摘要
    odds_sum = result["odds"].get("summary", "")
    if odds_sum and "暂未" not in odds_sum:
        parts.append(odds_sum)
    
    if parts:
        result["summary"] = "\n".join(parts)
    else:
        result["summary"] = "✅ 实时数据已获取，无重大伤病/停赛"
    
    return result


def adjust_lambda_for_injuries(lambda_home: float, lambda_away: float, 
                                injuries_home: Dict, injuries_away: Dict) -> Tuple[float, float]:
    """
    根据伤病情况调整期望进球
    
    Args:
        lambda_home: 主队期望进球
        lambda_away: 客队期望进球
        injuries_home: 主队伤病信息
        injuries_away: 客队伤病信息
    
    Returns:
        (adjusted_lambda_home, adjusted_lambda_away)
    """
    # 伤病影响系数（每名主力伤病降低5%，替补伤病降低2%）
    # 注意：这里简化处理，实际应根据球员位置和重要性调整
    
    home_injured = len(injuries_home.get("injured", []))
    home_suspended = len(injuries_home.get("suspended", []))
    home_doubtful = len(injuries_home.get("doubtful", []))
    
    away_injured = len(injuries_away.get("injured", []))
    away_suspended = len(injuries_away.get("suspended", []))
    away_doubtful = len(injuries_away.get("doubtful", []))
    
    # 调整系数
    home_penalty = 1 - (home_injured * 0.05 + home_suspended * 0.05 + home_doubtful * 0.02)
    away_penalty = 1 - (away_injured * 0.05 + away_suspended * 0.05 + away_doubtful * 0.02)
    
    # 确保不低于0.5（极端情况下仍有一定进攻能力）
    home_penalty = max(0.5, home_penalty)
    away_penalty = max(0.5, away_penalty)
    
    return lambda_home * home_penalty, lambda_away * away_penalty