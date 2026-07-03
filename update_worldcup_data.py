import requests
import json
import os
import time

# 配置
HEADERS = {'User-Agent': 'Mozilla/5.0'}
SEASON_ID = '26123'
OUTPUT_MD = os.path.join(os.path.dirname(os.path.abspath(__file__)), '世界杯数据完全汇总.md')
TEMP_JSON = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'all_data.json')

# 球员榜类型映射
PERSON_TYPES = [
    ('goals', '射手榜'), ('assists', '助攻榜'), ('yellow_cards', '黄牌'), ('red_cards', '红牌'),
    ('goal_penalty', '点球'), ('shots', '射门'), ('shots_on_target', '射正'),
    ('dribbles_attempted', '尝试过人'), ('dribbles_won', '成功过人'), ('fouled', '被犯规'),
    ('big_chance_created', '创造进球机会'), ('big_chance_missed', '错失绝佳机会'),
    ('key_passes', '关键传球'), ('passes', '传球'), ('pass_accuracy', '传球成功率'),
    ('touches', '触球'), ('crosses', '传中'), ('success_crosses', '成功传中'),
    ('long_balls', '长传'), ('success_long_balls', '成功长传'), ('tackles', '抢断'),
    ('interceptions', '拦截'), ('clearances', '解围'), ('aerials', '争顶总数'),
    ('aerials_won', '争顶成功'), ('ground_duels', '地面争抢'), ('ground_duels_won', '成功地面争抢'),
    ('last_man_tackle', '防线最后一人完成抢断'), ('error_lead_to_goal', '失误导致丢球'),
    ('error_lead_to_shot', '失误导致射门'), ('fouls', '犯规'), ('dispossessed', '丢失球权'),
    ('was_dribbled', '被过'), ('saves', '扑救'), ('penalty_saves', '扑出点球'),
    ('box_shot_saves', '禁区射门扑救'), ('runs_out', '出击'), ('runs_out_success', '成功出击'),
    ('claims_high', '摘高球'), ('punches', '拳击球'), ('rating', '评分'),
]


def fetch_person_rankings():
    person_data = {}
    for type_code, type_name in PERSON_TYPES:
        url = f'https://sport-data.dongqiudi.com/soccer/biz/data/person_ranking?app=dqd&version=853&platform=ios&type={type_code}&season_id={SEASON_ID}'
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            data = r.json()
            items = data['content']['data']
            person_data[type_name] = {'count': len(items), 'data': items}
            print(f'  [球员] {type_name}: {len(items)} 条')
        except Exception as e:
            print(f'  [球员] {type_name}: 失败 - {e}')
        time.sleep(0.3)
    return person_data


def fetch_team_rankings():
    # 先获取球队类型列表
    meta_url = f'https://sport-data.dongqiudi.com/soccer/biz/data/ranking/team?season_id={SEASON_ID}&app=dqd&version=853&platform=ios&language=zh-cn&app_type=&type=team'
    r = requests.get(meta_url, headers=HEADERS, timeout=15)
    team_types = [(item['type'], item['name']) for item in r.json()['content']['data']]

    team_data = {}
    for type_code, type_name in team_types:
        url = f'https://sport-data.dongqiudi.com/soccer/biz/data/team_ranking?app=dqd&version=853&platform=ios&type={type_code}&season_id={SEASON_ID}'
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            data = r.json()
            items = data['content']['data']
            team_data[type_name] = {'count': len(items), 'data': items}
            print(f'  [球队] {type_name}: {len(items)} 条')
        except Exception as e:
            print(f'  [球队] {type_name}: 失败 - {e}')
        time.sleep(0.3)
    return team_data


def fetch_standings():
    url = f'https://sport-data.dongqiudi.com/soccer/biz/data/standing?season_id={SEASON_ID}&app=dqd&version=853&platform=ios&language=zh-cn&app_type='
    r = requests.get(url, headers=HEADERS, timeout=15)
    return r.json()


def has_meaningful_extra_fields(items):
    if not items:
        return False, False
    meaningful_row1 = False
    meaningful_row2 = False
    for item in items:
        r1 = item.get('row_1', '')
        r2 = item.get('row_2', '')
        team = item.get('team_name', '')
        count = item.get('count', '')
        if r1 and r1 != team:
            meaningful_row1 = True
        if r2 and r2 != count:
            meaningful_row2 = True
    return meaningful_row1, meaningful_row2


def generate_markdown(person_data, team_data, standings):
    person_type_order = [name for _, name in PERSON_TYPES]
    team_type_order = list(team_data.keys())

    with open(OUTPUT_MD, 'w', encoding='utf-8') as f:
        f.write('# 懂球帝世界杯数据中心 - 完整数据汇总\n\n')
        f.write('**数据来源**: [懂球帝世界杯数据中心](https://pc.dongqiudi.com/data?cid=61)\n\n')
        f.write('**数据范围**: 2026世界杯全部赛事数据\n\n')
        f.write(f'**更新时间**: {time.strftime("%Y年%m月%d日 %H:%M")}\n\n')
        f.write('---\n\n')

        f.write('## 目录\n\n')
        f.write('- [一、积分榜（A-L组）](#一积分榜a-l组)\n')
        f.write('- [二、球员榜](#二球员榜)\n')
        for name in person_type_order:
            f.write(f'  - [{name}]\n')
        f.write('- [三、球队榜](#三球队榜)\n')
        for name in team_type_order:
            f.write(f'  - [{name}]\n')
        f.write('\n---\n\n')

        # 积分榜
        f.write('## 一、积分榜（A-L组）\n\n')
        group_round = standings['content']['rounds'][1]
        groups = group_round['content']['data']
        for group in groups:
            group_name = group.get('name', '未知组')
            teams = group.get('data', [])
            f.write(f'### {group_name}\n\n')
            f.write('| 排名 | 球队 | 场次 | 胜 | 平 | 负 | 进球 | 失球 | 积分 |\n')
            f.write('|:---:|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|\n')
            for team in teams:
                f.write(f"| {team['rank']} | {team['team_name']} | {team['matches_total']} | {team['matches_won']} | {team['matches_draw']} | {team['matches_lost']} | {team['goals_pro']} | {team['goals_against']} | {team['points']} |\n")
            f.write('\n')
        f.write('---\n\n')

        # 球员榜
        f.write('## 二、球员榜\n\n')
        f.write('以下各模块包含该统计项的**全部**球员数据。\n\n')
        for type_name in person_type_order:
            if type_name not in person_data:
                continue
            info = person_data[type_name]
            items = info['data']
            f.write(f'### {type_name}\n\n')
            f.write(f'*共 {len(items)} 条记录*\n\n')

            has_row1, has_row2 = has_meaningful_extra_fields(items)
            if has_row1 and has_row2:
                f.write('| 排名 | 球员 | 球队 | 数值 | 备注1 | 备注2 |\n')
                f.write('|:---:|:---|:---|:---:|:---:|:---:|\n')
            elif has_row1:
                f.write('| 排名 | 球员 | 球队 | 数值 | 备注 |\n')
                f.write('|:---:|:---|:---|:---:|:---:|\n')
            else:
                f.write('| 排名 | 球员 | 球队 | 数值 |\n')
                f.write('|:---:|:---|:---|:---:|\n')

            for item in items:
                rank = item.get('rank', '')
                player = item.get('person_name', '')
                team = item.get('team_name', '')
                value = item.get('count', '')
                row1 = item.get('row_1', '')
                row2 = item.get('row_2', '')
                if has_row1 and has_row2:
                    f.write(f"| {rank} | {player} | {team} | {value} | {row1} | {row2} |\n")
                elif has_row1:
                    f.write(f"| {rank} | {player} | {team} | {value} | {row1} |\n")
                else:
                    f.write(f"| {rank} | {player} | {team} | {value} |\n")
            f.write('\n')
        f.write('---\n\n')

        # 球队榜
        f.write('## 三、球队榜\n\n')
        f.write('以下各模块包含该统计项的**全部**球队数据。\n\n')
        for type_name in team_type_order:
            if type_name not in team_data:
                continue
            info = team_data[type_name]
            items = info['data']
            f.write(f'### {type_name}\n\n')
            f.write(f'*共 {len(items)} 条记录*\n\n')
            f.write('| 排名 | 球队 | 数值 |\n')
            f.write('|:---:|:---|:---:|\n')
            for item in items:
                rank = item.get('rank', '')
                team = item.get('team_name', '')
                value = item.get('count', '')
                f.write(f"| {rank} | {team} | {value} |\n")
            f.write('\n')

    size_kb = os.path.getsize(OUTPUT_MD) / 1024
    print(f'\n文档已更新: {OUTPUT_MD}')
    print(f'文件大小: {size_kb:.1f} KB')


def main():
    print('=== 开始抓取世界杯数据 ===')
    print(f'时间: {time.strftime("%Y-%m-%d %H:%M:%S")}')

    print('\n[1/3] 抓取球员榜数据...')
    person_data = fetch_person_rankings()

    print('\n[2/3] 抓取球队榜数据...')
    team_data = fetch_team_rankings()

    print('\n[3/3] 抓取积分榜数据...')
    standings = fetch_standings()

    print('\n[4/4] 生成 Markdown 文档...')
    generate_markdown(person_data, team_data, standings)

    # 保存原始JSON备份
    all_data = {'person': person_data, 'team': team_data, 'standings': standings}
    with open(TEMP_JSON, 'w', encoding='utf-8') as f:
        json.dump(all_data, f, ensure_ascii=False, indent=2)
    print(f'原始数据已保存: {TEMP_JSON}')

    print('\n=== 完成 ===')


if __name__ == '__main__':
    main()
