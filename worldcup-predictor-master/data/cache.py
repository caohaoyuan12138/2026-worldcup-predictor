"""
文件缓存层

功能：
1. JSON 文件缓存（带 TTL）
2. 缓存目录管理
3. 缓存清理 / 统计
"""

import json
import os
import time
from typing import Any, Optional
from datetime import datetime, timedelta

CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "data_local")
STATS_FILE = os.path.join(CACHE_DIR, "cache_stats.json")

os.makedirs(CACHE_DIR, exist_ok=True)


def get_cache_path(key: str) -> str:
    """根据 key 获取缓存路径"""
    safe_key = key.replace("/", "_").replace("\\", "_").replace(":", "_").replace("=", "_")
    return os.path.join(CACHE_DIR, f"{safe_key}.json")


def load(key: str, ttl: int = 3600) -> Optional[Any]:
    """
    加载缓存

    Args:
        key: 缓存键
        ttl: 有效期（秒）

    Returns:
        缓存数据或 None
    """
    path = get_cache_path(key)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if time.time() - data.get("_ts", 0) < ttl:
            return data.get("data")
    except (json.JSONDecodeError, IOError, KeyError):
        pass
    return None


def save(key: str, data: Any):
    """保存缓存"""
    path = get_cache_path(key)
    wrapper = {
        "_ts": int(time.time()),
        "_key": key,
        "data": data
    }
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(wrapper, f, ensure_ascii=False, indent=2)
    except IOError:
        pass


def exists(key: str, ttl: int = 3600) -> bool:
    """检查缓存是否存在且未过期"""
    return load(key, ttl) is not None


def clear(key: str):
    """删除指定缓存"""
    path = get_cache_path(key)
    if os.path.exists(path):
        os.remove(path)


def clear_all():
    """清空所有缓存"""
    if not os.path.exists(CACHE_DIR):
        return 0
    count = 0
    for f in os.listdir(CACHE_DIR):
        if f.endswith(".json") and f != "cache_stats.json":
            try:
                os.remove(os.path.join(CACHE_DIR, f))
                count += 1
            except IOError:
                pass
    return count


def stats() -> dict:
    """缓存统计"""
    if not os.path.exists(CACHE_DIR):
        return {"total": 0, "expired": 0, "active": 0}
    total = expired = active = 0
    now = time.time()
    for f in os.listdir(CACHE_DIR):
        if not f.endswith(".json") or f == "cache_stats.json":
            continue
        total += 1
        try:
            with open(os.path.join(CACHE_DIR, f), "r") as fp:
                data = json.load(fp)
            if now - data.get("_ts", 0) > 3600:
                expired += 1
            else:
                active += 1
        except (json.JSONDecodeError, IOError):
            expired += 1
    return {"total": total, "expired": expired, "active": active}
