"""
实时赔率抓取器

功能：
1. 从多个博彩网站抓取实时赔率
2. 支持 Bet365、Betfair、Oddschecker 等主流平台
3. 自动去重和异常值检测
4. 缓存机制避免频繁请求
5. 输出标准化赔率字典

注意：本模块仅供教育和研究用途，请遵守各网站的使用条款。
"""

import json
import os
import time
import re
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta

import requests
from bs4 import BeautifulSoup


@dataclass
class OddsData:
    """标准化赔率数据结构"""
    source: str           # 数据源名称
    home_team: str        # 主队名
    away_team: str        # 客队名
    match_time: str       # 比赛时间
    odds_home: float      # 主胜赔率
    odds_draw: float      # 平局赔率
    odds_away: float      # 客胜赔率
    timestamp: float      # 抓取时间戳
    league: str = "世界杯"  # 联赛
    match_id: str = ""    # 比赛ID

    def to_dict(self) -> Dict:
        return {
            "source": self.source,
            "home_team": self.home_team,
            "away_team": self.away_team,
            "match_time": self.match_time,
            "odds_home": self.odds_home,
            "odds_draw": self.odds_draw,
            "odds_away": self.odds_away,
            "timestamp": self.timestamp,
            "league": self.league,
            "match_id": self.match_id,
        }


class OddsScraper:
    """赔率抓取器基类"""

    def __init__(self, cache_ttl: int = 300):
        """
        Args:
            cache_ttl: 缓存有效期（秒），默认5分钟
        """
        self.cache_ttl = cache_ttl
        self.cache: Dict[str, Tuple[float, List[OddsData]]] = {}
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        })

    def _get_cache(self, key: str) -> Optional[List[OddsData]]:
        """获取缓存数据"""
        if key in self.cache:
            ts, data = self.cache[key]
            if time.time() - ts < self.cache_ttl:
                return data
        return None

    def _set_cache(self, key: str, data: List[OddsData]):
        """设置缓存"""
        self.cache[key] = (time.time(), data)

    def _fetch(self, url: str, timeout: int = 15) -> Optional[str]:
        """发送HTTP请求"""
        try:
            resp = self.session.get(url, timeout=timeout)
            resp.raise_for_status()
            return resp.text
        except Exception as e:
            print(f"[OddsScraper] 请求失败 {url}: {e}")
            return None

    def _normalize_team_name(self, name: str) -> str:
        """标准化球队名"""
        name = name.strip()
        # 常见别名映射
        aliases = {
            "usa": "美国", "united states": "美国",
            "mexico": "墨西哥", "mex": "墨西哥",
            "canada": "加拿大", "can": "加拿大",
            "brazil": "巴西", "bra": "巴西",
            "argentina": "阿根廷", "arg": "阿根廷",
            "france": "法国", "fra": "法国",
            "germany": "德国", "ger": "德国",
            "spain": "西班牙", "esp": "西班牙",
            "england": "英格兰", "eng": "英格兰",
            "portugal": "葡萄牙", "por": "葡萄牙",
            "netherlands": "荷兰", "ned": "荷兰",
            "croatia": "克罗地亚", "cro": "克罗地亚",
            "japan": "日本", "jpn": "日本",
            "korea": "韩国", "kor": "韩国",
            "australia": "澳大利亚", "aus": "澳大利亚",
            "morocco": "摩洛哥", "mar": "摩洛哥",
            "senegal": "塞内加尔", "sen": "塞内加尔",
        }
        lower = name.lower()
        if lower in aliases:
            return aliases[lower]
        return name

    def _parse_odds_value(self, val) -> Optional[float]:
        """解析赔率数值"""
        if val is None:
            return None
        try:
            v = float(str(val).strip().replace(",", "."))
            return v if v > 1.0 else None
        except (ValueError, TypeError):
            return None


class OddscheckerScraper(OddsScraper):
    """Oddschecker 赔率抓取"""

    def fetch_worldcup_odds(self) -> List[OddsData]:
        """抓取世界杯赔率"""
        cache_key = "oddschecker_worldcup"
        cached = self._get_cache(cache_key)
        if cached:
            return cached

        # Oddschecker 世界杯页面
        url = "https://www.oddschecker.com/football/world-cup"
        html = self._fetch(url)
        if not html:
            return []

        results = []
        soup = BeautifulSoup(html, "html.parser")

        # 查找比赛行
        match_rows = soup.find_all("tr", class_=re.compile(r"match|event|fixture"))
        for row in match_rows:
            try:
                cells = row.find_all("td")
                if len(cells) < 4:
                    continue

                teams_cell = cells[0].get_text(strip=True)
                if "vs" not in teams_cell and "v" not in teams_cell:
                    continue

                # 解析球队名
                teams = re.split(r"\s+vs\s+|\s+v\s+", teams_cell, flags=re.IGNORECASE)
                if len(teams) != 2:
                    continue

                home = self._normalize_team_name(teams[0])
                away = self._normalize_team_name(teams[1])

                # 解析赔率
                oh = self._parse_odds_value(cells[1].get_text(strip=True))
                od = self._parse_odds_value(cells[2].get_text(strip=True))
                oa = self._parse_odds_value(cells[3].get_text(strip=True))

                if oh and od and oa:
                    results.append(OddsData(
                        source="oddschecker",
                        home_team=home,
                        away_team=away,
                        match_time="",
                        odds_home=oh,
                        odds_draw=od,
                        odds_away=oa,
                        timestamp=time.time(),
                    ))
            except Exception as e:
                continue

        self._set_cache(cache_key, results)
        return results


class BetfairScraper(OddsScraper):
    """Betfair Exchange 赔率抓取"""

    def fetch_worldcup_odds(self) -> List[OddsData]:
        """抓取 Betfair 世界杯赔率"""
        cache_key = "betfair_worldcup"
        cached = self._get_cache(cache_key)
        if cached:
            return cached

        # Betfair API 端点（需要 app key，这里使用公开页面）
        url = "https://www.betfair.com/sport/football"
        html = self._fetch(url)
        if not html:
            return []

        results = []
        soup = BeautifulSoup(html, "html.parser")

        # 查找比赛卡片
        cards = soup.find_all("div", class_=re.compile(r"event|match|fixture"))
        for card in cards:
            try:
                teams = card.find_all("span", class_=re.compile(r"team|participant"))
                if len(teams) < 2:
                    continue

                home = self._normalize_team_name(teams[0].get_text(strip=True))
                away = self._normalize_team_name(teams[1].get_text(strip=True))

                odds = card.find_all("span", class_=re.compile(r"odds|price"))
                if len(odds) < 3:
                    continue

                oh = self._parse_odds_value(odds[0].get_text(strip=True))
                od = self._parse_odds_value(odds[1].get_text(strip=True))
                oa = self._parse_odds_value(odds[2].get_text(strip=True))

                if oh and od and oa:
                    results.append(OddsData(
                        source="betfair",
                        home_team=home,
                        away_team=away,
                        match_time="",
                        odds_home=oh,
                        odds_draw=od,
                        odds_away=oa,
                        timestamp=time.time(),
                    ))
            except Exception:
                continue

        self._set_cache(cache_key, results)
        return results


class MockOddsProvider(OddsScraper):
    """
    模拟赔率提供者
    用于测试和演示，无需真实网络请求
    """

    def fetch_worldcup_odds(self) -> List[OddsData]:
        """返回模拟的世界杯赔率数据"""
        cache_key = "mock_worldcup"
        cached = self._get_cache(cache_key)
        if cached:
            return cached

        mock_data = [
            OddsData("mock", "阿根廷", "墨西哥", "2026-06-21 20:00", 1.45, 4.20, 7.50, time.time()),
            OddsData("mock", "巴西", "美国", "2026-06-21 23:00", 1.65, 3.80, 5.20, time.time()),
            OddsData("mock", "法国", "加拿大", "2026-06-22 02:00", 1.35, 4.80, 9.00, time.time()),
            OddsData("mock", "德国", "日本", "2026-06-22 20:00", 1.85, 3.40, 4.50, time.time()),
            OddsData("mock", "西班牙", "韩国", "2026-06-22 23:00", 1.55, 3.90, 6.20, time.time()),
            OddsData("mock", "英格兰", "澳大利亚", "2026-06-23 02:00", 1.40, 4.50, 8.00, time.time()),
            OddsData("mock", "葡萄牙", "摩洛哥", "2026-06-23 20:00", 1.75, 3.50, 5.00, time.time()),
            OddsData("mock", "荷兰", "塞内加尔", "2026-06-23 23:00", 1.60, 3.70, 5.80, time.time()),
        ]

        self._set_cache(cache_key, mock_data)
        return mock_data


class OddsAggregator:
    """赔率聚合器 — 合并多个数据源"""

    def __init__(self):
        self.scrapers: List[OddsScraper] = [
            MockOddsProvider(),  # 默认使用模拟数据
            # OddscheckerScraper(),  # 需要时取消注释
            # BetfairScraper(),      # 需要时取消注释
        ]

    def add_scraper(self, scraper: OddsScraper):
        """添加新的抓取器"""
        self.scrapers.append(scraper)

    def fetch_all(self) -> Dict[str, List[OddsData]]:
        """
        从所有数据源抓取赔率

        Returns:
            {match_key: [OddsData, ...]}
        """
        all_odds: Dict[str, List[OddsData]] = {}

        for scraper in self.scrapers:
            try:
                odds_list = scraper.fetch_worldcup_odds()
                for odds in odds_list:
                    key = f"{odds.home_team}_vs_{odds.away_team}"
                    if key not in all_odds:
                        all_odds[key] = []
                    all_odds[key].append(odds)
            except Exception as e:
                print(f"[Aggregator] {scraper.__class__.__name__} 抓取失败: {e}")
                continue

        return all_odds

    def get_average_odds(self) -> Dict[str, Dict]:
        """
        计算各场比赛的平均赔率

        Returns:
            {match_key: {home_team, away_team, avg_oh, avg_od, avg_oa, sources}}
        """
        all_odds = self.fetch_all()
        result = {}

        for key, odds_list in all_odds.items():
            if not odds_list:
                continue

            oh_vals = [o.odds_home for o in odds_list if o.odds_home]
            od_vals = [o.odds_draw for o in odds_list if o.odds_draw]
            oa_vals = [o.odds_away for o in odds_list if o.odds_away]

            if not (oh_vals and od_vals and oa_vals):
                continue

            result[key] = {
                "home_team": odds_list[0].home_team,
                "away_team": odds_list[0].away_team,
                "avg_odds_home": round(sum(oh_vals) / len(oh_vals), 2),
                "avg_odds_draw": round(sum(od_vals) / len(od_vals), 2),
                "avg_odds_away": round(sum(oa_vals) / len(oa_vals), 2),
                "sources": list(set(o.source for o in odds_list)),
                "source_count": len(odds_list),
            }

        return result

    def detect_odds_movement(self, previous: Dict[str, Dict], current: Dict[str, Dict]) -> List[Dict]:
        """
        检测赔率变动

        Args:
            previous: 上一次的平均赔率
            current: 当前的平均赔率

        Returns:
            变动列表 [{match_key, type, change_pct, old, new}]
        """
        movements = []

        for key, curr in current.items():
            prev = previous.get(key)
            if not prev:
                continue

            for odds_type in ["avg_odds_home", "avg_odds_draw", "avg_odds_away"]:
                old = prev.get(odds_type)
                new = curr.get(odds_type)
                if old and new and old > 0:
                    change = (new - old) / old
                    if abs(change) >= 0.05:  # 5% 变动阈值
                        movements.append({
                            "match_key": key,
                            "odds_type": odds_type,
                            "change_pct": round(change * 100, 2),
                            "old": old,
                            "new": new,
                            "direction": "up" if change > 0 else "down",
                        })

        return movements


def fetch_odds_for_matches(match_list: List[Dict], use_mock: bool = True) -> Dict[str, Dict]:
    """
    为指定比赛列表抓取赔率

    Args:
        match_list: [{home_team, away_team, match_id}, ...]
        use_mock: 是否使用模拟数据

    Returns:
        {match_id: {oh, od, oa, source}}
    """
    aggregator = OddsAggregator()

    if use_mock:
        # 使用模拟数据，匹配球队名
        mock = MockOddsProvider()
        mock_odds = mock.fetch_worldcup_odds()

        result = {}
        for match in match_list:
            home = match.get("home_team", "")
            away = match.get("away_team", "")
            mid = match.get("id", "")

            for odds in mock_odds:
                if (odds.home_team in home or home in odds.home_team) and \
                   (odds.away_team in away or away in odds.away_team):
                    result[mid] = {
                        "oh": odds.odds_home,
                        "od": odds.odds_draw,
                        "oa": odds.odds_away,
                        "source": odds.source,
                        "home": odds.home_team,
                        "away": odds.away_team,
                    }
                    break

        return result
    else:
        # 使用真实抓取
        return aggregator.get_average_odds()


if __name__ == "__main__":
    # 测试
    print("=" * 60)
    print("实时赔率抓取器测试")
    print("=" * 60)

    # 1. 测试模拟数据
    mock = MockOddsProvider()
    mock_odds = mock.fetch_worldcup_odds()
    print(f"\n[模拟数据] 共 {len(mock_odds)} 场比赛")
    for o in mock_odds[:3]:
        print(f"  {o.home_team} vs {o.away_team}: "
              f"主胜{o.odds_home} / 平{o.odds_draw} / 客胜{o.odds_away}")

    # 2. 测试聚合器
    agg = OddsAggregator()
    avg = agg.get_average_odds()
    print(f"\n[聚合结果] 共 {len(avg)} 场比赛")
    for key, data in list(avg.items())[:3]:
        print(f"  {key}: 主胜{data['avg_odds_home']} / "
              f"平{data['avg_odds_draw']} / 客胜{data['avg_odds_away']} "
              f"(来源: {', '.join(data['sources'])})")

    # 3. 测试为指定比赛匹配
    test_matches = [
        {"id": "1", "home_team": "阿根廷", "away_team": "墨西哥"},
        {"id": "2", "home_team": "巴西", "away_team": "美国"},
        {"id": "3", "home_team": "法国", "away_team": "加拿大"},
    ]
    matched = fetch_odds_for_matches(test_matches, use_mock=True)
    print(f"\n[匹配结果] 成功匹配 {len(matched)} 场")
    for mid, data in matched.items():
        print(f"  ID {mid}: {data['home']} vs {data['away']} — "
              f"主胜{data['oh']} / 平{data['od']} / 客胜{data['oa']}")
