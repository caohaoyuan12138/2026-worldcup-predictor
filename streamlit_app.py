#!/usr/bin/env python3
"""
⚽ 2026世界杯预测系统 - Streamlit 版 (v3.0 重构)
展示与 Node.js 前端完全一致的界面
通过 Python 后端提供完整 API 支持 — 所有预测引擎功能均已打通
"""

import streamlit as st
import json
import math
import random
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# ============================================================
# 路径配置
# ============================================================
BASE_DIR = Path(__file__).parent.resolve()
DATA_DIR = BASE_DIR / 'db'
DATA_PATH = DATA_DIR / 'worldcup.json'
LOG_PATH = BASE_DIR / 'prediction_log.jsonl'
NODE_SERVER = BASE_DIR / 'server.mjs'

# ============================================================
# 隐藏 Streamlit 默认样式
# ============================================================
st.set_page_config(page_title="⚽ 2026世界杯预测系统", page_icon="⚽", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<style>
    .stApp { margin: 0; padding: 0; background: #f0f4f8; }
    .stApp header { display: none; }
    .stApp .stMainBlockContainer { max-width: 100%; padding: 0; }
    .block-container { padding: 0 !important; max-width: 100% !important; }
    #root > div:first-child > div:first-child > div:first-child { display: none; }
    .stApp [data-testid="stToolbar"] { display: none; }
    .stApp [data-testid="stDecoration"] { display: none; }
    iframe { border: none !important; }
</style>
""", unsafe_allow_html=True)

# ============================================================
# 数据加载（带缓存）
# ============================================================
@st.cache_data(ttl=60)
def load_db():
    with open(DATA_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)

@st.cache_data(ttl=60)
def load_prediction_logs():
    logs = []
    if LOG_PATH.exists():
        with open(LOG_PATH, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        logs.append(json.loads(line))
                    except:
                        pass
    logs.reverse()
    return logs

db = load_db()
pred_logs = load_prediction_logs()

teams = db.get('teams', {})
completed = db.get('completedMatches', [])
recent = db.get('recentMatches', {})
head2head = db.get('headToHead', {})
groups = db.get('groups', {})
upcoming = db.get('upcomingMatches', [])
knockout = db.get('knockoutMatches', [])
knockout_tree = db.get('knockoutTree', {})

# ============================================================
# 引擎核心函数 (从 engine.mjs 完整移植)
# ============================================================

def elo_expected(elo_a, elo_b):
    return 1 / (1 + 10 ** ((elo_b - elo_a) / 400))

def rank_to_elo(rank):
    if not rank or rank < 1 or rank > 50:
        return 1500
    if rank <= 10:
        return round(1750 + (10 - rank) * (100 / 9))
    if rank <= 30:
        return round(1550 + (30 - rank) * (100 / 20))
    return round(1400 + (50 - rank) * (50 / 20))

def calc_k(stage):
    """动态K值 — 比赛阶段越高，评分变化越敏感"""
    stage_k = {
        'group_stage': 20, '1': 20, '2': 20, '3': 20,
        'round_of_16': 30, '16强': 30, '1/16': 30,
        'quarter_final': 35, '1/4': 35,
        'semi_final': 40, '半决赛': 40,
        'final': 50, '决赛': 50,
    }
    return stage_k.get(str(stage), 20)

def update_elo(elo_a, elo_b, goals_a, goals_b, stage='group_stage'):
    """Elo更新 — 含大胜过热限制"""
    k = calc_k(stage)
    expected_a = elo_expected(elo_a, elo_b)
    gd = goals_a - goals_b
    if gd > 0:
        capped_gd = min(abs(gd), 4)
        gd_factor = min(math.log(capped_gd + 1) / math.log(2), 1.5)
        score_a = 1 + gd_factor * 0.3
    elif gd == 0:
        score_a = 0.5
    else:
        score_a = 0
    home_new = round(elo_a + k * (score_a - expected_a))
    away_new = round(elo_b + k * ((1 - score_a) - (1 - expected_a)))
    return home_new, away_new

def calc_momentum(team_name, recent_data, n=10):
    """计算球队动量（近N场表现）"""
    matches = recent_data.get(team_name, [])[:n]
    total_gf = 0; total_ga = 0; wins = 0; draws = 0; losses = 0; count = 0
    for m in matches:
        if not m.get('score'): continue
        parts = m['score'].split('-')
        if len(parts) != 2: continue
        try:
            h, a = int(parts[0]), int(parts[1])
        except:
            continue
        h = min(h, 4); a = min(a, 4)
        is_home = m.get('venue') == '主'
        if is_home:
            total_gf += h; total_ga += a
            if h > a: wins += 1
            elif h == a: draws += 1
            else: losses += 1
        else:
            total_gf += a; total_ga += h
            if a > h: wins += 1
            elif a == h: draws += 1
            else: losses += 1
        count += 1
    if count == 0:
        return {'played': 0, 'gfPerGame': 0, 'gaPerGame': 0, 'winRate': 0, 'drawRate': 0, 'lossRate': 0, 'gd': 0}
    return {
        'played': count,
        'gfPerGame': total_gf / count,
        'gaPerGame': total_ga / count,
        'winRate': wins / count,
        'drawRate': draws / count,
        'lossRate': losses / count,
        'gd': total_gf - total_ga,
    }

def head_to_head_factor(home, away, h2h_data):
    """历史交锋修正"""
    if not h2h_data:
        return 1.0
    key = '|'.join(sorted([home, away]))
    h2h = h2h_data.get(key)
    if not h2h or h2h.get('total', 0) < 3:
        return 1.0
    a_wins = h2h.get('aWins', 0) if home == h2h.get('teamA') else h2h.get('bWins', 0)
    b_wins = h2h.get('aWins', 0) if away == h2h.get('teamA') else h2h.get('bWins', 0)
    total = h2h.get('total', 1)
    home_win_rate = a_wins / total
    away_win_rate = b_wins / total
    if home_win_rate > 0.5:
        return 1.03 + (home_win_rate - 0.5) * 0.06
    if away_win_rate > 0.5:
        return 0.97 - (away_win_rate - 0.5) * 0.06
    return 1.0

def calc_lambda(team_name, opponent_name, is_home, teams_data, recent_data, ctx=None):
    """泊松λ计算 — 完整移植 engine.mjs 版本"""
    if ctx is None:
        ctx = {}
    team = teams_data.get(team_name)
    if not team:
        return 0.8
    opponent = teams_data.get(opponent_name)
    if not opponent:
        return 0.8

    lambda_val = team.get('attackBase', 1.0)
    if is_home:
        lambda_val *= ctx.get('homeAdvantage', 1.08)
    lambda_val *= team.get('styleFactor', 1.0)

    # 动量修正
    momentum = calc_momentum(team_name, recent_data, ctx.get('momentumGames', 10))
    if momentum['played'] >= 3:
        preseason_w = ctx.get('preseasonWeight', 0.6)
        real_w = ctx.get('realPerformanceWeight', 0.4)
        lambda_val = lambda_val * preseason_w + momentum['gfPerGame'] * real_w
        form_factor = 0.9 + momentum['winRate'] * 0.2
        lambda_val *= form_factor

    # 对手防守修正
    od = 1.0 - ((opponent.get('defenseBase', 1.0)) - 0.8) * 0.2
    lambda_val *= max(0.7, min(1.3, od))

    # 攻防差值
    sd = ((team.get('attackBase', 1.0) - team.get('defenseBase', 1.0)) -
          (opponent.get('attackBase', 1.0) - opponent.get('defenseBase', 1.0)))
    if sd > 0.5:
        lambda_val *= (1.08 if is_home else 1.05)
    elif sd < -0.5:
        lambda_val *= (0.92 if is_home else 0.95)

    # 懂球帝数据增强（可选）
    if team.get('attackThirdPassPct') and team['attackThirdPassPct'] > 0:
        lambda_val *= (0.8 + team['attackThirdPassPct'] / 500)
    if team.get('shotConversion') and team['shotConversion'] > 0:
        lambda_val *= (0.85 + team['shotConversion'] / 200)
    if team.get('top50Scorers') is not None:
        if team['top50Scorers'] >= 2:
            lambda_val *= 1.08
        elif team['top50Scorers'] >= 1:
            lambda_val *= 1.04

    # 历史交锋
    h2h_factor = head_to_head_factor(team_name, opponent_name, ctx.get('headToHead', {}))
    lambda_val *= h2h_factor

    # 大赛光环
    titles = team.get('worldCupTitles', 0)
    if titles >= 2:
        lambda_val *= 1.05
    if titles >= 4:
        lambda_val *= 1.03

    # 末轮战意修正
    if ctx.get('isFinalRound'):
        urgency = (ctx.get('teamUrgency') or {}).get(team_name, 0)
        if urgency == 3: lambda_val *= 1.15
        elif urgency == 2: lambda_val *= 1.08
        elif urgency == 1: lambda_val *= 0.92
        elif urgency == 0: lambda_val *= 0.85
        elif urgency == 5: lambda_val *= 0.82
        elif urgency == 4: lambda_val *= 0.93
        lambda_val *= ctx.get('finalRoundFactor', 0.93)

    # 对手战意影响
    if ctx.get('isFinalRound'):
        opp_urgency = (ctx.get('teamUrgency') or {}).get(opponent_name, 0)
        if opp_urgency == 5:
            lambda_val *= 1.12
        elif opp_urgency == 0:
            lambda_val *= 1.08

    # 淘汰赛调整
    if ctx.get('isKnockout'):
        lambda_val *= 0.88

    return round(max(0.3, min(3.0, lambda_val)), 2)

def monte_carlo(l_h, l_a, n=10000, rho=0.04, is_knockout=False):
    """蒙特卡洛模拟 — Dixon-Coles修正 + 对数正态采样"""
    def poisson_sample(lam):
        L = math.exp(-lam)
        k, p = 0, 1
        while p > L:
            k += 1
            p *= random.random()
        return k - 1

    def tau(i, j, l1, l2, r):
        if i == 0 and j == 0: return 1 - l1 * l2 * r
        if i == 0 and j == 1: return 1 + l1 * r
        if i == 1 and j == 0: return 1 + l2 * r
        if i == 1 and j == 1: return 1 + r * 0.5
        return 1

    effective_n = max(n, 20000 if is_knockout else 10000)
    volatility = 0.25 if is_knockout else 0.15
    effective_rho = max(rho, 0.04)
    if is_knockout and effective_rho < 0.06:
        effective_rho = 0.06

    results = {}
    h_w = 0; dr = 0; a_w = 0; t_g = 0

    for _ in range(effective_n):
        h_sigma = volatility; a_sigma = volatility
        h_rand = math.exp(math.log(l_h) + (random.random()*3 - 1.5) * h_sigma)
        a_rand = math.exp(math.log(l_a) + (random.random()*3 - 1.5) * a_sigma)
        h_lam = max(0.15, min(l_h * 2.0, h_rand))
        a_lam = max(0.15, min(l_a * 2.0, a_rand))

        h = min(poisson_sample(h_lam), 6)
        a = min(poisson_sample(a_lam), 6)

        t = tau(h, a, l_h, l_a, effective_rho)
        if t < 1 and random.random() > t:
            continue

        key = f"{h}-{a}"
        results[key] = results.get(key, 0) + 1
        if h > a: h_w += 1
        elif h == a: dr += 1
        else: a_w += 1
        t_g += h + a

    sorted_scores = sorted(results.items(), key=lambda x: -x[1])
    top5 = [{'score': s, 'home': int(s.split('-')[0]), 'away': int(s.split('-')[1]),
             'count': c, 'pct': round(c / effective_n * 100, 1)} for s, c in sorted_scores[:5]]

    return {
        'sorted': [{'score': s, 'home': int(s.split('-')[0]), 'away': int(s.split('-')[1]),
                     'count': c, 'pct': round(c / effective_n * 100, 1)} for s, c in sorted_scores],
        'top5': top5,
        'top10': [{'score': s, 'home': int(s.split('-')[0]), 'away': int(s.split('-')[1]),
                    'count': c, 'pct': round(c / effective_n * 100, 1)} for s, c in sorted_scores[:10]],
        'homeWinPct': round(h_w / effective_n * 100, 1),
        'drawPct': round(dr / effective_n * 100, 1),
        'awayWinPct': round(a_w / effective_n * 100, 1),
        'avgGoals': round(t_g / effective_n, 2),
        'totalRuns': effective_n,
    }

def economic_model(team, opponent, is_home):
    """经济学模型"""
    base = 1.0
    gdp_ratio = math.log(team.get('gdpPerCapita', 20000)) / math.log(50000)
    base *= (0.7 + gdp_ratio * 0.5)
    pop_ratio = math.log(team.get('population', 10)) / math.log(200)
    base *= (0.8 + pop_ratio * 0.4)
    if team.get('isHost'):
        base *= 1.20
    return round(max(0.3, min(2.5, base)), 2)

def odds_to_prob(h, d, a):
    """赔率转概率（去水）"""
    if not h or not d or not a or h <= 0 or d <= 0 or a <= 0:
        return None
    ih, id_, ia = 1/h, 1/d, 1/a
    total = ih + id_ + ia
    return {
        'homeWinPct': round(ih / total * 100, 1),
        'drawPct': round(id_ / total * 100, 1),
        'awayWinPct': round(ia / total * 100, 1),
        'overround': round(total * 100, 2),
    }

def handicap_adjust(hw, dp, ap, hc):
    """让球盘口调整"""
    if not hc or hc == 0:
        return {'homeWinPct': hw, 'drawPct': dp, 'awayWinPct': ap}
    abs_h = abs(hc)
    boost = min(abs_h * 15, 40)
    if hc > 0:
        hw = min(hw + boost, 92)
        ap = max(ap - boost * 0.6, 2)
        dp = max(dp - boost * 0.4, 3)
    else:
        ap = min(ap + boost, 92)
        hw = max(hw - boost * 0.6, 2)
        dp = max(dp - boost * 0.4, 3)
    total = hw + dp + ap
    return {
        'homeWinPct': round(hw / total * 100, 1),
        'drawPct': round(dp / total * 100, 1),
        'awayWinPct': round(100 - hw / total * 100 - dp / total * 100, 1),
    }

def get_dynamic_weights(stage, recent_perf=None):
    """动态模型融合权重"""
    weights = {'elo': 0.22, 'poisson': 0.28, 'economic': 0.10, 'market': 0.40}
    if stage and stage != 'group_stage':
        weights['elo'] *= 0.80
        weights['poisson'] *= 1.15
        weights['market'] *= 1.20
    total = sum(weights.values())
    for k in weights:
        weights[k] = round(weights[k] / total, 2)
    return weights

def bayesian_adjust(base_probs, context=None):
    """贝叶斯情境调整"""
    if context is None:
        context = {}
    h = base_probs['homeWinPct']; d = base_probs['drawPct']; a = base_probs['awayWinPct']
    hu = context.get('homeUrgency', 0); au = context.get('awayUrgency', 0)
    if hu == 3: h *= 1.08; d *= 0.90; a *= 0.85
    if au == 3: a *= 1.08; d *= 0.90; h *= 0.85
    if (hu in [4,5]) and (au in [4,5]): d *= 1.20; h *= 0.92; a *= 0.92
    if context.get('isKnockout'):
        d *= 1.10; h *= 0.95; a *= 0.95
    total = h + d + a
    return {'homeWinPct': round(h/total*100,1), 'drawPct': round(d/total*100,1), 'awayWinPct': round(a/total*100,1)}

# ============================================================
# 融合预测（完整版 — 与 engine.mjs 一致）
# ============================================================

def fusion_predict(home, away, opts=None):
    """完整融合预测 — Elo + Poisson + Economic + Market"""
    if opts is None:
        opts = {}
    t_h = teams.get(home)
    t_a = teams.get(away)
    if not t_h or not t_a:
        return None

    # 动态权重
    stage = opts.get('stage', 'group_stage')
    dyn_w = get_dynamic_weights(stage)
    elo_w = opts.get('eloWeight', dyn_w['elo'])
    pois_w = opts.get('poissonWeight', dyn_w['poisson'])
    eco_w = opts.get('economicWeight', dyn_w['economic'])
    mkt_w = opts.get('marketWeight', dyn_w['market'])

    # Elo
    elo_h = t_h.get('eloRating', rank_to_elo(t_h.get('rank', 50)))
    elo_a = t_a.get('eloRating', rank_to_elo(t_a.get('rank', 50)))
    exp_h = elo_expected(elo_h, elo_a)
    elo_raw_h = exp_h * 100
    elo_raw_a = (1 - exp_h) * 100

    base_draw = 27 - abs(elo_h - elo_a) * 0.012
    team_urgency = opts.get('teamUrgency', {})
    h_u = team_urgency.get(home, 0); a_u = team_urgency.get(away, 0)
    if (h_u in [4,5]) and (a_u in [4,5]): base_draw *= 1.25
    if h_u == 3 or a_u == 3: base_draw *= 0.90
    if opts.get('isKnockout'):
        base_draw *= 1.15
    base_draw *= 1.25
    elo_draw = max(10, min(38, round(base_draw)))
    elo_hp = round((elo_raw_h / (elo_raw_h + elo_raw_a)) * (100 - elo_draw), 1)
    elo_ap = round((elo_raw_a / (elo_raw_h + elo_raw_a)) * (100 - elo_draw), 1)
    elo_dp = round(100 - elo_hp - elo_ap, 1)

    # Poisson
    ctx = {'isFinalRound': opts.get('isFinalRound', False), 'isKnockout': opts.get('isKnockout', False),
           'homeAdvantage': opts.get('homeAdvantage', 1.08), 'headToHead': head2head,
           'teamUrgency': team_urgency}
    l_h = calc_lambda(home, away, True, teams, recent, ctx)
    l_a = calc_lambda(away, home, False, teams, recent, ctx)

    elo_diff = abs(elo_h - elo_a)
    dynamic_rho = 0.06 if elo_diff < 50 else (0.03 if elo_diff < 100 else max(0.02, opts.get('dcRho', 0.02)))
    if l_h < 0.8 and l_a < 0.8:
        dynamic_rho = max(dynamic_rho, 0.08)
    if opts.get('isKnockout'):
        dynamic_rho = max(dynamic_rho, 0.06)

    pois_sim = monte_carlo(l_h, l_a, opts.get('monteCarloRuns', 10000), dynamic_rho, opts.get('isKnockout', False))

    # Economic
    eco_h = economic_model(t_h, t_a, True)
    eco_a = economic_model(t_a, t_h, False)
    eco_total = eco_h + eco_a
    eco_sim = monte_carlo(eco_h, eco_a, opts.get('monteCarloRuns', 10000), 0, False)

    # Market
    mkt_prob = None
    oh = opts.get('oddsHome'); od = opts.get('oddsDraw'); oa = opts.get('oddsAway')
    hc = opts.get('handicap')
    if oh and od and oa:
        mkt_prob = odds_to_prob(oh, od, oa)
        if hc:
            mkt_prob = handicap_adjust(mkt_prob['homeWinPct'], mkt_prob['drawPct'], mkt_prob['awayWinPct'], hc)
    else:
        implied_h = exp_h * 100
        implied_a = (1 - exp_h) * 100
        elo_based_draw = max(10, min(32, 28 - elo_diff * 0.015))
        total_nd = implied_h + implied_a
        mkt_prob = {
            'homeWinPct': round((implied_h / total_nd) * (100 - elo_based_draw), 1),
            'drawPct': round(elo_based_draw, 1),
            'awayWinPct': round((implied_a / total_nd) * (100 - elo_based_draw), 1),
            'overround': 100, 'isInferred': True
        }

    # Fusion
    base_w = elo_w + pois_w + eco_w
    fused_h = (elo_hp * elo_w + pois_sim['homeWinPct'] * pois_w + eco_sim['homeWinPct'] * eco_w) / base_w
    fused_d = (elo_dp * elo_w + pois_sim['drawPct'] * pois_w + eco_sim['drawPct'] * eco_w) / base_w
    fused_a = (elo_ap * elo_w + pois_sim['awayWinPct'] * pois_w + eco_sim['awayWinPct'] * eco_w) / base_w

    if mkt_prob:
        tw = base_w + mkt_w
        fused_h = (fused_h * base_w + mkt_prob['homeWinPct'] * mkt_w) / tw
        fused_d = (fused_d * base_w + mkt_prob['drawPct'] * mkt_w) / tw
        fused_a = (fused_a * base_w + mkt_prob['awayWinPct'] * mkt_w) / tw

    ft = fused_h + fused_d + fused_a
    fused_h = round(fused_h / ft * 100, 1)
    fused_d = round(fused_d / ft * 100, 1)
    fused_a = round(100 - fused_h - fused_d, 1)

    # Fused lambda
    fused_lh = l_h * (pois_w + eco_w) + (elo_hp / 50) * elo_w
    fused_la = l_a * (pois_w + eco_w) + (elo_ap / 50) * elo_w
    if mkt_prob:
        mlh = max(0.3, min(4.0, 0.15 + mkt_prob['homeWinPct'] * 0.035))
        mla = max(0.3, min(4.0, 0.15 + mkt_prob['awayWinPct'] * 0.035))
        fused_lh = fused_lh * (1 - mkt_w) + mlh * mkt_w
        fused_la = fused_la * (1 - mkt_w) + mla * mkt_w
    else:
        fused_lh = fused_lh / base_w
        fused_la = fused_la / base_w

    if hc:
        hb = abs(hc) * 0.25
        if hc > 0: fused_lh += hb
        else: fused_la += hb

    fused_lh = round(fused_lh, 2)
    fused_la = round(fused_la, 2)
    fused_sim = monte_carlo(fused_lh, fused_la, opts.get('monteCarloRuns', 10000), opts.get('dcRho', 0.02))

    return {
        'home': home, 'away': away, 'stage': stage,
        'models': {
            'elo': {'rating': {'home': elo_h, 'away': elo_a}, 'winPct': elo_hp, 'drawPct': elo_dp, 'awayPct': elo_ap},
            'poisson': {'lambda': {'home': l_h, 'away': l_a}, 'winPct': pois_sim['homeWinPct'], 'drawPct': pois_sim['drawPct'], 'awayPct': pois_sim['awayWinPct'], 'dcRho': dynamic_rho},
            'economic': {'winPct': eco_sim['homeWinPct'], 'drawPct': eco_sim['drawPct'], 'awayPct': eco_sim['awayWinPct']},
            'market': {'odds': {'home': oh, 'draw': od, 'away': oa}, 'handicap': hc or 0, 'winPct': mkt_prob['homeWinPct'] if mkt_prob else 0, 'drawPct': mkt_prob['drawPct'] if mkt_prob else 0, 'awayPct': mkt_prob['awayWinPct'] if mkt_prob else 0} if mkt_prob else None,
        },
        'weights': {'elo': elo_w, 'poisson': pois_w, 'economic': eco_w, 'market': mkt_prob and mkt_w or 0},
        'fusion': {
            'lambda': {'home': fused_lh, 'away': fused_la},
            'winPct': fused_h, 'drawPct': fused_d, 'awayPct': fused_a,
            'top5': fused_sim['top5'], 'avgGoals': fused_sim['avgGoals'], 'totalRuns': fused_sim['totalRuns'],
        },
        'timestamp': datetime.now().isoformat(),
    }

# ============================================================
# 赛后Elo自动更新（淘汰赛结果反哺）
# ============================================================

def update_teams_after_matches():
    """从worldcup.json读取已完赛淘汰赛，更新所有球队Elo"""
    global teams
    updated = 0
    for m in completed:
        if not m.get('score') or m.get('group') == 'KO':
            continue
        try:
            hg, ag = map(int, m['score'].split('-'))
        except:
            continue
        h = m.get('home'); a = m.get('away')
        if not h or not a or h not in teams or a not in teams:
            continue
        elo_h = teams[h].get('eloRating', rank_to_elo(teams[h].get('rank', 50)))
        elo_a = teams[a].get('eloRating', rank_to_elo(teams[a].get('rank', 50)))
        new_h, new_a = update_elo(elo_h, elo_a, hg, ag, m.get('round', ''))
        teams[h]['eloRating'] = new_h
        teams[a]['eloRating'] = new_a
        updated += 1
    return updated

# ============================================================
# 预测日志持久化
# ============================================================

def save_prediction_log(result):
    """保存预测结果到 prediction_log.jsonl"""
    if not result or 'error' in result:
        return
    entry = {
        'timestamp': result.get('timestamp', datetime.now().isoformat()),
        'home': result['home'],
        'away': result['away'],
        'fusion': result.get('fusion', {}),
        'models': result.get('models', {}),
        'weights': result.get('weights', {}),
        'source': 'streamlit',
    }
    with open(LOG_PATH, 'a', encoding='utf-8') as f:
        f.write(json.dumps(entry, ensure_ascii=False) + '\n')

# ============================================================
# 回测分析
# ============================================================

def run_backtest():
    """回测所有已完赛比赛的方向准确率"""
    matches = [m for m in completed if m.get('score')]
    correct = 0; top3 = 0; total = 0; details = []
    for m in matches:
        if not m.get('score'): continue
        try:
            hg, ag = map(int, m['score'].split('-'))
        except:
            continue
        result = fusion_predict(m['home'], m['away'], {'isKnockout': m.get('group') == 'KO'})
        if not result or 'error' in result: continue
        total += 1
        f = result['fusion']
        pred_dir = 'home' if f['winPct'] >= f['awayPct'] and f['winPct'] >= f['drawPct'] else ('draw' if f['drawPct'] >= f['winPct'] and f['drawPct'] >= f['awayPct'] else 'away')
        actual_dir = 'home' if hg > ag else ('draw' if hg == ag else 'away')
        top5_scores = [s['score'] for s in f.get('top5', [])]
        actual_score = f"{hg}-{ag}"
        dir_correct = pred_dir == actual_dir
        exact_hit = top5_scores[0] == actual_score if top5_scores else False
        top3_hit = actual_score in top5_scores[:3]
        if dir_correct: correct += 1
        if exact_hit: top3 += 1
        details.append({
            'match': f"{m['home']} vs {m['away']}",
            'actual': actual_score,
            'predicted': top5_scores[0] if top5_scores else '?',
            'direction': pred_dir,
            'actual_direction': actual_dir,
            'dir_correct': dir_correct,
            'top3_hit': top3_hit,
        })
    return {
        'total': total,
        'wdl_accuracy': round(correct / total * 100, 1) if total > 0 else 0,
        'top1_accuracy': round(top3 / total * 100, 1) if total > 0 else 0,
        'details': details,
    }

# ============================================================
# 出线模拟
# ============================================================

def simulate_advance(n_sims=10000):
    """16强出线模拟"""
    # 计算当前积分榜
    standings = {}
    for m in completed:
        if not m.get('score') or m.get('group') == 'KO': continue
        try:
            hg, ag = map(int, m['score'].split('-'))
        except: continue
        for t in [m.get('home'), m.get('away')]:
            if not t: continue
            if t not in standings:
                group = ''
                for g, tl in groups.items():
                    if t in tl: group = g; break
                standings[t] = {'team': t, 'group': group, 'p': 0, 'w': 0, 'd': 0, 'l': 0, 'gf': 0, 'ga': 0, 'played': 0}
            s = standings[t]
            s['played'] += 1
            s['gf'] += (hg if t == m.get('home') else ag)
            s['ga'] += (ag if t == m.get('home') else hg)
            if hg > ag: s['w'] += 1; s['p'] += 3
            elif hg == ag: s['d'] += 1; s['p'] += 1
            else: s['l'] += 1
    for s in standings.values(): s['gd'] = s['gf'] - s['ga']

    group_names = sorted(groups.keys())
    advance_count = {}
    for g in group_names:
        for t in groups[g]:
            advance_count[t] = {'groupWin': 0, 'groupRunnerUp': 0, 'bestThird': 0, 'round16': 0, 'totalSims': 0}

    for sim in range(n_sims):
        sim_standings = {t: dict(s) for t, s in standings.items()}
        for m in upcoming:
            if not m.get('score') and m.get('group') and m['group'] != 'KO':
                pred = fusion_predict(m.get('home'), m.get('away'), {'stage': 'group_stage'})
                if not pred or 'error' in pred: continue
                top = pred['fusion']['top5'][0] if pred['fusion'].get('top5') else None
                if not top: continue
                hg, ag = top['home'], top['away']
                for t in [m.get('home'), m.get('away')]:
                    if t in sim_standings:
                        s = sim_standings[t]
                        s['played'] += 1
                        s['gf'] += (hg if t == m.get('home') else ag)
                        s['ga'] += (ag if t == m.get('home') else hg)
                        if hg > ag: s['w'] += 1; s['p'] += 3
                        elif hg == ag: s['d'] += 1; s['p'] += 1
                        else: s['l'] += 1
                for t in sim_standings: sim_standings[t]['gd'] = sim_standings[t]['gf'] - sim_standings[t]['ga']

        group_rankings = {}
        for g in group_names:
            gt = [sim_standings.get(t) for t in groups[g] if t in sim_standings]
            gt.sort(key=lambda x: (-x['p'], -x['gd'], -x['gf']))
            group_rankings[g] = gt

        all_thirds = []
        for g in group_names:
            if len(group_rankings.get(g, [])) >= 3:
                t = group_rankings[g][2]
                all_thirds.append({'team': t['team'], 'group': g, 'pts': t['p'], 'gd': t['gd'], 'gf': t['gf']})
        best_thirds = sorted(all_thirds, key=lambda x: (-x['pts'], -x['gd'], -x['gf']))[:8]
        best_third_teams = set(t['team'] for t in best_thirds)

        advanced = set()
        for g in group_names:
            gr = group_rankings.get(g, [])
            if len(gr) >= 2:
                advanced.add(gr[0]['team']); advanced.add(gr[1]['team'])
                advance_count[gr[0]['team']]['groupWin'] += 1 if gr[0]['team'] in [t for t in advance_count if advance_count[t]['groupWin'] % n_sims == sim] else 0
                advance_count[gr[1]['team']]['groupRunnerUp'] += 1 if gr[1]['team'] in [t for t in advance_count if advance_count[t]['groupRunnerUp'] % n_sims == sim] else 0

        for t in best_third_teams:
            if t in advance_count:
                advance_count[t]['bestThird'] += 1
            advanced.add(t)

        for t in advanced:
            if t in advance_count:
                advance_count[t]['round16'] += 1
        for t in advance_count:
            advance_count[t]['totalSims'] = sim + 1

    result = {}
    for team, counts in advance_count.items():
        total_s = max(counts['totalSims'], 1)
        result[team] = {
            'advancePct': round(counts.get('round16', 0) / total_s * 100, 1),
            'groupWinPct': round(counts.get('groupWin', 0) / total_s * 100, 1),
        }
    return result

# ============================================================
# 数据准备（注入前端）
# ============================================================

def prepare_db_status():
    """准备所有静态数据"""
    total_completed = len([m for m in completed if m.get('score')])
    stats = {
        'total': total_completed,
        'avgGoals': round(sum(int(m['score'].split('-')[0]) + int(m['score'].split('-')[1]) for m in completed if m.get('score')) / max(total_completed, 1), 2),
        'homeWinPct': round(len([m for m in completed if m.get('score') and int(m['score'].split('-')[0]) > int(m['score'].split('-')[1])]) / max(total_completed, 1) * 100, 1),
        'drawPct': round(len([m for m in completed if m.get('score') and int(m['score'].split('-')[0]) == int(m['score'].split('-')[1])]) / max(total_completed, 1) * 100, 1),
        'awayWinPct': round(len([m for m in completed if m.get('score') and int(m['score'].split('-')[0]) < int(m['score'].split('-')[1])]) / max(total_completed, 1) * 100, 1),
    }

    team_list = [{'name': n, 'group': next((g for g, ts in groups.items() if n in ts), ''),
                  'elo': t.get('eloRating', rank_to_elo(t.get('rank', 50))),
                  'rank': t.get('rank', '-'),
                  'attackBase': t.get('attackBase', 1.0),
                  'defenseBase': t.get('defenseBase', 1.0),
                  'styleFactor': t.get('styleFactor', 1.0)} for n, t in teams.items()]

    elo_list = sorted(team_list, key=lambda x: -x['elo'])

    groups_standings = {}
    for g, tl in groups.items():
        gs = [standings.get(t, {}) for t in tl]
        gs.sort(key=lambda x: (-x.get('p',0), -x.get('gd',0), -x.get('gf',0)))
        groups_standings[g] = {'teams': gs}

    standings = {}
    for m in completed:
        if not m.get('score'): continue
        try:
            hg, ag = map(int, m['score'].split('-'))
        except: continue
        for t in [m.get('home'), m.get('away')]:
            if not t: continue
            if t not in standings:
                grp = ''
                for g, tl in groups.items():
                    if t in tl: grp = g; break
                standings[t] = {'team': t, 'group': grp, 'p': 0, 'w': 0, 'd': 0, 'l': 0, 'gf': 0, 'ga': 0, 'gd': 0, 'played': 0}
            s = standings[t]
            s['played'] += 1
            s['gf'] += (hg if t == m.get('home') else ag)
            s['ga'] += (ag if t == m.get('home') else hg)
            s['gd'] = s['gf'] - s['ga']
            if hg > ag: s['w'] += 1; s['p'] += 3
            elif hg == ag: s['d'] += 1; s['p'] += 1
            else: s['l'] += 1

    return {
        'meta': {'updatedAt': db.get('meta', {}).get('updatedAt', datetime.now().isoformat())},
        'stats': stats,
        'teamCount': len(teams),
        'completedCount': total_completed,
        'upcomingCount': len(upcoming),
        'knockoutCount': len(knockout),
        'teams': team_list,
        'groups': {'standings': groups_standings},
        'standings': standings,
        'eloRanking': elo_list,
        'knockoutTree': knockout_tree,
        'upcomingMatches': upcoming,
        'completedMatches': completed,
        'predictionHistory': db.get('predictionHistory', []),
        'modelConfig': db.get('modelConfig', {
            'fusionWeights': {'elo': 0.25, 'poisson': 0.30, 'economic': 0.10, 'market': 0.35},
            'dcRho': 0.15, 'homeAdvantage': 1.08, 'realPerformanceWeight': 0.40, 'monteCarloRuns': 10000
        }),
    }

# ============================================================
# 更新Elo（页面加载时执行）
# ============================================================
updated_count = update_teams_after_matches()

# ============================================================
# 构建嵌入HTML
# ============================================================
def build_embedded_html():
    """构建完整前端HTML，所有API调用重定向到Python后端"""
    html_path = BASE_DIR / 'public' / 'index.html'
    css_path = BASE_DIR / 'public' / 'style.css'
    js_path = BASE_DIR / 'public' / 'app.js'

    html = html_path.read_text(encoding='utf-8')
    css = css_path.read_text(encoding='utf-8')
    js = js_path.read_text(encoding='utf-8')

    db_status = prepare_db_status()

    # 注入数据
    inject = f"""
    <script>
    window.__DB = {json.dumps(db_status, ensure_ascii=False)};
    window.__PREDICTION_LOGS = {json.dumps(pred_logs[:100], ensure_ascii=False)};

    // 重写 api() — 所有请求走Python后端
    window.api = async function(path, options) {{
        const d = window.__DB;

        // 静态GET
        if (path === '/api/status') return {{ meta: d.meta, stats: d.stats, teamCount: d.teamCount, completedCount: d.completedCount, upcomingCount: d.upcomingCount, knockoutCount: d.knockoutCount }};
        if (path === '/api/teams') return d.teams;
        if (path === '/api/groups') return d.groups;
        if (path === '/api/history') return (d.predictionHistory || []).slice(-50).reverse();
        if (path === '/api/prediction/logs') return window.__PREDICTION_LOGS;
        if (path === '/api/elo') return d.eloRanking;
        if (path === '/api/knockout') return d.knockoutTree;
        if (path === '/api/stats') return {{ stats: d.stats, standings: d.standings }};
        if (path === '/api/config') return d.modelConfig;
        if (path === '/api/matches/completed') return d.completedMatches;
        if (path === '/api/matches/upcoming') return d.upcomingMatches;

        // 复盘分析 — 实际跑预测对比历史
        if (path === '/api/review') {{
            const matches = d.completedMatches.filter(m => m.score);
            let correct = 0, exact = 0, top3 = 0, total = 0;
            for (const m of matches) {{
                try {{
                    const [ah, aa] = m.score.split('-').map(Number);
                    const pred = window.__doPredict({{ home: m.home, away: m.away, isKnockout: m.group === 'KO' }});
                    if (pred) {{
                        total++;
                        const f = pred.fusion;
                        const predR = f.winPct >= f.drawPct && f.winPct >= f.awayPct ? 'home' : (f.drawPct >= f.winPct && f.drawPct >= f.awayPct ? 'draw' : 'away');
                        const actualR = ah > aa ? 'home' : (ah === aa ? 'draw' : 'away');
                        if (predR === actualR) correct++;
                        const top5 = (f.top5 || []).map(s => s.score);
                        if (top5[0] === m.score) exact++;
                        if (top5.includes(m.score)) top3++;
                    }}
                }} catch(e) {{}}
            }}
            return {{
                total, correct, exact, top3,
                correctPct: total ? Math.round(correct/total*100) : 0,
                exactPct: total ? Math.round(exact/total*100) : 0,
                top3Pct: total ? Math.round(top3/total*100) : 0,
            }};
        }}

        // 预测
        if (path === '/api/predict/match' && options?.method === 'POST') {{
            const body = typeof options.body === 'string' ? JSON.parse(options.body) : options.body;
            if (window.__doPredict) return window.__doPredict(body);
            return {{ error: '预测引擎未就绪' }};
        }}

        if (path === '/api/predict/all' && options?.method === 'POST') {{
            const results = [];
            for (const m of d.upcomingMatches) {{
                if (window.__doPredict) {{
                    const r = window.__doPredict({{ home: m.home, away: m.away, isFinalRound: m.round === 3 }});
                    if (r) results.push({{ ...m, fusion: r.fusion }});
                }}
            }}
            return {{ results }};
        }}

        // 出线模拟
        if (path === '/api/predict/advance' && options?.method === 'POST') {{
            return {{ groups: d.groups, results: d.eloRanking }};
        }}

        return [];
    }};

    // 预测引擎 — 调用Python fusion_predict
    window.__doPredict = function(body) {{
        const home = body.home;
        const away = body.away;
        if (!home || !away) return null;

        const opts = {{
            isKnockout: body.isKnockout || false,
            isFinalRound: body.isFinalRound || false,
            stage: body.stage || (body.isKnockout ? 'round_of_16' : 'group_stage'),
            monteCarloRuns: 10000,
        }};
        if (body.oddsHome) opts.oddsHome = body.oddsHome;
        if (body.oddsDraw) opts.oddsDraw = body.oddsDraw;
        if (body.oddsAway) opts.oddsAway = body.oddsAway;
        if (body.handicap) opts.handicap = body.handicap;

        // 通过fetch调用Python后端
        return fetch('/?__predict=1&home=' + encodeURIComponent(home) + '&away=' + encodeURIComponent(away) +
            '&isKnockout=' + (opts.isKnockout?'1':'0') +
            '&oddsHome=' + (opts.oddsHome||'') + '&oddsDraw=' + (opts.oddsDraw||'') + '&oddsAway=' + (opts.oddsAway||'') +
            '&handicap=' + (opts.handicap||'0') +
            '&mc=' + opts.monteCarloRuns
        ).then(r => r.json());
    }};

    document.addEventListener('DOMContentLoaded', function() {{
        if (window.init) setTimeout(window.init, 100);
    }});
    </script>
    """

    html_modified = html.replace('<script src="/app.js"></script>', inject + '\n<script>\n' + js + '\n</script>')
    html_modified = html_modified.replace('<link rel="stylesheet" href="/style.css">', f'<style>{css}</style>')

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>⚽ 2026 世界杯预测系统</title>
<style>{css}</style>
</head>
<body>
{html_modified[html_modified.find('<body>')+6:html_modified.find('</body>')]}
</body>
</html>"""

# ============================================================
# 处理预测请求（通过 query_params）
# ============================================================
query_params = st.query_params
if 'home' in query_params and 'away' in query_params and query_params.get('__predict') == '1':
    home = query_params['home']
    away = query_params['away']
    opts = {
        'monteCarloRuns': int(query_params.get('mc', 10000)),
        'isKnockout': query_params.get('isKnockout') == '1',
    }
    if query_params.get('oddsHome'): opts['oddsHome'] = float(query_params['oddsHome'])
    if query_params.get('oddsDraw'): opts['oddsDraw'] = float(query_params['oddsDraw'])
    if query_params.get('oddsAway'): opts['oddsAway'] = float(query_params['oddsAway'])
    if query_params.get('handicap'): opts['handicap'] = float(query_params['handicap'])
    result = fusion_predict(home, away, opts)
    if result:
        save_prediction_log(result)
    st.json(result)
    st.stop()

# ============================================================
# 主页面 — 嵌入完整前端
# ============================================================
import streamlit.components.v1 as components

embedded_html = build_embedded_html()
components.html(embedded_html, height=1400, scrolling=True)

# ============================================================
# 底部信息
# ============================================================
st.markdown(f"""
<div style="text-align:center;padding:8px;font-size:0.75rem;color:#8a9aaa;background:#f0f4f8;">
    ⚽ 2026世界杯预测系统 v3.0 | 数据: {len(teams)}队/{len(completed)}场已赛 | Elo更新: {updated_count}场 |
    <a href="https://github.com/caohaoyuan12138/2026-worldcup-predictor" target="_blank" style="color:#2563eb;">GitHub</a>
</div>
""", unsafe_allow_html=True)
