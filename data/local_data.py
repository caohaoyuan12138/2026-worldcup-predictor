"""
本地数据管理器
- 维护本地积分榜和赛程 JSON 文件
- 提供更新接口，让你告诉我比赛结果后写入本地文件
- 启动时直接读取本地文件，不依赖 API
"""

import json
import os
import time

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data_local")
RANK_FILE = os.path.join(DATA_DIR, "standings.json")
SCHEDULE_FILE = os.path.join(DATA_DIR, "schedule.json")
TEAMS_FILE = os.path.join(DATA_DIR, "teams.json")

os.makedirs(DATA_DIR, exist_ok=True)


def load_standings():
    """从本地文件加载积分榜"""
    if not os.path.exists(RANK_FILE):
        return []
    with open(RANK_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_standings(standings):
    """保存积分榜到本地文件"""
    with open(RANK_FILE, "w", encoding="utf-8") as f:
        json.dump(standings, f, ensure_ascii=False, indent=2)


def load_schedule():
    """从本地文件加载赛程"""
    if not os.path.exists(SCHEDULE_FILE):
        return []
    with open(SCHEDULE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_schedule(schedule):
    """保存赛程到本地文件"""
    with open(SCHEDULE_FILE, "w", encoding="utf-8") as f:
        json.dump(schedule, f, ensure_ascii=False, indent=2)


def save_teams(teams):
    """保存球队列表到本地文件"""
    with open(TEAMS_FILE, "w", encoding="utf-8") as f:
        json.dump(teams, f, ensure_ascii=False, indent=2)


def load_teams():
    """加载球队列表"""
    if not os.path.exists(TEAMS_FILE):
        return []
    with open(TEAMS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def load_all():
    """加载所有本地数据"""
    return {
        "standings": load_standings(),
        "schedule": load_schedule(),
        "teams": load_teams(),
    }


def update_match_result(match_id, home_score, away_score, home_team=None, away_team=None):
    """
    更新单场比赛结果

    Args:
        match_id: 比赛 ID
        home_score: 主队得分
        away_score: 客队得分
        home_team: 主队名（可选）
        away_team: 客队名（可选）

    Returns:
        bool: 是否找到并更新了比赛
    """
    schedule = load_schedule()
    found = False
    for m in schedule:
        if str(m.get("id")) == str(match_id):
            m["host_team_score"] = home_score
            m["guest_team_score"] = away_score
            m["match_des"] = "完赛"
            m["match_status"] = "3"
            if home_team:
                m["host_team_name"] = home_team
            if away_team:
                m["guest_team_name"] = away_team
            found = True
            break
    if found:
        save_schedule(schedule)
    return found


def _cn_to_id(team_name):
    """根据中文名查找球队 ID（来自 schedule.json）"""
    cn_to_id_map = _build_cn_to_id_map()
    return cn_to_id_map.get(team_name)


def _build_cn_to_id_map():
    """从赛程构建中文名 → ID 的映射"""
    sched = load_schedule()
    cn_to_id = {}
    for m in sched:
        hid = m.get("host_team_id", "")
        aid = m.get("guest_team_id", "")
        hn = m.get("host_team_name", "")
        an = m.get("guest_team_name", "")
        if hid and hid != "0" and hn:
            cn_to_id[hn] = int(hid)
        if aid and aid != "0" and an:
            cn_to_id[an] = int(aid)
    return cn_to_id


def add_finished_match(match_id, date, home_team, away_team, home_score, away_score,
                      group="", match_type_name="小组赛", match_type_des=""):
    """
    添加一场新的完赛比赛（如果比赛中不存在则追加）
    """
    hid = _cn_to_id(home_team)
    aid = _cn_to_id(away_team)
    schedule = load_schedule()
    # 检查是否已存在
    exists = any(str(m.get("id")) == str(match_id) for m in schedule)
    if not exists:
        schedule.append({
            "id": str(match_id),
            "date": date,
            "host_team_name": home_team,
            "guest_team_name": away_team,
            "host_team_id": str(hid) if hid else "0",
            "guest_team_id": str(aid) if aid else "0",
            "host_team_score": home_score,
            "guest_team_score": away_score,
            "match_des": "完赛",
            "match_status": "3",
            "match_type_name": match_type_name,
            "match_type_des": match_type_des,
            "group_name": group,
        })
        save_schedule(schedule)
    else:
        update_match_result(str(match_id), home_score, away_score, home_team, away_team)


def recalculate_standings(schedule=None):
    """
    根据赛程中的完赛比赛重新计算积分榜
    使用中文名作为 key，从赛程中提取所有实际出现的球队（含未比赛的）
    返回更新后的积分榜列表
    """
    if schedule is None:
        schedule = load_schedule()

    # 从赛程提取所有实际参赛球队（中文名 → 组）
    actual_teams = {}  # group → set of cn_name
    for m in schedule:
        g = m.get("group_name", "")
        if not g:
            continue
        for key in ("host_team_name", "guest_team_name"):
            name = m.get(key, "")
            if not name or "胜者" in name or "败者" in name:
                continue
            actual_teams.setdefault(g, set()).add(name)

    # 统计已完赛比赛
    cn_to_en = {
        "墨西哥": "Mexico", "南非": "South Africa", "韩国": "South Korea", "捷克": "Czech Republic",
        "加拿大": "Canada", "波黑": "Bosnia", "美国": "USA", "巴拉圭": "Paraguay",
        "卡塔尔": "Qatar", "瑞士": "Switzerland", "巴西": "Brazil", "摩洛哥": "Morocco",
        "海地": "Haiti", "苏格兰": "Scotland", "澳大利亚": "Australia", "土耳其": "Turkey",
        "德国": "Germany", "库拉索": "Curaçao", "荷兰": "Netherlands", "日本": "Japan",
        "科特迪瓦": "Ivory Coast", "厄瓜多尔": "Ecuador", "瑞典": "Sweden", "突尼斯": "Tunisia",
        "西班牙": "Spain", "佛得角": "Cape Verde", "比利时": "Belgium", "埃及": "Egypt",
        "沙特": "Saudi Arabia", "沙特阿拉伯": "Saudi Arabia", "乌拉圭": "Uruguay",
        "伊朗": "Iran", "新西兰": "New Zealand",
        "法国": "France", "塞内加尔": "Senegal", "伊拉克": "Iraq", "挪威": "Norway",
        "阿根廷": "Argentina", "阿尔及利亚": "Algeria", "奥地利": "Austria", "约旦": "Jordan",
        "葡萄牙": "Portugal", "民主刚果": "DR Congo", "刚果民主共和国": "DR Congo",
        "英格兰": "England", "克罗地亚": "Croatia", "加纳": "Ghana", "波兰": "Poland",
        "巴拿马": "Panama", "乌兹别克": "Uzbekistan", "乌兹别克斯坦": "Uzbekistan", "哥伦比亚": "Colombia",
        "喀麦隆": "Cameroon",
    }

    teams = load_teams()
    en_to_info = {t['name']: t for t in teams}

    group_stats = {}
    finished = [m for m in schedule if m.get("match_des") == "完赛" and m.get("group_name")]

    for m in finished:
        g = m['group_name']
        hg = m.get("host_team_score")
        ag = m.get("guest_team_score")
        h_cn = m.get("host_team_name", "")
        a_cn = m.get("guest_team_name", "")
        if hg is None or ag is None:
            continue
        try:
            hg, ag = int(hg), int(ag)
        except (ValueError, TypeError):
            continue
        group_stats.setdefault(g, {})
        group_stats[g].setdefault(h_cn, {"win":0,"draw":0,"lose":0,"goal":0,"miss_goal":0,"score":0})
        group_stats[g].setdefault(a_cn, {"win":0,"draw":0,"lose":0,"goal":0,"miss_goal":0,"score":0})
        group_stats[g][h_cn]["goal"] += hg
        group_stats[g][h_cn]["miss_goal"] += ag
        group_stats[g][a_cn]["goal"] += ag
        group_stats[g][a_cn]["miss_goal"] += hg
        if hg > ag:
            group_stats[g][h_cn]["win"] += 1; group_stats[g][h_cn]["score"] += 3; group_stats[g][a_cn]["lose"] += 1
        elif hg < ag:
            group_stats[g][a_cn]["win"] += 1; group_stats[g][a_cn]["score"] += 3; group_stats[g][h_cn]["lose"] += 1
        else:
            group_stats[g][h_cn]["draw"] += 1; group_stats[g][h_cn]["score"] += 1
            group_stats[g][a_cn]["draw"] += 1; group_stats[g][a_cn]["score"] += 1

    # 生成积分榜（含未比赛的球队）
    standings = []
    for g in sorted(actual_teams.keys()):
        all_in_group = actual_teams[g]
        all_stats = group_stats.get(g, {})
        entries = []
        for cn_name in all_in_group:
            st = all_stats.get(cn_name, {"win":0,"draw":0,"lose":0,"goal":0,"miss_goal":0,"score":0})
            entries.append((cn_name, st))
        entries.sort(key=lambda x: (-x[1]["score"], -(x[1]["goal"]-x[1]["miss_goal"]), -x[1]["goal"]))
        for rank, (cn_name, st) in enumerate(entries, 1):
            en_name = cn_to_en.get(cn_name, "")
            info = en_to_info.get(en_name, {})
            standings.append({
                "team_group": g,
                "team_name": cn_name,
                "id": str(rank),
                "id_int": rank,
                "win": str(st["win"]), "lose": str(st["lose"]), "draw": str(st["draw"]),
                "score": str(st["score"]), "goal": str(st["goal"]), "miss_goal": str(st["miss_goal"]),
                "rank": str(rank),
                "fifa_code": info.get("fifa_code", ""),
                "fifa_ranking": info.get("fifa_ranking", 50),
                "continent": info.get("continent", ""),
                "country_code": info.get("country_code", ""),
            })

    save_standings(standings)
    return standings


def get_groups_summary():
    """获取小组赛汇总信息"""
    standings = load_standings()
    if not standings:
        return "暂无积分榜数据"

    groups = sorted(set(s.get("team_group", "?") for s in standings))
    lines = []
    for g in groups:
        gt = [s for s in standings if s.get("team_group") == g]
        gt.sort(key=lambda x: int(x.get("rank", 99) or 99))
        lines.append(f"\n**组 {g}**:")
        for t in gt:
            played = int(t.get("win", 0)) + int(t.get("draw", 0)) + int(t.get("lose", 0))
            gd = int(t.get("goal", 0)) - int(t.get("miss_goal", 0))
            gd_str = f"+{gd}" if gd > 0 else str(gd)
            lines.append(
                f"  {t.get('rank')}. {t.get('team_name')} "
                f"{t.get('win')}胜{t.get('draw')}平{t.get('lose')}负 "
                f"净{gd_str} 积分{t.get('score')}"
            )
    return "\n".join(lines)


def get_upcoming_matches(days=7):
    """获取未来 N 天的未赛比赛"""
    from datetime import datetime, timedelta
    schedule = load_schedule()
    now = datetime.now()
    cutoff = now + timedelta(days=days)
    upcoming = []
    for m in schedule:
        if m.get("match_des") == "完赛":
            continue
        dt_str = m.get("date", "")
        if dt_str:
            try:
                dt = datetime.strptime(dt_str[:10], "%Y-%m-%d")
                if now <= dt <= cutoff:
                    upcoming.append(m)
            except ValueError:
                pass
    return upcoming


def get_finished_matches(group=None):
    """获取已完赛比赛"""
    schedule = load_schedule()
    finished = [m for m in schedule if m.get("match_des") == "完赛"]
    if group:
        finished = [m for m in finished if m.get("group_name") == group]
    return finished
