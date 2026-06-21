"""
失败模式过滤 — 六项否决

功能：
1. 近态光环陷阱（连胜后过度乐观）
2. H2H 样本不足（< 3 次交手）
3. 阵容未知（赛前 24h 未公布名单）
4. 淘汰赛心理压力未量化
5. 裁判选派极端偏差
6. 政治/安全因素干扰

每项返回 (bool, reason) — True 表示通过，False 表示否决
"""

from typing import Dict, List, Tuple, Optional
from datetime import datetime


def check_recent_form_bias(team_id: int, elo_engine,
                            recent_results: List[Dict]) -> Tuple[bool, str]:
    """
    否决 1：近态光环陷阱

    如果球队近 3 场全胜且 Elo 涨幅 > 50 分，标记为"过度乐观风险"
    """
    if not recent_results or len(recent_results) < 3:
        return True, "数据不足，默认通过"

    last_3 = recent_results[-3:]
    wins = sum(1 for r in last_3 if r.get("result", 0) > 0.5)

    if wins >= 3:
        return False, "⚠️ 否决：近 3 场全胜，存在过度乐观风险（光环陷阱）"

    return True, "通过"


def check_h2h_sample(h2h_count: int) -> Tuple[bool, str]:
    """
    否决 2：H2H 样本不足

    两队历史交手 < 3 次时，H2H 统计不可靠
    """
    if h2h_count < 3:
        return False, f"⚠️ 否决：H2H 交手仅 {h2h_count} 次（< 3），样本不足"

    return True, f"通过（H2H {h2h_count} 次）"


def check_lineup_confirmed(lineup_announced: bool,
                           hours_to_kickoff: float) -> Tuple[bool, str]:
    """
    否决 3：阵容未知

    赛前 24h 未公布首发名单
    """
    if not lineup_announced and hours_to_kickoff < 24:
        return False, "⚠️ 否决：赛前 24h 未公布首发名单，阵容不确定性高"

    return True, "通过"


def check_knockout_pressure(phase: str, model_adjusted: bool = False) -> Tuple[bool, str]:
    """
    否决 4：淘汰赛心理压力未量化

    淘汰赛阶段需要额外心理压力修正
    """
    knockout_phases = ["round_of_16", "quarter_final", "semi_final", "final"]

    if phase in knockout_phases and not model_adjusted:
        return False, f"⚠️ 否决：{phase} 阶段心理压力未量化，需应用压力修正系数"

    return True, "通过"


def check_referee_bias(referee_nationality: str,
                       team_nationalities: List[str],
                       known_bias: float = 0) -> Tuple[bool, str]:
    """
    否决 5：裁判选派极端偏差

    裁判国籍与参赛队同洲，或有已知执法偏差
    """
    if abs(known_bias) > 0.05:
        return False, f"⚠️ 否决：裁判执法偏差系数 {known_bias:.2f} 超过阈值"

    return True, "通过"


def check_political_safety(risk_level: str = "low") -> Tuple[bool, str]:
    """
    否决 6：政治/安全因素干扰

    高风险地区/政治敏感比赛
    """
    if risk_level in ("high", "critical"):
        return False, f"⚠️ 否决：安全/政治风险等级 {risk_level}，建议跳过"

    return True, "通过"


def apply_all_filters(match_context: Dict) -> Dict:
    """
    应用全部六项否决过滤

    Args:
        match_context: {
            team_id, elo_engine, recent_results,
            h2h_count, lineup_announced, hours_to_kickoff,
            phase, referee_nationality, team_nationalities,
            referee_bias, political_risk
        }

    Returns:
        {passed: bool, checks: [...], veto_reason: str}
    """
    checks = []
    all_passed = True
    veto_reason = ""

    # 1. 近态光环
    ok, msg = check_recent_form_bias(
        match_context.get("team_id", 0),
        match_context.get("elo_engine"),
        match_context.get("recent_results", [])
    )
    checks.append({"name": "近态光环陷阱", "passed": ok, "msg": msg})
    if not ok:
        all_passed = False
        veto_reason = msg

    # 2. H2H 样本
    ok, msg = check_h2h_sample(match_context.get("h2h_count", 0))
    checks.append({"name": "H2H样本", "passed": ok, "msg": msg})
    if not ok:
        all_passed = False
        veto_reason = msg

    # 3. 阵容确认
    ok, msg = check_lineup_confirmed(
        match_context.get("lineup_announced", True),
        match_context.get("hours_to_kickoff", 48)
    )
    checks.append({"name": "阵容确认", "passed": ok, "msg": msg})
    if not ok:
        all_passed = False
        veto_reason = msg

    # 4. 淘汰赛压力
    ok, msg = check_knockout_pressure(
        match_context.get("phase", "group_stage"),
        match_context.get("model_adjusted", False)
    )
    checks.append({"name": "淘汰赛压力", "passed": ok, "msg": msg})
    if not ok:
        all_passed = False
        veto_reason = msg

    # 5. 裁判偏差
    ok, msg = check_referee_bias(
        match_context.get("referee_nationality", ""),
        match_context.get("team_nationalities", []),
        match_context.get("referee_bias", 0)
    )
    checks.append({"name": "裁判偏差", "passed": ok, "msg": msg})
    if not ok:
        all_passed = False
        veto_reason = msg

    # 6. 政治/安全
    ok, msg = check_political_safety(
        match_context.get("political_risk", "low")
    )
    checks.append({"name": "政治安全", "passed": ok, "msg": msg})
    if not ok:
        all_passed = False
        veto_reason = msg

    return {
        "passed": all_passed,
        "checks": checks,
        "veto_reason": veto_reason if not all_passed else ""
    }
