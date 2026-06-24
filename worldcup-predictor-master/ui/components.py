"""
UI 组件库 — 可复用的 Streamlit 组件

将 app.py 中的 UI 逻辑抽离，提升可维护性
"""

import streamlit as st
import pandas as pd
from typing import Dict, List, Optional


# ──────────────────────────────────────────────
#  通用组件
# ──────────────────────────────────────────────
def render_title():
    """渲染页面标题"""
    st.markdown(
        '<div class="main-title">⚽ 2026 美加墨世界杯比分预测</div>',
        unsafe_allow_html=True
    )
    st.markdown(
        f'<div class="subtitle">四层融合|Elo+泊松+蒙特卡洛+贝叶斯|'
        f'本地+API混合|{pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")}</div>',
        unsafe_allow_html=True
    )


def render_data_source_badge(src_ts: str = ""):
    """渲染数据源状态徽章"""
    if src_ts:
        st.markdown(
            f'<span class="data-source-badge source-live">'
            f'🟢 API已同步 — {src_ts}</span>',
            unsafe_allow_html=True
        )
    else:
        st.markdown(
            '<span class="data-source-badge source-cache">🔵 本地数据</span>',
            unsafe_allow_html=True
        )


def render_match_badge(home: str, away: str, home_score=None, away_score=None,
                       flag_func=None, is_finished: bool = False):
    """渲染比赛徽章"""
    hf = flag_func(home) if flag_func else "🏳️"
    af = flag_func(away) if flag_func else "🏳️"

    if is_finished and home_score is not None and away_score is not None:
        st.markdown(f'{hf} **{home} {home_score}:{away_score} {away}** {af}')
    else:
        st.markdown(f'{hf} {home} vs {away} {af}')


def render_progress_bar(label: str, value: float, color: str = "normal"):
    """渲染带标签的进度条"""
    st.progress(value, text=f"{label} {value:.1%}")


def render_metric_row(metrics: List[Dict], columns: int = 3):
    """
    渲染一行指标卡片

    Args:
        metrics: [{"label": str, "value": str}, ...]
        columns: 列数
    """
    cols = st.columns(columns)
    for i, m in enumerate(metrics):
        if i < len(cols):
            with cols[i]:
                st.metric(m.get("label", ""), m.get("value", ""))


# ──────────────────────────────────────────────
#  分析卡片组件
# ──────────────────────────────────────────────
def render_elo_card(elo_data: Dict):
    """渲染 Elo 分析卡片"""
    if not elo_data:
        return

    st.markdown("**📊 Elo 实力对比**")
    metrics = [
        {"label": "主队评分", "value": f"{elo_data.get('home_rating', '?'):.0f}"},
        {"label": "客队评分", "value": f"{elo_data.get('away_rating', '?'):.0f}"},
        {"label": "差值", "value": f"{elo_data.get('diff', 0):+d}"},
        {"label": "优势方", "value": elo_data.get("advantage", "势均力敌")},
    ]
    render_metric_row(metrics, columns=4)

    hw = elo_data.get("home_win", 0)
    dr = elo_data.get("draw", 0)
    aw = elo_data.get("away_win", 0)
    render_progress_bar("主胜", hw)
    render_progress_bar("平", dr)
    render_progress_bar("客胜", aw)
    st.caption("")


def render_poisson_card(pois_data: Dict):
    """渲染泊松分析卡片"""
    if not pois_data:
        return

    st.markdown("**⚽ Dixon-Coles 泊松模型**")
    metrics = [
        {"label": "主队 λ", "value": f"{pois_data.get('lambda_home', '?'):.3f}"},
        {"label": "客队 λ", "value": f"{pois_data.get('lambda_away', '?'):.3f}"},
        {"label": "总期望进球", "value": f"{pois_data.get('expected_total', '?'):.2f}"},
    ]
    render_metric_row(metrics, columns=3)

    mh = pois_data.get("motivation_home", 1.0)
    ma = pois_data.get("motivation_away", 1.0)
    if abs(mh - 1.0) > 0.01 or abs(ma - 1.0) > 0.01:
        st.caption(f"动机因子: 主队×{mh:.2f} / 客队×{ma:.2f}")


def render_monte_carlo_card(mc_data: Dict):
    """渲染蒙特卡洛分析卡片"""
    if not mc_data:
        return

    st.markdown("**🎲 蒙特卡洛模拟 (5000次)**")
    hw = mc_data.get("home_win", 0)
    dr = mc_data.get("draw", 0)
    aw = mc_data.get("away_win", 0)

    render_progress_bar("主胜", hw)
    if mc_data.get("is_knockout"):
        render_progress_bar("平(进加时)", dr)
    else:
        render_progress_bar("平", dr)
    render_progress_bar("客胜", aw)

    top = mc_data.get("top_scorelines", [])
    if top:
        top_str = " | ".join(f'{s["score"]} ({s["probability"]}%)' for s in top[:5])
        st.caption(f"最可能比分: {top_str}")

    # 加时赛信息
    if mc_data.get("extra_time"):
        et = mc_data["extra_time"]
        with st.expander("⏱️ 加时赛模拟"):
            c1, c2 = st.columns(2)
            c1.metric("加时主胜", f"{et.get('home_win_pct', 0):.1f}%")
            c2.metric("加时平局→点球", f"{et.get('draw_pct', 0):.1f}%")

    # 点球大战信息
    if mc_data.get("penalty_shootout"):
        ps = mc_data["penalty_shootout"]
        with st.expander("🎯 点球大战模拟"):
            c1, c2 = st.columns(2)
            c1.metric("点球主胜", f"{ps.get('home_win_pct', 0):.1f}%")
            c2.metric("点球客胜", f"{ps.get('away_win_pct', 0):.1f}%")


def render_bayesian_card(bayes_data: Dict):
    """渲染贝叶斯融合卡片"""
    if not bayes_data:
        return

    st.markdown("**🔗 贝叶斯融合**")
    metrics = [
        {"label": "融合主胜", "value": f"{bayes_data.get('home_win', 0):.1%}"},
        {"label": "融合平局", "value": f"{bayes_data.get('draw', 0):.1%}"},
        {"label": "融合客胜", "value": f"{bayes_data.get('away_win', 0):.1%}"},
    ]
    render_metric_row(metrics, columns=3)
    st.caption(
        f"模型权重 {bayes_data.get('weight_model', 0):.0%} / "
        f"市场权重 {bayes_data.get('weight_market', 0):.0%} | "
        f"置信度 {bayes_data.get('confidence', 0):.1%}"
    )


def render_kelly_card(kelly_data: Dict):
    """渲染 Kelly 仓位卡片"""
    if not kelly_data:
        return

    st.markdown("**💰 Kelly 仓位**")
    rec = kelly_data.get("recommendation", "跳过")
    stake = kelly_data.get("stake_pct", 0)
    color = "🟢" if rec in ("中仓", "重仓") else ("🟡" if rec == "轻仓" else "🔴")

    c1, c2 = st.columns(2)
    c1.metric("建议", f"{color} {rec}")
    c2.metric("仓位", f"{stake:.2f}%")

    edge = kelly_data.get("edge", 0)
    if abs(edge) > 0.01:
        st.caption(f"Edge: {edge:+.1%}")


def render_environment_card(env_data: Dict):
    """渲染环境因素卡片"""
    if not env_data or not any(v for k, v in env_data.items() if k != "home_tactical"):
        return

    with st.expander("🌍 环境因素"):
        env_lines = []
        if env_data.get("temperature", 22) > 28:
            env_lines.append(f"🌡️ 高温 {env_data['temperature']}°C（补水机制已激活）")
        if env_data.get("altitude", 0) > 1500:
            env_lines.append(f"⛰️ 海拔 {env_data['altitude']}m")
        if env_data.get("is_rain"):
            env_lines.append("🌧️ 有雨")
        if abs(env_data.get("timezone_diff", 0)) > 2:
            env_lines.append(f"🕐 时差 {env_data['timezone_diff']:.0f}h")
        if env_data.get("is_high_stakes"):
            env_lines.append("🔥 大赛高压")
        if env_data.get("home_tactical") and env_data.get("away_tactical"):
            env_lines.append(f"⚔️ 战术: {env_data['home_tactical']} vs {env_data['away_tactical']}")
        for line in env_lines:
            st.markdown(f"  {line}")


def render_intelligence_card(extra: str):
    """渲染实时情报卡片"""
    if not extra:
        return

    with st.expander("🌐 实时情报"):
        st.markdown(
            f'<div class="search-result">{extra}</div>',
            unsafe_allow_html=True
        )


def render_analysis_card(data: Dict):
    """
    渲染完整的多维度分析卡片

    Args:
        data: {
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
    if not data:
        return

    render_elo_card(data.get("elo"))
    render_poisson_card(data.get("poisson"))
    render_monte_carlo_card(data.get("monte_carlo"))
    render_bayesian_card(data.get("bayesian"))
    render_kelly_card(data.get("kelly"))

    # 综合预测
    pred = data.get("prediction", "")
    if pred:
        st.info(f"**📌 综合预测**: {pred}")

    render_environment_card(data.get("environment"))
    render_intelligence_card(data.get("extra"))


# ──────────────────────────────────────────────
#  积分榜组件
# ──────────────────────────────────────────────
def render_standings_table(standings: List[Dict], flag_func=None):
    """
    渲染积分榜表格

    Args:
        standings: 积分榜数据列表
        flag_func: 球队名 → emoji 的函数
    """
    if not standings:
        st.warning("⚠️ 暂无积分榜数据")
        return

    groups = sorted({s["team_group"] for s in standings})
    c1, c2, c3 = st.columns(3)
    c1.metric("参赛球队", f"{len(standings)} 支")
    c2.metric("小组数", f"{len(groups)} 个")
    c3.metric("数据源", "本地数据")

    for g in groups:
        gt = sorted([s for s in standings if s["team_group"] == g],
                    key=lambda x: int(x.get("rank", 99)))
        st.subheader(f"组 {g}")
        rows = []
        for t in gt:
            n = t["team_name"]
            p = int(t["win"]) + int(t["draw"]) + int(t["lose"])
            gd = int(t["goal"]) - int(t["miss_goal"])
            flag = flag_func(n) if flag_func else "🏳️"
            rows.append({
                "": flag,
                "排名": t["rank"],
                "球队": n,
                "赛": p,
                "胜": t["win"],
                "平": t["draw"],
                "负": t["lose"],
                "净": f"+{gd}" if gd > 0 else str(gd),
                "积分": t["score"],
            })
        st.table(pd.DataFrame(rows).set_index("排名"))


# ──────────────────────────────────────────────
#  赔率导入组件
# ──────────────────────────────────────────────
def render_odds_upload_section(importer_class, session_state_key: str = "_imported_odds"):
    """
    渲染赔率上传区域

    Args:
        importer_class: OddsImporter 类
        session_state_key: session_state 中存储赔率数据的 key
    """
    st.subheader("📥 上传赔率 & 情报 Excel")
    st.caption(
        "支持 .xlsx / .xls / .csv 格式。智能识别列名，无需固定模板。\n"
        "可单次上传比赛日的部分比赛，系统会自动匹配赛程。"
    )

    uploaded = st.file_uploader(
        "上传文件",
        type=["xlsx", "xls", "csv"],
        help="支持任意格式的表格，只要包含球队名和赔率列即可"
    )

    if uploaded is not None:
        try:
            importer = importer_class()
            df = importer.parse_file(uploaded)
            if df is not None and len(df) > 0:
                odds_dict = importer.to_match_odds_dict(df, auto_match=True)

                # 增量合并
                existing = st.session_state.get(session_state_key, {})
                merged, updated, added = importer.merge_with_existing(odds_dict, existing)
                st.session_state[session_state_key] = merged

                # 显示摘要
                summary = importer.get_import_summary(odds_dict)
                st.success(
                    f"✅ 成功导入 {summary['total']} 场比赛\n"
                    f"- 更新 {updated} 场 | 新增 {added} 场\n"
                    f"- 涉及球队: {', '.join(summary['teams'][:10])}"
                    f"{'...' if len(summary['teams']) > 10 else ''}"
                )

                if summary['dates']:
                    st.caption(f"比赛日期: {', '.join(summary['dates'])}")

                st.dataframe(df, use_container_width=True, hide_index=True)
            else:
                st.warning("⚠️ 文件为空或格式不正确")
        except ImportError:
            st.error("⚠️ 解析模块未安装，请确保 openpyxl 已安装")
        except Exception as e:
            st.error(f"⚠️ 解析失败: {str(e)[:200]}")

    # 显示已导入数据摘要
    imported = st.session_state.get(session_state_key, {})
    if imported:
        st.divider()
        st.subheader(f"📋 已导入 {len(imported)} 场比赛")

        # 按日期分组显示
        by_date = {}
        for mid, oi in imported.items():
            date = oi.get("date", "未指定日期")[:10] if oi.get("date") else "未指定日期"
            by_date.setdefault(date, []).append(oi)

        for date, matches in sorted(by_date.items()):
            with st.expander(f"📅 {date} ({len(matches)} 场)"):
                for oi in matches:
                    st.text(
                        f"  {oi.get('home', '?')} vs {oi.get('away', '?')} | "
                        f"主胜{oi.get('oh', '-')} 平{oi.get('od', '-')} 客胜{oi.get('oa', '-')}"
                    )

        if st.button("🗑️ 清除已导入赔率"):
            st.session_state[session_state_key] = {}
            st.rerun()


# ──────────────────────────────────────────────
#  风控状态组件
# ──────────────────────────────────────────────
def render_risk_status(risk_controller):
    """渲染风控状态面板"""
    status = risk_controller.get_status()
    with st.expander("📊 当日风控状态"):
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("日盈亏", f"¥{status['daily_pnl']:.2f}")
        c2.metric("亏损比例", f"{status['daily_loss_pct']:.1f}%")
        c3.metric("连亏次数", f"{status['consecutive_losses']}")
        c4.metric("状态", "⏸️ 暂停" if status['paused'] else "✅ 正常")

        if status.get("alerts"):
            st.markdown("**最近预警:**")
            for alert in status["alerts"][-3:]:
                level_color = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "🔵"}
                st.text(f"{level_color.get(alert['level'], '⚪')} [{alert['level']}] {alert['msg']}")


# ──────────────────────────────────────────────
#  比赛列表组件
# ──────────────────────────────────────────────
def render_match_list(matches: List[Dict], flag_func=None, max_display: int = 50,
                      show_odds: bool = True, imported_odds: Dict = None):
    """
    渲染比赛列表

    Args:
        matches: 比赛数据列表
        flag_func: 球队名 → emoji 函数
        max_display: 最大显示数量
        show_odds: 是否显示赔率
        imported_odds: 已导入的赔率字典
    """
    if not matches:
        st.info("暂无比赛")
        return

    imported_odds = imported_odds or {}

    for m in matches[:max_display]:
        h = m.get("host_team_name", "?")
        a = m.get("guest_team_name", "?")
        mid = m.get("id", "")
        dt = (m.get("date", "") or "")[:16]
        grp = m.get("group_name", "")
        mtype = m.get("match_type_name", "小组赛")

        hf = flag_func(h) if flag_func else "🏳️"
        af = flag_func(a) if flag_func else "🏳️"

        with st.expander(f"📅{dt}|{hf} {h} vs {a} {af}|{mtype} {grp}"):
            # 显示已导入赔率
            if mid in imported_odds:
                oi = imported_odds[mid]
                st.success(
                    f"📥 已导入赔率: 主胜{oi.get('oh', '-')} / "
                    f"平{oi.get('od', '-')} / 客胜{oi.get('oa', '-')}"
                )
                if oi.get("intel"):
                    st.markdown(
                        f'<div class="search-result">📰 {oi["intel"]}</div>',
                        unsafe_allow_html=True
                    )
            elif show_odds:
                st.info("💡 请在「赔率导入」Tab 上传 Excel 文件导入赔率")


# ──────────────────────────────────────────────
#  CSS 样式
# ──────────────────────────────────────────────
def inject_custom_css():
    """注入自定义 CSS 样式"""
    st.markdown("""
    <style>
    .main-title {
        font-size: 2.5rem;
        font-weight: bold;
        text-align: center;
        color: #f97316;
        margin-bottom: 0;
    }
    .subtitle {
        font-size: 1rem;
        text-align: center;
        color: #64748b;
        margin-bottom: 2rem;
    }
    .analysis-box {
        background: #1e293b;
        border-left: 4px solid #f97316;
        padding: 1rem;
        margin: .5rem 0;
        border-radius: 0 8px 8px 0;
        color: #e2e8f0;
    }
    .data-source-badge {
        display: inline-block;
        padding: 2px 8px;
        border-radius: 12px;
        font-size: .75rem;
        font-weight: 600;
    }
    .source-live {
        background: #064e3b;
        color: #34d399;
    }
    .source-cache {
        background: #78350f;
        color: #fbbf24;
    }
    .search-result {
        background: #1e293b;
        border: 1px solid #334155;
        border-radius: 8px;
        padding: .8rem;
        margin: .3rem 0;
        color: #cbd5e1;
        font-size: .9rem;
    }
    </style>
    """, unsafe_allow_html=True)
