"""
从本地赛程数据重建积分榜
核心逻辑：赛程里 host_team_name 是中文名 → 用 CN_TO_EN 映射到英文名 → 在 teams.json 查找 fifa_code/elo
team_name 直接用中文名保持（和用户输入格式一致）
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import local_data

CN_TO_EN = {
    "墨西哥": "Mexico", "南非": "South Africa", "韩国": "South Korea", "捷克": "Czech Republic",
    "加拿大": "Canada", "波黑": "Bosnia", "美国": "USA", "巴拉圭": "Paraguay",
    "卡塔尔": "Qatar", "瑞士": "Switzerland", "巴西": "Brazil", "摩洛哥": "Morocco",
    "海地": "Haiti", "苏格兰": "Scotland", "澳大利亚": "Australia", "土耳其": "Turkey",
    "德国": "Germany", "库拉索": "Curaçao", "荷兰": "Netherlands", "日本": "Japan",
    "科特迪瓦": "Ivory Coast", "厄瓜多尔": "Ecuador", "瑞典": "Sweden", "突尼斯": "Tunisia",
    "西班牙": "Spain", "佛得角": "Cape Verde", "比利时": "Belgium", "埃及": "Egypt",
    "沙特": "Saudi Arabia", "沙特阿拉伯": "Saudi Arabia", "乌拉圭": "Uruguay", "乌兹别克斯坦": "Uzbekistan",
    "伊朗": "Iran", "新西兰": "New Zealand",
    "法国": "France", "塞内加尔": "Senegal", "伊拉克": "Iraq", "挪威": "Norway",
    "阿根廷": "Argentina", "阿尔及利亚": "Algeria", "奥地利": "Austria", "约旦": "Jordan",
    "葡萄牙": "Portugal", "民主刚果": "DR Congo", "英格兰": "England", "克罗地亚": "Croatia",
    "加纳": "Ghana", "波兰": "Poland",
    "巴拿马": "Panama", "乌兹别克": "Uzbekistan", "乌兹别克斯坦": "Uzbekistan", "哥伦比亚": "Colombia",
    "刚果民主共和国": "DR Congo", "民主刚果": "DR Congo",
    "意大利": "Italy", "乌拉圭": "Uruguay",
    "希腊": "Greece", "尼日利亚": "Nigeria", "塞尔维亚": "Serbia",
}

schedule = local_data.load_schedule()
teams = local_data.load_teams()
# 英文名 → teams.json 信息
en_to_info = {t['name']: t for t in teams}

finished = [m for m in schedule if m.get('match_des') == '完赛' and m.get('group_name')]
print(f"已完赛小组赛: {len(finished)} 场\n")

groups = {}
unmapped = set()

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

    # 中文名 → 英文名 → teams.json 元数据
    h_en = CN_TO_EN.get(h_cn, '')
    a_en = CN_TO_EN.get(a_cn, '')
    h_info = en_to_info.get(h_en, {})
    a_info = en_to_info.get(a_en, {})

    if not h_en:
        unmapped.add(h_cn)
    if not a_en:
        unmapped.add(a_cn)

    hid = int(h_info.get('id', 0)) if h_info else 0
    aid = int(a_info.get('id', 0)) if a_info else 0

    if g not in groups:
        groups[g] = {}
    if hid and hid not in groups[g]:
        groups[g][hid] = {'win':0,'draw':0,'lose':0,'goal':0,'miss_goal':0,'score':0,'name':h_cn}
    if aid and aid not in groups[g]:
        groups[g][aid] = {'win':0,'draw':0,'lose':0,'goal':0,'miss_goal':0,'score':0,'name':a_cn}

    if hid and aid:
        groups[g][hid]['goal'] += hg
        groups[g][hid]['miss_goal'] += ag
        groups[g][aid]['goal'] += ag
        groups[g][aid]['miss_goal'] += hg
        if hg > ag:
            groups[g][hid]['win'] += 1; groups[g][hid]['score'] += 3; groups[g][aid]['lose'] += 1
        elif hg < ag:
            groups[g][aid]['win'] += 1; groups[g][aid]['score'] += 3; groups[g][hid]['lose'] += 1
        else:
            groups[g][hid]['draw'] += 1; groups[g][hid]['score'] += 1
            groups[g][aid]['draw'] += 1; groups[g][aid]['score'] += 1

# 生成积分榜
standings = []
for g in sorted(groups.keys()):
    teams_in = groups[g]
    sorted_t = sorted(teams_in.items(), key=lambda x: (-x[1]['score'], -(x[1]['goal']-x[1]['miss_goal']), -x[1]['goal']))
    for rank, (tid, st) in enumerate(sorted_t, 1):
        info = en_to_info.get(CN_TO_EN.get(st['name'], ''), {})
        standings.append({
            'team_group': g, 'id': str(tid), 'id_int': tid,
            'team_name': st['name'],  # 中文名
            'win': str(st['win']), 'lose': str(st['lose']), 'draw': str(st['draw']),
            'score': str(st['score']), 'goal': str(st['goal']), 'miss_goal': str(st['miss_goal']),
            'rank': str(rank),
            'fifa_code': info.get('fifa_code', ''),
            'fifa_ranking': info.get('fifa_ranking', 50),
            'continent': info.get('continent', ''),
            'country_code': info.get('country_code', ''),
        })

# 打印
for g in sorted(groups.keys()):
    gt = [s for s in standings if s['team_group']==g]
    total_games = sum(int(s['win'])+int(s['draw'])+int(s['lose']) for s in gt) // 2
    print(f"组 {g} ({len(gt)}队, {total_games}场已赛):")
    for s in gt:
        played = int(s['win'])+int(s['draw'])+int(s['lose'])
        gd = int(s['goal']) - int(s['miss_goal'])
        print(f"  {s['rank']}. {s['team_name']} {played}赛 {s['win']}胜{s['draw']}平{s['lose']}负 净{gd:+d} 积分{s['score']}")
    print()

local_data.save_standings(standings)
print(f"✅ 积分榜已保存: {len(standings)} 支球队")

if unmapped:
    print(f"\n⚠️ 未映射球队名: {unmapped}")
