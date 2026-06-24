"""
一次性脚本：修复积分榜计算，把所有已完赛比赛（包括比分0的）正确统计
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import local_data

schedule = local_data.load_schedule()
teams = local_data.load_teams()
teams_dict = {int(t['id']): t for t in teams}

finished = [m for m in schedule if m.get('match_des') == '完赛' and m.get('group_name')]
print(f"已完赛小组赛: {len(finished)} 场")

groups = {}
for m in finished:
    g = m['group_name']
    hid = m.get('host_team_id')
    aid = m.get('guest_team_id')
    hg = m.get('host_team_score')
    ag = m.get('guest_team_score')

    if hid is None or aid is None or hg is None or ag is None:
        print(f"  ⚠️ 跳过 id={m['id']} {m.get('host_team_name')} vs {m.get('guest_team_name')} (数据缺失)")
        continue
    try:
        hg, ag = int(hg), int(ag)
    except:
        continue
    # 用球队名映射到 teams.json 的 ID（因为赛程里的 ID 可能是旧的）
    h_name = m.get('host_team_name', '')
    a_name = m.get('guest_team_name', '')
    # 从 teams.json 用名字找 ID
    hid = None
    aid = None
    for tid, info in teams_dict.items():
        if info.get('name') == h_name:
            hid = tid
        if info.get('name') == a_name:
            aid = tid
    # 如果 teams.json 里没找到中文名，用英文名匹配
    if hid is None or aid is None:
        en_map = {
            '比利时': 'Belgium', '埃及': 'Egypt', '伊朗': 'Iran', '新西兰': 'New Zealand',
            '西班牙': 'Spain', '佛得角': 'Cape Verde', '沙特': 'Saudi Arabia', '乌拉圭': 'Uruguay',
            '法国': 'France', '塞内加尔': 'Senegal', '伊拉克': 'Iraq', '挪威': 'Norway',
            '阿根廷': 'Argentina', '阿尔及利亚': 'Algeria', '奥地利': 'Austria', '约旦': 'Jordan',
            '葡萄牙': 'Portugal', '民主刚果': 'DR Congo', '英格兰': 'England', '克罗地亚': 'Croatia',
            '巴拿马': 'Panama', '乌兹别克': 'Uzbekistan', '哥伦比亚': 'Colombia',
            '加纳': 'Ghana', '波兰': 'Poland',
        }
        if hid is None and h_name in en_map:
            for tid, info in teams_dict.items():
                if info.get('name') == en_map[h_name]:
                    hid = tid
                    break
        if aid is None and a_name in en_map:
            for tid, info in teams_dict.items():
                if info.get('name') == en_map[a_name]:
                    aid = tid
                    break
    if hid is None or aid is None:
        print(f"  ⚠️ 无法映射 id={m['id']} {h_name} vs {a_name}")
        continue

    if g not in groups:
        groups[g] = {}
    if hid not in groups[g]:
        groups[g][hid] = {'win':0,'draw':0,'lose':0,'goal':0,'miss_goal':0,'score':0,'name': teams_dict.get(hid,{}).get('name','?')}
    if aid not in groups[g]:
        groups[g][aid] = {'win':0,'draw':0,'lose':0,'goal':0,'miss_goal':0,'score':0,'name': teams_dict.get(aid,{}).get('name','?')}

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

standings = []
for g in sorted(groups.keys()):
    teams_in = groups[g]
    sorted_t = sorted(teams_in.items(), key=lambda x: (-x[1]['score'], -(x[1]['goal']-x[1]['miss_goal']), -x[1]['goal']))
    for rank, (tid, st) in enumerate(sorted_t, 1):
        info = teams_dict.get(tid, {})
        standings.append({
            'team_group': g, 'id': str(tid), 'id_int': tid,
            'team_name': info.get('name', st['name']),
            'win': str(st['win']), 'lose': str(st['lose']), 'draw': str(st['draw']),
            'score': str(st['score']), 'goal': str(st['goal']), 'miss_goal': str(st['miss_goal']),
            'rank': str(rank),
            'fifa_code': info.get('fifa_code',''), 'fifa_ranking': info.get('fifa_ranking',50),
            'continent': info.get('continent',''), 'country_code': info.get('country_code',''),
        })

# 打印积分榜
for g in sorted(groups.keys()):
    gt = [s for s in standings if s['team_group']==g]
    total_games = sum(int(s['win'])+int(s['draw'])+int(s['lose']) for s in gt) // 2
    print(f"\n组 {g} ({len(gt)}队, {total_games}场):")
    for s in gt:
        played = int(s['win'])+int(s['draw'])+int(s['lose'])
        gd = int(s['goal']) - int(s['miss_goal'])
        print(f"  {s['rank']}. {s['team_name']} {played}赛 {s['win']}胜{s['draw']}平{s['lose']}负 净{gd:+d} 积分{s['score']}")

local_data.save_standings(standings)
print(f"\n✅ 积分榜已保存: {len(standings)} 支球队, {len(groups)} 个组")
