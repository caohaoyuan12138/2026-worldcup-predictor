"""
风控红线模块

功能：
1. 浓度限制（单一联赛/日期）
2. 连亏止损（达到阈值暂停）
3. 日亏损上限
4. 异常检测（赔率突变预警）
"""

import config
from typing import Dict, List, Optional
from datetime import datetime


class RiskController:
    """实时风控控制器"""

    def __init__(self, max_daily_loss_pct: float = 0.10,
                 max_concentration_pct: float = 0.20,
                 max_consecutive_losses: int = 3,
                 odds_change_alert: float = 0.05):
        # 日亏损上限（总资金 10%）
        self.max_daily_loss_pct = max_daily_loss_pct
        # 单一联赛集中度上限（总仓位 20%）
        self.max_concentration_pct = max_concentration_pct
        # 最大连亏次数
        self.max_consecutive_losses = max_consecutive_losses
        # 赔率变化预警阈值
        self.odds_change_alert = odds_change_alert

        # 状态追踪
        self.daily_pnl = 0           # 当日盈亏
        self.daily_start_bankroll = 0  # 当日初始资金
        self.consecutive_losses = 0    # 当前连亏次数
        self.league_exposure = {}      # 联赛仓位占比
        self.paused = False            # 是否暂停
        self.alerts = []               # 预警信息

        self.bets_today = []           # 今日已投注记录

    def reset_day(self, bankroll: float):
        """每日开盘重置"""
        self.daily_pnl = 0
        self.daily_start_bankroll = bankroll
        self.consecutive_losses = 0
        self.league_exposure = {}
        self.paused = False
        self.alerts = []
        self.bets_today = []

    def check_all(self, proposed_bet: Dict) -> Dict:
        """
        全量风控检查（所有红线规则）

        Args:
            proposed_bet: {league, stake_pct, odds, match_id, ...}

        Returns:
            {approved: bool, reason: str, adjusted_stake: float, alerts: [...]}
        """
        alerts = []

        # ----- 1. 日亏损检查 -----
        if self.daily_start_bankroll > 0:
            loss_pct = abs(min(self.daily_pnl, 0)) / self.daily_start_bankroll
            if loss_pct >= self.max_daily_loss_pct:
                self.paused = True
                alerts.append({
                    "level": "CRITICAL",
                    "rule": "日亏损上限",
                    "msg": f"当日亏损 {loss_pct:.1%}，已触发 {self.max_daily_loss_pct:.1%} 上限，暂停所有投注"
                })
                return {"approved": False, "reason": "日亏损上限", "alerts": alerts}

        # ----- 2. 连亏止损 -----
        if self.consecutive_losses >= self.max_consecutive_losses:
            self.paused = True
            alerts.append({
                "level": "HIGH",
                "rule": "连亏止损",
                "msg": f"连续亏损 {self.consecutive_losses} 次，建议暂停 24 小时"
            })
            return {"approved": False, "reason": "连亏止损", "alerts": alerts}

        # ----- 3. 联赛集中度检查 -----
        league = proposed_bet.get("league", "unknown")
        current_league_pct = self.league_exposure.get(league, 0)
        new_stake_pct = proposed_bet.get("stake_pct", 0)
        if current_league_pct + new_stake_pct > self.max_concentration_pct:
            adjusted = max(0, self.max_concentration_pct - current_league_pct)
            alerts.append({
                "level": "MEDIUM",
                "rule": "联赛集中度",
                "msg": f"联赛 {league} 仓位将达到 {current_league_pct + new_stake_pct:.1%}，已调整至 {adjusted:.1%}"
            })
            proposed_bet["stake_pct"] = adjusted
            adjusted_stake = adjusted
        else:
            adjusted_stake = new_stake_pct

        # ----- 4. 赔率突变预警 -----
        prev_odds = proposed_bet.get("prev_odds")
        curr_odds = proposed_bet.get("odds")
        if prev_odds and curr_odds and prev_odds > 0:
            change = abs(curr_odds - prev_odds) / prev_odds
            if change >= self.odds_change_alert:
                alerts.append({
                    "level": "MEDIUM",
                    "rule": "赔率突变",
                    "msg": f"赔率从 {prev_odds} 变动至 {curr_odds}（{change:.1%}），建议评估市场信息"
                })

        # ----- 5. 大额单注预警 -----
        if new_stake_pct > 0.03:
            alerts.append({
                "level": "LOW",
                "rule": "单注偏大",
                "msg": f"单注仓位 {new_stake_pct:.1%} 超过 3%，确认是否在计划内"
            })

        return {
            "approved": True,
            "reason": "通过",
            "adjusted_stake_pct": adjusted_stake,
            "alerts": alerts
        }

    def record_result(self, bet: Dict, won: bool):
        """记录投注结果，更新状态"""
        stake = bet.get("stake_pct", 0) * self.daily_start_bankroll if self.daily_start_bankroll else 0
        odds = bet.get("odds", 1)

        if won:
            pnl = stake * (odds - 1)
            self.consecutive_losses = 0
        else:
            pnl = -stake
            self.consecutive_losses += 1

        self.daily_pnl += pnl
        league = bet.get("league", "unknown")
        self.league_exposure[league] = self.league_exposure.get(league, 0) + bet.get("stake_pct", 0)

        self.bets_today.append({
            "match": bet.get("match", ""),
            "won": won,
            "pnl": pnl,
            "stake": stake,
        })

    def get_status(self) -> Dict:
        """获取当日风控状态"""
        daily_loss_pct = 0
        if self.daily_start_bankroll > 0:
            daily_loss_pct = abs(min(self.daily_pnl, 0)) / self.daily_start_bankroll

        return {
            "paused": self.paused,
            "daily_pnl": round(self.daily_pnl, 2),
            "daily_loss_pct": round(daily_loss_pct * 100, 2),
            "consecutive_losses": self.consecutive_losses,
            "league_exposure": {k: round(v * 100, 2) for k, v in self.league_exposure.items()},
            "bets_today": len(self.bets_today),
            "alerts": self.alerts[-5:]  # 最近 5 条预警
        }
