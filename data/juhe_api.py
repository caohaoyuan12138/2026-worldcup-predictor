"""
聚合数据API模块 - 2026世界杯赛程数据

内置配置：
- MCP服务：https://mcp.juhe.cn/sse?token=fcfvwrpiiVqZfwoOzNrdn4IfepbqaD2CXDWT5CLo7RzS1K
- API调用：https://apis.juhe.cn/fapigw/worldcup2026/schedule
- API Key：cacdf03f36ed28cd9c61785656c30dfb

功能：
- 获取完整赛程数据
- 获取实时比分
- 获取球队信息
"""

import requests
import json
from typing import Dict, List, Optional
from datetime import datetime

# 聚合API内置配置
JUHE_API_BASE = "https://apis.juhe.cn/fapigw/worldcup2026"
JUHE_API_KEY = "cacdf03f36ed28cd9c61785656c30dfb"  # 内置API Key
JUHE_MCP_URL = "https://mcp.juhe.cn/sse?token=fcfvwrpiiVqZfwoOzNrdn4IfepbqaD2CXDWT5CLo7RzS1K"  # MCP服务


def get_schedule() -> List[Dict]:
    """
    获取2026世界杯完整赛程
    
    Returns:
        赛程列表，每个比赛包含：
        - match_id: 比赛ID
        - date_time: 比赛时间
        - host_team_id: 主队ID
        - guest_team_id: 客队ID
        - host_team_name: 主队名称
        - guest_team_name: 客队名称
        - host_team_score: 主队比分（已完赛）
        - guest_team_score: 客队比分（已完赛）
        - match_status: 比赛状态（1未开赛/2进行中/3已完赛）
        - match_des: 比赛描述
        - stage: 比赛阶段（小组赛/淘汰赛）
        - venue: 比赛场地
    """
    try:
        url = f"{JUHE_API_BASE}/schedule"
        params = {
            "key": JUHE_API_KEY,
        }
        
        r = requests.get(url, params=params, timeout=30)
        
        if r.status_code == 200:
            data = r.json()
            
            # 检查返回状态
            if data.get("error_code") == 0 or data.get("reason") == "查询成功":
                result = data.get("result", {})
                # 数据格式：按日期分组
                date_list = result.get("data", [])
                
                # 转换数据格式
                matches = []
                for date_item in date_list:
                    schedule_list = date_item.get("schedule_list", [])
                    for item in schedule_list:
                        match = {
                            "match_id": item.get("team_id", "") or item.get("match_id", ""),
                            "date_time": item.get("date_time", ""),
                            "host_team_id": str(item.get("host_team_id", "")),
                            "guest_team_id": str(item.get("guest_team_id", "")),
                            "host_team_name": item.get("host_team_name", ""),
                            "guest_team_name": item.get("guest_team_name", ""),
                            "host_team_score": str(item.get("host_team_score", "")) if item.get("host_team_score") else "",
                            "guest_team_score": str(item.get("guest_team_score", "")) if item.get("guest_team_score") else "",
                            "match_status": str(item.get("match_status", "1")),
                            "match_des": item.get("match_des", _get_match_status_desc(item.get("match_status", 1))),
                            "stage": item.get("match_type_name", "小组赛"),
                            "match_type_name": item.get("match_type_name", "小组赛"),
                            "match_type_des": item.get("match_type_des", ""),
                            "venue": item.get("venue", ""),
                            "group": item.get("group", ""),
                            "group_name": item.get("group_name", ""),  # 关键字段！
                            "host_team_logo": item.get("host_team_logo_url", ""),
                            "guest_team_logo": item.get("guest_team_logo_url", ""),
                        }
                        matches.append(match)
                
                return matches
            else:
                # API返回错误
                error_msg = data.get("reason", "未知错误")
                print(f"聚合API错误: {error_msg}")
                return []
        else:
            print(f"聚合API请求失败: HTTP {r.status_code}")
            return []
    
    except requests.exceptions.Timeout:
        print("聚合API请求超时")
        return []
    except Exception as e:
        print(f"聚合API异常: {str(e)}")
        return []


def _get_match_status_desc(status: int) -> str:
    """获取比赛状态描述"""
    status_map = {
        0: "未开赛",
        1: "未开赛",
        2: "进行中",
        3: "完赛",
        4: "已取消",
        5: "推迟",
    }
    return status_map.get(status, "未知")


def get_teams() -> List[Dict]:
    """
    获取2026世界杯参赛球队信息
    
    Returns:
        球队列表，每个球队包含：
        - team_id: 球队ID
        - team_name: 球队名称
        - country: 国家
        - continent: 所属洲
        - fifa_rank: FIFA排名
    """
    try:
        url = f"{JUHE_API_BASE}/teams"
        params = {
            "key": JUHE_API_KEY,
        }
        
        r = requests.get(url, params=params, timeout=30)
        
        if r.status_code == 200:
            data = r.json()
            
            if data.get("error_code") == 0:
                result = data.get("result", {})
                teams = result.get("list", [])
                
                # 转换数据格式
                team_list = []
                for item in teams:
                    team = {
                        "team_id": str(item.get("teamId", "")),
                        "team_name": item.get("teamName", ""),
                        "country": item.get("country", ""),
                        "continent": item.get("continent", ""),
                        "fifa_rank": item.get("fifaRank", 0),
                        "flag": item.get("flag", ""),
                    }
                    team_list.append(team)
                
                return team_list
            else:
                return []
        else:
            return []
    
    except Exception as e:
        print(f"获取球队信息异常: {str(e)}")
        return []


def get_live_matches() -> List[Dict]:
    """
    获取正在进行的比赛
    
    Returns:
        进行中的比赛列表
    """
    schedule = get_schedule()
    live_matches = [m for m in schedule if m.get("match_status") == "2"]
    return live_matches


def get_finished_matches() -> List[Dict]:
    """
    获取已完赛的比赛
    
    Returns:
        已完赛比赛列表
    """
    schedule = get_schedule()
    finished_matches = [m for m in schedule if m.get("match_status") == "3"]
    return finished_matches


def get_upcoming_matches() -> List[Dict]:
    """
    获取未开赛的比赛
    
    Returns:
        未开赛比赛列表
    """
    schedule = get_schedule()
    upcoming_matches = [m for m in schedule if m.get("match_status") in ["0", "1"]]
    return upcoming_matches


def get_match_by_id(match_id: str) -> Optional[Dict]:
    """
    根据比赛ID获取比赛详情
    
    Args:
        match_id: 比赛ID
    
    Returns:
        比赛详情字典
    """
    schedule = get_schedule()
    for match in schedule:
        if match.get("match_id") == match_id:
            return match
    return None


def get_standings() -> List[Dict]:
    """
    获取小组积分榜
    
    Returns:
        积分榜列表
    """
    try:
        url = f"{JUHE_API_BASE}/standings"
        params = {
            "key": JUHE_API_KEY,
        }
        
        r = requests.get(url, params=params, timeout=30)
        
        if r.status_code == 200:
            data = r.json()
            
            if data.get("error_code") == 0:
                result = data.get("result", {})
                standings = result.get("list", [])
                
                # 转换数据格式
                standing_list = []
                for item in standings:
                    standing = {
                        "group": item.get("group", ""),
                        "team_id": str(item.get("teamId", "")),
                        "team_name": item.get("teamName", ""),
                        "played": item.get("played", 0),
                        "won": item.get("won", 0),
                        "draw": item.get("draw", 0),
                        "lost": item.get("lost", 0),
                        "goals_for": item.get("goalsFor", 0),
                        "goals_against": item.get("goalsAgainst", 0),
                        "goal_diff": item.get("goalDiff", 0),
                        "points": item.get("points", 0),
                    }
                    standing_list.append(standing)
                
                return standing_list
            else:
                return []
        else:
            return []
    
    except Exception as e:
        print(f"获取积分榜异常: {str(e)}")
        return []


def sync_all_data() -> Dict:
    """
    同步所有数据
    
    Returns:
        {
            "schedule": 赛程列表,
            "teams": 球队列表,
            "standings": 积分榜列表,
            "sync_time": 同步时间,
        }
    """
    schedule = get_schedule()
    teams = get_teams()
    standings = get_standings()
    
    return {
        "schedule": schedule,
        "teams": teams,
        "standings": standings,
        "sync_time": datetime.now().isoformat(),
    }


# MCP服务（用于实时推送）
def get_mcp_url() -> str:
    """获取MCP服务URL"""
    return JUHE_MCP_URL


# 测试
if __name__ == "__main__":
    print("=== 聚合API测试 ===")
    print(f"API Key: {JUHE_API_KEY}")
    print(f"MCP URL: {JUHE_MCP_URL}")
    
    # 测试获取赛程
    print("\n=== 获取赛程 ===")
    schedule = get_schedule()
    print(f"获取到 {len(schedule)} 场比赛")
    
    if schedule:
        for m in schedule[:3]:
            print(f"  {m['host_team_name']} vs {m['guest_team_name']} ({m['match_des']})")
    
    # 测试获取球队
    print("\n=== 获取球队 ===")
    teams = get_teams()
    print(f"获取到 {len(teams)} 支球队")
    
    if teams:
        for t in teams[:3]:
            print(f"  {t['team_name']} (FIFA #{t['fifa_rank']})")
    
    # 测试获取积分榜
    print("\n=== 获取积分榜 ===")
    standings = get_standings()
    print(f"获取到 {len(standings)} 条积分记录")
    
    # 测试同步所有数据
    print("\n=== 同步所有数据 ===")
    all_data = sync_all_data()
    print(f"赛程: {len(all_data['schedule'])}场")
    print(f"球队: {len(all_data['teams'])}支")
    print(f"积分榜: {len(all_data['standings'])}条")
    print(f"同步时间: {all_data['sync_time']}")