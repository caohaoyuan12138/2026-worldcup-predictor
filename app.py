"""
2026 美加墨世界杯比分预测模型 — Streamlit 主入口
四层融合架构：Elo + Dixon-Coles 泊松 + 蒙特卡洛 + 贝叶斯
数据源：本地 JSON 文件（standings.json / schedule.json）
"""

import json, os, sys, time
from typing import Any

import streamlit as st
import pandas as pd
import numpy as np
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config
import data.local_data as ld
import model.elo_engine as elo
import model.poisson as poisson
import model.monte_carlo as mc
import model.bayesian as bayesian

# ──────────────────────────────────────────────
#  球队元数据（中文名 → 完整信息）
# ──────────────────────────────────────────────
TEAM = {
    "墨西哥": (1,"MEX","CONCACAF",12), "捷克": (2,"CZE","UEFA",35), "南非": (3,"RSA","CAF",60),
    "韩国": (4,"KOR","AFC",28), "加拿大": (5,"CAN","CONCACAF",45), "波黑": (6,"BIH","UEFA",70),
    "卡塔尔": (7,"QAT","AFC",55), "瑞士": (8,"SUI","UEFA",25), "巴西": (9,"BRA","CONMEBOL",3),
    "摩洛哥": (10,"MAR","CAF",18), "海地": (11,"HAI","CONCACAF",80), "苏格兰": (12,"SCO","UEFA",30),
    "美国": (13,"USA","CONCACAF",15), "土耳其": (14,"TUR","UEFA",24), "巴拉圭": (15,"PAR","CONMEBOL",22),
    "澳大利亚": (16,"AUS","AFC",38), "德国": (17,"GER","UEFA",6), "库拉索": (18,"CUW","CONCACAF",99),
    "科特迪瓦": (19,"CIV","CAF",42), "厄瓜多尔": (20,"ECU","CONMEBOL",44), "荷兰": (21,"NED","UEFA",7),
    "瑞典": (22,"SWE","UEFA",27), "日本": (23,"JPN","AFC",20), "突尼斯": (24,"TUN","CAF",75),
    "比利时": (25,"BEL","UEFA",14), "埃及": (26,"EGY","CAF",36), "伊朗": (27,"IRN","AFC",23),
    "新西兰": (28,"NZL","OFC",56), "西班牙": (29,"ESP","UEFA",4), "佛得角": (30,"CPV","CAF",64),
    "沙特阿拉伯": (31,"KSA","AFC",48), "乌拉圭": (32,"URU","CONMEBOL",8), "法国": (33,"FRA","UEFA",2),
    "伊拉克": (34,"IRQ","AFC",72), "塞内加尔": (35,"SEN","CAF",16), "挪威": (36,"NOR","UEFA",41),
    "阿根廷": (37,"ARG","CONMEBOL",1), "阿尔及利亚": (38,"ALG","CAF",58), "奥地利": (39,"AUT","UEFA",29),
    "约旦": (40,"JOR","AFC",68), "葡萄牙": (41,"POR","UEFA",5), "刚果民主共和国": (42,"COD","CAF",67),
    "乌兹别克斯坦": (43,"UZB","AFC",88), "哥伦比亚": (44,"COL","CONMEBOL",21), "英格兰": (45,"ENG","UEFA",9),
    "克罗地亚": (46,"CRO","UEFA",10), "加纳": (47,"GHA","CAF",65), "巴拿马": (48,"PAN","CONCACAF",49),
}
ID2META = {v[0]: (k, v[1], v[2], v[3]) for k, v in TEAM.items()}
CN2ID = {k: v[0] for k, v in TEAM.items()}
FLAG = {
    "MEX":"🇲🇽","CZE":"🇨🇿","RSA":"🇿🇦","KOR":"🇰🇷","CAN":"🇨🇦","BIH":"🇧🇦","QAT":"🇶🇦","SUI":"🇨🇭",
    "BRA":"🇧🇷","MAR":"🇲🇦","HAI":"🇭🇹","SCO":"🏴󠁧󠁢󠁳󠁣󠁴󠁿","USA":"🇺🇸","TUR":"🇹🇷","PAR":"🇵🇾","AUS":"🇦🇺",
    "GER":"🇩🇪","CUW":"🇨🇼","CIV":"🇨🇮","ECU":"🇪🇨","NED":"🇳🇱","SWE":"🇸🇪","JPN":"🇯🇵","TUN":"🇹🇳",
    "BEL":"🇧🇪","EGY":"🇪🇬","IRN":"🇮🇷","NZL":"🇳🇿","ESP":"🇪🇸","CPV":"🇨🇻","KSA":"🇸🇦","URU":"🇺🇾",
    "FRA":"🇫🇷","IRQ":"🇮🇶","SEN":"🇸🇳","NOR":"🇳🇴","ARG":"🇦🇷","ALG":"🇩🇿","AUT":"🇦🇹","JOR":"🇯🇴",
    "POR":"🇵🇹","COD":"🇨🇩","UZB":"🇺🇿","COL":"🇨🇴","ENG":"🏴󠁧󠁢󠁥󠁮󠁧󠁿","CRO":"🇭🇷","GHA":"🇬🇭","PAN":"🇵🇦",
}

st.set_page_config(page_title="2026 世界杯比分预测", page_icon="⚽", layout="wide")
st.markdown("""
<style>
.main-title{font-size:2.5rem;font-weight:bold;text-align:center;color:#f97316;margin-bottom:0}
.subtitle{font-size:1rem;text-align:center;color:#64748b;margin-bottom:2rem}
.analysis-box{background:#1e293b;border-left:4px solid #f97316;padding:1rem;margin:.5rem 0;border-radius:0 8px 8px 0;color:#e2e8f0}
.data-source-badge{display:inline-block;padding:2px 8px;border-radius:12px;font-size:.75rem;font-weight:600}
.source-live{background:#064e3b;color:#34d399}
.source-cache{background:#78350f;color:#fbbf24}
.search-result{background:#1e293b;border:1px solid #334155;border-radius:8px;padding:.8rem;margin:.3rem 0;color:#cbd5e1;font-size:.9rem}
</style>
""", unsafe_allow_html=True)


@st.cache_data(ttl=1800, show_spinner=False)
def search_team_news(team_name, query_type="status"):
    q = {"status":f"{team_name} 世界杯 2026 最新状态 伤病 阵容","recent":f"{team_name} 最近比赛 2026年6月"}.get(query_type,"")
    res = []
    try:
        r = requests.get("https://api.duckduckgo.com/",params={"q":q,"format":"json","no_html":1,"skip_disambig":1},timeout=8)
        d = r.json()
        a = d.get("AbstractText","")
        if a: res.append(f"📰 摘要: {a[:300]}")
        for t in d.get("RelatedTopics",[])[:5]:
            if isinstance(t,dict) and t.get("Text") and len(t["Text"])>20:
                res.append(f"🔗 {t['Text'][:200]}")
    except Exception as e:
        res.append(f"⚠️ 搜索暂不可用: {str(e)[:80]}")
    return res


# ──────────────────────────────────────────────
#  数据加载
# ──────────────────────────────────────────────
def _check_api_for_updates():
    """
    后台检测 juhe API 是否有新赛果。
    策略：用 API 数据 **merge** 到本地，而不是整体覆盖。
      - 只更新 API 中 "完赛" 或 "进行中"（有真实赛果）的比赛
      - 保留本地已手动录入的比赛（本地状态 != "未开赛" 的优先）
      - 同步新增的场次（API 中有但本地没有）
    返回 (updated_count, message)
    """
    try:
        import data.api_client as api
        remote_matches = api.get_matches() or []
        if not remote_matches:
            return 0, "API 返回空数据"

        # ── 1. 用 API 数据构建 merge 后的赛程 ──
        # 索引本地赛程
        local = ld.load_schedule()
        local_by_id = {str(m.get("id")): m for m in local}

        # 判断 API 比赛是否有真实赛果（完赛 或 进行中且有非 0:0 比分）
        def _api_has_real_score(rm):
            md = rm.get("match_des", "")
            hs = rm.get("host_team_score")
            g = rm.get("guest_team_score")
            if hs is None or g is None:
                return False
            if md == "完赛":
                return True
            if md == "进行中":
                return True  # 进行中的也有实时比分
            return False

        # 判断本地是否已手动录入过（非 "未开赛" 状态）
        def _locally_populated(lm):
            if lm is None:
                return False
            return lm.get("match_des") not in ("", None) or lm.get("host_team_score") is not None

        merge_schedule = []
        updated_ids = set()

        # 先用本地全部赛程作为基础
        for lm in local:
            merge_schedule.append(dict(lm))

        # 再用 API 数据 merge
        api_updated_ids = set()
        api_added_ids = set()
        for rm in remote_matches:
            rid = str(rm.get("id", ""))
            api_has_score = _api_has_real_score(rm)
            local_match = local_by_id.get(rid)

            if local_match is not None:
                # 本地已有这场比赛
                local_populated = _locally_populated(local_match)
                if api_has_score and not local_populated:
                    # API 有赛果 + 本地未手动录入 → 用 API 更新
                    local_match["host_team_score"] = rm.get("host_team_score")
                    local_match["guest_team_score"] = rm.get("guest_team_score")
                    local_match["match_des"] = rm.get("match_des", local_match.get("match_des", ""))
                    local_match["match_status"] = rm.get("match_status", local_match.get("match_status", ""))
                    api_updated_ids.add(rid)
                # 否则保留本地数据不动（尊重手动录入）
            else:
                # API 中有但本地没有 → 新增（只加有赛果的或未来赛程都加）
                new_m = {
                    "id": rid,
                    "date": rm.get("date", ""),
                    "date_time": rm.get("date_time", ""),
                    "host_team_id": str(rm.get("host_team_id", "")),
                    "guest_team_id": str(rm.get("guest_team_id", "")),
                    "host_team_name": rm.get("host_team_name", ""),
                    "guest_team_name": rm.get("guest_team_name", ""),
                    "host_team_score": rm.get("host_team_score", ""),
                    "guest_team_score": rm.get("guest_team_score", ""),
                    "host_team_penalty_score": rm.get("host_team_penalty_score", ""),
                    "guest_team_penalty_score": rm.get("guest_team_penalty_score", ""),
                    "match_status": rm.get("match_status", ""),
                    "match_des": rm.get("match_des", ""),
                    "match_type_name": rm.get("match_type_name", ""),
                    "match_type_des": rm.get("match_type_des", ""),
                    "group_name": rm.get("group_name", ""),
                    "host_team_logo_url": rm.get("host_team_logo_url", ""),
                    "guest_team_logo_url": rm.get("guest_team_logo_url", ""),
                }
                merge_schedule.append(new_m)
                api_added_ids.add(rid)

        # 保存 merge 后的赛程
        ld.save_schedule(merge_schedule)

        # ── 2. 重算积分榜 ──
        standings = ld.recalculate_standings(merge_schedule)
        ld.save_standings(standings)

        # ── 3. 构建返回信息 ──
        update_count = len(api_updated_ids) + len(api_added_ids)
        parts = []
        if api_updated_ids:
            parts.append(f"更新 {len(api_updated_ids)} 场（API有新赛果）")
        if api_added_ids:
            parts.append(f"新增 {len(api_added_ids)} 场")
        if not parts:
            return 0, "数据已是最新，手动录入已保留"
        return update_count, "、".join(parts)

    except Exception as e:
        return 0, f"API 检测失败: {str(e)[:100]}"


def _auto_sync_if_needed():
    """
    检查距离上次自动同步是否超过阈值，若是则后台拉 API。
    结果写入 st.session_state["_api_last_check"] 供 UI 显示。
    """
    import time as _time
    now = _time.time()
    last = st.session_state.get("_last_auto_sync", 0)
    interval = st.session_state.get("_auto_sync_interval", 1800)  # 默认 30 分钟
    if now - last < interval:
        return  # 还没到间隔，跳过
    st.session_state["_last_auto_sync"] = now
    cnt, msg = _check_api_for_updates()
    ts = pd.Timestamp.now().strftime("%H:%M")
    if cnt > 0:
        st.session_state["_api_last_check"] = f"{ts}（+{cnt}场）"
        st.session_state["_api_new_data"] = True  # 标记有新数据，下次 rerun 刷新
    else:
        st.session_state["_api_last_check"] = ts


@st.cache_data(ttl=60, show_spinner=False)
def load_all_data():
    raw = ld.load_all()                       # {"standings":[...],"schedule":[...],"teams":[...]}
    # 兼容两种 key 名：schedule 或 matches
    matches = raw.get("schedule") or raw.get("matches") or []

    # 确保 standings 是最新的：根据赛程重算
    standings = ld.recalculate_standings(matches)   # 直接从比赛列表算积分
    raw["standings"] = standings

    # Elo — 内置元数据初始化
    engine = elo.EloEngine()
    for cn_, (tid, code, cont, rank) in TEAM.items():
        # 检测东道主身份
        is_host = tid in config.HOST_TEAM_IDS if hasattr(config, 'HOST_TEAM_IDS') else False
        engine.set_team(tid, cn_, "", fifa_rank=rank, continent=cont,
                        is_defending_champion=(code == "FRA"),
                        is_host_nation=is_host)
    name2id = {cn_: tid for cn_, (tid, *_) in TEAM.items()}
    for m in matches:
        if m.get("match_des") != "完赛":
            continue
        hg, ag = m.get("host_team_score"), m.get("guest_team_score")
        if hg is None or ag is None:
            continue
        hid = m.get("host_team_id") or name2id.get(m.get("host_team_name", ""))
        aid = m.get("guest_team_id") or name2id.get(m.get("guest_team_name", ""))
        if hid and aid:
            try:
                stage, is_ko = _detect_stage_and_knockout(m)
                engine.update_after_match(int(hid), int(aid), int(hg), int(ag), stage=stage)
            except Exception:
                pass
    raw["elo"] = engine
    raw["matches"] = matches   # 保证下游 render_xxx(data) 能拿到数据
    return raw


def flag(cn_name):
    meta = TEAM.get(cn_name)
    return FLAG.get(meta[1],"🏳️") if meta else "🏳️"


def gid(name):
    """中文名或英文名 → ID（对齐 schedule.json 的官方 ID）"""
    # 1. 中文名直接查
    if name in CN2ID: return CN2ID[name]
    # 2. 遍历 TEAM 字典，用FIFA code 或英文名匹配
    for cn_, (tid, code, cont, rank) in TEAM.items():
        if name == cn_ or name == code or name == code.upper():
            return tid
    # 3. 在赛程中出现的名称（可能拼写略有不同），通过赛程 team_id 反查
    try:
        for m in ld.load_schedule():
            if m.get("host_team_name") == name or m.get("guest_team_name") == name:
                hid = m.get("host_team_id")
                aid = m.get("guest_team_id")
                team_id = hid if m.get("host_team_name") == name else aid
                if str(team_id) != "0":
                    return int(team_id)
    except Exception:
        pass
    # 4. 最后通过 ID2META 遍历查找
    for tid, (cn_, code, cont, rank) in ID2META.items():
        if name in (cn_, code, code.upper()):
            return tid
    return None


# ──────────────────────────────────────────────
#  Tab 1 — 积分榜
# ──────────────────────────────────────────────
def render_standings(data):
    st.header("📊 小组赛积分榜")
    stnc = data.get("standings") or []
    if not stnc:
        st.warning("⚠️ 暂无积分榜数据，请在「数据管理」中录入比赛结果")
        return
    groups = sorted({s["team_group"] for s in stnc})
    c1,c2,c3 = st.columns(3)
    c1.metric("参赛球队", f"{len(stnc)} 支")
    c2.metric("小组数", f"{len(groups)} 个")
    c3.metric("数据源", "本地数据")
    for g in groups:
        gt = sorted([s for s in stnc if s["team_group"]==g], key=lambda x:int(x.get("rank",99)))
        st.subheader(f"组 {g}")
        rows = []
        for t in gt:
            n = t["team_name"]
            p = int(t["win"])+int(t["draw"])+int(t["lose"])
            gd = int(t["goal"])-int(t["miss_goal"])
            rows.append({"":flag(n),"排名":t["rank"],"球队":n,"赛":p,
                         "胜":t["win"],"平":t["draw"],"负":t["lose"],
                         "净":f"+{gd}" if gd>0 else str(gd),"积分":t["score"]})
        st.table(pd.DataFrame(rows).set_index("排名"))


# ──────────────────────────────────────────────
#  Tab 2 — 淘汰赛
# ──────────────────────────────────────────────
def _resolve_knockout_placeholders(matches, standings):
    """
    解析淘汰赛中的占位符（如 A2, B2, C1 等）为实际球队名。
    占位符格式: {组别}{名次}，如 A2 = A组第2名
    淘汰赛赛程中 4 个最佳小组第3名的占位符格式: A3/B3/C3/D3/F3 (按积分排序取前4)
    """
    # 构建组别排名映射 group -> [(team_name, rank), ...]
    group_rankings = {}
    for s in standings:
        g = s.get("team_group", "")
        if not g:
            continue
        group_rankings.setdefault(g, []).append(s)

    # 每组内按 rank 排序
    for g in group_rankings:
        group_rankings[g].sort(key=lambda x: int(x.get("rank", "99") or "99"))

    # 手动映射占位符 -> 实际球队名
    resolved = {}
    placeholder_map = {
        "A1": _get_team(group_rankings, "A", 1),
        "A2": _get_team(group_rankings, "A", 2),
        "A3": _get_team(group_rankings, "A", 3),
        "B1": _get_team(group_rankings, "B", 1),
        "B2": _get_team(group_rankings, "B", 2),
        "B3": _get_team(group_rankings, "B", 3),
        "C1": _get_team(group_rankings, "C", 1),
        "C2": _get_team(group_rankings, "C", 2),
        "C3": _get_team(group_rankings, "C", 3),
        "D1": _get_team(group_rankings, "D", 1),
        "D2": _get_team(group_rankings, "D", 2),
        "D3": _get_team(group_rankings, "D", 3),
        "E1": _get_team(group_rankings, "E", 1),
        "E2": _get_team(group_rankings, "E", 2),
        "E3": _get_team(group_rankings, "E", 3),
        "F1": _get_team(group_rankings, "F", 1),
        "F2": _get_team(group_rankings, "F", 2),
        "F3": _get_team(group_rankings, "F", 3),
        "G1": _get_team(group_rankings, "G", 1),
        "G2": _get_team(group_rankings, "G", 2),
        "G3": _get_team(group_rankings, "G", 3),
        "H1": _get_team(group_rankings, "H", 1),
        "H2": _get_team(group_rankings, "H", 2),
        "H3": _get_team(group_rankings, "H", 3),
        "I1": _get_team(group_rankings, "I", 1),
        "I2": _get_team(group_rankings, "I", 2),
        "I3": _get_team(group_rankings, "I", 3),
        "J1": _get_team(group_rankings, "J", 1),
        "J2": _get_team(group_rankings, "J", 2),
        "J3": _get_team(group_rankings, "J", 3),
        "K1": _get_team(group_rankings, "K", 1),
        "K2": _get_team(group_rankings, "K", 2),
        "K3": _get_team(group_rankings, "K", 3),
        "L1": _get_team(group_rankings, "L", 1),
        "L2": _get_team(group_rankings, "L", 2),
        "L3": _get_team(group_rankings, "L", 3),
    }

    # 先填充单个占位符
    for m in matches:
        h_name = m.get("host_team_name", "")
        a_name = m.get("guest_team_name", "")

        # 解析主队占位符
        if h_name in placeholder_map and placeholder_map[h_name]:
            m["host_team_name"] = placeholder_map[h_name]
        # 解析客队占位符（可能是复合的，如 "A3/B3/C3/D3/F3"）
        if a_name in placeholder_map and placeholder_map[a_name]:
            m["guest_team_name"] = placeholder_map[a_name]

    # 处理复合占位符（4 个最佳小组第3名）
    # 收集所有小组第3名，按积分排序取前4
    all_third_place = []
    for g in sorted(group_rankings.keys()):
        teams_in_group = group_rankings[g]
        if len(teams_in_group) >= 3:
            third = teams_in_group[2]
            all_third_place.append({
                "group": g,
                "name": third.get("team_name", ""),
                "score": int(third.get("score", "0") or "0"),
                "gd": int(third.get("goal", "0") or "0") - int(third.get("miss_goal", "0") or "0"),
                "goals": int(third.get("goal", "0") or "0"),
            })

    # 先按小组顺序分配，再处理 "4 个最佳第3名" 的占位符
    best_third_names = set()
    if len(all_third_place) >= 4:
        # 按积分、净胜球、进球数排序取前4
        all_third_place.sort(key=lambda x: (-x["score"], -x["gd"], -x["goals"]))
        best_third_names = {t["name"] for t in all_third_place[:4]}

    # 复合占位符映射（4个最佳小组第3名的可能组合）
    # 2026世界杯1/16决赛有4个最佳小组第3名席位
    # 这些席位可能来自 C/D/E/F/G/H/I/J/K 组（取决于哪些组有第3名晋级）
    compound_placeholders = {
        "A3/B3/C3/D3/F3": lambda: _pick_best_third(all_third_place, "F", best_third_names),
        "C3/D3/F3/G3/H3": lambda: _pick_best_third(all_third_place, "H", best_third_names),
        "A3/E3/H3/I3/J3": lambda: _pick_best_third(all_third_place, "J", best_third_names),
        "E3/H3/I3/J3/K3": lambda: _pick_best_third(all_third_place, "K", best_third_names),
        "A3/B3/E3/F3/I3/J3/K3": lambda: _pick_best_third(all_third_place, "K", best_third_names),
        "B3/E3/F3/I3/J3": lambda: _pick_best_third(all_third_place, "J", best_third_names),
        "D3/E3/I3/J3/L3": lambda: _pick_best_third(all_third_place, "L", best_third_names),
        "E3/F3/G3/I3/J3": lambda: _pick_best_third(all_third_place, "J", best_third_names),
        "A3/E3/F3/H3/I3/J3": lambda: _pick_best_third(all_third_place, "J", best_third_names),
        "C3/E3/F3/H3/I3": lambda: _pick_best_third(all_third_place, "I", best_third_names),
        "B3/C3/D3/E3/F3": lambda: _pick_best_third(all_third_place, "F", best_third_names),
        "G3/H3/I3/J3/K3": lambda: _pick_best_third(all_third_place, "K", best_third_names),
        "A3/B3/C3/D3/E3/F3/G3/H3/I3/J3/K3": lambda: _pick_best_third(all_third_place, "K", best_third_names),
    }

    for m in matches:
        h_name = m.get("host_team_name", "")
        a_name = m.get("guest_team_name", "")

        # 处理复合占位符
        if h_name in compound_placeholders:
            resolved_name = compound_placeholders[h_name]()
            if resolved_name:
                m["host_team_name"] = resolved_name
        if a_name in compound_placeholders:
            resolved_name = compound_placeholders[a_name]()
            if resolved_name:
                m["guest_team_name"] = resolved_name

    return matches


def _get_team(group_rankings, group, rank):
    """获取指定组别的指定名次球队名"""
    teams = group_rankings.get(group, [])
    idx = rank - 1  # rank 1 = index 0
    if 0 <= idx < len(teams):
        return teams[idx].get("team_name", "")
    return ""


def _pick_best_third(all_third_place, exclude_group, best_third_names):
    """从最佳第3名中选择一个（排除指定组）"""
    for t in all_third_place:
        if t["name"] in best_third_names and t["group"] != exclude_group:
            return t["name"]
    # fallback: 任意一个最佳第3
    for t in all_third_place:
        if t["name"] in best_third_names:
            return t["name"]
    return ""


def render_knockout(data):
    st.header("🏆 淘汰赛对阵图")
    matches = data.get("matches") or []
    standings = data.get("standings") or []
    stages = {"1/16决赛":[],"1/8决赛":[],"1/4决赛":[],"半决赛":[],"季军战":[],"决赛":[]}
    for m in matches:
        name = m.get("match_type_name","")
        if "1/16" in name: stages["1/16决赛"].append(m)
        elif "1/8" in name: stages["1/8决赛"].append(m)
        elif "1/4" in name or "四分之一" in name: stages["1/4决赛"].append(m)
        elif "半决赛" in name: stages["半决赛"].append(m)
        elif "季军" in name: stages["季军战"].append(m)
        elif "决赛" in name: stages["决赛"].append(m)

    has_r16 = bool(stages["1/16决赛"])
    if not has_r16:
        st.info("淘汰赛数据暂未开放（需小组赛结束后更新）")
        return

    # 解析占位符为实际球队
    r16_matches = stages["1/16决赛"]
    all_knockout = []
    for stage_ms in stages.values():
        all_knockout.extend(stage_ms)
    _resolve_knockout_placeholders(all_knockout, standings)

    # 检查是否仍有未解析的占位符
    unresolved = [m for m in r16_matches if not m.get("host_team_name", "") or m["host_team_name"].startswith(("A","B","C","D","E","F","G","H","I","J","K","L")) and len(m["host_team_name"]) <= 3]
    if unresolved:
        st.info("⏳ 部分淘汰赛球队尚未确定，请先完成小组赛数据录入")

    for stage, ms in stages.items():
        if ms:
            f = sum(1 for x in ms if x.get("match_des")=="完赛")
            st.caption(f"{stage}: {len(ms)}场 (已赛{f})")

    r16 = stages["1/16决赛"]
    def _col(c,title,ms):
        with c:
            st.markdown(f"**{title}**")
            for m in ms: _badge(m)
    def _badge(m):
        h,a = m.get("host_team_name","?"),m.get("guest_team_name","?")
        hs,gs = m.get("host_team_score",""),m.get("guest_team_score","")
        if m.get("match_des")=="完赛" and hs is not None and gs is not None:
            st.markdown(f'{flag(h)} **{h} {hs}:{gs} {a}** {flag(a)}')
        else:
            st.markdown(f'{flag(h)} {h} vs {a} {flag(a)}')

    st.markdown("### 🌳 上半区")
    c1,c2,c3,c4 = st.columns(4)
    _col(c1,"1/16 决赛",r16[:8])
    _col(c2,"1/8 决赛",stages["1/8决赛"][:4])
    _col(c3,"1/4 决赛",stages["1/4决赛"][:2])
    _col(c4,"半决赛",stages["半决赛"][:1])
    st.divider()
    st.markdown("### 🌳 下半区")
    c1,c2,c3,c4 = st.columns(4)
    _col(c1,"1/16 决赛",r16[8:])
    _col(c2,"1/8 决赛",stages["1/8决赛"][4:])
    _col(c3,"1/4 决赛",stages["1/4决赛"][2:])
    _col(c4,"半决赛",stages["半决赛"][1:])
    st.divider()
    st.markdown("### 🏅 三四名 & 决赛")
    c1,c2 = st.columns(2)
    with c1:
        st.markdown("**季军战**")
        for m in stages["季军战"]: _badge(m)
    with c2:
        st.markdown("**决赛**")
        for m in stages["决赛"]: _badge(m)


# ──────────────────────────────────────────────
#  Tab 3 — 比赛分析
# ──────────────────────────────────────────────
def _do_analysis(hid, aid, engine, hn, an, oh, od, oa, stage, extra,
                  is_knockout=False, motivation_home=1.0, motivation_away=1.0,
                  use_market_odds=False):
    """
    多维度分析 — 返回结构化字典，每个维度一个独立区块。

    Returns:
        {
            "elo": {...},
            "poisson": {...},
            "monte_carlo": {...},
            "bayesian": {...} | None,
            "kelly": {...} | None,
            "prediction": str,
            "environment": {...} | None,
            "extra": str | None,
        }
    """
    hid = int(hid) if hid else None
    aid = int(aid) if aid else None

    result = {}

    # ── 1. Elo 维度 ──
    eh = engine.get_rating(hid) or 1500
    ea = engine.get_rating(aid) or 1500
    eh_adj = engine.teams[hid].get_adjusted_rating(engine.teams.get(aid), True) if hid in engine.teams else eh
    ea_adj = engine.teams[aid].get_adjusted_rating(engine.teams.get(hid), False) if aid in engine.teams else ea
    exp = engine.simulate_match(hid, aid)
    diff = int(round(eh - ea))
    adv = "主队占优" if diff > 25 else ("客队占优" if diff < -25 else "势均力敌")

    result["elo"] = {
        "home_rating": round(eh, 0),
        "away_rating": round(ea, 0),
        "home_adjusted": round(eh_adj, 0),
        "away_adjusted": round(ea_adj, 0),
        "diff": diff,
        "advantage": adv,
        "home_win": exp["home_win"],
        "draw": exp["draw"],
        "away_win": exp["away_win"],
    }

    # ── 2. 泊松维度 ──
    lh, la = poisson.calc_expected_goals(
        hid, aid, engine,
        stage=stage,
        motivation_home=motivation_home,
        motivation_away=motivation_away)
    result["poisson"] = {
        "lambda_home": round(lh, 3),
        "lambda_away": round(la, 3),
        "expected_total": round(lh + la, 2),
        "stage_avg_goals": stage,
        "motivation_home": motivation_home,
        "motivation_away": motivation_away,
    }

    # ── 3. 蒙特卡洛维度 ──
    env = _build_match_environment(hid, aid, hn, an)
    sim = mc.Simulator(n_sim=5000).run_detailed(lh, la, env,
                                                 is_knockout=is_knockout)
    mc_hw = sim.get("final_home_win", sim["home_win"]) if is_knockout else sim["home_win"]
    mc_aw = sim.get("final_away_win", sim["away_win"]) if is_knockout else sim["away_win"]
    mc_dr = sim.get("final_draw", sim["draw"]) if is_knockout else sim["draw"]

    top = sim.get("top_scorelines", [])
    result["monte_carlo"] = {
        "home_win": round(mc_hw, 4),
        "draw": round(mc_dr, 4),
        "away_win": round(mc_aw, 4),
        "top_scorelines": top[:5],
        "total_goals_avg": round(lh + la, 2),
        "is_knockout": is_knockout,
        "lambda_home_used": round(sim.get("lambda_home", lh), 3),
        "lambda_away_used": round(sim.get("lambda_away", la), 3),
    }

    # 加时/点球信息
    if is_knockout:
        if sim.get("extra_time"):
            et = sim["extra_time"]
            result["monte_carlo"]["extra_time"] = {
                "home_win_pct": et.get("home_win", 0),
                "draw_pct": et.get("draw", 0),
                "goals_dist": et.get("goals_distribution", {}),
            }
        if sim.get("penalty_shootout"):
            ps = sim["penalty_shootout"]
            result["monte_carlo"]["penalty_shootout"] = {
                "home_win_pct": ps.get("home_win", 0),
                "away_win_pct": ps.get("away_win", 0),
                "draw_after_5": ps.get("draw_after_5", 0),
                "avg_home_pen": ps.get("avg_home_penalties", 0),
                "avg_away_pen": ps.get("avg_away_penalties", 0),
            }

    # ── 4. 贝叶斯融合维度 ──
    result["bayesian"] = None
    if use_market_odds and oh and od and oa:
        try:
            mp = bayesian.calc_market_implied_prob(float(oh), float(od), float(oa))
            model_confidence = min(0.6 + abs(exp["home_win"] - 0.5) * 0.5, 0.9)
            fu = bayesian.bayesian_fusion(
                {"home_win": exp["home_win"], "draw": exp["draw"], "away_win": exp["away_win"]},
                mp, stage, model_confidence)
            result["bayesian"] = {
                "home_win": fu["home_win"],
                "draw": fu["draw"],
                "away_win": fu["away_win"],
                "confidence": fu["confidence"],
                "weight_model": fu["weight_model"],
                "weight_market": fu["weight_market"],
                "market_implied": mp,
            }
        except Exception:
            pass

    # ── 5. Kelly 维度 ──
    result["kelly"] = None
    try:
        import strategy.kelly as km
        if oh and float(oh) > 1.01:
            si = km.calc_match_stake(exp["home_win"], float(oh), 0.5, "A")
            result["kelly"] = {
                "recommendation": si["recommendation"],
                "stake_pct": round(si["adjusted_stake"] * 100, 2),
                "raw_kelly": si["raw_kelly"],
                "edge": si["edge"],
                "model_prob": si["model_prob"],
                "market_prob": si["market_prob"],
            }
    except Exception:
        pass

    # ── 6. 综合预测（融合所有维度）──
    pred_parts = []

    # 6.1 Elo 实力判断
    ew = exp["home_win"]
    ed = exp["draw"]
    ea = exp["away_win"]
    elo_diff = eh - ea
    if elo_diff > 80:
        pred_parts.append(f"🏠 {hn} 实力明显占优（Elo差 {elo_diff:+.0f}）")
    elif elo_diff > 40:
        pred_parts.append(f"🏠 {hn} 实力占优（Elo差 {elo_diff:+.0f}）")
    elif elo_diff < -80:
        pred_parts.append(f"✈️ {an} 实力明显占优（Elo差 {elo_diff:+.0f}）")
    elif elo_diff < -40:
        pred_parts.append(f"✈️ {an} 实力占优（Elo差 {elo_diff:+.0f}）")
    else:
        pred_parts.append("⚖️ 两队实力接近")

    # 6.2 泊松期望进球判断
    total_goals = lh + la
    if total_goals > 2.8:
        pred_parts.append(f"🔥 预计进球较多（{total_goals:.1f}球）")
    elif total_goals < 1.8:
        pred_parts.append(f"🛡️ 预计进球偏少（{total_goals:.1f}球）")
    else:
        pred_parts.append(f"⚽ 预计进球适中（{total_goals:.1f}球）")

    # 6.3 蒙特卡洛最可能比分
    if top:
        best_score = top[0]
        pred_parts.append(f"🎯 最可能比分 {best_score['score']}（{best_score['probability']}%）")

    # 6.4 动机因子影响
    if abs(motivation_home - 1.0) > 0.05 or abs(motivation_away - 1.0) > 0.05:
        mot_lines = []
        if motivation_home > 1.05:
            mot_lines.append(f"{hn}战意高涨")
        elif motivation_home < 0.95:
            mot_lines.append(f"{hn}战意一般")
        if motivation_away > 1.05:
            mot_lines.append(f"{an}战意高涨")
        elif motivation_away < 0.95:
            mot_lines.append(f"{an}战意一般")
        if mot_lines:
            pred_parts.append(f"💪 {' / '.join(mot_lines)}")

    # 6.5 市场赔率融合判断
    if result.get("bayesian"):
        bay = result["bayesian"]
        bw = bay["home_win"]
        bd = bay["draw"]
        ba = bay["away_win"]
        conf = bay["confidence"]
        # 模型 vs 市场分歧
        model_home = exp["home_win"]
        market_home = bay["market_implied"]["home_win"]
        diff_mm = model_home - market_home
        if abs(diff_mm) > 0.08:
            if diff_mm > 0:
                pred_parts.append(f"📈 模型看好{hn}（模型{model_home:.1%} vs 市场{market_home:.1%}）")
            else:
                pred_parts.append(f"📉 市场看好{hn}（市场{market_home:.1%} vs 模型{model_home:.1%}）")
        if conf > 0.7:
            pred_parts.append(f"✅ 融合置信度高（{conf:.0%}）")
        elif conf < 0.4:
            pred_parts.append(f"⚠️ 融合置信度低（{conf:.0%}），建议谨慎")

    # 6.6 Kelly 仓位建议
    if result.get("kelly"):
        kel = result["kelly"]
        rec = kel["recommendation"]
        edge = kel["edge"]
        if rec in ("轻仓", "中仓", "重仓"):
            pred_parts.append(f"💰 Kelly建议{rec}（edge {edge:+.1%}）")
        elif rec == "观望":
            pred_parts.append(f"👀 Kelly建议观望（edge {edge:+.1%}）")

    # 6.7 淘汰赛加时提示
    if is_knockout:
        if ed > 0.25:
            pred_parts.append(f"⏱️ 淘汰赛平局概率{ed:.1%}，可能进入加时")
        if sim.get("extra_time") and sim["extra_time"].get("draw_pct", 0) > 30:
            pred_parts.append("🎯 加时后仍可能点球决胜")

    # 6.8 环境因素
    if env.is_water_break:
        pred_parts.append("💧 补水机制激活（高温）")
    if env.venue_altitude > 1500:
        pred_parts.append(f"⛰️ 高海拔场地（{env.venue_altitude}m）")
    if env.is_rain:
        pred_parts.append("🌧️ 雨天作战")
    if abs(env.timezone_diff_hours) > 3:
        pred_parts.append(f"🕐 时差影响（{env.timezone_diff_hours:.0f}h）")

    result["prediction"] = "\n".join(pred_parts) if pred_parts else "❓ 数据不足，无法给出综合预测"

    # ── 7. 环境因素摘要 ──
    result["environment"] = {
        "temperature": env.temperature,
        "altitude": env.venue_altitude,
        "is_rain": env.is_rain,
        "timezone_diff": env.timezone_diff_hours,
        "is_water_break": env.is_water_break,
        "is_high_stakes": env.is_high_stakes,
        "home_tactical": env.home_tactical_style,
        "away_tactical": env.away_tactical_style,
    }

    # ── 8. 实时情报 ──
    result["extra"] = extra

    return result


def _build_match_environment(hid, aid, hn, an) -> mc.MatchEnvironment:
    """
    构建比赛环境 — 从球队信息推断环境参数。
    默认返回中性环境，可由外部调用覆盖。
    """
    # 检测东道主球队（根据球队名中的关键词）
    host_keywords_home = {
        "Mex": "Mexico", "USA": "USA", "United States": "USA", "US": "USA",
        "Canada": "Canada", "CAN": "Canada",
    }
    host_nation_home = ""
    host_nation_away = ""
    for kw, nation in host_keywords_home.items():
        if kw in hn:
            host_nation_home = nation
        if kw in an:
            host_nation_away = nation

    # 2026 世界杯举办国：美国/墨西哥/加拿大 → 无需额外旅行
    is_host_match = bool(host_nation_home or host_nation_away)

    # 补水机制：高温天气
    is_water_break = False  # 默认关闭，可由外部设置

    return mc.MatchEnvironment(
        home_team_id=hid or 0,
        away_team_id=aid or 0,
        venue_altitude=0,
        temperature=22,
        is_rain=False,
        home_travel_distance_km=0,
        home_rest_days=7,
        home_days_since_last=7,
        is_high_stakes=False,
        is_water_break=is_water_break,
    )


def _render_analysis_card(data: dict):
    """
    渲染多维度分析卡片 — 每个维度一个独立区块
    """
    if not data:
        return

    # ── 1. Elo 实力对比 ──
    elo = data.get("elo", {})
    if elo:
        st.markdown("**📊 Elo 实力对比**")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric(f"主队评分", f"{elo.get('home_rating', '?'):.0f}")
        c2.metric(f"客队评分", f"{elo.get('away_rating', '?'):.0f}")
        c3.metric("差值", f"{elo.get('diff', 0):+d}")
        c4.metric("优势方", elo.get("advantage", "势均力敌"))

        # Elo 预测概率条
        hw = elo.get("home_win", 0)
        dr = elo.get("draw", 0)
        aw = elo.get("away_win", 0)
        st.progress(hw, text=f"主胜 {hw:.1%}")
        st.progress(dr, text=f"平   {dr:.1%}")
        st.progress(aw, text=f"客胜 {aw:.1%}")
        st.caption("")
    
    # ── 2. 泊松期望进球 ──
    pois = data.get("poisson", {})
    if pois:
        st.markdown("**⚽ Dixon-Coles 泊松模型**")
        c1, c2, c3 = st.columns(3)
        c1.metric(f"主队 λ", f"{pois.get('lambda_home', '?'):.3f}")
        c2.metric(f"客队 λ", f"{pois.get('lambda_away', '?'):.3f}")
        c3.metric("总期望进球", f"{pois.get('expected_total', '?'):.2f}")
        mh = pois.get("motivation_home", 1.0)
        ma = pois.get("motivation_away", 1.0)
        if abs(mh - 1.0) > 0.01 or abs(ma - 1.0) > 0.01:
            st.caption(f"动机因子: 主队×{mh:.2f} / 客队×{ma:.2f}")

    # ── 3. 蒙特卡洛模拟 ──
    mc = data.get("monte_carlo", {})
    if mc:
        st.markdown("**🎲 蒙特卡洛模拟 (5000次)**")
        hw = mc.get("home_win", 0)
        dr = mc.get("draw", 0)
        aw = mc.get("away_win", 0)
        st.progress(hw, text=f"主胜 {hw:.1%}")
        if mc.get("is_knockout"):
            st.progress(dr, text=f"平(进加时) {dr:.1%}")
        else:
            st.progress(dr, text=f"平   {dr:.1%}")
        st.progress(aw, text=f"客胜 {aw:.1%}")

        top = mc.get("top_scorelines", [])
        if top:
            top_str = " | ".join(f'{s["score"]} ({s["probability"]}%)' for s in top[:5])
            st.caption(f"最可能比分: {top_str}")

        # 加时赛信息
        if mc.get("extra_time"):
            et = mc["extra_time"]
            with st.expander("⏱️ 加时赛模拟"):
                c1, c2 = st.columns(2)
                c1.metric("加时主胜", f"{et.get('home_win_pct', 0):.1f}%")
                c2.metric("加时平局→点球", f"{et.get('draw_pct', 0):.1f}%")
                st.caption(f"加时平均进球: 主{et.get('avg_goals_home',0)} 客{et.get('avg_goals_away',0)}")

        # 点球大战信息
        if mc.get("penalty_shootout"):
            ps = mc["penalty_shootout"]
            with st.expander("🎯 点球大战模拟"):
                c1, c2 = st.columns(2)
                c1.metric("点球主胜", f"{ps.get('home_win_pct', 0):.1f}%")
                c2.metric("点球客胜", f"{ps.get('away_win_pct', 0):.1f}%")
                st.caption(f"平均进球: 主{ps.get('avg_home_pen',0)} 客{ps.get('avg_away_pen',0)}")

    # ── 4. 贝叶斯融合 ──
    bayes = data.get("bayesian")
    if bayes:
        st.markdown("**🔗 贝叶斯融合**")
        c1, c2, c3 = st.columns(3)
        c1.metric("融合主胜", f"{bayes.get('home_win', 0):.1%}")
        c2.metric("融合平局", f"{bayes.get('draw', 0):.1%}")
        c3.metric("融合客胜", f"{bayes.get('away_win', 0):.1%}")
        st.caption(f"模型权重 {bayes.get('weight_model',0):.0%} / 市场权重 {bayes.get('weight_market',0):.0%} | 置信度 {bayes.get('confidence',0):.1%}")

    # ── 5. Kelly 仓位 ──
    kelly = data.get("kelly")
    if kelly:
        st.markdown("**💰 Kelly 仓位**")
        k1, k2 = st.columns(2)
        rec = kelly.get("recommendation", "跳过")
        stake = kelly.get("stake_pct", 0)
        color = "🟢" if rec in ("中仓", "重仓") else ("🟡" if rec == "轻仓" else "🔴")
        k1.metric("建议", f"{color} {rec}")
        k2.metric("仓位", f"{stake:.2f}%")
        edge = kelly.get("edge", 0)
        if abs(edge) > 0.01:
            st.caption(f"Edge: {edge:+.1%}")

    # ── 6. 综合预测 ──
    pred = data.get("prediction", "")
    if pred:
        st.info(f"**📌 综合预测**: {pred}")

    # ── 7. 环境因素 ──
    env = data.get("environment", {})
    if env and any(v for k, v in env.items() if k != "home_tactical"):
        with st.expander("🌍 环境因素"):
            env_lines = []
            if env.get("temperature", 22) > 28:
                env_lines.append(f"🌡️ 高温 {env['temperature']}°C（补水机制已激活）")
            if env.get("altitude", 0) > 1500:
                env_lines.append(f"⛰️ 海拔 {env['altitude']}m")
            if env.get("is_rain"):
                env_lines.append("🌧️ 有雨")
            if abs(env.get("timezone_diff", 0)) > 2:
                env_lines.append(f"🕐 时差 {env['timezone_diff']:.0f}h")
            if env.get("is_high_stakes"):
                env_lines.append("🔥 大赛高压")
            if env.get("home_tactical") and env.get("away_tactical"):
                env_lines.append(f"⚔️ 战术: {env['home_tactical']} vs {env['away_tactical']}")
            for line in env_lines:
                st.markdown(f"  {line}")

    # ── 8. 实时情报 ──
    extra = data.get("extra")
    if extra:
        with st.expander("🌐 实时情报"):
            st.markdown(f'<div class="search-result">{extra}</div>', unsafe_allow_html=True)


def _detect_stage_and_knockout(match):
    """
    根据比赛信息判断阶段和是否淘汰赛。
    返回 (stage, is_knockout)
    """
    match_type = match.get("match_type_name", "")
    if "小组赛" in match_type or "group" in match_type.lower():
        return "group_stage", False
    elif "1/16" in match_type:
        return "round_of_16", True
    elif "1/8" in match_type:
        return "quarter_final", True  # 简化为 quarter_final 阶段
    elif "1/4" in match_type or "四分之一" in match_type:
        return "quarter_final", True
    elif "半决赛" in match_type:
        return "semi_final", True
    elif "决赛" in match_type:
        return "final", True
    elif "季军" in match_type:
        return "semi_final", True  # 季军战按 semi_final 处理
    return "group_stage", False


def _estimate_motivation(match, standings, hid, aid):
    """
    估算小组赛末轮动机因子。
    Returns: (motivation_home, motivation_away)
    """
    # 默认正常动机
    mh = config.MOTIVATION_NORMAL
    ma = config.MOTIVATION_NORMAL

    # 仅对小组赛有效
    stage, is_knockout = _detect_stage_and_knockout(match)
    if is_knockout or not standings:
        return mh, ma

    group = match.get("group_name", "")
    if not group:
        return mh, ma

    # 找出两队的当前积分
    group_standings = [s for s in standings if s.get("team_group") == group]
    group_standings.sort(key=lambda x: (-int(x.get("score", "0") or "0"),
                                          -(int(x.get("goal", "0") or "0") - int(x.get("miss_goal", "0") or "0"))))

    def _team_score(tid):
        for s in group_standings:
            if str(s.get("id", "")) == str(tid) or s.get("team_name", "") == tid:
                return int(s.get("score", "0") or "0")
        return -1

    score_h = _team_score(hid)
    score_a = _team_score(aid)

    # 简单判断
    if score_h < 0 or score_a < 0:
        return mh, ma  # 找不到积分信息

    # 已确定出线（ >= 4 分通常大概率）
    if score_h >= 4:
        mh = config.MOTIVATION_QUALIFIED  # 可能轮换
    if score_a >= 4:
        ma = config.MOTIVATION_QUALIFIED

    # 已确定淘汰（0-1分）
    if score_h <= 0 and match.get("match_type_des", "") == "第3轮":
        mh = config.MOTIVATION_ELIMINATED
    if score_a <= 0 and match.get("match_type_des", "") == "第3轮":
        ma = config.MOTIVATION_ELIMINATED

    # 最后一轮生死战（双方都在 1-3 分之间）
    if match.get("match_type_des", "") == "第3轮" and score_h <= 3 and score_a <= 3:
        mh = max(mh, config.MOTIVATION_GROUP_DECIDER)
        ma = max(ma, config.MOTIVATION_GROUP_DECIDER)

    return mh, ma


def render_predictions(data):
    st.header("🔮 比赛分析")
    matches = data.get("matches") or []
    engine = data.get("elo")
    standings = data.get("standings") or []
    done = [m for m in matches if m.get("match_des") == "完赛"]
    todo = [m for m in matches if m.get("match_des") != "完赛"]

    # 搜索增强开关从全局侧边栏读取
    srch = st.session_state.get("search_enhanced", False)

    t1, t2, t3 = st.tabs([
        f"📺 已完赛 ({len(done)})",
        f"🔮 未赛预测 ({len(todo)})",
        f"📥 赔率导入"
    ])

    # ── Tab 1: 已完赛 ──
    with t1:
        if not done:
            st.info("暂无已完成比赛")
        for m in sorted(done, key=lambda x: x.get("date", ""), reverse=True)[:30]:
            h, a = m.get("host_team_name", "?"), m.get("guest_team_name", "?")
            hf, af = flag(h), flag(a)
            hs, gs = m.get("host_team_score", ""), m.get("guest_team_score", "")
            dt = (m.get("date", "") or "")[:10]
            grp = m.get("group_name", "")
            ttl = (f"{dt}|{hf}**{h} {hs}:{gs} {a}**{af}|{grp}"
                   if hs is not None and gs is not None
                   else f"{dt}|{hf} {h} vs {a} {af}|{grp}")
            with st.expander(ttl):
                hid = m.get("host_team_id") or gid(h)
                aid = m.get("guest_team_id") or gid(a)
                if not (hid and aid):
                    st.warning("无法识别球队 ID")
                    continue
                stage, is_knockout = _detect_stage_and_knockout(m)
                mh, ma = _estimate_motivation(m, standings, hid, aid)
                xtra = None
                if srch:
                    with st.spinner("🌐 搜索中..."):
                        hn_ = search_team_news(h, "status") if h else []
                        an_ = search_team_news(a, "status") if a else []
                    ps = []
                    if hn_: ps.append(f"**{h}**:{'; '.join(hn_[:2])}")
                    if an_: ps.append(f"**{a}**:{'; '.join(an_[:2])}")
                    xtra = "|".join(ps) if ps else None
                analysis = _do_analysis(
                    hid, aid, engine, h, a,
                    m.get("odds_home"), m.get("odds_draw"), m.get("odds_away"),
                    stage, xtra,
                    is_knockout=is_knockout,
                    motivation_home=mh, motivation_away=ma,
                    use_market_odds=bool(m.get("odds_home")),
                )
                _render_analysis_card(analysis)

    # ── Tab 2: 未赛预测 ──
    with t2:
        # 检查是否有已导入的赔率
        imported_odds = st.session_state.get("_imported_odds", {})

        c1, c2 = st.columns(2)
        with c1:
            sa = st.checkbox("显示全部比赛", value=False)
        with c2:
            sg = st.selectbox("按小组筛选",
                              ["全部"] + sorted({m.get("group_name", "") for m in todo if m.get("group_name")}))
        filt = todo
        if not sa:
            from datetime import datetime, timedelta
            now = datetime.now()
            co = now + timedelta(days=21)
            filt = [m for m in filt if not m.get("date") or datetime.strptime(m["date"][:10], "%Y-%m-%d") <= co]
        if sg != "全部":
            filt = [m for m in filt if m.get("group_name") == sg]
        if not filt:
            st.info("暂无符合条件的比赛")

        for m in filt:
            h, a = m.get("host_team_name", "?"), m.get("guest_team_name", "?")
            mid = m.get("id", "")
            with st.expander(
                f"📅{(m.get('date', '') or '')[:16]}|{flag(h)} {h} vs {a} {flag(a)}|{m.get('match_type_name', '小组赛')} {m.get('group_name', '')}"
            ):
                # 显示已导入的赔率（如果有）
                if mid in imported_odds:
                    oi = imported_odds[mid]
                    st.success(f"📥 已导入赔率: 主胜{oi.get('oh', '-')} / 平{oi.get('od', '-')} / 客胜{oi.get('oa', '-')}")
                    if oi.get("intel"):
                        st.markdown(f'<div class="search-result">📰 {oi["intel"]}</div>', unsafe_allow_html=True)
                else:
                    st.info("💡 请在「赔率导入」Tab 上传 Excel 文件导入赔率")

                if srch:
                    st.markdown(f"**📰 {h} 动态:**")
                    for it in search_team_news(h, "status")[:3]:
                        st.markdown(f'<div class="search-result">{it}</div>', unsafe_allow_html=True)
                    st.markdown(f"**📰 {a} 动态:**")
                    for it in search_team_news(a, "status")[:3]:
                        st.markdown(f'<div class="search-result">{it}</div>', unsafe_allow_html=True)

                if st.button(f"🎯 分析这场比赛", key=f"analyze_{mid}"):
                    hid = m.get("host_team_id") or gid(h)
                    aid = m.get("guest_team_id") or gid(a)
                    if not (hid and aid):
                        st.warning("无法识别球队 ID")
                        continue
                    stage, is_knockout = _detect_stage_and_knockout(m)
                    mh, ma = _estimate_motivation(m, standings, hid, aid)

                    # 使用导入的赔率（如有），否则 None
                    oi = imported_odds.get(mid, {})
                    oh = oi.get("oh") if oi else None
                    od = oi.get("od") if oi else None
                    oa = oi.get("oa") if oi else None

                    xtra = None
                    if srch:
                        with st.spinner("🌐 搜索中..."):
                            hn_ = search_team_news(h, "status") if h else []
                            an_ = search_team_news(a, "status") if a else []
                        ps = []
                        if hn_: ps.append(f"**{h}**:{'; '.join(hn_[:2])}")
                        if an_: ps.append(f"**{a}**:{'; '.join(an_[:2])}")
                        xtra = "|".join(ps) if ps else None

                    analysis = _do_analysis(
                        hid, aid, engine, h, a,
                        oh, od, oa,
                        stage, xtra,
                        is_knockout=is_knockout,
                        motivation_home=mh, motivation_away=ma,
                        use_market_odds=bool(oh),
                    )
                    _render_analysis_card(analysis)

    # ── Tab 3: 赔率导入 ──
    with t3:
        st.subheader("📥 上传赔率 & 情报 Excel")
        st.caption("支持 .xlsx / .xls / .csv 格式。列名：比赛ID/日期/主队/客队/主胜赔率/平局赔率/客胜赔率/情报")

        uploaded = st.file_uploader(
            "上传文件",
            type=["xlsx", "xls", "csv"],
            help="Excel 列：id, date, home_team, away_team, odds_home, odds_draw, odds_away, intelligence")

        if uploaded is not None:
            try:
                from data.odds_importer import OddsImporter
                importer = OddsImporter()
                df = importer.parse_file(uploaded)
                if df is not None and len(df) > 0:
                    odds_dict = importer.to_match_odds_dict(df)
                    st.session_state["_imported_odds"] = odds_dict
                    st.success(f"✅ 成功导入 {len(odds_dict)} 场比赛的赔率数据")
                    st.dataframe(df, use_container_width=True, hide_index=True)
                else:
                    st.warning("⚠️ 文件为空或格式不正确")
            except ImportError:
                st.error("⚠️ 解析模块未安装，请确保 openpyxl 已安装")
            except Exception as e:
                st.error(f"⚠️ 解析失败: {str(e)[:200]}")

        # 显示已导入数据摘要
        imported = st.session_state.get("_imported_odds", {})
        if imported:
            st.divider()
            st.subheader(f"📋 已导入 {len(imported)} 场比赛")
            for mid, oi in list(imported.items())[:20]:
                st.text(f"  ID {mid}: {oi.get('home', '?')} vs {oi.get('away', '?')} | "
                        f"主胜{oi.get('oh', '-')} 平{oi.get('od', '-')} 客胜{oi.get('oa', '-')}")
            if st.button("🗑️ 清除已导入赔率"):
                st.session_state["_imported_odds"] = {}
                st.rerun()


# ──────────────────────────────────────────────
#  Tab 4 — 仓位建议（Kelly + 过滤 + 风控）
# ──────────────────────────────────────────────
def render_portfolio(data):
    st.header("💰 Kelly 仓位建议")
    st.caption("⚠️ 本模块仅用于模型验证和教育目的")

    import strategy.kelly as km
    import strategy.filters as sf
    import strategy.risk_control as rc

    matches = data.get("matches") or []
    engine = data.get("elo")
    upcoming = [m for m in matches if m.get("match_des") != "完赛"]
    if not upcoming:
        st.info("暂无未赛比赛")
        return

    # 风控控制器
    risk_ctrl = rc.RiskController()
    risk_ctrl.reset_day(1000)  # 假设本金 1000

    # 给用户选择赔率来源
    odds_source = st.radio("赔率来源", ["手动输入", "预设赔率"], horizontal=True)

    items = []
    for m in upcoming:
        hn, an = m.get("host_team_name", ""), m.get("guest_team_name", "")
        hid = m.get("host_team_id") or gid(hn)
        aid = m.get("guest_team_id") or gid(an)
        if not hid or not aid:
            continue
        try:
            hid, aid = int(hid), int(aid)
            exp = engine.simulate_match(hid, aid)
        except Exception:
            continue
        if not exp:
            continue

        # 用户输入赔率 — 确保 prob_h / oh_ 在两种模式下都已定义
        prob_h = exp["home_win"]
        if odds_source == "手动输入":
            c1, c2, c3 = st.columns(3)
            with c1:
                oh_ = st.number_input(f"{hn}胜赔率", key=f"pf_oh_{m.get('id','')}", value=2.50, min_value=1.01, step=0.1, format="%.2f")
            with c2:
                od_ = st.number_input("平局赔率", key=f"pf_od_{m.get('id','')}", value=3.40, min_value=1.01, step=0.1, format="%.2f")
            with c3:
                oa_ = st.number_input(f"{an}胜赔率", key=f"pf_oa_{m.get('id','')}", value=2.80, min_value=1.01, step=0.1, format="%.2f")
        else:
            # 预设赔率（基于 Elo 估算）
            prob_d = exp["draw"]
            prob_a = exp["away_win"]
            # 简单转为小数赔率 (去 vig 10%)
            oh_ = round(1 / (prob_h * 0.9) + 0.99, 2) if prob_h > 0.01 else 99.0
            od_ = round(1 / (prob_d * 0.9) + 0.99, 2) if prob_d > 0.01 else 99.0
            oa_ = round(1 / (prob_a * 0.9) + 0.99, 2) if prob_a > 0.01 else 99.0

        # Kelly 计算
        try:
            stake_info = km.calc_match_stake(prob_h, float(oh_), 0.5, "A")
        except Exception:
            stake_info = {"recommendation": "跳过", "adjusted_stake": 0.0, "edge": 0.0, "model_prob": prob_h, "market_prob": 1.0/float(oh_) if float(oh_) > 0 else 0.0}

        edge = stake_info.get("edge", 0)
        recommendation = stake_info.get("recommendation", "跳过")

        # 六项否决过滤
        match_ctx = {
            "team_id": hid,
            "elo_engine": engine,
            "recent_results": [],
            "h2h_count": 3,
            "lineup_announced": True,
            "hours_to_kickoff": 48,
            "phase": "group_stage",
            "referee_nationality": "",
            "team_nationalities": [],
            "referee_bias": 0,
            "political_risk": "low",
        }
        filter_result = sf.apply_all_filters(match_ctx)
        filter_passed = filter_result["passed"]
        filter_reason = filter_result.get("veto_reason", "")

        # 风控检查
        bet_info = {
            "league": "世界杯",
            "stake_pct": stake_info.get("adjusted_stake", 0),
            "odds": float(oh_),
            "match_id": m.get("id", ""),
        }
        risk_result = risk_ctrl.check_all(bet_info)

        # 过滤未通过的，标记但不直接排除
        if not filter_passed:
            recommendation = f"⛔否决"
        elif not risk_result["approved"]:
            recommendation = f"🚫风控"

        items.append({
            "日期": (m.get("date", "") or "")[:10],
            "比赛": f"{hn} vs {an}",
            "阶段": m.get("match_type_name", ""),
            "Elo主胜": f"{exp['home_win']:.1%}",
            "赔率": f"{oh_}",
            "市场隐含": f"{stake_info.get('market_prob',0):.1%}",
            "Edge": f"{edge:+.1%}",
            "Kelly仓位": f"{stake_info.get('adjusted_stake',0)*100:.2f}%",
            "建议": recommendation,
            "过滤": "✅通过" if filter_passed else filter_reason[:30],
        })

    if items:
        df = pd.DataFrame(items)
        # 按 Edge 降序排列
        st.dataframe(df.head(25), use_container_width=True, hide_index=True)

        # 风控状态
        status = risk_ctrl.get_status()
        with st.expander("📊 当日风控状态"):
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("日盈亏", f"¥{status['daily_pnl']:.2f}")
            c2.metric("亏损比例", f"{status['daily_loss_pct']:.1f}%")
            c3.metric("连亏次数", f"{status['consecutive_losses']}")
            c4.metric("状态", "⏸️ 暂停" if status['paused'] else "✅ 正常")
    else:
        st.info("暂无可分析的比赛")


# ──────────────────────────────────────────────
#  Tab 5 — 数据管理
# ──────────────────────────────────────────────
def render_data_manager():
    st.header("🛠️ 本地数据管理")
    st.caption("你告诉我比赛结果 → 我更新本地文件 → 刷新页面即生效")

    # 数据源切换
    col_title, col_btn1, col_btn2 = st.columns([3, 1, 1])
    with col_title:
        st.write("")
    with col_btn2:
        if st.button("🔄 从API拉取最新数据"):
            try:
                import data.api_client as api
                with st.spinner("⏳ 正在拉取 juhe API 最新积分榜和赛程..."):
                    rank_data = api.get_standings()
                    sched_data = api.get_matches()
                if rank_data:
                    ld.save_standings(rank_data)
                    st.success(f"✅ 积分榜已更新: {len(rank_data)} 条")
                if sched_data:
                    ld.save_schedule(sched_data)
                    st.success(f"✅ 赛程已更新: {len(sched_data)} 场")
                if rank_data or sched_data:
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.warning("API 返回空数据，请检查网络连接")
            except Exception as e:
                st.error(f"⚠️ API 拉取失败: {str(e)[:200]}")

    c1,c2,c3 = st.columns(3)
    loc = ld.load_all()
    c1.metric("积分榜条目",f"{len(loc.get('standings',[]))} 条")
    sc = loc.get("schedule",[])
    fin = sum(1 for m in sc if m.get("match_des")=="完赛")
    c2.metric("赛程",f"{len(sc)} 场 (已赛{fin})")
    c3.metric("最后更新",time.strftime("%H:%M:%S"))

    st.divider()
    st.subheader("📝 单场更新")
    mode = st.radio("方式",["按比赛ID","按日期+球队名"],horizontal=True)

    if mode=="按比赛ID":
        ci,ch,ca = st.columns(3)
        with ci: mid = st.text_input("比赛 ID")
        with ch: hg = st.text_input("主队比分")
        with ca: ag = st.text_input("客队比分")
        if st.button("✅ 更新比分") and mid and hg and ag:
            try:
                ok = ld.update_match_result(mid,int(hg),int(ag))
                if ok: ld.recalculate_standings(); st.success(f"✅ {mid}: {hg}-{ag}"); st.cache_data.clear(); st.rerun()
                else: st.error(f"❌ 未找到 {mid}")
            except ValueError: st.error("比分必须是整数")
    else:
        cd,cht,cat,chg2,cag2 = st.columns(5)
        with cd: ds = st.text_input("日期")
        with cht: ht = st.text_input("主队名")
        with cat: at = st.text_input("客队名")
        with chg2: hg2 = st.text_input("主队分")
        with cag2: ag2 = st.text_input("客队分")
        if st.button("✅ 更新比分") and ds and ht and at and hg2 and ag2:
            s = ld.load_schedule()
            fid = None
            for m in s:
                if m.get("date","").startswith(ds) and ht in m.get("host_team_name","") and at in m.get("guest_team_name",""):
                    fid=m["id"]; break
            if fid: ld.update_match_result(fid,int(hg2),int(ag2))
            else: ld.add_finished_match(f"manual_{ds}_{ht}_{at}",ds,ht,at,int(hg2),int(ag2))
            ld.recalculate_standings()
            st.success(f"✅ {ds} {ht} {hg2}:{ag2} {at}"); st.cache_data.clear(); st.rerun()

    st.divider()
    st.subheader("📋 批量粘贴")
    st.caption("每行: 小组 日期 | 主队 | 比分 | 客队")
    batch = st.text_area("粘贴",height=120,placeholder="A组 2026-06-22 | 墨西哥 | 2:1 | 韩国\nB组 2026-06-22 | 瑞士 | 3:0 | 波黑")
    if st.button("🔄 批量解析") and batch.strip():
        lines = [l.strip() for l in batch.strip().split("\n") if l.strip()]
        up,errs = 0,[]
        for line in lines:
            try:
                parts = [p.strip() for p in line.split("|")]
                if len(parts)<4: errs.append(f"格式:{line}"); continue
                h_,sc_,a_ = parts[1],parts[2],parts[3]
                hg_s,ag_s = sc_.split(":")
                hg,ag = int(hg_s),int(ag_s)
                s = ld.load_schedule()
                fd = False
                for m in s:
                    if h_ in m.get("host_team_name","") and a_ in m.get("guest_team_name","") and m.get("match_des")!="完赛":
                        ld.update_match_result(m["id"],hg,ag); up+=1; fd=True; break
                if not fd:
                    for m in s:
                        if h_ in m.get("guest_team_name","") and a_ in m.get("host_team_name","") and m.get("match_des")!="完赛":
                            ld.update_match_result(m["id"],ag,hg); up+=1; fd=True; break
                if not fd: errs.append(f"未找到:{line}")
            except Exception as e: errs.append(f"解析失败:{line}")
        if up>0: ld.recalculate_standings(); st.success(f"✅ 已更新 {up} 场"); st.cache_data.clear(); st.rerun()
        if errs: st.warning(f"⚠️ {len(errs)} 条失败:{'; '.join(errs[:5])}")

    st.divider()
    with st.expander("🔍 查看已完赛比赛"):
        for m in sorted([m for m in sc if m.get("match_des")=="完赛"],key=lambda x:x.get("date",""),reverse=True):
            st.text(f"  {m.get('group_name','  ')} {m.get('date','')[:10]} | {m['host_team_name']} {m.get('host_team_score')}:{m.get('guest_team_score')} {m['guest_team_name']}")


# ──────────────────────────────────────────────
#  主入口
# ──────────────────────────────────────────────
def main():
    st.markdown('<div class="main-title">⚽ 2026 美加墨世界杯比分预测</div>',unsafe_allow_html=True)
    st.markdown(f'<div class="subtitle">四层融合|Elo+泊松+蒙特卡洛+贝叶斯|本地+API混合|{pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")}</div>',unsafe_allow_html=True)

    # ── 自动同步（每 30 分钟检测一次） ──
    _auto_sync_if_needed()

    # 如果有新数据提醒
    if st.session_state.get("_api_new_data"):
        st.toast("🎉 API 发现新比赛数据，已自动同步到本地！", icon="✅")
        st.session_state["_api_new_data"] = False
        # 延迟 rerun 让最新数据生效
        import time as _time; _time.sleep(1)
        st.cache_data.clear()
        st.rerun()

    data = load_all_data()

    with st.sidebar:
        st.title("🎮 控制面板")
        # 数据源徽章 + 自动同步状态
        src_ts = st.session_state.get("_api_last_check", "") or data.get("_api_last_check", "")
        if src_ts:
            st.markdown(
                f'<span class="data-source-badge source-live">🟢 API已同步 — {src_ts}</span>',
                unsafe_allow_html=True)
        else:
            st.markdown(
                '<span class="data-source-badge source-cache">🔵 本地数据</span>',
                unsafe_allow_html=True)
        ms = data.get("matches") or []
        if ms:
            f = sum(1 for m in ms if m.get("match_des")=="完赛")
            st.metric("比赛",f"{len(ms)}场")
            st.caption(f"已赛 {f} | 未赛 {len(ms)-f}")
        stnc = data.get("standings") or []
        if stnc: st.metric("球队",f"{len(stnc)} 支")

        # ── 全局搜索增强开关 ──
        st.divider()
        st.session_state.setdefault("search_enhanced", False)
        st.checkbox("🌐 实时搜索增强（分析球队动态）",
                     key="search_enhanced")

        # ── 自动同步间隔 ──
        st.divider()
        st.session_state.setdefault("_auto_sync_interval", 1800)
        interval_min = st.selectbox(
            "⏱️ 自动同步间隔",
            options=[("关闭自动同步", 0), ("每 10 分钟", 600), ("每 30 分钟", 1800), ("每 1 小时", 3600)],
            index=2,
            format_func=lambda x: x[0])
        st.session_state["_auto_sync_interval"] = interval_min[1]

        # ── 手动立即同步 ──
        if st.button("🔄 立即同步 API 数据"):
            st.session_state["_last_auto_sync"] = 0  # 重置计时器触发同步
            cnt, msg = _check_api_for_updates()
            if cnt > 0:
                st.cache_data.clear()
                st.toast(f"✅ {msg}", icon="🎉")
                st.rerun()
            else:
                st.info(msg)

        eng = data.get("elo")
        if eng and eng.teams:
            with st.expander("🏆 Elo 实力排行"):
                for r,(tid,info) in enumerate(sorted(eng.export_ratings().items(),key=lambda x:-x[1]["rating"])[:20],1):
                    flag_ = FLAG.get(ID2META.get(tid,(None,None,None,None))[1],"🏳️") if tid in ID2META else "🏳️"
                    st.text(f"{r}. {flag_} {info['name']} — {info['rating']:.0f}")
        st.divider()
        if st.button("🔄 刷新"): st.cache_data.clear(); st.rerun()

    tabs = st.tabs(["📊 积分榜","🏆 淘汰赛","🔮 比赛分析","💰 仓位建议","🛠️ 数据管理"])
    with tabs[0]: render_standings(data)
    with tabs[1]: render_knockout(data)
    with tabs[2]: render_predictions(data)
    with tabs[3]: render_portfolio(data)
    with tabs[4]: render_data_manager()


if __name__ == "__main__":
    main()
