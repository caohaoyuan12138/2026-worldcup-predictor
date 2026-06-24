import streamlit as st
import json
import math
import random
import os
from datetime import datetime

# ============================================================
# 页面配置
# ============================================================
st.set_page_config(page_title="⚽ 2026世界杯预测系统", page_icon="⚽", layout="wide")

# 加载数据库
DATA_DIR = os.path.join(os.path.dirname(__file__), 'db')
DATA_PATH = os.path.join(DATA_DIR, 'worldcup.json')

@st.cache_resource
def load_db():
    with open(DATA_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)

db = load_db()
teams = db.get('teams', {})
completed = db.get('completedMatches', [])
recent = db.get('recentMatches', {})
head2head = db.get('headToHead', {})
groups = db.get('groups', {})
group_standings = db.get('groupStandings', {})
knockout_tree = db.get('knockoutTree', {})

# ============================================================
# 引擎核心函数 (从 engine.mjs 移植)
# ============================================================
def elo_expected(elo_a, elo_b):
    return 1 / (1 + 10 ** ((elo_b - elo_a) / 400))

def rank_to_elo(rank):
    return round(2100 - (rank - 1) * (900 / 47))

def calc_lambda(team_name, opponent_name, is_home, teams_data, recent_data, ctx=None):
    if ctx is None: ctx = {}
    team = teams_data.get(team_name)
    if not team: return 0.5
    lambda_base = team.get('attackBase', 1.0)
    defense = team.get('defenseBase', 1.0)
    style = team.get('styleFactor', 1.0)
    elo = team.get('eloRating', rank_to_elo(team.get('rank', 50)))
    
    lambda_val = lambda_base / defense * style
    if is_home: lambda_val *= ctx.get('headToAdvantage', 1.08)
    
    # 近10场修正
    recent_data_list = recent_data.get(team_name, [])
    if recent_data_list:
        total_goals = 0
        count = 0
        for m in recent_data_list:
            if not m.get('score'): continue
            parts = m['score'].split('-')
            if len(parts) != 2: continue
            try:
                h, a = int(parts[0]), int(parts[1])
            except: continue
            is_h = m.get('venue') == '主'
            total_goals += h if is_h else a
            count += 1
        if count >= 3:
            gf_per_game = total_goals / count
            lambda_val = lambda_val * 0.6 + gf_per_game * 0.4
    
    # 历史交锋修正
    h2h_data = ctx.get('headToHead', {})
    key = f"{team_name}-{opponent_name}"
    h2h = h2h_data.get(key)
    if h2h:
        wins = h2h.get('homeWins', 0) if is_home else h2h.get('awayWins', 0)
        draws = h2h.get('draws', 0)
        total = wins + draws + h2h.get('awayWins' if is_home else 'homeWins', 0)
        if total >= 2:
            h2h_factor = 1.0 + (wins / total - 0.333) * 0.3
            lambda_val *= h2h_factor
    
    # 战意修正
    if ctx.get('isFinalRound'):
        urgency = (ctx.get('teamUrgency') or {}).get(team_name, 0)
        if urgency == 3: lambda_val *= 1.12
        elif urgency == 2: lambda_val *= 1.06
        elif urgency == 1: lambda_val *= 0.95
        elif urgency == 0: lambda_val *= 0.88
        elif urgency == 5: lambda_val *= 0.90
        elif urgency == 4: lambda_val *= 0.95
        lambda_val *= ctx.get('finalRoundFactor', 0.95)
    
    return round(lambda_val, 2)

def monte_carlo(l_h, l_a, n=5000, rho=0.02):
    results = {}
    def poisson_rv(lam):
        L = math.exp(-lam)
        k = 0
        p = 1
        while p > L:
            k += 1
            p *= random.random()
        return k - 1
    
    for _ in range(n):
        i = poisson_rv(l_h)
        j = poisson_rv(l_a)
        # Dixon-Coles tau
        if i == 0 and j == 0:
            tau = 1 - l_h * l_a * rho
            if random.random() > tau:
                r = random.random()
                if r < 0.5: i = 1
                else: j = 1
        elif i == 0 and j == 1:
            tau = 1 + l_h * rho
            if random.random() > tau: j = 0
        elif i == 1 and j == 0:
            tau = 1 + l_a * rho
            if random.random() > tau: i = 0
        elif i == 1 and j == 1:
            tau = 1 - rho
            if random.random() > tau:
                if random.random() < 0.5: i = 0
                else: j = 0
        
        score = f"{i}-{j}"
        results[score] = results.get(score, 0) + 1
    
    top5 = sorted(results.items(), key=lambda x: -x[1])[:5]
    return [(s, round(c/n*100, 1)) for s, c in top5]

def compute_standings(completed_matches, groups_data):
    standings = {}
    for m in completed_matches:
        for team in [m['home'], m['away']]:
            if team not in standings:
                group = ''
                for g, tlist in groups_data.items():
                    if team in tlist: group = g; break
                standings[team] = {'team': team, 'p': 0, 'w': 0, 'd': 0, 'l': 0, 'gf': 0, 'ga': 0, 'gd': 0, 'group': group}
        try:
            h, a = map(int, m['score'].split('-'))
        except: continue
        s_h, s_a = standings[m['home']], standings[m['away']]
        s_h['gf'] += h; s_h['ga'] += a; s_h['gd'] = s_h['gf'] - s_h['ga']
        s_a['gf'] += a; s_a['ga'] += h; s_a['gd'] = s_a['gf'] - s_a['ga']
        if h > a: s_h['w'] += 1; s_h['p'] += 3; s_a['l'] += 1
        elif h == a: s_h['d'] += 1; s_h['p'] += 1; s_a['d'] += 1; s_a['p'] += 1
        else: s_a['w'] += 1; s_a['p'] += 3; s_h['l'] += 1
    return standings

def fusion_predict(home, away, opts=None):
    if opts is None: opts = {}
    t_h = teams.get(home)
    t_a = teams.get(away)
    if not t_h or not t_a: return None
    
    elo_h = t_h.get('eloRating', rank_to_elo(t_h.get('rank', 50)))
    elo_a = t_a.get('eloRating', rank_to_elo(t_a.get('rank', 50)))
    elo_diff = abs(elo_h - elo_a)
    
    # 动态 rho
    rho = 0.05 if elo_diff < 50 else (0.02 if elo_diff < 100 else 0.01)
    
    # 战意
    team_urgency = opts.get('teamUrgency', {})
    ctx = {'isFinalRound': opts.get('isFinalRound', False), 'headToAdvantage': 1.08,
           'headToHead': head2head, 'teamUrgency': team_urgency}
    
    l_h = calc_lambda(home, away, True, teams, recent, ctx)
    l_a = calc_lambda(away, home, False, teams, recent, ctx)
    
    # Elo
    exp_h = elo_expected(elo_h, elo_a)
    base_draw = 25 - elo_diff * 0.015
    h_u = team_urgency.get(home, 0)
    a_u = team_urgency.get(away, 0)
    if (h_u in [4,5]) and (a_u in [4,5]): base_draw *= 1.25
    if h_u == 3 or a_u == 3: base_draw *= 0.85
    base_draw = max(10, min(38, round(base_draw)))
    elo_hp = round((exp_h / (exp_h + (1-exp_h))) * (100 - base_draw), 1)
    elo_ap = round(((1-exp_h) / (exp_h + (1-exp_h))) * (100 - base_draw), 1)
    elo_dp = round(100 - elo_hp - elo_ap, 1)
    
    # 泊松
    top5 = monte_carlo(l_h, l_a, opts.get('monteCarloRuns', 5000), rho)
    ps_h = sum(p for s, p in top5 if int(s.split('-')[0]) > int(s.split('-')[1]))
    ps_d = sum(p for s, p in top5 if int(s.split('-')[0]) == int(s.split('-')[1]))
    ps_a = sum(p for s, p in top5 if int(s.split('-')[0]) < int(s.split('-')[1]))
    ps_t = ps_h + ps_d + ps_a
    if ps_t > 0:
        ps_h = round(ps_h / ps_t * 100, 1)
        ps_d = round(ps_d / ps_t * 100, 1)
        ps_a = round(100 - ps_h - ps_d, 1)
    
    # 赔率市场
    odds_h = opts.get('oddsHome')
    odds_d = opts.get('oddsDraw')
    odds_a = opts.get('oddsAway')
    handicap = opts.get('handicap')
    
    mkt_hp, mkt_dp, mkt_ap = None, None, None
    if odds_h and odds_d and odds_a:
        ih, id_, ia = 1/odds_h, 1/odds_d, 1/odds_a
        total = ih + id_ + ia
        mkt_hp = round(ih / total * 100, 1)
        mkt_dp = round(id_ / total * 100, 1)
        mkt_ap = round(100 - mkt_hp - mkt_dp, 1)
        # 让球修正
        if handicap:
            abs_h = abs(handicap)
            boost = min(abs_h * 15, 40)
            if handicap > 0:
                mkt_hp = min(mkt_hp + boost, 92)
                mkt_ap = max(mkt_ap - boost * 0.6, 2)
                mkt_dp = max(mkt_dp - boost * 0.4, 3)
            else:
                mkt_ap = min(mkt_ap + boost, 92)
                mkt_hp = max(mkt_hp - boost * 0.6, 2)
                mkt_dp = max(mkt_dp - boost * 0.4, 3)
            total2 = mkt_hp + mkt_dp + mkt_ap
            mkt_hp = round(mkt_hp / total2 * 100, 1)
            mkt_dp = round(mkt_dp / total2 * 100, 1)
            mkt_ap = round(100 - mkt_hp - mkt_dp, 1)
    else:
        # 隐含赔率
        implied_h = round(exp_h * 100, 1)
        mkt_hp = implied_h
        mkt_dp = base_draw
        mkt_ap = round(100 - implied_h - base_draw, 1)
    
    # 融合
    ew = opts.get('eloWeight', 0.25)
    pw = opts.get('poissonWeight', 0.30)
    ecw = opts.get('economicWeight', 0.10)
    mw = opts.get('marketWeight', 0.35)
    
    base_w = ew + pw + ecw
    fused_h = (elo_hp * ew + ps_h * pw + mkt_hp * ecw) / base_w
    fused_d = (elo_dp * ew + ps_d * pw + mkt_dp * ecw) / base_w
    fused_a = (elo_ap * ew + ps_a * pw + mkt_ap * ecw) / base_w
    
    fused_h = (fused_h * base_w + mkt_hp * mw) / (base_w + mw)
    fused_d = (fused_d * base_w + mkt_dp * mw) / (base_w + mw)
    fused_a = (fused_a * base_w + mkt_ap * mw) / (base_w + mw)
    f_total = fused_h + fused_d + fused_a
    fused_h = round(fused_h / f_total * 100, 1)
    fused_d = round(fused_d / f_total * 100, 1)
    fused_a = round(100 - fused_h - fused_d, 1)
    
    # 融合 λ
    fused_lh = l_h * (pw + ecw) + (elo_hp / 50) * ew
    fused_la = l_a * (pw + ecw) + (elo_ap / 50) * ew
    
    return {
        'home': home, 'away': away,
        'elo': {'winPct': elo_hp, 'drawPct': elo_dp, 'awayPct': elo_ap, 'rating': {'home': elo_h, 'away': elo_a}},
        'poisson': {'winPct': ps_h, 'drawPct': ps_d, 'awayPct': ps_a, 'dcRho': rho},
        'market': {'winPct': mkt_hp, 'drawPct': mkt_dp, 'awayPct': mkt_ap, 'handicap': handicap or 0, 'isInferred': not (opts.get('oddsHome'))},
        'fusion': {
            'winPct': fused_h, 'drawPct': fused_d, 'awayPct': fused_a,
            'lambda': {'home': l_h, 'away': l_a},
            'fusedLambda': {'home': round(fused_lh, 2), 'away': round(fused_la, 2)},
            'top5': [{'score': s, 'pct': p} for s, p in top5]
        },
        'weights': {'elo': ew, 'poisson': pw, 'economic': ecw, 'market': mw}
    }

# ============================================================
# Streamlit UI
# ============================================================
st.title("⚽ 2026 世界杯预测系统")
st.caption("四维融合模型: Elo等级分 + 泊松分布 + 经济学 + 赔率市场")

tab1, tab2, tab3, tab4, tab5 = st.tabs(["🎯 预测", "📊 复盘分析", "🏆 晋级图", "🏅 Elo排名", "⚙️ 配置"])

with tab1:
    col1, col2 = st.columns([1, 2])
    with col1:
        st.subheader("比赛参数")
        team_list = sorted(teams.keys())
        home = st.selectbox("主队", team_list, index=team_list.index('葡萄牙') if '葡萄牙' in team_list else 0)
        away = st.selectbox("客队", team_list, index=team_list.index('乌兹别克斯坦') if '乌兹别克斯坦' in team_list else min(1, len(team_list)-1))
        
        use_odds = st.checkbox("输入赔率", False)
        if use_odds:
            c1, c2, c3 = st.columns(3)
            with c1: odds_h = st.number_input("主胜赔", min_value=1.01, value=1.88, step=0.01)
            with c2: odds_d = st.number_input("平赔", min_value=1.01, value=4.05, step=0.01)
            with c3: odds_a = st.number_input("客胜赔", min_value=1.01, value=2.85, step=0.01)
        else:
            odds_h = odds_d = odds_a = None
        
        use_handicap = st.checkbox("让球盘口", False)
        if use_handicap:
            hdcp = st.number_input("让球 (+主受让, -主让球)", value=-2.0, step=0.25)
        else:
            hdcp = None
        
        final_round = st.checkbox("最后一轮", False)
        
        if st.button("🚀 开始预测", type="primary", use_container_width=True):
            with st.spinner("计算中..."):
                opts = {'monteCarloRuns': 5000}
                if odds_h: opts.update({'oddsHome': odds_h, 'oddsDraw': odds_d, 'oddsAway': odds_a})
                if hdcp: opts['handicap'] = -hdcp  # 用户语义转引擎
                if final_round: opts['isFinalRound'] = True
                
                result = fusion_predict(home, away, opts)
                
                if result:
                    st.session_state['last_pred'] = result
    
    with col2:
        pred = st.session_state.get('last_pred')
        if pred:
            f = pred['fusion']
            e = pred['elo']
            p = pred['poisson']
            m = pred['market']
            
            # VS 头部
            st.markdown(f"""
            <div style="text-align:center;padding:16px;background:linear-gradient(135deg,#2563eb,#60a5fa);border-radius:12px;color:white;margin-bottom:12px;">
                <div style="display:flex;justify-content:center;align-items:center;gap:16px;">
                    <div><div style="font-size:1.4rem;font-weight:700;">{pred['home']}</div><div style="font-size:0.75rem;opacity:0.8;">Elo {e['rating']['home']}</div></div>
                    <div style="font-size:2rem;font-weight:900;">VS</div>
                    <div><div style="font-size:1.4rem;font-weight:700;">{pred['away']}</div><div style="font-size:0.75rem;opacity:0.8;">Elo {e['rating']['away']}</div></div>
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            # 胜率条
            st.markdown(f"**🏠 {pred['home']}** {'🤝 平局':^30} **{pred['away']} ✈️**")
            cols = st.columns([f['winPct'], max(f['drawPct'], 6), f['awayPct']])
            with cols[0]: st.markdown(f"<div style='background:#2563eb;color:white;text-align:center;padding:4px;border-radius:4px;font-weight:700;'>{f['winPct']}%</div>", unsafe_allow_html=True)
            with cols[1]: st.markdown(f"<div style='background:#d97706;color:white;text-align:center;padding:4px;border-radius:4px;'>{f['drawPct']}%</div>", unsafe_allow_html=True)
            with cols[2]: st.markdown(f"<div style='background:#dc2626;color:white;text-align:center;padding:4px;border-radius:4px;'>{f['awayPct']}%</div>", unsafe_allow_html=True)
            
            # Top5 比分
            st.subheader("🎯 最可能比分")
            top_cols = st.columns(5)
            for i, s in enumerate(f['top5']):
                with top_cols[i]:
                    is_top = i == 0
                    st.markdown(f"""
                    <div style="text-align:center;padding:8px;border:1px solid {'#2563eb' if is_top else '#c8d4e0'};border-radius:8px;background:{'#eff6ff' if is_top else 'white'};">
                        <div style="font-size:1.2rem;font-weight:700;color:{'#2563eb' if is_top else '#1a2338'};">{s['score']}</div>
                        <div style="font-size:0.7rem;color:#4a5a70;">{s['pct']}%</div>
                    </div>
                    """, unsafe_allow_html=True)
            
            # 模型对比
            st.subheader("🔬 各模型胜率对比")
            for label, data, color in [
                ('⚡ Elo', e, '#2563eb'), ('📊 泊松', p, '#7c3aed'), ('🎯 市场', m, '#d97706')
            ]:
                st.markdown(f"""
                <div style="margin:4px 0;">
                    <div style="display:flex;justify-content:space-between;font-size:0.8rem;">
                        <span>{label}</span><span>{data['winPct']}% / {data['drawPct']}% / {data['awayPct']}%</span>
                    </div>
                    <div style="display:flex;height:16px;border-radius:4px;overflow:hidden;">
                        <div style="width:{data['winPct']}%;background:{color};text-align:center;font-size:0.65rem;color:white;">{data['winPct']}%</div>
                        <div style="width:{max(data['drawPct'],3)}%;background:{color}88;text-align:center;font-size:0.65rem;">{data['drawPct']}%</div>
                        <div style="width:{data['awayPct']}%;background:{color}44;text-align:center;font-size:0.65rem;">{data['awayPct']}%</div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
            
            # 融合 λ + 权重
            st.markdown(f"""
            <div style="display:flex;justify-content:center;gap:16px;padding:8px;background:#f0f4f8;border-radius:8px;margin-top:8px;">
                <div style="text-align:center;"><span style="font-size:0.7rem;color:#4a5a70;">📈 融合λ</span><br><span style="font-size:1.1rem;font-weight:700;color:#2563eb;">{f['fusedLambda']['home']}</span></div>
                <div style="text-align:center;"><span style="font-size:0.7rem;color:#4a5a70;">⚖️ 权重</span><br><span style="font-size:0.75rem;">{int(pred['weights']['elo']*100)}/{int(pred['weights']['poisson']*100)}/{int(pred['weights']['economic']*100)}/{int(pred['weights']['market']*100)}</span></div>
                <div style="text-align:center;"><span style="font-size:0.7rem;color:#4a5a70;">📉 融合λ</span><br><span style="font-size:1.1rem;font-weight:700;color:#dc2626;">{f['fusedLambda']['away']}</span></div>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.info("👈 左侧选择球队和参数，点击「开始预测」")

with tab2:
    st.subheader("📊 48场复盘分析")
    if st.button("🔄 运行复盘", use_container_width=True):
        with st.spinner("逐一模拟48场比赛..."):
            correct = 0
            total = len(completed)
            wrong_list = []
            for m in completed:
                try:
                    opts = {}
                    if m.get('oddsHome'): opts.update({'oddsHome': m['oddsHome'], 'oddsDraw': m['oddsDraw'], 'oddsAway': m['oddsAway']})
                    if m.get('handicap'): opts['handicap'] = m['handicap']
                    r = fusion_predict(m['home'], m['away'], opts)
                    if not r: continue
                    h, a = map(int, m['score'].split('-'))
                    actual = 'home' if h > a else ('draw' if h == a else 'away')
                    pred_r = 'home' if r['fusion']['winPct'] >= r['fusion']['drawPct'] and r['fusion']['winPct'] >= r['fusion']['awayPct'] else ('draw' if r['fusion']['drawPct'] >= r['fusion']['winPct'] and r['fusion']['drawPct'] >= r['fusion']['awayPct'] else 'away')
                    if pred_r == actual: correct += 1
                    else: wrong_list.append(m)
                except: pass
            
            st.metric("方向正确率", f"{correct}/{total} ({correct/total*100:.1f}%)")
            
            with st.expander(f"❌ 错判详情 ({len(wrong_list)}场)", expanded=False):
                for m in wrong_list:
                    st.markdown(f"**{m['home']} {m['score']} {m['away']}**")
                    st.caption(f"赔率: {m.get('oddsHome','-')}/{m.get('oddsDraw','-')}/{m.get('oddsAway','-')} | 让球: {m.get('handicap',0)}")

with tab3:
    st.subheader("🏆 淘汰赛对阵")
    
    # 小组形势
    if group_standings:
        st.markdown("**📋 小组末轮形势**")
        gcols = st.columns(4)
        for i, (g, info) in enumerate(sorted(group_standings.items())):
            with gcols[i % 4]:
                st.markdown(f"**{g}组**")
                st.caption(info.get('description', ''))
    
    # 对阵树
    if knockout_tree:
        for round_key, round_label, round_color in [
            ('round64', '1/16 决赛', '#2563eb'),
            ('round16', '1/8 决赛', '#7c3aed'),
            ('round8', '1/4 决赛', '#d97706'),
            ('semi', '半决赛', '#dc2626'),
            ('final', '决赛', '#16a34a'),
        ]:
            matches = knockout_tree.get(round_key, [])
            if matches:
                st.markdown(f"**{round_label}** ({len(matches)}场)")
                mcols = st.columns(4)
                for i, m in enumerate(matches):
                    with mcols[i % 4]:
                        st.markdown(f"📍 {m.get('venue','')}")

with tab4:
    st.subheader("🏅 Elo 排行榜")
    elo_list = sorted([(n, t.get('eloRating', rank_to_elo(t.get('rank', 50))), t.get('rank', '-'), groups.get(n, '')) for n, t in teams.items()], key=lambda x: -x[1])
    for i, (name, elo, rank, grp) in enumerate(elo_list[:20]):
        st.text(f"{i+1:>2}. {name:<12} Elo {elo:<5} FIFA #{rank}  Group {grp}")

with tab5:
    st.subheader("⚙️ 模型配置")
    col1, col2, col3, col4 = st.columns(4)
    with col1: st.number_input("Elo权重", value=0.25, step=0.05, key="ew")
    with col2: st.number_input("泊松权重", value=0.30, step=0.05, key="pw")
    with col3: st.number_input("经济学权重", value=0.10, step=0.05, key="ecw")
    with col4: st.number_input("市场权重", value=0.35, step=0.05, key="mw")
    st.info("权重调整后点击预测生效")

# ============================================================
# 底部
# ============================================================
st.divider()
st.caption("⚽ 2026世界杯预测系统 v3.0 | 数据: 48队/72组交锋/479条近10场/48场赔率")