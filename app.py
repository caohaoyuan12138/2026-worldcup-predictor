"""
2026 美加墨世界杯比分预测模型 — Streamlit 主入口
四层融合架构：Elo + Dixon-Coles 泊松 + 蒙特卡洛 + 贝叶斯
数据源：本地 JSON 文件（standings.json / schedule.json） + BSD API实时数据
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
import model.llm_analyzer as llm  # 大模型推理增强
import model.explanation_layer as exp  # 解释层模块
import model.score_matrix as sm  # 比分矩阵模块
import model.review as review  # 复盘模块
import data.bsd_api as bsd  # BSD实时数据API
import data.news_api as news  # 新闻数据API
import data.weather_api as weather  # 天气API（实时环境信息）
import data.juhe_api as juhe  # 聚合数据API（赛程/球队/积分榜）

# 确保LLM模块函数存在（fallback）
if not hasattr(llm, 'set_llm_enabled'):
    llm.set_llm_enabled = lambda x: None
if not hasattr(llm, 'is_llm_enabled'):
    llm.is_llm_enabled = lambda: True

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


@st.cache_data(ttl=300, show_spinner=False)  # 缓存5分钟
def load_all_data():
    """加载所有数据（带缓存）- 优先从聚合API获取"""
    # 优先从聚合API获取实时数据
    try:
        juhe_data = juhe.sync_all_data()
        if juhe_data.get("schedule") and len(juhe_data["schedule"]) > 0:
            # 聚合API有数据，使用聚合数据
            raw = {
                "schedule": juhe_data["schedule"],
                "matches": juhe_data["schedule"],
                "teams": juhe_data["teams"],
                "standings": juhe_data["standings"],
                "source": "聚合API",
                "sync_time": juhe_data["sync_time"],
            }
        else:
            # 聚合API返回空数据，使用本地数据
            raw = ld.load_all()
            raw["source"] = "本地数据"
    except Exception as e:
        # 聚合API异常，使用本地数据
        raw = ld.load_all()
        raw["source"] = "本地数据（API异常）"
    
    # 兼容两种 key 名：schedule 或 matches
    matches = raw.get("schedule") or raw.get("matches") or []

    # 确保 standings 是最新的：根据赛程重算
    if not raw.get("standings") or len(raw.get("standings", [])) == 0:
        standings = ld.recalculate_standings(matches)
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
    
    # 只处理已完赛的比赛
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


@st.cache_resource  # Elo引擎作为资源缓存，不重复初始化
def get_elo_engine():
    """获取Elo引擎（资源缓存）"""
    data = load_all_data()
    return data.get("elo")


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

    # ── 动画树状图 CSS ──
    st.markdown("""
    <style>
    .knockout-tree { display: flex; flex-direction: column; align-items: center; gap: 8px; font-family: sans-serif; }
    .ko-round { display: flex; justify-content: center; gap: 12px; margin: 8px 0; flex-wrap: wrap; }
    .ko-match {
        background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
        border: 1px solid #334155;
        border-radius: 10px;
        padding: 10px 14px;
        min-width: 180px;
        text-align: center;
        color: #e2e8f0;
        position: relative;
        transition: all 0.3s ease;
        animation: koFadeIn 0.6s ease-out both;
    }
    .ko-match:hover { transform: translateY(-3px); border-color: #f97316; box-shadow: 0 4px 12px rgba(249,115,22,0.25); }
    .ko-match.finished { border-color: #22c55e; }
    .ko-match.upcoming { border-color: #64748b; opacity: 0.85; }
    .ko-match.unresolved { border-color: #ef4444; border-style: dashed; }
    .ko-team { font-size: 0.95rem; font-weight: 600; display: flex; align-items: center; justify-content: center; gap: 6px; }
    .ko-score { font-size: 1.1rem; color: #f97316; font-weight: bold; margin: 4px 0; }
    .ko-vs { font-size: 0.75rem; color: #94a3b8; margin: 2px 0; }
    .ko-stage-label { font-size: 0.7rem; color: #64748b; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 4px; }
    .ko-connector { width: 2px; height: 16px; background: #475569; margin: 0 auto; }
    .ko-connector-h { width: 40px; height: 2px; background: #475569; }
    @keyframes koFadeIn { from { opacity: 0; transform: translateY(15px); } to { opacity: 1; transform: translateY(0); } }
    .group-qualify-panel { background: #0f172a; border-radius: 12px; padding: 16px; margin: 12px 0; border: 1px solid #1e293b; }
    .group-qualify-panel h4 { color: #f97316; margin: 0 0 10px 0; font-size: 1rem; }
    .qualify-row { display: flex; gap: 8px; flex-wrap: wrap; }
    .qualify-chip {
        background: #1e293b; border-radius: 20px; padding: 4px 12px;
        font-size: 0.85rem; color: #e2e8f0; border: 1px solid #334155;
        display: flex; align-items: center; gap: 4px;
    }
    .qualify-chip.champion { border-color: #fbbf24; color: #fbbf24; }
    .qualify-chip.runner { border-color: #94a3b8; color: #94a3b8; }
    .qualify-chip.third { border-color: #b45309; color: #b45309; }
    .qualify-chip.eliminated { opacity: 0.4; text-decoration: line-through; }
    </style>
    """, unsafe_allow_html=True)

    # ── 小组出线情况面板 ──
    group_rankings = {}
    for s in standings:
        g = s.get("team_group", "")
        if g:
            group_rankings.setdefault(g, []).append(s)
    for g in group_rankings:
        group_rankings[g].sort(key=lambda x: int(x.get("rank", "99") or "99"))

    with st.expander("📊 小组出线情况（点击展开）", expanded=True):
        # 12个小组，每行4个
        groups = sorted(group_rankings.keys())
        for i in range(0, len(groups), 4):
            cols = st.columns(4)
            for j, g in enumerate(groups[i:i+4]):
                with cols[j]:
                    teams = group_rankings[g]
                    st.markdown(f"**组 {g}**")
                    for rank, t in enumerate(teams, 1):
                        name = t.get("team_name", "?")
                        fl = flag(name)
                        score = t.get("score", "0")
                        gd = int(t.get("goal", 0)) - int(t.get("miss_goal", 0))
                        cls = ""
                        label = ""
                        if rank == 1:
                            cls = "champion"
                            label = "🥇"
                        elif rank == 2:
                            cls = "runner"
                            label = "🥈"
                        elif rank == 3:
                            cls = "third"
                            label = "🥉"
                        else:
                            cls = "eliminated"
                            label = "❌"
                        st.markdown(
                            f'<div class="qualify-chip {cls}">{label} {fl} {name} ({score}分 净{gd:+d})</div>',
                            unsafe_allow_html=True
                        )

    # ── 最佳小组第3名 ──
    all_third = []
    for g, teams in group_rankings.items():
        if len(teams) >= 3:
            t = teams[2]
            all_third.append({
                "group": g,
                "name": t.get("team_name", ""),
                "score": int(t.get("score", "0") or "0"),
                "gd": int(t.get("goal", "0") or "0") - int(t.get("miss_goal", "0") or "0"),
                "goals": int(t.get("goal", "0") or "0"),
            })
    if all_third:
        all_third.sort(key=lambda x: (-x["score"], -x["gd"], -x["goals"]))
        with st.expander(f"🏅 最佳小组第3名排名（前4晋级）", expanded=True):
            c = st.columns(4)
            for i, t in enumerate(all_third[:8]):
                with c[i % 4]:
                    fl = flag(t["name"])
                    badge = "✅ 晋级" if i < 4 else "❌ 淘汰"
                    color = "#22c55e" if i < 4 else "#ef4444"
                    st.markdown(
                        f'<div style="background:#1e293b;border-radius:8px;padding:8px 12px;'
                        f'border:1px solid {color};text-align:center;">'
                        f'<div style="font-size:1.2rem">{fl} {t["name"]}</div>'
                        f'<div style="font-size:0.8rem;color:#94a3b8">组{t["group"]} | {t["score"]}分 净{t["gd"]:+d}</div>'
                        f'<div style="font-size:0.75rem;color:{color};font-weight:bold">{badge}</div></div>',
                        unsafe_allow_html=True
                    )

    # ── 淘汰赛树状图 ──
    def _ko_match_card(m, stage_label=""):
        h = m.get("host_team_name", "?")
        a = m.get("guest_team_name", "?")
        hs = m.get("host_team_score", "")
        gs = m.get("guest_team_score", "")
        is_finished = m.get("match_des") == "完赛" and hs is not None and gs is not None
        is_unresolved = not h or (len(h) <= 3 and h[0] in "ABCDEFGHIJKL" and h[-1] in "123")
        cls = "finished" if is_finished else ("unresolved" if is_unresolved else "upcoming")
        hf, af = flag(h), flag(a)
        score_html = f'<div class="ko-score">{hs} : {gs}</div>' if is_finished else '<div class="ko-vs">VS</div>'
        anim_delay = f"animation-delay: {hash(h+a) % 10 * 0.1}s;"
        return (
            f'<div class="ko-match {cls}" style="{anim_delay}">'
            f'<div class="ko-stage-label">{stage_label}</div>'
            f'<div class="ko-team">{hf} {h}</div>'
            f'{score_html}'
            f'<div class="ko-team">{af} {a}</div>'
            f'</div>'
        )

    def _ko_round(matches, stage_label, per_row=4):
        if not matches:
            return ""
        cards = ""
        for i, m in enumerate(matches):
            cards += _ko_match_card(m, stage_label if i == 0 else "")
        return f'<div class="ko-round">{cards}</div>'

    st.markdown("---")
    st.subheader("🌳 淘汰赛晋级之路")

    # 上半区
    st.markdown("**⬆️ 上半区**")
    r16 = stages["1/16决赛"]
    html = '<div class="knockout-tree">'
    html += _ko_round(r16[:8], "1/16决赛", 4)
    html += '<div class="ko-connector"></div>'
    html += _ko_round(stages["1/8决赛"][:4], "1/8决赛", 4)
    html += '<div class="ko-connector"></div>'
    html += _ko_round(stages["1/4决赛"][:2], "1/4决赛", 2)
    html += '<div class="ko-connector"></div>'
    html += _ko_round(stages["半决赛"][:1], "半决赛", 1)
    html += '</div>'
    st.markdown(html, unsafe_allow_html=True)

    # 下半区
    st.markdown("**⬇️ 下半区**")
    html = '<div class="knockout-tree">'
    html += _ko_round(r16[8:], "1/16决赛", 4)
    html += '<div class="ko-connector"></div>'
    html += _ko_round(stages["1/8决赛"][4:], "1/8决赛", 4)
    html += '<div class="ko-connector"></div>'
    html += _ko_round(stages["1/4决赛"][2:], "1/4决赛", 2)
    html += '<div class="ko-connector"></div>'
    html += _ko_round(stages["半决赛"][1:], "半决赛", 1)
    html += '</div>'
    st.markdown(html, unsafe_allow_html=True)

    # 决赛 & 季军战
    st.markdown("**🏆 决赛 & 季军战**")
    html = '<div class="knockout-tree">'
    html += _ko_round(stages["季军战"], "季军战", 2)
    html += _ko_round(stages["决赛"], "决赛", 1)
    html += '</div>'
    st.markdown(html, unsafe_allow_html=True)


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
    # 确保 hid/aid 是整数或 None
    try:
        hid = int(hid) if hid else None
    except (ValueError, TypeError):
        hid = None
    try:
        aid = int(aid) if aid else None
    except (ValueError, TypeError):
        aid = None

    result = {
        "_home_name": hn,
        "_away_name": an,
    }

    # ── 1. Elo 维度 ──
    # 如果球队ID无效，尝试通过球队名查找
    if hid is None or hid not in engine.teams:
        hid = gid(hn) if hn else None
    if aid is None or aid not in engine.teams:
        aid = gid(an) if an else None

    # 获取评分，如果球队不在引擎中，使用默认值
    eh = engine.get_rating(hid) if hid and hid in engine.teams else 1500
    ea = engine.get_rating(aid) if aid and aid in engine.teams else 1500

    # 获取调整后的评分
    if hid and hid in engine.teams:
        eh_adj = engine.teams[hid].get_adjusted_rating(engine.teams.get(aid), True)
    else:
        eh_adj = eh
    if aid and aid in engine.teams:
        ea_adj = engine.teams[aid].get_adjusted_rating(engine.teams.get(hid), False)
    else:
        ea_adj = ea

    # 模拟比赛（如果球队ID有效）
    if hid and aid and hid in engine.teams and aid in engine.teams:
        exp = engine.simulate_match(hid, aid)
    else:
        # 默认概率
        exp = {"home_win": 0.33, "draw": 0.34, "away_win": 0.33}

    diff = int(round(eh - ea))
    adv = "主队占优" if diff > 25 else ("客队占优" if diff < -25 else "势均力敌")

    # 获取FIFA排名
    hid_meta = ID2META.get(hid, (hn, None, None, None)) if hid else (hn, None, None, None)
    aid_meta = ID2META.get(aid, (an, None, None, None)) if aid else (an, None, None, None)
    hid_fifa = hid_meta[3] if hid_meta[3] else "?"
    aid_fifa = aid_meta[3] if aid_meta[3] else "?"

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
        "home_fifa_rank": hid_fifa,
        "away_fifa_rank": aid_fifa,
    }

    # ── 2. 泊松维度 ──
    lh, la = poisson.calc_expected_goals(
        hid, aid, engine,
        stage=stage,
        motivation_home=motivation_home,
        motivation_away=motivation_away)
    
    # ── 2.1 BSD API实时数据调整 ──
    bsd_adjustment_note = ""
    if bsd.is_bsd_available():
        inj_h = bsd.get_team_injuries(hn)
        inj_a = bsd.get_team_injuries(an)
        
        # 根据伤病调整lambda
        lh_adj, la_adj = bsd.adjust_lambda_for_injuries(lh, la, inj_h, inj_a)
        
        if lh_adj != lh or la_adj != la:
            bsd_adjustment_note = (
                f"BSD实时数据调整: 主队λ从{lh:.3f}调整为{lh_adj:.3f}，"
                f"客队λ从{la:.3f}调整为{la_adj:.3f}"
            )
            lh, la = lh_adj, la_adj
    
    result["poisson"] = {
        "lambda_home": round(lh, 3),
        "lambda_away": round(la, 3),
        "expected_total": round(lh + la, 2),
        "stage_avg_goals": stage,
        "motivation_home": motivation_home,
        "motivation_away": motivation_away,
        "bsd_adjustment": bsd_adjustment_note,
    }

    # ── 3. 蒙特卡洛维度 ──
    env = _build_match_environment(hid, aid, hn, an)
    sim = mc.Simulator(n_sim=config.MC_SIMULATIONS).run_detailed(lh, la, env,
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

    # ── 6. 综合预测（融合所有维度 + 详细推理）──
    pred_parts = []
    reasoning = []  # 详细推理过程

    # 6.1 Elo 实力判断
    # 注意：eh/ea 是Elo评分，ew/ed/aw 是胜率概率
    ew = exp["home_win"]
    ed = exp["draw"]
    aw = exp["away_win"]  # 改为 aw，避免覆盖 ea（客队Elo评分）
    elo_diff = eh - ea
    # 获取FIFA排名用于推理
    hid_fifa = result["elo"].get("home_fifa_rank", "?")
    aid_fifa = result["elo"].get("away_fifa_rank", "?")
    fifa_info = f"FIFA排名：{hn} #{hid_fifa} vs {an} #{aid_fifa}"

    if elo_diff > 80:
        pred_parts.append(f"🏠 {hn} 实力明显占优（Elo差 {elo_diff:+.0f}）")
        reasoning.append(f"• Elo评分：{hn} {eh:.0f} vs {an} {ea:.0f}，差值{elo_diff:+.0f}超过80分，实力差距显著。{fifa_info}。Elo模型预测{hn}胜率{ew:.1%}。")
    elif elo_diff > 40:
        pred_parts.append(f"🏠 {hn} 实力占优（Elo差 {elo_diff:+.0f}）")
        reasoning.append(f"• Elo评分：{hn} {eh:.0f} vs {an} {ea:.0f}，差值{elo_diff:+.0f}，{hn}略占优势。{fifa_info}。Elo模型预测{hn}胜率{ew:.1%}。")
    elif elo_diff < -80:
        pred_parts.append(f"✈️ {an} 实力明显占优（Elo差 {elo_diff:+.0f}）")
        reasoning.append(f"• Elo评分：{an} {ea:.0f} vs {hn} {eh:.0f}，差值{abs(elo_diff):.0f}超过80分，{an}实力明显更强。{fifa_info}。Elo模型预测{an}胜率{aw:.1%}。")
    elif elo_diff < -40:
        pred_parts.append(f"✈️ {an} 实力占优（Elo差 {elo_diff:+.0f}）")
        reasoning.append(f"• Elo评分：{an} {ea:.0f} vs {hn} {eh:.0f}，差值{abs(elo_diff):.0f}，{an}略占优势。{fifa_info}。Elo模型预测{an}胜率{aw:.1%}。")
    else:
        pred_parts.append("⚖️ 两队实力接近")
        reasoning.append(f"• Elo评分：{hn} {eh:.0f} vs {an} {ea:.0f}，差值仅{abs(elo_diff):.0f}分，两队实力非常接近。{fifa_info}。Elo模型预测平局概率{ed:.1%}。")

    # 6.2 泊松期望进球判断
    total_goals = lh + la
    if total_goals > 2.8:
        pred_parts.append(f"🔥 预计进球较多（{total_goals:.1f}球）")
        reasoning.append(f"• 泊松模型：{hn}期望进球{lh:.2f}，{an}期望进球{la:.2f}，合计{total_goals:.1f}球。两队进攻火力强，预计是一场进球大战。")
    elif total_goals < 1.8:
        pred_parts.append(f"🛡️ 预计进球偏少（{total_goals:.1f}球）")
        reasoning.append(f"• 泊松模型：{hn}期望进球{lh:.2f}，{an}期望进球{la:.2f}，合计{total_goals:.1f}球。两队防守稳健或进攻乏力，预计进球不多。")
    else:
        pred_parts.append(f"⚽ 预计进球适中（{total_goals:.1f}球）")
        reasoning.append(f"• 泊松模型：{hn}期望进球{lh:.2f}，{an}期望进球{la:.2f}，合计{total_goals:.1f}球，属于正常进球范围。")
    
    # 6.2.1 BSD实时数据调整说明
    if bsd_adjustment_note:
        reasoning.append(f"• BSD实时数据：{bsd_adjustment_note}。伤病/停赛球员已纳入期望进球调整。")

    # 6.2.2 新闻数据推理
    try:
        news_summary = news.format_news_for_prediction(hn, an)
        if news_summary and "暂无" not in news_summary:
            reasoning.append(f"• 新闻动态：{news_summary}")
            
            # 获取伤病影响调整
            match_news = news.get_match_news_summary(hn, an)
            news_adj = match_news.get("impact_adjustment", {})
            
            # 如果新闻数据有伤病影响，进一步调整lambda
            if news_adj.get("lambda_home", 1.0) < 1.0 or news_adj.get("lambda_away", 1.0) < 1.0:
                # 新闻伤病调整叠加到BSD调整之上
                lh = lh * news_adj.get("lambda_home", 1.0)
                la = la * news_adj.get("lambda_away", 1.0)
                reasoning.append(f"• 伤病名单影响：根据WorldCupWiki伤病名单，{hn}λ调整为{lh:.3f}，{an}λ调整为{la:.3f}。")
    except Exception as e:
        pass  # 新闻数据获取失败不影响主流程

    # 6.3 蒙特卡洛最可能比分
    if top:
        best_score = top[0]
        pred_parts.append(f"🎯 最可能比分 {best_score['score']}（{best_score['probability']}%）")
        top3_str = ", ".join([f"{s['score']}({s['probability']}%)" for s in top[:3]])
        reasoning.append(f"• 蒙特卡洛模拟{config.MC_SIMULATIONS}次：最可能比分是{best_score['score']}（概率{best_score['probability']}%）。TOP3比分：{top3_str}。")

    # 6.4 动机因子影响
    if abs(motivation_home - 1.0) > 0.05 or abs(motivation_away - 1.0) > 0.05:
        mot_lines = []
        mot_reasons = []
        if motivation_home > 1.05:
            mot_lines.append(f"{hn}战意高涨")
            mot_reasons.append(f"{hn}动机因子{motivation_home:.2f}（生死战/关键出线战）")
        elif motivation_home < 0.95:
            mot_lines.append(f"{hn}战意一般")
            mot_reasons.append(f"{hn}动机因子{motivation_home:.2f}（已出线可能轮换 / 已淘汰）")
        if motivation_away > 1.05:
            mot_lines.append(f"{an}战意高涨")
            mot_reasons.append(f"{an}动机因子{motivation_away:.2f}（生死战/关键出线战）")
        elif motivation_away < 0.95:
            mot_lines.append(f"{an}战意一般")
            mot_reasons.append(f"{an}动机因子{motivation_away:.2f}（已出线可能轮换 / 已淘汰）")
        if mot_lines:
            pred_parts.append(f"💪 {' / '.join(mot_lines)}")
            reasoning.append(f"• 动机分析：{'；'.join(mot_reasons)}。动机因子已调整期望进球。")

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
                reasoning.append(f"• 贝叶斯融合：模型预测{hn}胜率{model_home:.1%}，但市场赔率隐含胜率仅{market_home:.1%}，存在{diff_mm:.1%}的价值偏差。模型权重{bay['weight_model']:.0%}，市场权重{bay['weight_market']:.0%}。")
            else:
                pred_parts.append(f"📉 市场看好{hn}（市场{market_home:.1%} vs 模型{model_home:.1%}）")
                reasoning.append(f"• 贝叶斯融合：市场赔率隐含{hn}胜率{market_home:.1%}，高于模型预测的{model_home:.1%}，市场可能掌握了模型未考虑的信息（如伤病、阵容）。模型权重{bay['weight_model']:.0%}，市场权重{bay['weight_market']:.0%}。")
        else:
            reasoning.append(f"• 贝叶斯融合：模型与市场基本一致（偏差{abs(diff_mm):.1%}），融合后{hn}胜率{bw:.1%}，置信度{conf:.0%}。")
        if conf > 0.7:
            pred_parts.append(f"✅ 融合置信度高（{conf:.0%}）")
            reasoning.append(f"  → 融合置信度{conf:.0%}（高），预测可靠性较强。")
        elif conf < 0.4:
            pred_parts.append(f"⚠️ 融合置信度低（{conf:.0%}），建议谨慎")
            reasoning.append(f"  → 融合置信度{conf:.0%}（低），模型与市场分歧大或数据不足，建议谨慎参考。")

    # 6.6 Kelly 仓位建议
    if result.get("kelly"):
        kel = result["kelly"]
        rec = kel["recommendation"]
        edge = kel["edge"]
        if rec in ("轻仓", "中仓", "重仓"):
            pred_parts.append(f"💰 Kelly建议{rec}（edge {edge:+.1%}）")
            reasoning.append(f"• Kelly公式：模型概率{kel.get('model_prob', 0):.1%} vs 市场隐含概率{kel.get('market_prob', 0):.1%}，edge={edge:+.1%}。半Kelly策略建议{rec}，仓位{kel.get('adjusted_stake', 0)*100:.2f}%。")
        elif rec == "观望":
            pred_parts.append(f"👀 Kelly建议观望（edge {edge:+.1%}）")
            reasoning.append(f"• Kelly公式：edge={edge:+.1%}接近零，无明确价值，建议观望。")

    # 6.7 淘汰赛加时提示
    if is_knockout:
        if ed > 0.25:
            pred_parts.append(f"⏱️ 淘汰赛平局概率{ed:.1%}，可能进入加时")
            reasoning.append(f"• 淘汰赛特性：90分钟平局概率{ed:.1%}，若平局将进入30分钟加时赛（进球期望降至常规时间的40%）。")
        if sim.get("extra_time") and sim["extra_time"].get("draw_pct", 0) > 30:
            pred_parts.append("🎯 加时后仍可能点球决胜")
            et_draw = sim["extra_time"].get("draw_pct", 0)
            reasoning.append(f"• 加时赛模拟：加时后仍平局概率{et_draw:.1f}%，将进入点球大战（假设命中率75%，每队5轮）。")

    # 6.8 环境因素
    env_factors = []
    if env.is_water_break:
        pred_parts.append("💧 补水机制激活（高温）")
        env_factors.append(f"气温{env.temperature}°C超过阈值，补水机制激活，下半场体能恢复+3%")
    if env.venue_altitude > 1500:
        pred_parts.append(f"⛰️ 高海拔场地（{env.venue_altitude}m）")
        env_factors.append(f"海拔{env.venue_altitude}m，低海拔球队体能-6%")
    if env.is_rain:
        pred_parts.append("🌧️ 雨天作战")
        env_factors.append("雨天影响：控球型球队进攻-2%，长传型球队+2%")
    if abs(env.timezone_diff_hours) > 3:
        pred_parts.append(f"🕐 时差影响（{env.timezone_diff_hours:.0f}h）")
        env_factors.append(f"时差{env.timezone_diff_hours:.0f}小时，体能-3%")
    if env.is_high_stakes:
        env_factors.append("大赛高压环境，双方进攻期望-3%（更保守）")
    if env_factors:
        reasoning.append(f"• 环境因素：{'；'.join(env_factors)}。")
    else:
        reasoning.append(f"• 环境因素：中性环境（气温{env.temperature}°C，海拔{env.venue_altitude}m，无雨天/时差影响）。")

    # 最终预测结论
    result["prediction"] = "\n".join(pred_parts) if pred_parts else "❓ 数据不足，无法给出综合预测"
    result["prediction_reasoning"] = "\n".join(reasoning) if reasoning else ""

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

    # ── 8. BSD实时赔率 ──
    result["bsd_odds"] = None
    if bsd.is_bsd_available():
        try:
            bsd_odds_data = bsd.get_best_odds(hn, an)
            if bsd_odds_data and bsd_odds_data.get("summary"):
                result["bsd_odds"] = bsd_odds_data
                # 如果没有手动导入赔率，使用BSD赔率作为市场赔率
                if not use_market_odds and bsd_odds_data.get("average_home"):
                    oh = bsd_odds_data.get("average_home")
                    od = bsd_odds_data.get("average_draw")
                    oa = bsd_odds_data.get("average_away")
                    if oh and od and oa:
                        # 重新计算贝叶斯融合
                        mp = bayesian.calc_market_implied_prob(float(oh), float(od), float(oa))
                        prior = {"home_win": exp["home_win"], "draw": exp["draw"], "away_win": exp["away_win"]}
                        posterior = bayesian.bayesian_fusion(prior, mp)
                        result["bayesian"] = {
                            "market_probs": mp,
                            "posterior_probs": posterior,
                            "source": "BSD API",
                        }
                        reasoning.append(f"• BSD实时赔率：主胜{oh:.2f}（隐含概率{mp['home_win']:.1%}）、平{od:.2f}（{mp['draw']:.1%}）、客胜{oa:.2f}（{mp['away_win']:.1%}）。贝叶斯融合后：主胜{posterior['home_win']:.1%}、平{posterior['draw']:.1%}、客胜{posterior['away_win']:.1%}。")
        except Exception as e:
            pass  # BSD赔率获取失败不影响主流程

    # ── 9. 实时情报 ──
    result["extra"] = extra
    
    # ── 10. 解释层分析（核心）──
    try:
        # 创建解释引擎
        explanation_engine = exp.ExplanationEngine()
        
        # 收集所有数据
        elo_data = result.get("elo", {})
        poisson_data = result.get("poisson", {})
        mc_data = result.get("monte_carlo", {})
        bayesian_data = result.get("bayesian", {})
        environment_data = result.get("environment", {})
        
        # 获取伤病数据
        try:
            match_news = news.get_match_news_summary(hn, an)
            injury_data = {
                "home_injuries": match_news.get("home_injuries", {}).get("confirmed_out", []),
                "away_injuries": match_news.get("away_injuries", {}).get("confirmed_out", []),
                "home_fitness": 100 - match_news.get("home_injuries", {}).get("impact_score", 0) * 2,
                "away_fitness": 100 - match_news.get("away_injuries", {}).get("impact_score", 0) * 2,
            }
        except:
            injury_data = {
                "home_injuries": [],
                "away_injuries": [],
                "home_fitness": 100,
                "away_fitness": 100,
            }
        
        # 战术数据
        tactical_data = {
            "home_formation": environment_data.get("home_tactical", "4-3-3"),
            "away_formation": environment_data.get("away_tactical", "4-4-2"),
            "home_style": environment_data.get("home_tactical", "balanced"),
            "away_style": environment_data.get("away_tactical", "balanced"),
        }
        
        # 市场数据
        bsd_odds_data = result.get("bsd_odds", {})
        market_data = {
            "odds_home": bsd_odds_data.get("average_home", oh) if oh else None,
            "odds_draw": bsd_odds_data.get("average_draw", od) if od else None,
            "odds_away": bsd_odds_data.get("average_away", oa) if oa else None,
        }
        
        # 生成比分矩阵
        lambda_home = poisson_data.get("lambda_home", 1.4)
        lambda_away = poisson_data.get("lambda_away", 1.4)
        score_matrix = sm.generate_score_matrix(lambda_home, lambda_away)
        
        # 执行解释层分析
        explanation_result = explanation_engine.analyze(
            elo_data=elo_data,
            poisson_data=poisson_data,
            mc_data=mc_data,
            bayesian_data=bayesian_data,
            environment_data=environment_data,
            injury_data=injury_data,
            tactical_data=tactical_data,
            market_data=market_data,
            score_matrix=score_matrix,
        )
        
        result["explanation"] = explanation_result
        
    except Exception as e:
        # 解释层失败不影响主流程
        pass

    return result


def _build_match_environment(hid, aid, hn, an) -> mc.MatchEnvironment:
    """
    构建比赛环境 — 使用天气API获取真实环境信息。
    根据比赛场地获取实时气温、海拔、时差等数据。
    """
    # 使用天气API获取比赛场地的真实环境信息
    try:
        match_env = weather.get_match_environment(hn, an)
        venue_altitude = match_env.get("altitude", 0)
        temperature = match_env.get("temperature", 22)
        is_rain = match_env.get("is_rain", False)
        timezone_diff = match_env.get("timezone_diff", 0)
        venue_city = match_env.get("venue_city", "未知")
        env_source = match_env.get("source", "预设数据")
    except:
        venue_altitude = 0
        temperature = 22
        is_rain = False
        timezone_diff = 0
        venue_city = "未知"
        env_source = "预设数据（API未连接）"

    # 补水机制：气温>25°C触发补水
    is_water_break = temperature > 25

    return mc.MatchEnvironment(
        home_team_id=hid or 0,
        away_team_id=aid or 0,
        venue_altitude=venue_altitude,
        temperature=temperature,
        is_rain=is_rain,
        home_travel_distance_km=0,
        home_rest_days=7,
        home_days_since_last=7,
        is_high_stakes=False,
        is_water_break=is_water_break,
    )


def _render_analysis_card(data: dict):
    """
    渲染多维度分析卡片 — 整合到单个输出卡片
    """
    if not data:
        return

    # 获取球队名用于显示国旗
    _hn = data.get("_home_name", "")
    _an = data.get("_away_name", "")
    _hf = flag(_hn) if _hn else "🏳️"
    _af = flag(_an) if _an else "🏳️"

    # ── 整合到单个卡片 ──
    with st.container():
        st.markdown(f"### {_hf} {_hn} vs {_af} {_an} 比赛分析")
        
        # 核心预测输出（最重要）
        explanation = data.get("explanation")
        if explanation:
            st.markdown("**🎯 核心预测输出**")
            
            # 胜平负概率
            probs = explanation.win_draw_lose_probs
            c1, c2, c3 = st.columns(3)
            c1.metric("主胜概率", f"{probs['home_win']:.1%}")
            c2.metric("平局概率", f"{probs['draw']:.1%}")
            c3.metric("客胜概率", f"{probs['away_win']:.1%}")
            
            # 权重说明
            weights = probs.get("weights", {})
            if weights:
                st.caption(f"权重配置: 市场赔率{weights.get('market', 0)*100:.0f}% | Elo{weights.get('elo', 0)*100:.0f}% | 伤病{weights.get('injury', 0)*100:.0f}% | 战术{weights.get('tactical', 0)*100:.0f}%")
            
            # 预期进球
            goals = explanation.expected_goals
            c1, c2, c3 = st.columns(3)
            c1.metric(f"{_hn}预期进球", f"{goals['lambda_home']:.2f}")
            c2.metric(f"{_an}预期进球", f"{goals['lambda_away']:.2f}")
            c3.metric("总预期进球", f"{goals['total_expected']:.2f}")
            
            # 大小球和首选比分
            over_under = explanation.total_goals_prediction
            st.markdown(f"**大小球**: {over_under['recommendation']} (置信度{over_under['confidence']}) | **首选比分**: {explanation.top_score}")
            
            # 比分概率列表
            score_probs = explanation.score_probs[:5]
            score_str = " | ".join([f"{s['score']}({s['probability']}%)".format(s) for s in score_probs])
            st.caption(f"比分池: {score_str}")
            
            st.divider()
        
        # 详细分析（折叠）
        with st.expander("📊 详细分析（点击展开）"):
            # Elo实力对比
            elo = data.get("elo", {})
            if elo:
                st.markdown("**Elo实力对比**")
                c1, c2, c3, c4 = st.columns(4)
                c1.metric(f"{_hn}评分", f"{elo.get('home_rating', '?'):.0f}")
                c2.metric(f"{_an}评分", f"{elo.get('away_rating', '?'):.0f}")
                c3.metric("差值", f"{elo.get('diff', 0):+d}")
                c4.metric("FIFA排名", f"{elo.get('home_fifa_rank', '?')} vs {elo.get('away_fifa_rank', '?')}")
            
            # 泊松模型
            pois = data.get("poisson", {})
            if pois:
                st.markdown("**Dixon-Coles泊松模型**")
                c1, c2, c3 = st.columns(3)
                c1.metric(f"{_hn}λ", f"{pois.get('lambda_home', '?'):.3f}")
                c2.metric(f"{_an}λ", f"{pois.get('lambda_away', '?'):.3f}")
                c3.metric("总期望", f"{pois.get('expected_total', '?'):.2f}")
            
            # 蒙特卡洛模拟
            mc = data.get("monte_carlo", {})
            if mc:
                st.markdown(f"**蒙特卡洛模拟({config.MC_SIMULATIONS}次)**")
                hw = mc.get("home_win", 0)
                dr = mc.get("draw", 0)
                aw = mc.get("away_win", 0)
                st.caption(f"主胜{hw:.1%} | 平{dr:.1%} | 客胜{aw:.1%}")
                top = mc.get("top_scorelines", [])
                if top:
                    st.caption(f"最可能比分: {top[0]['score']}({top[0]['probability']}%)")
            
            # 贝叶斯融合
            bayes = data.get("bayesian")
            if bayes:
                st.markdown("**贝叶斯融合**")
                st.caption(f"融合: 主胜{bayes.get('home_win', 0):.1%} | 平{bayes.get('draw', 0):.1%} | 客胜{bayes.get('away_win', 0):.1%}")
            
            # BSD赔率
            bsd_odds = data.get("bsd_odds")
            if bsd_odds and bsd_odds.get("average_home", 0) > 0:
                st.markdown("**BSD实时赔率**")
                st.caption(f"主胜{bsd_odds.get('average_home', 0):.2f} | 平{bsd_odds.get('average_draw', 0):.2f} | 客胜{bsd_odds.get('average_away', 0):.2f}")
            
            # Kelly仓位
            kelly = data.get("kelly")
            if kelly:
                st.markdown("**Kelly仓位**")
                rec = kelly.get("recommendation", "跳过")
                stake = kelly.get("stake_pct", 0)
                st.caption(f"建议: {rec} | 仓位: {stake:.2f}%")
            
            # 解释层维度
            if explanation:
                st.markdown("**解释层维度**")
                elo_a = explanation.elo_analysis
                injury_a = explanation.injury_fitness
                tactical_a = explanation.tactical_matchup
                
                st.caption(f"Elo: {elo_a['level']} | 伤病影响: 主{injury_a['total_home_impact']*100:+.1f}% 客{injury_a['total_away_impact']*100:+.1f}% | 战术: {tactical_a['summary'][:30]}")
                
                # 风险分析摘要
                risk = explanation.risk_analysis
                st.markdown("**风险分析**")
                st.caption(f"冷门{risk['upset']['level']} | 角球预期{risk['corner']['total_corners_expected']} | 黄牌预期{risk['card']['total_cards_expected']} | 双方进球{risk['btts']['probability']:.1%}")
            
            # 比分矩阵摘要
            if explanation:
                matrix_analysis = sm.analyze_matrix(explanation.score_matrix)
                st.markdown("**比分矩阵**")
                st.caption(f"主胜{matrix_analysis['home_win_prob']}% | 平{matrix_analysis['draw_prob']}% | 客胜{matrix_analysis['away_win_prob']}% | 大2.5球{matrix_analysis['over_2_5_prob']}%")
        
        # LLM深度分析
        if llm.is_llm_enabled():
            with st.expander("🤖 LongCat深度分析"):
                elo_data_for_llm = {
                    "home_rating": elo.get("home_rating", 1500),
                    "away_rating": elo.get("away_rating", 1500),
                    "diff": elo.get("diff", 0),
                    "home_fifa_rank": elo.get("home_fifa_rank", "?"),
                    "away_fifa_rank": elo.get("away_fifa_rank", "?"),
                }
                
                bsd_odds_data = data.get("bsd_odds", {})
                odds_data_for_llm = {
                    "average_home": bsd_odds_data.get("average_home", "?"),
                    "average_draw": bsd_odds_data.get("average_draw", "?"),
                    "average_away": bsd_odds_data.get("average_away", "?"),
                }
                
                injury_data_for_llm = {"home_summary": "", "away_summary": ""}
                news_data_for_llm = []
                report_data_for_llm = {"home_report": "", "away_report": ""}
                
                with st.spinner("分析中..."):
                    llm_analysis = llm.generate_match_analysis(
                        _hn, _an, elo_data_for_llm, odds_data_for_llm,
                        injury_data_for_llm, news_data_for_llm, report_data_for_llm
                    )
                
                st.markdown(llm_analysis)
                st.caption(f"模型: {llm.LLM_CONFIG.get('model', 'LongCat-2.0-Preview')}")
        
        # 观点摘要
        if explanation:
            st.divider()
            st.markdown("**📝 观点摘要**")
            st.markdown(explanation.summary)

    # ── 8. 环境因素 ──
    env = data.get("environment", {})
    # 始终显示环境因素（即使都是默认值，也展示中性环境说明）
    with st.expander("🌍 环境因素"):
        env_lines = []
        temp = env.get("temperature", 22)
        alt = env.get("altitude", 0)
        is_rain = env.get("is_rain", False)
        tz = env.get("timezone_diff", 0)
        is_high = env.get("is_high_stakes", False)
        ht = env.get("home_tactical", "balanced")
        at = env.get("away_tactical", "balanced")

        # 气温（始终显示）
        if temp > 28:
            env_lines.append(f"🌡️ 高温 {temp}°C（补水机制已激活）")
        elif temp > 25:
            env_lines.append(f"🌡️ 气温 {temp}°C（接近补水阈值）")
        else:
            env_lines.append(f"🌡️ 气温 {temp}°C（舒适）")

        # 海拔（始终显示）
        if alt > 1500:
            env_lines.append(f"⛰️ 高海拔 {alt}m（体能影响-6%）")
        elif alt > 0:
            env_lines.append(f"⛰️ 海拔 {alt}m（轻微影响）")
        else:
            env_lines.append(f"⛰️ 海拔 {alt}m（海平面）")

        # 天气
        if is_rain:
            env_lines.append("🌧️ 有雨（控球型-2%，长传型+2%）")
        else:
            env_lines.append("☀️ 无雨")

        # 时差（始终显示）
        if abs(tz) > 3:
            env_lines.append(f"🕐 时差 {tz:.0f}h（体能-3%）")
        else:
            env_lines.append(f"🕐 时差 {tz:.0f}h（无影响）")

        # 比赛重要性
        if is_high:
            env_lines.append("🔥 大赛高压（进攻期望-3%）")
        else:
            env_lines.append("⚽ 小组赛阶段（正常压力）")

        # 战术
        env_lines.append(f"⚔️ 战术: {ht} vs {at}")

        for line in env_lines:
            st.markdown(f"  {line}")

    # ── 9. 实时数据（BSD API）──
    if bsd.is_bsd_available():
        with st.expander("📡 实时数据（BSD API）"):
            realtime_data = bsd.get_realtime_match_data(_hn, _an)
            
            # 伤病信息
            inj_h = realtime_data.get("injuries_home", {})
            inj_a = realtime_data.get("injuries_away", {})
            st.markdown(f"**📋 {_hf} {_hn} 伤病情况:**")
            st.markdown(f"  {inj_h.get('summary', '暂无数据')}")
            st.markdown(f"**📋 {_af} {_an} 伤病情况:**")
            st.markdown(f"  {inj_a.get('summary', '暂无数据')}")
            
            # 阵容信息
            lineup = realtime_data.get("lineups", {})
            st.markdown(f"**👕 阵容:** {lineup.get('summary', '暂无数据')}")
            
            # 教练信息
            coach_h = realtime_data.get("coach_home", {})
            coach_a = realtime_data.get("coach_away", {})
            if coach_h.get("summary"):
                st.markdown(f"**👤 {_hn} 教练:** {coach_h.get('summary', '')}")
            if coach_a.get("summary"):
                st.markdown(f"**👤 {_an} 教练:** {coach_a.get('summary', '')}")
            
            # 赔率对比
            odds = realtime_data.get("odds", {})
            if odds.get("summary"):
                st.markdown(f"**💰 赔率:** {odds.get('summary', '')}")
            
            # 综合摘要
            st.divider()
            st.markdown(realtime_data.get("summary", ""))

    # ── 10. 新闻动态（RSS + WorldCupWiki）──
    with st.expander("📰 新闻动态（免费数据源）"):
        match_news = news.get_match_news_summary(_hn, _an)
        
        # 伤病名单
        st.markdown(f"**📋 {_hn} 伤病名单:**")
        st.markdown(f"  {match_news['home_injuries']['summary']}")
        st.markdown(f"**📋 {_an} 伤病名单:**")
        st.markdown(f"  {match_news['away_injuries']['summary']}")
        
        # 影响评分
        st.caption(f"伤病影响评分: {_hn} {match_news['home_injuries']['impact_score']}/10 | {_an} {match_news['away_injuries']['impact_score']}/10")
        
        # 最新新闻
        st.divider()
        st.markdown(f"**📰 {_hn} 最新新闻:**")
        for n in match_news["home_news"][:3]:
            st.markdown(f"  • [{n['title'][:60]}...]({n['link']})")
        
        st.markdown(f"**📰 {_an} 最新新闻:**")
        for n in match_news["away_news"][:3]:
            st.markdown(f"  • [{n['title'][:60]}...]({n['link']})")
        
        # 数据来源
        st.divider()
        st.caption("数据来源: Sports Mole RSS | WorldCupWiki 伤病名单")

    # ── 10. 实时情报（手动导入）──
    extra = data.get("extra")
    if extra:
        with st.expander("🌐 实时情报"):
            st.markdown(f'<div class="search-result">{extra}</div>', unsafe_allow_html=True)
    
    # ── 11. 解释层核心输出 ──
    explanation = data.get("explanation")
    if explanation:
        st.divider()
        st.markdown("### 🎯 核心预测输出")
        
        # 胜平负概率
        probs = explanation.win_draw_lose_probs
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("主胜概率", f"{probs['home_win']:.1%}")
        c2.metric("平局概率", f"{probs['draw']:.1%}")
        c3.metric("客胜概率", f"{probs['away_win']:.1%}")
        
        # 调整因子展示
        adjustments = probs.get("adjustments", {})
        if adjustments:
            adj_text = "调整因子: Elo{:+.1%} | 环境{:+.1%} | 伤病主{:+.1%}/客{:+.1%} | 战术{:+.1%}".format(
                adjustments.get("elo", 0),
                adjustments.get("environment", 0),
                adjustments.get("injury_home", 0),
                adjustments.get("injury_away", 0),
                adjustments.get("tactical_home", 0),
            )
            c4.metric("调整", adj_text[:30])
        
        # 预期进球
        goals = explanation.expected_goals
        c1, c2, c3 = st.columns(3)
        c1.metric(f"{_hn} 预期进球", f"{goals['lambda_home']:.2f}")
        c2.metric(f"{_an} 预期进球", f"{goals['lambda_away']:.2f}")
        c3.metric("总预期进球", f"{goals['total_expected']:.2f}")
        
        # 大小球预测
        over_under = explanation.total_goals_prediction
        c1, c2, c3 = st.columns(3)
        c1.metric("大小球推荐", over_under['recommendation'])
        c2.metric("置信度", over_under['confidence'])
        c3.metric("最可能总进球", f"{over_under['most_likely_total']}")
        
        # 首选比分
        st.info(f"**📌 首选比分**: {explanation.top_score}")
        
        # 比分概率列表
        score_probs = explanation.score_probs[:5]
        score_str = " | ".join([f"{s['score']} ({s['probability']}%)".format(s) for s in score_probs])
        st.caption(f"比分池: {score_str}")
    
    # ── 12. 解释层维度展示 ──
    if explanation:
        with st.expander("🔬 解释层维度分析"):
            st.markdown("**这不是装饰，所有维度都会影响最终预测！**")
            
            # Elo评分系统
            elo_analysis = explanation.elo_analysis
            st.markdown(f"**📊 Elo评分系统**")
            st.markdown(f"  • 主队评分: {elo_analysis['home_rating']} | 客队评分: {elo_analysis['away_rating']}")
            st.markdown(f"  • 评分差距: {elo_analysis['diff']} → {elo_analysis['level']}")
            st.markdown(f"  • 对胜率影响: {elo_analysis['impact']*100:+.1f}%")
            
            # 补水时刻战术影响
            hydration = explanation.hydration_impact
            st.markdown(f"**💧 补水时刻战术影响**")
            st.markdown(f"  • 上半场30分钟: 主队战术调整概率{hydration['first_half_30min']['home_tactical_shift']*100:.1f}%")
            st.markdown(f"  • 下半场30分钟: 主队战术调整概率{hydration['second_half_30min']['home_tactical_shift']*100:.1f}%")
            st.markdown(f"  • 补水后进球影响: {hydration['goal_impact']*100:+.1f}%")
            st.markdown(f"  • {hydration['summary']}")
            
            # 主场/天气因素
            env_factors = explanation.environment_factors
            st.markdown(f"**🌍 主场/天气因素**")
            st.markdown(f"  • 主场优势: +{env_factors['home_advantage']*100:.1f}%")
            st.markdown(f"  • 温度影响: {env_factors['temperature_impact']*100:+.1f}%")
            st.markdown(f"  • 雨天影响: {env_factors['rain_impact']*100:+.1f}%")
            st.markdown(f"  • 海拔影响: {env_factors['altitude_impact']*100:+.1f}%")
            st.markdown(f"  • 总环境影响: {env_factors['total_impact']*100:+.1f}%")
            
            # 伤停/体能
            injury_fitness = explanation.injury_fitness
            st.markdown(f"**🏥 伤停/体能分析**")
            st.markdown(f"  • 主队伤病人数: {injury_fitness['home_injury_count']} → 影响{injury_fitness['home_injury_impact']*100:+.1f}%")
            st.markdown(f"  • 客队伤病人数: {injury_fitness['away_injury_count']} → 影响{injury_fitness['away_injury_impact']*100:+.1f}%")
            st.markdown(f"  • 主队体能: {injury_fitness['home_fitness']}% → 影响{injury_fitness['home_fitness_impact']*100:+.1f}%")
            st.markdown(f"  • 客队体能: {injury_fitness['away_fitness']}% → 影响{injury_fitness['away_fitness_impact']*100:+.1f}%")
            
            # 战术相克
            tactical = explanation.tactical_matchup
            st.markdown(f"**⚔️ 战术相克分析**")
            st.markdown(f"  • 阵型: {tactical['home_formation']} vs {tactical['away_formation']}")
            st.markdown(f"  • 风格: {tactical['home_style']} vs {tactical['away_style']}")
            st.markdown(f"  • 主队战术优势: {tactical['total_home_advantage']*100:+.1f}%")
            st.markdown(f"  • {tactical['summary']}")
            
            # 市场信号
            market = explanation.market_signals
            st.markdown(f"**📈 市场信号分析**")
            st.markdown(f"  • 赔率: 主胜{market['odds_home']} 平{market['odds_draw']} 客胜{market['odds_away']}")
            st.markdown(f"  • 隐含概率: 主胜{market['implied_home']:.1%} 平{market['implied_draw']:.1%} 客胜{market['implied_away']:.1%}")
            st.markdown(f"  • 市场信号: {market['signal']} (置信度{market['confidence']})")
    
    # ── 13. 风险分析（拆分）──
    if explanation:
        risk = explanation.risk_analysis
        with st.expander("⚠️ 风险分析（多维度拆分）"):
            # 冷门风险
            upset = risk['upset']
            st.markdown(f"**🎯 冷门风险**")
            st.markdown(f"  • 风险级别: {upset['level']}")
            st.markdown(f"  • 冷门概率: {upset['probability']:.1%}")
            st.markdown(f"  • 方向: {upset['direction']}")
            
            # 角球风险
            corner = risk['corner']
            st.markdown(f"**🚩 角球风险**")
            st.markdown(f"  • 主队预期角球: {corner['home_corners_expected']}")
            st.markdown(f"  • 客队预期角球: {corner['away_corners_expected']}")
            st.markdown(f"  • 总角球预期: {corner['total_corners_expected']}")
            st.markdown(f"  • 大9.5角球概率: {corner['over_9_5_prob']:.1%}")
            
            # 红黄牌风险
            card = risk['card']
            st.markdown(f"**📋 红黄牌风险**")
            st.markdown(f"  • 主队预期黄牌: {card['home_cards_expected']}")
            st.markdown(f"  • 客队预期黄牌: {card['away_cards_expected']}")
            st.markdown(f"  • 总黄牌预期: {card['total_cards_expected']}")
            st.markdown(f"  • 红牌概率: {card['red_card_probability']:.1%}")
            
            # 双方进球风险
            btts = risk['btts']
            st.markdown(f"**⚽ 双方进球(BTTS)**")
            st.markdown(f"  • 概率: {btts['probability']:.1%}")
            st.markdown(f"  • 推荐: {btts['recommendation']}")
            
            # 大小球风险
            over_under_risk = risk['over_under']
            st.markdown(f"**📊 大小球风险**")
            st.markdown(f"  • 风险级别: {over_under_risk['level']}")
            st.markdown(f"  • 预期总进球: {over_under_risk['expected_total']}")
            
            # 关键球员风险
            key_player = risk['key_player']
            st.markdown(f"**👤 关键球员风险**")
            st.markdown(f"  • 风险级别: {key_player['level']}")
            st.markdown(f"  • 主队关键伤病: {key_player['home_key_injuries']}")
            st.markdown(f"  • 客队关键伤病: {key_player['away_key_injuries']}")
            if key_player['affected_players']:
                st.markdown(f"  • 受影响球员: {', '.join(key_player['affected_players'])}")
            
            # 球员心理压力
            psychology = risk['psychology']
            st.markdown(f"**🧠 球员心理压力**")
            st.markdown(f"  • 压力级别: {psychology['level']}")
            st.markdown(f"  • 主队压力: {psychology['home_pressure']}")
            st.markdown(f"  • 客队压力: {psychology['away_pressure']}")
            st.markdown(f"  • 压力不对称: {psychology['pressure_asymmetry']:.2f}")
            
            # 观点摘要
            st.divider()
            st.markdown(f"**📝 风险观点摘要**")
            st.markdown(risk['summary'])
    
    # ── 14. 0-8球比分矩阵 ──
    if explanation:
        with st.expander("📊 0-8球比分矩阵"):
            matrix = explanation.score_matrix
            
            # 显示矩阵表格
            st.markdown("**比分概率矩阵（百分比）**")
            
            # 创建DataFrame显示
            import pandas as pd
            df_matrix = pd.DataFrame(matrix, 
                                     columns=[f"客{j}球" for j in range(len(matrix[0]))],
                                     index=[f"主{i}球" for i in range(len(matrix))])
            
            # 高亮显示概率>5%的比分
            def highlight_high(s):
                return ['background-color: #90EE90' if v > 5 else '' for v in s]
            
            st.dataframe(df_matrix.style.apply(highlight_high))
            
            # 矩阵分析
            matrix_analysis = sm.analyze_matrix(matrix)
            
            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("主胜概率", f"{matrix_analysis['home_win_prob']}%")
            c2.metric("平局概率", f"{matrix_analysis['draw_prob']}%")
            c3.metric("客胜概率", f"{matrix_analysis['away_win_prob']}%")
            c4.metric("大2.5球", f"{matrix_analysis['over_2_5_prob']}%")
            c5.metric("双方进球", f"{matrix_analysis['btts_prob']}%")
            
            st.caption(f"主队零封概率: {matrix_analysis['clean_sheet_home']}% | 客队零封概率: {matrix_analysis['clean_sheet_away']}%")
    
    # ── 15. 观点摘要 ──
    if explanation:
        st.divider()
        st.markdown("### 📝 观点摘要")
        st.markdown(explanation.summary)


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

    t1, t2, t3 = st.tabs([
        f"📺 已完赛 ({len(done)})",
        f"🔮 未赛预测 ({len(todo)})",
        f"📥 赔率导入"
    ])

    # ── Tab 1: 已完赛 ──
    with t1:
        if not done:
            st.info("暂无已完成比赛")

        # 模型复盘统计
        review_stats = {"total": 0, "correct_direction": 0, "correct_result": 0,
                        "elo_correct": 0, "poisson_correct": 0, "mc_correct": 0}

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
                analysis = _do_analysis(
                    hid, aid, engine, h, a,
                    m.get("odds_home"), m.get("odds_draw"), m.get("odds_away"),
                    stage, None,  # xtra 已移除
                    is_knockout=is_knockout,
                    motivation_home=mh, motivation_away=ma,
                    use_market_odds=bool(m.get("odds_home")),
                )
                _render_analysis_card(analysis)
                
                # 保存预测数据到session_state（用于复盘）
                prediction_key = f"_prediction_{h}_{a}"
                st.session_state[prediction_key] = analysis

                # ── 模型复盘 ──
                if hs is not None and gs is not None:
                    actual_h = int(hs)
                    actual_a = int(gs)
                    actual_result = "home" if actual_h > actual_a else ("away" if actual_a > actual_h else "draw")

                    # Elo复盘
                    elo_pred = analysis.get("elo", {})
                    if elo_pred:
                        elo_home = elo_pred.get("home_win", 0)
                        elo_draw = elo_pred.get("draw", 0)
                        elo_away = elo_pred.get("away_win", 0)
                        elo_pred_result = "home" if elo_home > max(elo_draw, elo_away) else ("away" if elo_away > max(elo_home, elo_draw) else "draw")
                        elo_correct = (elo_pred_result == actual_result)
                        review_stats["elo_correct"] += int(elo_correct)

                    # 泊松复盘
                    pois_pred = analysis.get("poisson", {})
                    if pois_pred:
                        lh_p = pois_pred.get("lambda_home", 0)
                        la_p = pois_pred.get("lambda_away", 0)
                        pois_pred_result = "home" if lh_p > la_p else ("away" if la_p > lh_p else "draw")
                        pois_correct = (pois_pred_result == actual_result)
                        review_stats["poisson_correct"] += int(pois_correct)

                    # 蒙特卡洛复盘
                    mc_pred = analysis.get("monte_carlo", {})
                    if mc_pred:
                        mc_home = mc_pred.get("home_win", 0)
                        mc_draw = mc_pred.get("draw", 0)
                        mc_away = mc_pred.get("away_win", 0)
                        mc_pred_result = "home" if mc_home > max(mc_draw, mc_away) else ("away" if mc_away > max(mc_home, mc_draw) else "draw")
                        mc_correct = (mc_pred_result == actual_result)
                        review_stats["mc_correct"] += int(mc_correct)

                    # 综合方向判断（Elo+泊松+MC多数投票）
                    votes = []
                    if elo_pred: votes.append(elo_pred_result)
                    if pois_pred: votes.append(pois_pred_result)
                    if mc_pred: votes.append(mc_pred_result)
                    if votes:
                        from collections import Counter
                        majority = Counter(votes).most_common(1)[0][0]
                        direction_correct = (majority == actual_result)
                        review_stats["correct_direction"] += int(direction_correct)
                        review_stats["total"] += 1

                    # 显示单场复盘
                    with st.expander("📊 模型复盘"):
                        c1, c2, c3 = st.columns(3)
                        if elo_pred:
                            c1.metric("Elo预测", f"{'✅' if elo_correct else '❌'} {elo_pred_result}")
                        if pois_pred:
                            c2.metric("泊松预测", f"{'✅' if pois_correct else '❌'} {pois_pred_result}")
                        if mc_pred:
                            c3.metric("MC预测", f"{'✅' if mc_correct else '❌'} {mc_pred_result}")
                        st.caption(f"实际结果: {actual_h}:{actual_a} ({actual_result}) | 多数投票: {'✅' if direction_correct else '❌'}")

        # 显示整体复盘统计
        if review_stats["total"] > 0:
            st.divider()
            st.subheader("📈 模型复盘统计")
            total = review_stats["total"]
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("总场次", total)
            c2.metric("方向正确率", f"{review_stats['correct_direction']/total:.1%}")
            if review_stats["elo_correct"] > 0:
                c3.metric("Elo准确率", f"{review_stats['elo_correct']/total:.1%}")
            if review_stats["mc_correct"] > 0:
                c4.metric("MC准确率", f"{review_stats['mc_correct']/total:.1%}")
            st.caption("方向正确率 = Elo+泊松+MC 多数投票与实际结果一致的比率")

    # ── Tab 2: 未赛预测 ──
    with t2:
        # 检查是否有已导入的赔率
        imported_odds = st.session_state.get("_imported_odds", {})

        from datetime import datetime, timedelta
        today = datetime.now().date()
        tomorrow = today + timedelta(days=1)

        # 按日期分组未赛比赛
        matches_by_date = {}
        for m in todo:
            d = m.get("date", "")[:10]
            if d:
                matches_by_date.setdefault(d, []).append(m)

        # 找出有比赛的所有日期（排序）
        all_dates = sorted(matches_by_date.keys())

        # 默认只展示"后一天"的比赛（即明天，如果明天有比赛；否则找下一个有比赛的日期）
        default_show_date = None
        for d in all_dates:
            d_obj = datetime.strptime(d, "%Y-%m-%d").date()
            if d_obj >= today:
                default_show_date = d
                break

        c1, c2, c3 = st.columns([2, 2, 3])
        with c1:
            sa = st.checkbox("显示全部比赛", value=False)
        with c2:
            sg = st.selectbox("按小组筛选",
                              ["全部"] + sorted({m.get("group_name", "") for m in todo if m.get("group_name")}))
        with c3:
            if sa:
                date_options = ["全部日期"] + all_dates
                sd = st.selectbox("按日期筛选", date_options, index=0)
            else:
                # 非全部模式：显示当前默认日期信息
                if default_show_date:
                    dd = datetime.strptime(default_show_date, "%Y-%m-%d").date()
                    day_label = "今天" if dd == today else ("明天" if dd == tomorrow else f"{dd.month}月{dd.day}日")
                    st.info(f"📅 展示 {day_label} ({default_show_date}) 的 {len(matches_by_date.get(default_show_date, []))} 场比赛")
                else:
                    st.info("📅 暂无 upcoming 比赛")

        filt = todo
        if not sa:
            # 只展示后一天（默认日期）的比赛
            if default_show_date:
                filt = matches_by_date.get(default_show_date, [])
            else:
                filt = []
        else:
            # 全部模式但按日期筛选
            if sa and 'sd' in dir() and sd != "全部日期":
                filt = matches_by_date.get(sd, [])

        if sg != "全部":
            filt = [m for m in filt if m.get("group_name") == sg]

        if not filt:
            if not sa and default_show_date:
                st.info(f"⏳ {default_show_date} 暂无符合条件的比赛")
            else:
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

                    analysis = _do_analysis(
                        hid, aid, engine, h, a,
                        oh, od, oa,
                        stage, None,  # xtra 已移除
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
#  Tab 4 — 复盘分析
# ──────────────────────────────────────────────
def render_review(data):
    """复盘分析Tab"""
    st.header("📝 复盘分析")
    st.caption("比赛结束后，根据真实赛果分析预测准确性")
    
    # 初始化复盘引擎
    if "_review_engine" not in st.session_state:
        st.session_state["_review_engine"] = review.ReviewEngine()
    
    engine = st.session_state["_review_engine"]
    
    # 获取已完赛比赛
    matches = data.get("matches") or []
    finished_matches = [m for m in matches if m.get("match_des") == "完赛"]
    
    if not finished_matches:
        st.info("暂无已完赛比赛可供复盘")
        return
    
    # 统计数据展示
    stats = engine.get_statistics()
    if stats["total"] > 0:
        st.subheader("📊 总体命中率统计")
        c1, c2, c3, c4, c5, c6 = st.columns(6)
        c1.metric("复盘场次", stats["total"])
        c2.metric("一选命中", f"{stats['first_choice_hit_rate']}%")
        c3.metric("胜平负命中", f"{stats['result_hit_rate']}%")
        c4.metric("大小球命中", f"{stats['over_under_hit_rate']}%")
        c5.metric("总进球区间", f"{stats['total_range_hit_rate']}%")
        c6.metric("冷门命中", f"{stats['upset_hit_rate']}%")
        
        st.caption(f"平均比分偏差: {stats['avg_score_deviation']}球 | 平均总进球偏差: {stats['avg_total_deviation']}球")
    
    st.divider()
    
    # 选择比赛复盘
    st.subheader("🔍 单场复盘")
    
    # 比赛选择
    match_options = [f"{m.get('host_team_name','?')} vs {m.get('guest_team_name','?')} ({m.get('host_team_score','?')}-{m.get('guest_team_score','?')})" 
                     for m in finished_matches]
    
    selected_match = st.selectbox("选择已完赛比赛", match_options, key="review_match_select")
    
    if selected_match:
        # 获取比赛数据
        idx = match_options.index(selected_match)
        match_data = finished_matches[idx]
        
        home_name = match_data.get("host_team_name", "")
        away_name = match_data.get("guest_team_name", "")
        actual_home_goals = match_data.get("host_team_score", 0)
        actual_away_goals = match_data.get("guest_team_score", 0)
        
        st.markdown(f"**比赛**: {home_name} vs {away_name}")
        st.markdown(f"**实际比分**: {actual_home_goals}-{actual_away_goals}")
        
        # 检查是否有预测数据
        prediction_key = f"_prediction_{home_name}_{away_name}"
        prediction_data = st.session_state.get(prediction_key)
        
        # 复盘按钮（始终显示）
        col1, col2 = st.columns(2)
        
        with col1:
            if prediction_data:
                # 已有预测数据，直接复盘
                if st.button("📊 开始复盘", key="start_review_btn", type="primary"):
                    result = engine.review_match(
                        f"{home_name} vs {away_name}",
                        actual_home_goals,
                        actual_away_goals,
                        prediction_data
                    )
                    st.session_state["_last_review_result"] = result
            else:
                # 无预测数据，先自动预测再复盘
                if st.button("🤖 自动预测并复盘", key="auto_predict_review_btn", type="primary"):
                    with st.spinner("正在预测并复盘..."):
                        # 自动预测
                        analysis = _do_analysis(data, home_name, away_name)
                        st.session_state[prediction_key] = analysis
                        
                        # 复盘
                        result = engine.review_match(
                            f"{home_name} vs {away_name}",
                            actual_home_goals,
                            actual_away_goals,
                            analysis
                        )
                        st.session_state["_last_review_result"] = result
        
        with col2:
            if prediction_data:
                st.success("✅ 已有预测数据，可直接复盘")
            else:
                st.info("💡 点击按钮自动预测并复盘")
        
        # 显示复盘结果
        if "_last_review_result" in st.session_state:
            result = st.session_state["_last_review_result"]
            
            # 显示命中情况
            st.subheader("命中情况")
            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("一选命中", "✅" if result.first_choice_hit else "❌")
            c2.metric("二选命中", "✅" if result.second_choice_hit else "❌")
            c3.metric("胜平负命中", "✅" if result.result_hit else "❌")
            c4.metric("大小球命中", "✅" if result.over_under_hit else "❌")
            c5.metric("总进球区间", "✅" if result.total_range_hit else "❌")
            
            # ── 各模型预测准确性（新增）──
            st.subheader("📊 各模型预测准确性")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Elo模型", "✅" if result.elo_hit else "❌", result.elo_prediction.get("predicted", "?"))
            c2.metric("泊松模型", "✅" if result.poisson_hit else "❌", result.poisson_prediction.get("predicted", "?"))
            c3.metric("蒙特卡洛", "✅" if result.mc_hit else "❌", result.mc_prediction.get("predicted", "?"))
            c4.metric("贝叶斯融合", "✅" if result.bayesian_hit else "❌", result.bayesian_prediction.get("predicted", "?"))
            
            # 各模型预测详情
            with st.expander("📋 各模型预测详情"):
                st.markdown(f"**Elo模型**: {result.elo_prediction.get('home_win_prob', 0):.1%} 主胜 / {result.elo_prediction.get('draw_prob', 0):.1%} 平 / {result.elo_prediction.get('away_win_prob', 0):.1%} 客胜")
                st.markdown(f"**泊松模型**: λ主{result.poisson_prediction.get('lambda_home', 0):.2f} / λ客{result.poisson_prediction.get('lambda_away', 0):.2f} / 预期{result.poisson_prediction.get('expected_total', 0):.1f}球")
                st.markdown(f"**蒙特卡洛**: {result.mc_prediction.get('home_win_prob', 0):.1%} 主胜 / {result.mc_prediction.get('draw_prob', 0):.1%} 平 / {result.mc_prediction.get('away_win_prob', 0):.1%} 客胜")
                st.markdown(f"**贝叶斯融合**: {result.bayesian_prediction.get('home_win_prob', 0):.1%} 主胜 / {result.bayesian_prediction.get('draw_prob', 0):.1%} 平 / {result.bayesian_prediction.get('away_win_prob', 0):.1%} 客胜 / 置信度{result.bayesian_prediction.get('confidence', 0):.0%}")
            
            # ── 深度复盘分析（新增）──
            if result.model_analysis:
                st.subheader("🔍 深度复盘分析")
                
                # 综合分析
                st.markdown(f"**综合评价**: {result.model_analysis.get('overall', '无')}")
                
                # 异常检测
                anomalies = result.model_analysis.get("anomalies", [])
                if anomalies:
                    st.warning("检测到以下异常：")
                    for anomaly in anomalies:
                        st.markdown(anomaly)
                
                # 各模型分析
                with st.expander("📊 各模型偏差分析"):
                    for model_name in ["elo", "poisson", "mc", "bayesian"]:
                        model_data = result.model_analysis.get(model_name, {})
                        st.markdown(f"**{model_name.upper()}模型**:")
                        st.markdown(f"  • {model_data.get('summary', '无')}")
                        st.markdown(f"  • 偏差: {model_data.get('deviation', '无')}")
                        st.markdown(f"  • 建议: {model_data.get('suggestion', '无')}")
            
            # 显示偏差分析
            st.subheader("偏差分析")
            st.markdown(f"**比分偏差**: {result.score_deviation}球")
            st.markdown(f"**结果偏差**: {result.result_deviation}")
            st.markdown(f"**总进球偏差**: {result.total_goals_deviation}球")
            
            # 偏差原因
            st.subheader("偏差原因")
            for reason in result.deviation_reasons:
                st.markdown(f"- {reason}")
            
            # 显示完整报告
            st.divider()
            st.subheader("复盘报告")
            st.markdown(result.report)
            
            # 保存复盘历史
            st.success("复盘完成！数据已保存到历史记录")
    
    st.divider()
    
    # 复盘历史
    st.subheader("📚 复盘历史")
    
    if engine.history:
        for i, r in enumerate(engine.history[-10:], 1):  # 显示最近10场
            with st.expander(f"{i}. {r.match} - {r.actual_score}"):
                st.markdown(f"**预测比分**: {r.predicted_top_score}")
                st.markdown(f"**命中**: 一选{'✅' if r.first_choice_hit else '❌'} | 胜平负{'✅' if r.result_hit else '❌'} | 大小球{'✅' if r.over_under_hit else '❌'}")
                st.markdown(f"**偏差原因**: {r.deviation_reasons[0] if r.deviation_reasons else '无'}")
    else:
        st.info("暂无复盘历史")
    
    # 导出复盘数据
    st.divider()
    st.subheader("📤 导出复盘数据")
    
    if st.button("导出复盘报告（JSON）", key="export_review_btn"):
        if engine.history:
            import json
            from datetime import datetime
            
            export_data = {
                "statistics": engine.get_statistics(),
                "history": [
                    {
                        "match": r.match,
                        "actual_score": r.actual_score,
                        "predicted_score": r.predicted_top_score,
                        "first_choice_hit": r.first_choice_hit,
                        "result_hit": r.result_hit,
                        "over_under_hit": r.over_under_hit,
                        "deviation_reasons": r.deviation_reasons,
                    }
                    for r in engine.history
                ],
                "export_time": datetime.now().isoformat(),
            }
            
            st.download_button(
                "下载 JSON 文件",
                json.dumps(export_data, ensure_ascii=False, indent=2),
                file_name=f"review_report_{datetime.now().strftime('%Y%m%d')}.json",
                mime="application/json"
            )
        else:
            st.warning("暂无复盘数据可导出")


#  Tab 5 — 仓位建议（Kelly + 过滤 + 风控）
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
    st.header("🛠️ 数据管理")
    st.caption("数据来源：聚合API（内置） + 本地数据")

    # 数据源显示
    loc = ld.load_all()
    source = loc.get("source", "本地数据")
    sync_time = loc.get("sync_time", "未知")
    
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("数据来源", source)
    c2.metric("积分榜条目", f"{len(loc.get('standings',[]))} 条")
    sc = loc.get("schedule", [])
    fin = sum(1 for m in sc if m.get("match_des")=="完赛")
    c3.metric("赛程", f"{len(sc)} 场 (已赛{fin})")
    c4.metric("同步时间", sync_time[:19] if sync_time else time.strftime("%H:%M:%S"))

    st.divider()

    # API同步按钮
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔄 从聚合API拉取最新数据", type="primary"):
            try:
                with st.spinner("⏳ 正在从聚合API拉取赛程/球队/积分榜..."):
                    juhe_data = juhe.sync_all_data()
                    
                    if juhe_data.get("schedule"):
                        # 保存到本地
                        ld.save_schedule(juhe_data["schedule"])
                        st.success(f"✅ 赛程已更新: {len(juhe_data['schedule'])} 场")
                    
                    if juhe_data.get("teams"):
                        ld.save_teams(juhe_data["teams"])
                        st.success(f"✅ 球队已更新: {len(juhe_data['teams'])} 支")
                    
                    if juhe_data.get("standings"):
                        ld.save_standings(juhe_data["standings"])
                        st.success(f"✅ 积分榜已更新: {len(juhe_data['standings'])} 条")
                    
                    if juhe_data.get("schedule") or juhe_data.get("standings"):
                        st.cache_data.clear()
                        st.rerun()
                    else:
                        st.warning("⚠️ 聚合API返回空数据")
            except Exception as e:
                st.error(f"❌ 聚合API拉取失败: {str(e)[:200]}")
    
    with col2:
        if st.button("📊 查看聚合API状态"):
            st.info(f"**聚合API配置**")
            st.caption(f"API地址: https://apis.juhe.cn/fapigw/worldcup2026/schedule")
            st.caption(f"API Key: cacdf03f36ed28cd9c61785656c30dfb（内置）")
            st.caption(f"MCP服务: https://mcp.juhe.cn/sse?token=...（内置）")

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

        # ── BSD API Key（内置）──
        st.divider()
        st.markdown("**🔑 BSD API Key（实时数据）**")
        st.caption("内置API Key已配置")
        st.success("✅ BSD API已启用")
        st.caption("可获取：伤病/阵容/赔率等实时数据")

        # ── 大模型推理（内置LongCat）──
        st.divider()
        st.markdown("**🤖 大模型推理增强**")
        st.caption("内置模型: LongCat-2.0-Preview")
        
        llm_enabled = st.checkbox("启用大模型推理", value=True, key="llm_enabled_checkbox")
        llm.set_llm_enabled(llm_enabled)
        
        if llm_enabled:
            st.success("✅ LongCat-2.0-Preview 已启用")
            st.caption("用于生成深度分析和推理增强")
        else:
            st.info("💡 大模型推理已禁用，仅使用数学模型预测")

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
            with st.expander("🏆 Elo 实力排行（全部48支球队）"):
                # 显示全部48支球队，按Elo评分排序
                sorted_teams = sorted(eng.export_ratings().items(), key=lambda x: -x[1]["rating"])
                for r, (tid, info) in enumerate(sorted_teams, 1):
                    meta = ID2META.get(tid, (None, None, None, None))
                    flag_ = FLAG.get(meta[1], "🏳️") if meta[1] else "🏳️"
                    fifa_rank = meta[3] if meta[3] else "?"
                    st.text(f"{r}. {flag_} {info['name']} — Elo:{info['rating']:.0f} | FIFA排名:{fifa_rank}")
        st.divider()
        if st.button("🔄 刷新"): st.cache_data.clear(); st.rerun()

    tabs = st.tabs(["📊 积分榜","🏆 淘汰赛","🔮 比赛分析","📝 复盘分析","💰 仓位建议","🛠️ 数据管理"])
    with tabs[0]: render_standings(data)
    with tabs[1]: render_knockout(data)
    with tabs[2]: render_predictions(data)
    with tabs[3]: render_review(data)
    with tabs[4]: render_portfolio(data)
    with tabs[5]: render_data_manager()


if __name__ == "__main__":
    main()
