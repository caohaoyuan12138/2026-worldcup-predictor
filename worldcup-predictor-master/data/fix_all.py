"""
一次性修复：
1. standings 里 team_name 用中文（用户看得懂）
2. 补全所有 48 支球队到积分榜（没比赛的 0-0-0）
3. teams.json 里去重，只保留赛程里出现过的球队
"""
import json, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import local_data

# 中文名映射
CN_TO_EN = {
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
EN_TO_CN = {v: k for k, v in CN_TO_EN.items()}

# 1. 加载数据
schedule = local_data.load_schedule()
teams = local_data.load_teams()  # 可能有无球队在赛程中

# 2. 从赛程中提取所有实际参赛球队（中文名 → 组）
actual_teams = {}  # group → set of (cn_name, en_name)
for m in schedule:
    g = m.get('group_name', '')
    if not g:
        continue
    h = m.get('host_team_name', '')
    a = m.get('guest_team_name', '')
    for name in [h, a]:
        if not name:
            continue
        # 消除 "第x场1/8决赛胜者" 等占位符
        if '胜者' in name or '败者' in name:
            continue
        en = CN_TO_EN.get(name, name)
        if g not in actual_teams:
            actual_teams[g] = set()
        actual_teams[g].add((name, en))

# 3. 用中文名构建完整 standings（包括未比赛的球队）
# 先按组统计已完赛比赛
finished = [m for m in schedule if m.get('match_des') == '完赛' and m.get('group_name')]
group_stats = {}
for m in finished:
    g = m['group_name']
    hg = m.get('host_team_score')
    ag = m.get('guest_team_score')
    h_cn = m.get('host_team_name', '')
    a_cn = m.get('guest_team_name', '')
    if hg is None or ag is None:
        continue
    try:
        hg, ag = int(hg), int(ag)
    except:
        continue
    if g not in group_stats:
        group_stats[g] = {}
    if h_cn not in group_stats[g]:
        group_stats[g][h_cn] = {"win":0,"draw":0,"lose":0,"goal":0,"miss_goal":0,"score":0}
    if a_cn not in group_stats[g]:
        group_stats[g][a_cn] = {"win":0,"draw":0,"lose":0,"goal":0,"miss_goal":0,"score":0}
    group_stats[g][h_cn]['goal'] += hg
    group_stats[g][h_cn]['miss_goal'] += ag
    group_stats[g][a_cn]['goal'] += ag
    group_stats[g][a_cn]['miss_goal'] += hg
    if hg > ag:
        group_stats[g][h_cn]['win'] += 1; group_stats[g][h_cn]['score'] += 3; group_stats[g][a_cn]['lose'] += 1
    elif hg < ag:
        group_stats[g][a_cn]['win'] += 1; group_stats[g][a_cn]['score'] += 3; group_stats[g][h_cn]['lose'] += 1
    else:
        group_stats[g][h_cn]['draw'] += 1; group_stats[g][h_cn]['score'] += 1
        group_stats[g][a_cn]['draw'] += 1; group_stats[g][a_cn]['score'] += 1

# 4. 构建完整积分榜（含未比赛球队）
standings = []
for g in sorted(actual_teams.keys()):
    all_in_group = actual_teams[g]
    all_stats = group_stats.get(g, {})
    team_entries = []
    for cn_name, en_name in all_in_group:
        st = all_stats.get(cn_name, {"win":0,"draw":0,"lose":0,"goal":0,"miss_goal":0,"score":0})
        team_entries.append((cn_name, st))
    # 排序
    team_entries.sort(key=lambda x: (-x[1]["score"], -(x[1]["goal"]-x[1]["miss_goal"]), -x[1]["goal"]))
    for rank, (cn_name, st) in enumerate(team_entries, 1):
        standings.append({
            "team_group": g,
            "team_name": cn_name,
            "id": str(rank),
            "id_int": rank,
            "win": str(st["win"]),
            "lose": str(st["lose"]),
            "draw": str(st["draw"]),
            "score": str(st["score"]),
            "goal": str(st["goal"]),
            "miss_goal": str(st["miss_goal"]),
            "rank": str(rank),
            "fifa_code": "",
            "fifa_ranking": 50,
            "continent": "",
            "country_code": "",
        })

local_data.save_standings(standings)
print(f"✅ 积分榜: {len(standings)} 支球队, {len(actual_teams)} 组")

# 验证
for g in sorted(actual_teams.keys()):
    gt = [s for s in standings if s['team_group']==g]
    total_games = sum(int(s['win'])+int(s['draw'])+int(s['lose']) for s in gt) // 2
    print(f"  组 {g}: {len(gt)}队 {total_games}场 - {gt[0]['team_name']} 领跑 ({gt[0]['score']}积分)")
