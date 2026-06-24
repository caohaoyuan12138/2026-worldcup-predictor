"""
世界杯数据 API 客户端
数据源：juhe.cn 聚合数据 API + 本地缓存 fallback
"""

import requests
import json
import time
import os
from typing import Dict, List, Optional, Any
import config

CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "data_local")
CACHE_TTL = 600
os.makedirs(CACHE_DIR, exist_ok=True)

# Load from environment or Streamlit secrets — do NOT hardcode
JUHE_KEY = os.environ.get("JUHE_KEY", "")
JUHE_BASE = "https://apis.juhe.cn/fapigw/worldcup2026"

# 本地静态球队数据（含 fifa_code、fifa_ranking、elo 等）
TEAMS_JSON_PATH = os.path.join(CACHE_DIR, "teams.json")


def _cache_path(name: str) -> str:
    return os.path.join(CACHE_DIR, f"juhe_{name}.json")


def _load_cache(name: str) -> Optional[Any]:
    p = _cache_path(name)
    if not os.path.exists(p):
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        # 不再检查 TTL，始终使用本地缓存作为可靠 fallback
        return data.get("payload")
    except (json.JSONDecodeError, IOError):
        pass
    return None


def _load_cache_even_expired(name: str) -> Optional[Any]:
    """加载缓存，即使过期也使用（用于 API 不可达时的 fallback）"""
    p = _cache_path(name)
    if not os.path.exists(p):
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("payload")
    except (json.JSONDecodeError, IOError):
        pass
    return None


def _save_cache(name: str, payload: Any):
    p = _cache_path(name)
    try:
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"_ts": int(time.time()), "payload": payload}, f,
                      ensure_ascii=False, indent=2)
    except IOError:
        pass


def _request(path: str, params: Dict = None, retries: int = 2) -> Optional[Dict]:
    url = f"{JUHE_BASE}/{path}"
    p = {"key": JUHE_KEY}
    if params:
        p.update(params)
    for attempt in range(retries):
        try:
            resp = requests.get(url, params=p, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            if data.get("error_code") == 0 or data.get("reason") == "查询成功":
                return data.get("result")
            else:
                print(f"[API] {path}: {data.get('reason')}")
                return None
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
            else:
                print(f"[API] {path} 失败: {e}")
    return None


# ==================== 本地球队元数据 ====================
def _load_local_teams() -> Dict[int, Dict]:
    """从 teams.json 加载球队元数据（fifa_code, ranking, elo, group, continent）"""
    if not os.path.exists(TEAMS_JSON_PATH):
        return {}
    try:
        with open(TEAMS_JSON_PATH, "r", encoding="utf-8") as f:
            teams_list = json.load(f)
        return {int(t["id"]): t for t in teams_list}
    except (json.JSONDecodeError, IOError, KeyError):
        return {}


def _enrich_team(team: Dict, local_teams: Dict) -> Dict:
    """用本地数据补全球队元数据"""
    tid = int(team.get("id", 0))
    local = local_teams.get(tid)
    if local:
        team["fifa_code"] = local.get("fifa_code", "")
        team["fifa_ranking"] = local.get("fifa_ranking", 50)
        if not team.get("team_group"):
            team["team_group"] = local.get("group", "")
        team["continent"] = local.get("continent", "")
        team["country_code"] = local.get("country_code", "")
        team["elo"] = local.get("elo", 1500)
    else:
        # 未匹配到的球队给默认值
        if not team.get("fifa_code"):
            team["fifa_code"] = ""
        if not team.get("fifa_ranking"):
            team["fifa_ranking"] = 50
    return team


# ==================== 积分榜 ====================
def get_standings() -> Optional[List[Dict]]:
    """获取小组赛积分榜（带本地缓存 fallback）"""
    cached = _load_cache("rank")
    if cached:
        return cached

    result = _request("rank")
    if result:
        raw_groups = result.get("data", [])
        flat = []
        local_teams = _load_local_teams()
        for grp in raw_groups:
            group_name = grp.get("team_group", "?")
            for team in grp.get("team_rank", []):
                entry = {
                    "team_group": group_name,
                    "id": str(team.get("id", "")),
                    "team_name": team.get("team_name", ""),
                    "team_logo": team.get("team_logo", ""),
                    "win": team.get("win", "0"),
                    "lose": team.get("lose", "0"),
                    "draw": team.get("draw", "0"),
                    "score": team.get("score", "0"),
                    "goal": team.get("goal", "0"),
                    "miss_goal": team.get("miss_goal", "0"),
                    "rank": team.get("rank", "99"),
                    "id_int": int(team.get("id", 0)),
                }
                _enrich_team(entry, local_teams)
                flat.append(entry)
        _save_cache("rank", flat)
        return flat if flat else None

    # API 失败 → fallback 到过期缓存
    fallback = _load_cache_even_expired("rank")
    if fallback:
        print("[API] 积分榜使用过期缓存数据")
        return fallback
    return None


# ==================== 赛程 ====================
def get_matches(status: str = None) -> Optional[List[Dict]]:
    """获取完整赛程（带本地缓存 fallback）"""
    cached = _load_cache("schedule_flat")
    if cached:
        if status:
            return [m for m in cached if m.get("match_des") == status]
        return cached

    result = _request("schedule")
    if not result:
        # API 失败 → fallback 到过期缓存
        fallback = _load_cache_even_expired("schedule_flat")
        if fallback:
            print("[API] 赛程使用过期缓存数据")
            if status:
                return [m for m in fallback if m.get("match_des") == status]
            return fallback
        return None

    flat = []
    for day in result.get("data", []):
        for match in day.get("schedule_list", []):
            flat.append({
                "id": str(match.get("match_id", team.get("id", ""))),
                "date": match.get("date", ""),
                "date_time": match.get("date_time", ""),
                "host_team_id": str(match.get("host_team_id", "")),
                "guest_team_id": str(match.get("guest_team_id", "")),
                "host_team_name": match.get("host_team_name", ""),
                "guest_team_name": match.get("guest_team_name", ""),
                "host_team_score": match.get("host_team_score"),
                "guest_team_score": match.get("guest_team_score"),
                "match_status": match.get("match_status", ""),
                "match_des": match.get("match_des", ""),
                "match_type_name": match.get("match_type_name", ""),
                "match_type_des": match.get("match_type_des", ""),
                "group_name": match.get("group_name", ""),
                "host_team_logo_url": match.get("host_team_logo_url", ""),
                "guest_team_logo_url": match.get("guest_team_logo_url", ""),
            })
    _save_cache("schedule_flat", flat)
    if status:
        return [m for m in flat if m.get("match_des") == status]
    return flat


# ==================== 球队列表 ====================
def get_teams() -> Optional[List[Dict]]:
    """获取球队列表，自动补全 fifa_code 和 fifa_ranking"""
    cached = _load_cache("teams_list")
    if cached:
        # 检查缓存是否已是 enriched 过的（有 fifa_code 的即为 enriched）
        for t in cached:
            if t.get("fifa_code"):
                return cached
        # 缓存没有 enriched → 重新用本地数据补全
        local_teams = _load_local_teams()
        if local_teams:
            enriched = []
            for t in cached:
                _enrich_team(t, local_teams)
                enriched.append(t)
            _save_cache("teams_list", enriched)
            return enriched

    matches = get_matches() or []
    teams = {}
    for m in matches:
        hid = m.get("host_team_id")
        aid = m.get("guest_team_id")
        if hid and hid not in teams:
            teams[hid] = {"id": hid, "name": m.get("host_team_name", ""),
                           "fifa_code": "", "team_group": m.get("group_name", "")}
        if aid and aid not in teams:
            teams[aid] = {"id": aid, "name": m.get("guest_team_name", ""),
                           "fifa_code": "", "team_group": m.get("group_name", "")}

    local_teams = _load_local_teams()
    result = []
    for tid, t in teams.items():
        t["id_int"] = int(tid)
        _enrich_team(t, local_teams)
        result.append(t)

    _save_cache("teams_list", result)
    return result if result else None
