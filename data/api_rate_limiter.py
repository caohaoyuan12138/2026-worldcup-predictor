"""
API 速率限制器 - 控制 juhe.cn API 调用次数（每天 50 次）

功能：
- 每日自动重置计数器
- 记录每次调用的端点和时间
- 提供剩余次数查询
- 超过限制时自动拒绝调用
"""

import json
import os
import time
from datetime import datetime, date
from typing import Optional

RATE_LIMIT_DIR = os.path.join(os.path.dirname(__file__), "..", "data_local")
RATE_LIMIT_FILE = os.path.join(RATE_LIMIT_DIR, "api_rate_limit.json")
MAX_DAILY_CALLS = 50  # juhe.cn 每天限制 50 次

os.makedirs(RATE_LIMIT_DIR, exist_ok=True)


def _load_rate_data() -> dict:
    """加载速率限制数据"""
    if not os.path.exists(RATE_LIMIT_FILE):
        return {"date": str(date.today()), "calls": 0, "call_log": []}
    try:
        with open(RATE_LIMIT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        # 如果日期变了，重置计数
        if data.get("date") != str(date.today()):
            return {"date": str(date.today()), "calls": 0, "call_log": []}
        return data
    except (json.JSONDecodeError, IOError):
        return {"date": str(date.today()), "calls": 0, "call_log": []}


def _save_rate_data(data: dict):
    """保存速率限制数据"""
    try:
        with open(RATE_LIMIT_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except IOError:
        pass


def can_call_api() -> bool:
    """检查是否还可以调用 API"""
    data = _load_rate_data()
    return data["calls"] < MAX_DAILY_CALLS


def record_call(endpoint: str = "") -> bool:
    """
    记录一次 API 调用

    Args:
        endpoint: API 端点名称（如 schedule, teams, standings）

    Returns:
        bool: 如果调用成功记录返回 True，如果超过限制返回 False
    """
    data = _load_rate_data()
    if data["calls"] >= MAX_DAILY_CALLS:
        return False

    data["calls"] += 1
    data["call_log"].append({
        "endpoint": endpoint,
        "timestamp": datetime.now().isoformat()
    })
    # 只保留最近 100 条日志
    if len(data["call_log"]) > 100:
        data["call_log"] = data["call_log"][-100:]

    _save_rate_data(data)
    return True


def get_remaining_calls() -> int:
    """获取剩余可调用次数"""
    data = _load_rate_data()
    return max(0, MAX_DAILY_CALLS - data["calls"])


def get_rate_limit_status() -> dict:
    """获取速率限制状态"""
    data = _load_rate_data()
    return {
        "date": data["date"],
        "calls_today": data["calls"],
        "max_daily": MAX_DAILY_CALLS,
        "remaining": max(0, MAX_DAILY_CALLS - data["calls"]),
        "last_call": data["call_log"][-1] if data["call_log"] else None
    }


def reset_rate_limit():
    """重置速率限制（用于测试）"""
    _save_rate_data({"date": str(date.today()), "calls": 0, "call_log": []})


# 测试
if __name__ == "__main__":
    print("=== API 速率限制器状态 ===")
    status = get_rate_limit_status()
    print(f"日期: {status['date']}")
    print(f"今日已调用: {status['calls_today']}/{status['max_daily']}")
    print(f"剩余: {status['remaining']}")
    if status['last_call']:
        print(f"上次调用: {status['last_call']['endpoint']} @ {status['last_call']['timestamp']}")
