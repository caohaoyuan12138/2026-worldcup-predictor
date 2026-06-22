#!/usr/bin/env python3
"""Replace render_predictions function with optimized version"""

with open('app.py', 'r', encoding='utf-8') as f:
    content = f.read()

old_start = 'def render_predictions(data):'
old_end = '    # ── Tab 3: 赔率导入 ──'

start_idx = content.find(old_start)
end_idx = content.find(old_end, start_idx)

if start_idx == -1 or end_idx == -1:
    print(f'Function not found: start={start_idx}, end={end_idx}')
    exit(1)

print(f'Found function: {end_idx - start_idx} chars')

new_func = '''def render_predictions(data):
    st.header("🔮 比赛分析")
    matches = data.get("matches") or []
    engine = data.get("elo")
    standings = data.get("standings") or []
    if not matches:
        matches = ld.load_schedule()
    if not standings:
        standings = ld.load_standings()

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
        else:
            # 使用 selectbox 选择比赛，避免一次性分析所有比赛
            done_options = []
            for m in done:
                h = m.get("host_team_name", "?")
                a = m.get("guest_team_name", "?")
                hs = m.get("host_team_score", "")
                gs = m.get("guest_team_score", "")
                dt = (m.get("date", "") or "")[:10]
                grp = m.get("group_name", "")
                label = f"{dt} | {h} {hs}:{gs} {a} | {grp}"
                done_options.append(label)

            selected_done = st.selectbox(
                "选择已完赛比赛进行分析",
                options=done_options,
                index=0,
                key="review_match_select"
            )

            selected_idx = done_options.index(selected_done)
            m = done[selected_idx]

            h, a = m.get("host_team_name", "?"), m.get("guest_team_name", "?")
            hs = m.get("host_team_score", "")
            gs = m.get("guest_team_score", "")
            dt = (m.get("date", "") or "")[:10]
            grp = m.get("group_name", "")

            st.markdown(f"### 📺 {dt} | {h} {hs}:{gs} {a} | {grp}")

            hid = m.get("host_team_id") or gid(h)
            aid = m.get("guest_team_id") or gid(a)
            if not (hid and aid):
                st.warning("无法识别球队 ID")
            else:
                analysis_key = f"_analysis_{h}_{a}"
                if analysis_key not in st.session_state:
                    with st.spinner("🔍 正在分析（蒙特卡洛模拟 50000 次）..."):
                        stage, is_knockout = _detect_stage_and_knockout(m)
                        mh, ma = _estimate_motivation(m, standings, hid, aid)
                        st.session_state[analysis_key] = _do_analysis(
                            hid, aid, engine, h, a,
                            m.get("odds_home"), m.get("odds_draw"), m.get("odds_away"),
                            stage, None,
                            is_knockout=is_knockout,
                            motivation_home=mh, motivation_away=ma,
                            use_market_odds=bool(m.get("odds_home")),
                        )
                analysis = st.session_state[analysis_key]
                _render_analysis_card(analysis)

                prediction_key = f"_prediction_{h}_{a}"
                st.session_state[prediction_key] = analysis

                # 模型复盘
                if hs is not None and gs is not None:
                    actual_h = int(hs)
                    actual_a = int(gs)
                    actual_result = "home" if actual_h > actual_a else ("away" if actual_a > actual_h else "draw")

                    elo_pred = analysis.get("elo", {})
                    pois_pred = analysis.get("poisson", {})
                    mc_pred = analysis.get("monte_carlo", {})

                    st.divider()
                    st.subheader("📊 模型复盘")
                    c1, c2, c3 = st.columns(3)
                    if elo_pred:
                        elo_home = elo_pred.get("home_win", 0)
                        elo_draw = elo_pred.get("draw", 0)
                        elo_away = elo_pred.get("away_win", 0)
                        elo_result = "home" if elo_home > max(elo_draw, elo_away) else ("away" if elo_away > max(elo_home, elo_draw) else "draw")
                        elo_correct = (elo_result == actual_result)
                        c1.metric("Elo预测", f"{'✅' if elo_correct else '❌'} {elo_result}")
                    if pois_pred:
                        lh_p = pois_pred.get("lambda_home", 0)
                        la_p = pois_pred.get("lambda_away", 0)
                        pois_result = "home" if lh_p > la_p else ("away" if la_p > lh_p else "draw")
                        pois_correct = (pois_result == actual_result)
                        c2.metric("泊松预测", f"{'✅' if pois_correct else '❌'} {pois_result}")
                    if mc_pred:
                        mc_home = mc_pred.get("home_win", 0)
                        mc_draw = mc_pred.get("draw", 0)
                        mc_away = mc_pred.get("away_win", 0)
                        mc_result = "home" if mc_home > max(mc_draw, mc_away) else ("away" if mc_away > max(mc_home, mc_draw) else "draw")
                        mc_correct = (mc_result == actual_result)
                        c3.metric("MC预测", f"{'✅' if mc_correct else '❌'} {mc_result}")

                    votes = []
                    if elo_pred: votes.append(elo_result)
                    if pois_pred: votes.append(pois_result)
                    if mc_pred: votes.append(mc_result)
                    if votes:
                        from collections import Counter
                        majority = Counter(votes).most_common(1)[0][0]
                        direction_correct = (majority == actual_result)
                        st.caption(f"实际结果: {actual_h}:{actual_a} ({actual_result}) | 多数投票: {'✅' if direction_correct else '❌'}")

    # ── Tab 2: 未赛预测 ──
    with t2:
        if not todo:
            st.info("暂无未赛比赛")
        else:
            # 使用 selectbox 选择比赛，避免创建大量 expander
            todo_options = []
            for m in todo:
                h = m.get("host_team_name", "?")
                a = m.get("guest_team_name", "?")
                dt = (m.get("date", "") or "")[:16]
                grp = m.get("group_name", "")
                mtype = m.get("match_type_name", "小组赛")
                label = f"{dt} | {h} vs {a} | {mtype} {grp}"
                todo_options.append(label)

            selected_todo = st.selectbox(
                "选择未赛比赛进行预测",
                options=todo_options,
                index=0,
                key="predict_match_select"
            )

            selected_idx = todo_options.index(selected_todo)
            m = todo[selected_idx]

            h, a = m.get("host_team_name", "?"), m.get("guest_team_name", "?")
            mid = m.get("id", "")
            dt = (m.get("date", "") or "")[:16]
            grp = m.get("group_name", "")
            mtype = m.get("match_type_name", "小组赛")

            st.markdown(f"### 🔮 {dt} | {h} vs {a} | {mtype} {grp}")

            imported_odds = st.session_state.get("_imported_odds", {})
            if mid in imported_odds:
                oi = imported_odds[mid]
                st.success(f"📥 已导入赔率: 主胜{oi.get('oh', '-')} / 平{oi.get('od', '-')} / 客胜{oi.get('oa', '-')}")
                if oi.get("intel"):
                    st.markdown(f'<div class="search-result">{oi["intel"]}</div>', unsafe_allow_html=True)
            else:
                st.info("💡 请在「赔率导入」Tab 上传 Excel 文件导入赔率")

            if st.button(f"🎯 分析这场比赛", key=f"analyze_{mid}"):
                hid = m.get("host_team_id") or gid(h)
                aid = m.get("guest_team_id") or gid(a)
                if not (hid and aid):
                    st.warning("无法识别球队 ID")
                else:
                    stage, is_knockout = _detect_stage_and_knockout(m)
                    mh, ma = _estimate_motivation(m, standings, hid, aid)

                    oi = imported_odds.get(mid, {})
                    oh = oi.get("oh") if oi else None
                    od = oi.get("od") if oi else None
                    oa = oi.get("oa") if oi else None

                    with st.spinner("🔍 正在分析（蒙特卡洛模拟 50000 次）..."):
                        analysis = _do_analysis(
                            hid, aid, engine, h, a,
                            oh, od, oa,
                            stage, None,
                            is_knockout=is_knockout,
                            motivation_home=mh, motivation_away=ma,
                            use_market_odds=bool(oh),
                        )
                    st.session_state[f"_analysis_{mid}"] = analysis
                    _render_analysis_card(analysis)

'''

content = content[:start_idx] + new_func + content[end_idx:]

with open('app.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('Done - replaced render_predictions function')
