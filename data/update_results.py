"""
批量更新比赛结果 — 将用户提供的赛果写入本地数据
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import local_data

raw = """6月12日（星期五）
03:00 A组：墨西哥 2-0 南非
10:00 A组：韩国 2-1 捷克
6月13日（星期六）
03:00 B组：加拿大 1-1 波黑
09:00 D组：美国 4-1 巴拉圭
6月14日（星期日）
03:00 B组：卡塔尔 1-1 瑞士
06:00 C组：巴西 1-1 摩洛哥
09:00 C组：海地 0-1 苏格兰
12:00 D组：澳大利亚 2-0 土耳其
6月15日（星期一）
01:00 E组：德国 7-1 库拉索
04:00 F组：荷兰 2-2 日本
07:00 E组：科特迪瓦 1-0 厄瓜多尔
10:00 F组：瑞典 5-1 突尼斯
6月16日（星期二）
00:00 H组：西班牙 0-0 佛得角
03:00 G组：比利时 1-1 埃及
06:00 H组：沙特 1-1 乌拉圭
09:00 G组：伊朗 2-2 新西兰
6月17日（星期三）
03:00 I组：法国 3-1 塞内加尔
06:00 I组：伊拉克 1-4 挪威
09:00 J组：阿根廷 3-0 阿尔及利亚
12:00 J组：奥地利 3-1 约旦
6月18日（星期四）
01:00 K组：葡萄牙 1-1 民主刚果
04:00 L组：英格兰 4-2 克罗地亚
07:00 L组：加纳 1-0 巴拿马
10:00 K组：乌兹别克 1-3 哥伦比亚
6月19日（星期五）
00:00 A组：捷克 1-1 南非
03:00 B组：瑞士 4-1 波黑
06:00 B组：加拿大 6-0 卡塔尔
09:00 A组：墨西哥 1-0 韩国
6月20日（星期六）
03:00 D组：美国 2-0 澳大利亚
06:00 C组：苏格兰 0-1 摩洛哥
08:30 C组：巴西 3-0 海地
11:00 D组：土耳其 0-1 巴拉圭
6月21日（星期日）
01:00 F组：荷兰 5-1 瑞典
04:00 E组：德国 2-1 科特迪瓦
08:00 E组：厄瓜多尔 0-0 库拉索
12:00 F组：突尼斯 0-4 日本"""

# 解析
results = []
current_date = None

for line in raw.strip().split("\n"):
    line = line.strip()
    if not line:
        continue
    # 日期行
    if "月" in line and "日" in line and "（" in line:
        import re
        m = re.search(r'(\d+)月(\d+)日', line)
        if m:
            month, day = int(m.group(1)), int(m.group(2))
            current_date = f"2026-{month:02d}-{day:02d}"
        continue
    if not current_date:
        continue

    # 比赛行: "03:00 A组：墨西哥 2-0 南非"
    parts = line.split()
    if len(parts) < 4:
        continue
    time_str = parts[0]  # "03:00"
    # parts[1] = "A组：墨西哥"  parts[2] = "2-0"  parts[3] = "南非"
    group_part = parts[1]  # "A组：墨西哥"
    score_part = parts[2]  # "2-0"
    away_raw = parts[3]    # "南非"

    # 提取小组和主队
    group = group_part[0]  # "A"
    home_raw = group_part[2:]  # "墨西哥"（去掉"A组"）
    # 如果 home_raw 包含 ：
    if "：" in home_raw:
        home_raw = home_raw.split("：", 1)[1]

    # 比分
    if "-" not in score_part:
        continue
    hg_str, ag_str = score_part.split("-", 1)
    try:
        hg, ag = int(hg_str), int(ag_str)
    except ValueError:
        continue

    results.append({
        "date": f"{current_date} {time_str}:00",
        "group": group,
        "home": home_raw,
        "away": away_raw,
        "hg": hg,
        "ag": ag,
    })

print(f"解析到 {len(results)} 场比赛")

# 加载现有赛程
schedule = local_data.load_schedule()

# 构建 lookup: (home_en, away_en) → match
# 先建中文名映射
name_map = {
    "墨西哥": "Mexico", "南非": "South Africa", "韩国": "South Korea", "捷克": "Czech Republic",
    "加拿大": "Canada", "波黑": "Bosnia", "美国": "USA", "巴拉圭": "Paraguay",
    "卡塔尔": "Qatar", "瑞士": "Switzerland", "巴西": "Brazil", "摩洛哥": "Morocco",
    "海地": "Haiti", "苏格兰": "Scotland", "澳大利亚": "Australia", "土耳其": "Turkey",
    "德国": "Germany", "库拉索": "Curaçao", "荷兰": "Netherlands", "日本": "Japan",
    "科特迪瓦": "Ivory Coast", "厄瓜多尔": "Ecuador", "瑞典": "Sweden", "突尼斯": "Tunisia",
    "西班牙": "Spain", "佛得角": "Cape Verde", "比利时": "Belgium", "埃及": "Egypt",
    "沙特": "Saudi Arabia", "乌拉圭": "Uruguay", "伊朗": "Iran", "新西兰": "New Zealand",
    "法国": "France", "塞内加尔": "Senegal", "伊拉克": "Iraq", "挪威": "Norway",
    "阿根廷": "Argentina", "阿尔及利亚": "Algeria", "奥地利": "Austria", "约旦": "Jordan",
    "葡萄牙": "Portugal", "民主刚果": "DR Congo", "英格兰": "England", "克罗地亚": "Croatia",
    "巴拿马": "Panama", "乌兹别克": "Uzbekistan", "哥伦比亚": "Colombia",
}

# 双向映射
en_to_cn = {v: k for k, v in name_map.items()}

match_lookup = {}
for m in schedule:
    h = m.get("host_team_name", "")
    a = m.get("guest_team_name", "")
    match_lookup[(h, a)] = m
    match_lookup[(a, h)] = m

# 更新比分
updated = 0
not_found = []
for r in results:
    home_en = name_map.get(r["home"], r["home"])
    away_en = name_map.get(r["away"], r["away"])

    m = match_lookup.get((home_en, away_en))
    swapped = False
    if not m:
        # 尝试反向
        m = match_lookup.get((away_en, home_en))
        if m:
            swapped = True

    if not m:
        # 模糊匹配：日期 + 一个队名
        for sm in schedule:
            sm_date = sm.get("date", "")[:10]
            sm_h = sm.get("host_team_name", "")
            sm_a = sm.get("guest_team_name", "")
            if sm_date != r["date"][:10]:
                continue
            h_ok = home_en == sm_h or r["home"] in sm_h or sm_h in home_en
            a_ok = away_en == sm_a or r["away"] in sm_a or sm_a in away_en
            if h_ok and a_ok:
                m = sm
                break
            h_ok_rev = home_en == sm_a or r["home"] in sm_a or sm_a in home_en
            a_ok_rev = away_en == sm_h or r["away"] in sm_h or sm_h in away_en
            if h_ok_rev and a_ok_rev:
                m = sm
                swapped = True
                break

    if m:
        if swapped:
            m["host_team_score"] = r["ag"]
            m["guest_team_score"] = r["hg"]
        else:
            m["host_team_score"] = r["hg"]
            m["guest_team_score"] = r["ag"]
        m["match_des"] = "完赛"
        m["match_status"] = "3"
        updated += 1
        h_name = r["home"] if not swapped else r["away"]
        a_name = r["away"] if not swapped else r["home"]
        s_hg = r["hg"] if not swapped else r["ag"]
        s_ag = r["ag"] if not swapped else r["hg"]
        print(f"  ✅ {r['date'][:16]} {r['group']}组 {h_name} {s_hg}:{s_ag} {a_name} (id={m.get('id')})")
    else:
        not_found.append(r)
        print(f"  ❌ 未找到: {r['date'][:16]} {r['group']}组 {r['home']} {r['hg']}:{r['ag']} {r['away']}")

# 保存
local_data.save_schedule(schedule)
print(f"\n赛程已保存: {updated} 场更新")

# 重算积分榜
standings = local_data.recalculate_standings()
local_data.save_standings(standings)
print(f"积分榜已重算并保存: {len(standings)} 支球队")

if not_found:
    print(f"\n⚠️ {len(not_found)} 场未找到:")
    for r in not_found:
        print(f"  {r['date'][:16]} {r['group']}组 {r['home']} {r['hg']}:{r['ag']} {r['away']}")
