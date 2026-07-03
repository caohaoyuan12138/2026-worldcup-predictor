"""
xG 分析仪表盘 — Streamlit 页面

从 data/xg/ 加载实际 xG 数据，提供：
1. xG 球队对比表（xG vs 实际进球）
2. xG 趋势图（逐场 xG + 叠加实际进球）
3. 超/低预期表现图（进球 - xG）
4. 射门质量分布（xG 直方图、身体部位、射门类型）
5. 比赛详情（射门 xG 时间线）

用法：被 app.py 引入，作为 xG 分析 tab 的渲染函数
"""

import json
import os
import sys
from typing import Any, Dict, List

import streamlit as st
import pandas as pd
import numpy as np

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


# ── 辅助函数 ──

@st.cache_data
def load_xg_data():
    """加载所有 xG 数据文件"""
    data = {}
    paths = {
        'team_xg': os.path.join(BASE_DIR, 'data', 'xg', 'actual_team_xg.json'),
        'match_xg': os.path.join(BASE_DIR, 'data', 'xg', 'match_xg_results.json'),
        'validation': os.path.join(BASE_DIR, 'data', 'xg', 'validation_report.json'),
    }
    for key, path in paths.items():
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                data[key] = json.load(f)
        else:
            data[key] = None
    return data


def load_worldcup_data():
    """加载 worldcup.json 中的球队数据"""
    path = os.path.join(BASE_DIR, 'db', 'worldcup.json')
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            wc = json.load(f)
        teams = wc.get('teams', {})
        completed = wc.get('completedMatches', [])
        return teams, completed
    return {}, []


def color_xg_diff(val):
    """根据 xG 差值返回颜色样式"""
    if val > 0.5:
        return 'color: #22c55e; font-weight: bold'
    elif val < -0.5:
        return 'color: #ef4444; font-weight: bold'
    return ''


# ── 仪表盘各板块 ──

def render_xg_table(data):
    """1. xG 球队对比表"""
    st.subheader("📊 球队 xG 对比")
    st.caption("各队预期进球 vs 实际进球，按 xG 差值排序")

    team_xg = data.get('team_xg')
    if not team_xg:
        st.warning("⚠️ 无球队 xG 数据")
        return

    rows = []
    for name, t in team_xg.items():
        rows.append({
            '球队': name,
            '场次': t['matches_played'],
            '进攻 xG/场': t['offensive_xg'],
            '进球/场': t['goals_per_game'],
            '差值 (进球-xG)': round(t['total_goals_for'] - t['total_xg_for'], 3),
            '防守 xG/场': t['defensive_xg'],
            'xG 差 (进-防)': t['xg_diff'],
            '转换率': t['conversion_ratio'],
            '射门质量': t['shot_quality'],
            'xG 方差': t['xg_variance'],
        })

    df = pd.DataFrame(rows)
    df = df.sort_values('差值 (进球-xG)', ascending=False).reset_index(drop=True)

    # 颜色标记
    styled = df.style.map(color_xg_diff, subset=['差值 (进球-xG)'])
    st.dataframe(styled, use_container_width=True, height=min(60 * len(df) + 40, 600))

    # 汇总指标
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        total_xg = sum(t['total_xg_for'] for t in team_xg.values())
        total_goals = sum(t['total_goals_for'] for t in team_xg.values())
        st.metric("总 xG", f"{total_xg:.1f}", delta=f"{total_goals - total_xg:+.1f}")
    with col2:
        over = sum(1 for t in team_xg.values() if t['total_goals_for'] > t['total_xg_for'])
        under = sum(1 for t in team_xg.values() if t['total_goals_for'] < t['total_xg_for'])
        st.metric("超预期球队", over, delta=f"低预期 {under}")
    with col3:
        avg_xg = sum(t['offensive_xg'] for t in team_xg.values()) / max(len(team_xg), 1)
        st.metric("场均 xG", f"{avg_xg:.2f}")
    with col4:
        avg_conv = sum(t['conversion_ratio'] for t in team_xg.values()) / max(len(team_xg), 1)
        st.metric("平均转换率", f"{avg_conv:.2f}")


def render_xg_trends(data):
    """2. xG 逐场趋势图"""
    st.subheader("📈 xG 逐场趋势")
    st.caption("选择球队查看 xG 趋势，实际进球以圆点叠加")

    match_xg = data.get('match_xg')
    if not match_xg:
        st.warning("⚠️ 无比赛 xG 数据")
        return

    # 收集所有球队名
    all_teams = set()
    for m in match_xg:
        all_teams.add(m['home_team'])
        all_teams.add(m['away_team'])
    all_teams = sorted(all_teams)

    selected = st.multiselect("选择对比球队", all_teams, default=all_teams[:3])
    if not selected:
        st.info("👆 请至少选择一支球队")
        return

    # 构建逐场 xG 序列
    team_series = {t: {'matches': [], 'xg': [], 'goals': [], 'labels': []} for t in selected}
    for m in match_xg:
        for side, team_key in [('home', 'home_team'), ('away', 'away_team')]:
            team = m[team_key]
            if team in selected:
                opp = m['away_team'] if side == 'home' else m['home_team']
                xg = m[f'{side}_xg']
                goals = m[f'{side}_goals']
                team_series[team]['matches'].append(f"vs {opp}")
                team_series[team]['xg'].append(xg)
                team_series[team]['goals'].append(goals)
                team_series[team]['labels'].append(f"{opp}\n{xg:.2f}/{goals}")

    # 使用 Streamlit 原生图表
    chart_data = {}
    for t in selected:
        series = team_series[t]
        if series['xg']:
            chart_data[f"{t} xG"] = series['xg']

    if chart_data:
        df_chart = pd.DataFrame(chart_data)
        st.line_chart(df_chart, use_container_width=True, height=350)

    # 每支球队的详细数据
    for t in selected:
        series = team_series[t]
        if not series['xg']:
            st.caption(f"{t}: 无比赛数据")
            continue
        df_team = pd.DataFrame({
            '对手': series['matches'],
            'xG': [round(v, 3) for v in series['xg']],
            '进球': series['goals'],
            '实际差': [round(g - x, 3) for g, x in zip(series['goals'], series['xg'])],
        })
        st.caption(f"**{t}** — 场均 xG: {np.mean(series['xg']):.3f} | 场均进球: {np.mean(series['goals']):.2f}")
        st.dataframe(df_team, use_container_width=True, hide_index=True)


def render_over_underperformance(data):
    """3. 超/低预期表现图"""
    st.subheader("🎯 超预期 vs 低预期")
    st.caption("总进球 - 总 xG，正值 = 得分效率高于预期")

    team_xg = data.get('team_xg')
    if not team_xg:
        st.warning("⚠️ 无球队 xG 数据")
        return

    df = pd.DataFrame([
        {'球队': name, '差值': round(t['total_goals_for'] - t['total_xg_for'], 3),
         '转换率': t['conversion_ratio'], 'xG': t['offensive_xg'], '进球': t['goals_per_game']}
        for name, t in team_xg.items()
    ]).sort_values('差值', ascending=False).reset_index(drop=True)

    # 条形图
    st.bar_chart(df.set_index('球队')['差值'], use_container_width=True, height=400)

    # Top 5 / Bottom 5
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**🔥 超预期 Top 5**")
        top5 = df.head(5)
        for _, r in top5.iterrows():
            st.markdown(f"- **{r['球队']}** 进球{r['进球']:.2f} vs xG{r['xG']:.2f} = **{r['差值']:+.3f}**")
    with col2:
        st.markdown("**🧊 低预期 Bottom 5**")
        bot5 = df.tail(5).iloc[::-1]
        for _, r in bot5.iterrows():
            st.markdown(f"- **{r['球队']}** 进球{r['进球']:.2f} vs xG{r['xG']:.2f} = **{r['差值']:+.3f}**")

    # 转换率散点图
    st.caption("**转换率分布**（进球 / xG）")
    conv_df = df[df['xG'] > 0].copy()
    conv_df['转换率标签'] = conv_df['转换率'].apply(lambda v: f"{v:.2f}")
    st.dataframe(
        conv_df[['球队', 'xG', '进球', '转换率']].style.highlight_max(subset=['转换率'], color='#22c55e'),
        use_container_width=True, hide_index=True,
    )


def render_shot_quality(data):
    """4. 射门质量分布"""
    st.subheader("🎯 射门质量分布")
    st.caption("所有已完赛比赛的射门 xG 分布")

    match_xg = data.get('match_xg')
    if not match_xg:
        st.warning("⚠️ 无比赛 xG 数据")
        return

    # 聚合所有射门
    all_shots = []
    for m in match_xg:
        for s in m.get('shots', []):
            all_shots.append({
                'xg': s['xg'],
                'is_goal': s['is_goal'],
                'body_part': s.get('body_part', 'Unknown'),
                'team': s.get('team', 'unknown'),
                'minute': s.get('minute', 0),
            })

    if not all_shots:
        st.info("无射门数据")
        return

    df_shots = pd.DataFrame(all_shots)

    # xG 直方图
    st.markdown("**xG 值分布**（低 xG = 远射/小角度，高 xG = 禁区内/一对一）")
    col1, col2 = st.columns([3, 1])
    with col1:
        hist_values = np.histogram(df_shots['xg'], bins=20, range=(0, 1))[0]
        hist_df = pd.DataFrame({'射门数': hist_values})
        st.bar_chart(hist_df, use_container_width=True, height=250)
    with col2:
        # 射门分类
        low_xg = len(df_shots[df_shots['xg'] < 0.1])
        mid_xg = len(df_shots[(df_shots['xg'] >= 0.1) & (df_shots['xg'] < 0.3)])
        high_xg = len(df_shots[df_shots['xg'] >= 0.3])
        st.metric("低质量 (<0.1)", low_xg)
        st.metric("中质量 (0.1-0.3)", mid_xg)
        st.metric("高质量 (>0.3)", high_xg)

    # 身体部位分布
    st.markdown("**身体部位分布**")
    body_counts = df_shots['body_part'].value_counts()
    body_df = body_counts.reset_index()
    body_df.columns = ['部位', '射门数']
    st.dataframe(body_df, use_container_width=True, hide_index=True)

    # 射门 xG 按球队排序
    st.markdown("**球队射门质量**（场均射门 xG 均值）")
    team_shot_xg = df_shots.groupby('team')['xg'].agg(['mean', 'count', 'sum']).reset_index()
    team_shot_xg.columns = ['主客', '平均 xG', '射门数', '总 xG']
    team_shot_xg = team_shot_xg.sort_values('平均 xG', ascending=False)
    st.dataframe(team_shot_xg.style.highlight_max(subset=['平均 xG'], color='#22c55e'),
                 use_container_width=True, hide_index=True)


def render_match_detail(data):
    """5. 比赛详情：射门 xG 时间线"""
    st.subheader("⚽ 比赛射门 xG 时间线")
    st.caption("选择比赛查看逐次射门的 xG 贡献")

    match_xg = data.get('match_xg')
    if not match_xg:
        st.warning("⚠️ 无比赛 xG 数据")
        return

    # 选择比赛
    match_options = {f"{m['home_team']} vs {m['away_team']} ({m['home_goals']}-{m['away_goals']})": m
                     for m in match_xg}
    selected_label = st.selectbox("选择比赛", list(match_options.keys()))
    match = match_options[selected_label]

    # 比赛摘要
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric(f"{match['home_team']} xG", match['home_xg'])
    with col2:
        st.metric(f"{match['away_team']} xG", match['away_xg'])
    with col3:
        st.metric("实际比分", f"{match['home_goals']}-{match['away_goals']}")
    with col4:
        st.metric("总射门", f"{match['home_shots']}+{match['away_shots']}")

    shots = match.get('shots', [])
    if not shots:
        st.info("无射门数据")
        return

    # 构建时间线数据
    timeline = []
    home_cum = 0
    away_cum = 0
    for s in sorted(shots, key=lambda x: x['minute']):
        if s['team'] == 'home':
            home_cum += s['xg']
        else:
            away_cum += s['xg']
        timeline.append({
            'minute': s['minute'],
            'team': s['team'],
            'xg': s['xg'],
            'is_goal': s['is_goal'],
            'body_part': s.get('body_part', ''),
            'home_cum': home_cum,
            'away_cum': away_cum,
        })

    df_timeline = pd.DataFrame(timeline)

    # 累积 xG 线图
    cum_df = df_timeline[['minute', 'home_cum', 'away_cum']].drop_duplicates('minute').set_index('minute')
    st.line_chart(cum_df, use_container_width=True, height=300)

    # 射门事件表
    st.markdown("**射门事件**")
    events = []
    for s in sorted(shots, key=lambda x: x['minute']):
        team_name = match['home_team'] if s['team'] == 'home' else match['away_team']
        goal_mark = "⚽" if s['is_goal'] else " "
        events.append({
            '时间': f"{s['minute']}'",
            '球队': team_name,
            'xG': round(s['xg'], 3),
            '部位': s.get('body_part', ''),
            '结果': f"{goal_mark} {'进球' if s['is_goal'] else '射门'}",
            '坐标': f"({s.get('x', 0):.0f}, {s.get('y', 0):.0f})",
        })
    df_events = pd.DataFrame(events)
    st.dataframe(df_events.style.map(
        lambda v: 'background-color: #065f46; color: white' if v == '⚽ 进球' else '',
        subset=['结果']
    ), use_container_width=True, hide_index=True)


def render_validation_summary(data):
    """6. 模型验证摘要"""
    st.subheader("📐 xG 模型验证")
    st.caption("校准曲线与精度指标")

    validation = data.get('validation')
    if not validation:
        st.warning("⚠️ 无验证数据")
        return

    # 全局指标
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("MAE", f"{validation['mae']:.3f}")
    with col2:
        st.metric("RMSE", f"{validation['rmse']:.3f}")
    with col3:
        st.metric("总 xG", f"{validation['total_xg']:.1f}")
    with col4:
        r = validation.get('xg_goal_ratio', 0)
        st.metric("xG/进球比", f"{r:.3f}")

    # 校准曲线
    calibration = validation.get('calibration', [])
    if calibration:
        st.markdown("**校准曲线**（射门 xG 分桶 vs 实际进球率）")
        cal_df = pd.DataFrame(calibration)
        cal_chart = cal_df.set_index('bin_label')[['actual_rate', 'expected_rate']]
        cal_chart.columns = ['实际进球率', '预期进球率(xG)']
        st.line_chart(cal_chart, use_container_width=True, height=300)

        # 偏差分析
        cal_df['偏差'] = cal_df['actual_rate'] - cal_df['expected_rate']
        avg_bias = cal_df['偏差'].abs().mean()
        st.metric("平均绝对校准偏差", f"{avg_bias:.4f}",
                  delta="较好" if avg_bias < 0.05 else "需优化")
        st.dataframe(
            cal_df[['bin_center', 'n_shots', 'n_goals', 'actual_rate', 'expected_rate', '偏差']]
            .style.highlight_max(subset=['偏差'], color='#f97316'),
            use_container_width=True, hide_index=True,
        )

    # 球队验证结果 Top 10
    team_results = validation.get('team_results', [])
    if team_results:
        st.markdown("**球队 xG 准确度**")
        tr_df = pd.DataFrame(team_results).sort_values('xg_vs_actual', ascending=False)
        st.dataframe(tr_df[['team', 'matches', 'total_xg', 'total_goals', 'xg_vs_actual', 'mae']]
                     .style.highlight_max(subset=['xg_vs_actual'], color='#22c55e')
                     .highlight_min(subset=['xg_vs_actual'], color='#ef4444'),
                     use_container_width=True, hide_index=True)


# ── 主入口 ──

def render_xg_dashboard():
    """xG 仪表盘主入口 - 由 app.py 调用"""
    data = load_xg_data()

    if not any(data.values()):
        st.warning("⚠️ xG 数据未生成，请先运行 model/xg_model/compute_match_xg.py")
        st.code("cd model/xg_model && python compute_match_xg.py", language="bash")
        st.code("cd scripts && node update_xg_data.mjs", language="bash")
        return

    # 加载状态摘要
    team_count = len(data.get('team_xg', {}))
    match_count = len(data.get('match_xg', []))
    shot_count = sum(len(m.get('shots', [])) for m in (data.get('match_xg') or []))
    st.markdown(f"**数据状态**: {team_count} 支球队 | {match_count} 场比赛 | {shot_count} 次射门")

    # 子标签页
    tabs = st.tabs([
        "📊 球队对比",
        "📈 xG 趋势",
        "🎯 超/低预期",
        "🎯 射门质量",
        "⚽ 比赛时间线",
        "📐 模型验证",
    ])
    with tabs[0]:
        render_xg_table(data)
    with tabs[1]:
        render_xg_trends(data)
    with tabs[2]:
        render_over_underperformance(data)
    with tabs[3]:
        render_shot_quality(data)
    with tabs[4]:
        render_match_detail(data)
    with tabs[5]:
        render_validation_summary(data)


if __name__ == "__main__":
    st.set_page_config(page_title="xG 分析仪表盘", layout="wide")
    render_xg_dashboard()
