"""
赔率抓取器 — OddSlot + OddsFilter

功能：
1. 从 oddslot.com/odds 抓取比赛赔率 + AI 预测胜率
2. 从 oddsfilter.com 抓取完整 JSON 赔率数据
3. 数据标准化和交叉验证
4. 异常处理 + 重试 + 缓存
"""

import requests
import re
import json
import time
import os
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
from bs4 import BeautifulSoup
import config

CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "data_local")
CACHE_TTL = 600  # 赔率缓存 10 分钟

os.makedirs(CACHE_DIR, exist_ok=True)


def _cache_path(name: str) -> str:
    return os.path.join(CACHE_DIR, f"odds_{name}.json")


def _load_cache(name: str) -> Optional[Dict]:
    p = _cache_path(name)
    if not os.path.exists(p):
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        if time.time() - data.get("_cached_at", 0) < CACHE_TTL:
            return data.get("payload")
    except (json.JSONDecodeError, KeyError):
        pass
    return None


def _save_cache(name: str, payload: Any):
    p = _cache_path(name)
    data = {"_cached_at": int(time.time()), "payload": payload}
    try:
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except IOError:
        pass


def _get_page(url: str, retries: int = 3) -> Optional[str]:
    """请求页面 HTML"""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,*/*",
        "Accept-Language": "en-US,en;q=0.9",
    }
    for attempt in range(retries):
        try:
            resp = requests.get(url, headers=headers, timeout=20)
            resp.raise_for_status()
            return resp.text
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
            else:
                print(f"[Scraper] 请求失败 {url}: {e}")
    return None


# ============================================================
# OddSlot 抓取
# ============================================================

def scrape_oddslot() -> Optional[List[Dict]]:
    """
    从 oddslot.com/odds 抓取赔率数据

    Returns:
        [{home_team, away_team, odds_home, odds_draw, odds_away,
          pred_home, pred_draw, pred_away, confidence, ...}, ...]
    """
    cached = _load_cache("oddslot")
    if cached is not None:
        return cached

    html = _get_page(config.ODDSLOT_URL)
    if not html:
        return None

    matches = []

    # OddSlot 页面结构：每个比赛是一个卡片
    # 包含：联赛名、队名、时间、赔率（1/X/2）、预测胜率
    soup = BeautifulSoup(html, "lxml")

    # 尝试多种选择器找比赛卡片
    # OddSlot 用 Tailwind CSS，比赛通常在 flex/grid 布局中
    cards = soup.select("[class*='match'], [class*='game'], [class*='fixture']")

    if not cards:
        # 备选：尝试从页面中提取所有数字（赔率）和文本
        # 用正则从 HTML 中提取结构化的赔率数据
        cards = _extract_oddslot_by_pattern(soup)

    if not cards:
        # 最终备选：正则直接从 HTML 提取
        matches = _regex_extract_oddslot(html)

    if matches:
        _save_cache("oddslot", matches)

    return matches if matches else None


def _extract_oddslot_by_pattern(soup: BeautifulSoup) -> List[Dict]:
    """通过 DOM 模式提取 OddSlot 比赛数据"""
    matches = []

    # 查找所有包含赔率的容器
    # 赔率通常是浮点数（如 1.45, 3.20, 5.60）
    all_divs = soup.find_all("div")
    for div in all_divs:
        text = div.get_text(strip=True)
        # 匹配 "数字.数字" 格式的赔率
        odds_pattern = re.findall(r'(\d+\.\d+)', text)
        if len(odds_pattern) >= 3:
            # 可能是赔率行
            parent = div.parent
            if parent:
                parent_text = parent.get_text(strip=True)
                # 尝试找队名
                team_names = _extract_team_names(parent_text)
                if len(team_names) >= 2:
                    try:
                        odds = [float(x) for x in odds_pattern[:3]]
                        if all(1.01 <= o <= 100 for o in odds):
                            matches.append({
                                "home_team": team_names[0],
                                "away_team": team_names[1],
                                "odds_home": odds[0],
                                "odds_draw": odds[1],
                                "odds_away": odds[2],
                                "source": "oddslot"
                            })
                    except ValueError:
                        continue

    return matches


def _regex_extract_oddslot(html: str) -> List[Dict]:
    """正则提取 OddSlot HTML 中的赔率"""
    matches = []

    # 赔率模式：连续三个浮点数（1/X/2）
    # 在 OddSlot 中，赔率通常在特定 class 的 span/div 中
    pattern = re.compile(
        r'(\d+\.\d{1,2})\s*[×xX]\s*(\d+\.\d{1,2})\s*[×xX]\s*(\d+\.\d{1,2})'
    )

    # 也匹配独立的赔率数字
    lines = html.split("\n")
    for line in lines:
        odds = re.findall(r'(\d+\.\d{2})', line)
        if len(odds) >= 3:
            vals = [float(o) for o in odds[:3]]
            if all(1.0 <= v <= 100.0 for v in vals):
                matches.append({
                    "raw_line": line[:50],
                    "values": vals,
                    "source": "oddslot_regex"
                })

    return matches


def _extract_team_names(text: str) -> List[str]:
    """从文本中提取队名"""
    # 常见分隔符
    separators = [" vs ", " VS ", " - ", " – ", " — "]
    for sep in separators:
        if sep in text:
            parts = text.split(sep)
            if len(parts) >= 2:
                return [parts[0].strip()[-40:], parts[1].strip()[:40]]
    return []


# ============================================================
# OddsFilter 抓取
# ============================================================

def scrape_oddsfilter() -> Optional[List[Dict]]:
    """
    从 oddsfilter.com 抓取赔率数据

    OddsFilter 使用 Next.js，数据嵌入在 HTML 的 self.__next_f.push 中

    Returns:
        [{home_team, away_team, odds_home, odds_draw, odds_away,
          league, date, markets: {...}}, ...]
    """
    cached = _load_cache("oddsfilter")
    if cached is not None:
        return cached

    html = _get_page(config.ODDSFILTER_URL)
    if not html:
        return None

    matches = []

    # 提取 Next.js 嵌入的 JSON 数据
    # 格式：self.__next_f.push([1,"JSON_DATA"])
    next_data_pattern = re.compile(
        r'self\.__next_f\.push\(\[1,"(.+?)"\]\)', re.DOTALL
    )
    matches_raw = next_data_pattern.findall(html)

    for raw in matches_raw:
        try:
            # unescape
            json_str = raw.replace('\\"', '"').replace('\\n', '\n').replace('\\t', '\t')
            data = json.loads(json_str)
            parsed = _parse_oddsfilter_data(data)
            if parsed:
                matches.extend(parsed)
        except (json.JSONDecodeError, Exception):
            continue
    if matches:
        _save_cache("oddsfilter", matches)

    return matches if matches else None


def _parse_oddsfilter_data(data: Any) -> List[Dict]:
    """解析 OddsFilter 的 JSON 数据"""
    results = []

    if isinstance(data, dict):
        # 查找比赛列表
        events = data.get("events") or data.get("matches") or data.get("data", [])
        if isinstance(events, dict):
            events = events.get("events") or events.get("matches") or []

        for event in events:
            if not isinstance(event, dict):
                continue

            home = event.get("homeTeam", {})
            away = event.get("awayTeam", {})
            league = event.get("league", {})

            if isinstance(home, dict):
                home_name = home.get("name", "")
            elif isinstance(home, str):
                home_name = home
            else:
                home_name = ""

            if isinstance(away, dict):
                away_name = away.get("name", "")
            elif isinstance(away, str):
                away_name = away
            else:
                away_name = ""

            if not home_name or not away_name:
                continue

            # 提取 Markets 赔率
            markets = event.get("markets", [])
            odds_home = odds_draw = odds_away = None
            other_markets = {}

            for market in markets:
                if not isinstance(market, dict):
                    continue
                market_name = market.get("name", "") or market.get("nameShort", "")

                outcomes = market.get("outcomes", [])
                outcome_dict = {}
                for oc in outcomes:
                    if isinstance(oc, dict):
                        oc_name = oc.get("name", "")
                        oc_val = oc.get("avgValue") or oc.get("price")
                        outcome_dict[oc_name] = oc_val

                if market_name in ("Full time", "1X2"):
                    odds_home = outcome_dict.get("1")
                    odds_draw = outcome_dict.get("X")
                    odds_away = outcome_dict.get("2")
                else:
                    other_markets[market_name] = outcome_dict

            if odds_home and odds_draw and odds_away:
                results.append({
                    "home_team": home_name,
                    "away_team": away_name,
                    "odds_home": float(odds_home),
                    "odds_draw": float(odds_draw),
                    "odds_away": float(odds_away),
                    "league": league.get("name", "") if isinstance(league, dict) else str(league),
                    "date": event.get("startAt", ""),
                    "markets": other_markets,
                    "source": "oddsfilter"
                })

    return results


# ============================================================
# 数据标准化 + 交叉验证
# ============================================================

def normalize_team_name(name: str) -> str:
    """标准化队名，便于匹配"""
    name = name.strip()
    # 常见别名映射
    aliases = {
        "Cabo Verde": "Cape Verde",
        "Curaçao": "Curacao",
        "Korea Republic": "South Korea",
        "Korea DPR": "North Korea",
        "IR Iran": "Iran",
        "PR China": "China",
        "Türkiye": "Turkey",
        "México": "Mexico",
        "UAE": "United Arab Emirates",
    }
    return aliases.get(name, name)


def cross_validate_odds(oddslot_data: List[Dict],
                        oddsfilter_data: List[Dict]) -> List[Dict]:
    """
    交叉验证两个数据源的赔率，取平均值

    匹配规则：主队名 + 客队名匹配（忽略大小写和别名）

    Returns:
        合并后的赔率列表
    """
    merged = []

    # 先索引 OddsFilter 数据
    of_index = {}
    for item in oddsfilter_data:
        key = (
            normalize_team_name(item.get("home_team", "")).lower(),
            normalize_team_name(item.get("away_team", "")).lower()
        )
        of_index[key] = item

    # 遍历 OddSlot，尝试匹配
    matched_keys = set()
    for item in oddslot_data:
        home = normalize_team_name(item.get("home_team", "")).lower()
        away = normalize_team_name(item.get("away_team", "")).lower()
        key = (home, away)

        entry = {
            "home_team": item.get("home_team", ""),
            "away_team": item.get("away_team", ""),
            "source": "merged"
        }

        # OddSlot 赔率
        os_odds = (item.get("odds_home"), item.get("odds_draw"),
                    item.get("odds_away"))

        # OddsFilter 赔率
        of_item = of_index.get(key)
        if of_item:
            matched_keys.add(key)
            of_odds = (of_item.get("odds_home"), of_item.get("odds_draw"),
                        of_item.get("odds_away"))

            # 取平均值
            if all(v is not None for v in os_odds) and all(v is not None for v in of_odds):
                entry["odds_home"] = round(
                    (os_odds[0] + of_odds[0]) / 2, 2)
                entry["odds_draw"] = round(
                    (os_odds[1] + of_odds[1]) / 2, 2)
                entry["odds_away"] = round(
                    (os_odds[2] + of_odds[2]) / 2, 2)
                entry["sources"] = 2
            elif all(v is not None for v in os_odds):
                entry["odds_home"] = os_odds[0]
                entry["odds_draw"] = os_odds[1]
                entry["odds_away"] = os_odds[2]
                entry["sources"] = 1
            elif all(v is not None for v in of_odds):
                entry["odds_home"] = of_odds[0]
                entry["odds_draw"] = of_odds[1]
                entry["odds_away"] = of_odds[2]
                entry["sources"] = 1

            entry["markets"] = of_item.get("markets", {})
        else:
            # 仅 OddSlot 有
            if all(v is not None for v in os_odds):
                entry["odds_home"] = os_odds[0]
                entry["odds_draw"] = os_odds[1]
                entry["odds_away"] = os_odds[2]
                entry["sources"] = 1

        # OddSlot 预测胜率
        pred_home = item.get("pred_home") or item.get("pred_home_win")
        pred_draw = item.get("pred_draw")
        pred_away = item.get("pred_away") or item.get("pred_away_win")
        if pred_home is not None:
            entry["pred_home"] = pred_home
        if pred_draw is not None:
            entry["pred_draw"] = pred_draw
        if pred_away is not None:
            entry["pred_away"] = pred_away
        if item.get("confidence"):
            entry["confidence"] = item["confidence"]

        if entry.get("odds_home"):
            merged.append(entry)

    # 添加仅 OddsFilter 有的比赛
    for key, item in of_index.items():
        if key not in matched_keys:
            merged.append({
                "home_team": item.get("home_team", ""),
                "away_team": item.get("away_team", ""),
                "odds_home": item.get("odds_home"),
                "odds_draw": item.get("odds_draw"),
                "odds_away": item.get("odds_away"),
                "league": item.get("league", ""),
                "date": item.get("date", ""),
                "markets": item.get("markets", {}),
                "sources": 1,
                "source": "oddsfilter_only"
            })

    return merged


def fetch_all_odds() -> List[Dict]:
    """
    获取所有赔率数据（自动抓取 + 交叉验证）

    Returns:
        合并后的赔率列表
    """
    print("[Scraper] 正在抓取 OddSlot 数据...")
    oddslot_data = scrape_oddslot()
    print(f"[Scraper] OddSlot: 获取 {len(oddslot_data) if oddslot_data else 0} 条")

    print("[Scraper] 正在抓取 OddsFilter 数据...")
    oddsfilter_data = scrape_oddsfilter()
    print(f"[Scraper] OddsFilter: 获取 {len(oddsfilter_data) if oddsfilter_data else 0} 条")

    if oddslot_data and oddsfilter_data:
        merged = cross_validate_odds(oddslot_data, oddsfilter_data)
        print(f"[Scraper] 交叉验证后: {len(merged)} 条")
        return merged
    elif oddslot_data:
        return oddslot_data
    elif oddsfilter_data:
        return oddsfilter_data
    else:
        print("[Scraper] ⚠️ 两个数据源都未获取到数据")
        return []
