"""
赔率 & 情报 Excel 导入器 — 智能识别版

功能：
1. 解析用户上传的 Excel/CSV 文件
2. 支持灵活列名映射（中英文）
3. 智能识别表格结构 — 无需固定模板
4. 支持单次上传比赛日部分比赛（自动匹配赛程）
5. 转换为 match_odds 字典供 app.py 使用

支持的列名（不区分大小写）：
  - 比赛ID / id / match_id / 编号
  - 日期 / date / match_date / match_datetime
  - 主队 / home / home_team / 主队名 / 主队名称
  - 客队 / away / away_team / 客队名 / 客队名称
  - 主胜赔率 / odds_home / oh / home_odds / 主胜
  - 平局赔率 / odds_draw / od / draw_odds / 平局
  - 客胜赔率 / odds_away / oa / away_odds / 客胜
  - 情报 / intel / intelligence / 备注 / note
"""

import pandas as pd
import io
import re
from typing import Dict, Optional, List, Tuple
import json
import os

# 列名映射（小写 → 标准名）
COLUMN_MAP = {
    # ID
    "id": "id", "match_id": "id", "编号": "id", "比赛id": "id", "比赛编号": "id",
    "game_id": "id", "matchid": "id", "赛事id": "id", "场次": "id",
    # 日期
    "date": "date", "match_date": "date", "日期": "date",
    "datetime": "date", "date_time": "date", "比赛日期": "date",
    "time": "date", "match_time": "date", "比赛时间": "date", "开赛时间": "date",
    # 主队
    "home_team": "home_team", "home": "home_team", "主队": "home_team",
    "主队名": "home_team", "主队名称": "home_team",
    "home team": "home_team", "hometeam": "home_team",
    "team_a": "home_team", "team a": "home_team", "a队": "home_team",
    "team1": "home_team", "team 1": "home_team", "队伍1": "home_team",
    "队伍一": "home_team", "第一队": "home_team", "主场": "home_team",
    # 客队
    "away_team": "away_team", "away": "away_team", "客队": "away_team",
    "客队名": "away_team", "客队名称": "away_team",
    "away team": "away_team", "awayteam": "away_team",
    "team_b": "away_team", "team b": "away_team", "b队": "away_team",
    "team2": "away_team", "team 2": "away_team", "队伍2": "away_team",
    "队伍二": "away_team", "第二队": "away_team", "客场": "away_team",
    # 主胜赔率
    "odds_home": "odds_home", "oh": "odds_home", "home_odds": "odds_home",
    "主胜赔率": "odds_home", "主胜": "odds_home", "主胜赔": "odds_home",
    "主队胜赔率": "odds_home", "主队胜": "odds_home",
    "win": "odds_home", "1": "odds_home", "胜": "odds_home",
    "home_win": "odds_home", "home odds": "odds_home",
    "主": "odds_home", "h": "odds_home",
    # 平局赔率
    "odds_draw": "odds_draw", "od": "odds_draw", "draw_odds": "odds_draw",
    "平局赔率": "odds_draw", "平局": "odds_draw", "平局赔": "odds_draw",
    "draw": "odds_draw", "x": "odds_draw", "平": "odds_draw",
    "d": "odds_draw",
    # 客胜赔率
    "odds_away": "odds_away", "oa": "odds_away", "away_odds": "odds_away",
    "客胜赔率": "odds_away", "客胜": "odds_away", "客胜赔": "odds_away",
    "客队胜赔率": "odds_away", "客队胜": "odds_away",
    "lose": "odds_away", "2": "odds_away", "负": "odds_away",
    "away_win": "odds_away", "away odds": "odds_away",
    "客": "odds_away", "a": "odds_away",
    # 情报
    "intel": "intel", "intelligence": "intel", "情报": "intel",
    "备注": "intel", "intel_": "intel", "note": "intel",
    "战报": "intel", "分析": "intel", "report": "intel",
    "preview": "intel", "情报信息": "intel", "情报备注": "intel",
}

# 智能识别关键词（用于模糊匹配）
KEYWORDS = {
    "home_team": ["home", "主队", "主队名", "队伍1", "team1", "team a", "a队", "第一队", "主场"],
    "away_team": ["away", "客队", "客队名", "队伍2", "team2", "team b", "b队", "第二队", "客场"],
    "odds_home": ["home_odds", "主胜", "win", "胜", "1", "oh", "主", "h"],
    "odds_draw": ["draw_odds", "平局", "draw", "平", "x", "od", "d"],
    "odds_away": ["away_odds", "客胜", "lose", "负", "2", "oa", "客", "a"],
    "intel": ["intel", "情报", "备注", "战报", "分析", "note", "report"],
    "id": ["id", "编号", "match_id", "game_id", "场次"],
    "date": ["date", "日期", "时间", "time", "datetime", "match_date", "match_time", "开赛"],
}


class OddsImporter:
    """赔率文件导入器 — 智能识别版"""

    def __init__(self, schedule_path: str = None):
        """
        Args:
            schedule_path: 本地赛程 JSON 路径，用于智能匹配比赛
        """
        self.schedule = None
        if schedule_path and os.path.exists(schedule_path):
            with open(schedule_path, "r", encoding="utf-8") as f:
                self.schedule = json.load(f)
        else:
            # 尝试默认路径
            default_path = os.path.join(os.path.dirname(__file__), "..", "data_local", "schedule.json")
            if os.path.exists(default_path):
                with open(default_path, "r", encoding="utf-8") as f:
                    self.schedule = json.load(f)

    def parse_file(self, uploaded_file) -> Optional[pd.DataFrame]:
        """
        解析上传的文件为 DataFrame

        Args:
            uploaded_file: Streamlit UploadedFile 对象 或文件路径

        Returns:
            pd.DataFrame 或 None
        """
        try:
            # 支持文件路径（str）和 Streamlit UploadedFile
            if isinstance(uploaded_file, str):
                name = uploaded_file.lower()
                if name.endswith(".csv"):
                    df = pd.read_csv(uploaded_file, encoding="utf-8-sig")
                else:
                    df = pd.read_excel(uploaded_file)
            else:
                name = (uploaded_file.name or "").lower()
                if name.endswith(".csv"):
                    df = pd.read_csv(uploaded_file, encoding="utf-8-sig")
                else:
                    try:
                        import openpyxl
                    except ImportError:
                        raise ImportError("需要安装 openpyxl: pip install openpyxl")
                    # 将 UploadedFile 保存到临时位置再读取
                    import tempfile
                    with tempfile.NamedTemporaryFile(suffix=name[-5:], delete=False) as tmp:
                        tmp.write(uploaded_file.read())
                        tmp_path = tmp.name
                    df = pd.read_excel(tmp_path)
        except Exception as e:
            raise ValueError(f"文件读取失败: {str(e)[:100]}")

        if df.empty:
            return None

        # 智能识别表格结构
        df = self._smart_detect_structure(df)

        # 列名标准化 + 映射
        df = self._normalize_columns(df)

        # 检查必要列
        required = ["home_team", "away_team"]
        missing = [r for r in required if r not in df.columns]
        if missing:
            # 尝试模糊匹配
            df = self._fuzzy_match_columns(df)
            missing = [r for r in required if r not in df.columns]
            if missing:
                raise ValueError(
                    f"缺少必要列: {missing}。请确保文件包含「主队」和「客队」列。\n"
                    f"当前列名: {list(df.columns)}"
                )

        return df

    def _smart_detect_structure(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        智能识别表格结构：
        1. 检测是否有标题行（前1-3行非数据行）
        2. 检测是否有合并表头
        3. 检测数据起始行
        4. 清理空行/空列
        """
        # 保存原始列名用于调试
        original_cols = list(df.columns)

        # 策略1: 如果第一行看起来像列名（包含关键词），但当前列名是数字
        # 则把第一行提升为列名
        if all(isinstance(c, (int, float)) for c in original_cols):
            # 检查第一行是否包含文本
            first_row = df.iloc[0].astype(str).tolist()
            has_keywords = any(
                any(kw in cell.lower() for kw in ["队", "odds", "赔率", "胜", "平", "负", "date", "id"])
                for cell in first_row
            )
            if has_keywords:
                df.columns = first_row
                df = df.iloc[1:].reset_index(drop=True)
                return df

        # 策略2: 检测前3行是否有大量空值（可能是标题行）
        for skip_rows in range(1, min(4, len(df))):
            row = df.iloc[skip_rows - 1]
            non_null = row.notna().sum()
            if non_null <= 2:  # 如果一行只有1-2个非空值，可能是标题
                # 检查下一行是否像数据行
                if skip_rows < len(df):
                    next_row = df.iloc[skip_rows]
                    next_non_null = next_row.notna().sum()
                    if next_non_null >= 3:
                        df = df.iloc[skip_rows:].reset_index(drop=True)
                        break

        # 策略3: 清理完全为空的行和列
        df = df.dropna(how="all").dropna(axis=1, how="all").reset_index(drop=True)

        # 策略4: 如果列名是 Unnamed，尝试从第一行推断
        unnamed_cols = [c for c in df.columns if str(c).startswith("Unnamed")]
        if len(unnamed_cols) > 0 and len(unnamed_cols) >= len(df.columns) * 0.5:
            first_row = df.iloc[0].astype(str).tolist()
            if any(len(str(c)) > 1 for c in first_row):
                df.columns = first_row
                df = df.iloc[1:].reset_index(drop=True)

        return df

    def _normalize_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """列名标准化 + 映射到标准名"""
        df.columns = [str(c).strip() for c in df.columns]
        rename = {}
        for col in df.columns:
            key = col.lower().strip()
            # 去除特殊字符
            key_clean = re.sub(r'[^\w\u4e00-\u9fff]', '', key)
            if key in COLUMN_MAP:
                rename[col] = COLUMN_MAP[key]
            elif key_clean in COLUMN_MAP:
                rename[col] = COLUMN_MAP[key_clean]
        return df.rename(columns=rename)

    def _fuzzy_match_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """模糊匹配列名 — 包含关键词即匹配，返回重命名后的 DataFrame"""
        rename = {}
        assigned = set()

        for col in df.columns:
            key = col.lower().strip()
            key_clean = re.sub(r'[^\w\u4e00-\u9fff]', '', key)

            for std_name, keywords in KEYWORDS.items():
                if std_name in assigned:
                    continue
                if any(kw in key or kw in key_clean for kw in keywords):
                    rename[col] = std_name
                    assigned.add(std_name)
                    break

        return df.rename(columns=rename)

    def _match_to_schedule(self, home: str, away: str, date: str = None) -> Optional[str]:
        """
        根据球队名和日期匹配到赛程中的比赛ID

        Args:
            home: 主队名
            away: 客队名
            date: 日期（可选，格式 YYYY-MM-DD）

        Returns:
            比赛ID 或 None
        """
        if not self.schedule:
            return None

        best_match = None
        best_score = 0

        for m in self.schedule:
            sched_home = m.get("host_team_name", "")
            sched_away = m.get("guest_team_name", "")
            sched_date = m.get("date", "")

            # 计算匹配分数
            score = 0

            # 主队匹配
            if home == sched_home:
                score += 10
            elif home in sched_home or sched_home in home:
                score += 5

            # 客队匹配
            if away == sched_away:
                score += 10
            elif away in sched_away or sched_away in away:
                score += 5

            # 日期匹配（如果提供）
            if date and sched_date:
                try:
                    # 简化比较，只比较日期部分
                    d1 = str(date)[:10]
                    d2 = str(sched_date)[:10]
                    if d1 == d2:
                        score += 8
                    elif d1[:7] == d2[:7]:  # 同月
                        score += 3
                except Exception:
                    pass

            if score > best_score:
                best_score = score
                best_match = m.get("id")

        # 最低匹配阈值
        if best_score >= 10:
            return str(best_match) if best_match else None
        return None

    def to_match_odds_dict(self, df: pd.DataFrame, auto_match: bool = True) -> Dict[str, Dict]:
        """
        将 DataFrame 转换为 {match_id: {oh, od, oa, home, away, intel}} 字典

        Args:
            df: 解析后的 DataFrame
            auto_match: 是否自动匹配赛程ID

        Returns:
            字典，key 为比赛 ID 字符串
        """
        result = {}
        unmatched = []

        for idx, row in df.iterrows():
            # 获取球队名
            ht = str(row.get("home_team", "")).strip()
            at = str(row.get("away_team", "")).strip()

            if not ht or not at:
                continue

            # 生成或匹配 ID
            mid = str(row.get("id", "")).strip()
            date = str(row.get("date", "")).strip()

            if not mid or mid == "nan" or mid == "None":
                if auto_match and self.schedule:
                    mid = self._match_to_schedule(ht, at, date if date != "nan" else None)

                if not mid:
                    # 用 主队_客队_日期 作为备选 key
                    date_part = str(date)[:10] if date and date != "nan" else ""
                    mid = f"{ht}_{at}_{date_part}" if date_part else f"{ht}_{at}"

            if not mid:
                continue

            # 解析赔率
            def parse_odds(val):
                if pd.isna(val):
                    return None
                try:
                    v = float(val)
                    return v if v > 1.0 else None
                except (ValueError, TypeError):
                    return None

            oh = parse_odds(row.get("odds_home"))
            od = parse_odds(row.get("odds_draw"))
            oa = parse_odds(row.get("odds_away"))

            intel_val = row.get("intel", "")
            intel_str = str(intel_val).strip() if not pd.isna(intel_val) else ""

            result[mid] = {
                "oh": oh,
                "od": od,
                "oa": oa,
                "home": ht,
                "away": at,
                "intel": intel_str,
                "date": date if date != "nan" else "",
                "source_row": idx,
            }

        return result

    def merge_with_existing(self, new_odds: Dict[str, Dict], existing_odds: Dict[str, Dict] = None) -> Dict[str, Dict]:
        """
        将新导入的赔率与已有赔率合并
        支持增量更新：只更新上传的比赛，保留其他比赛

        Args:
            new_odds: 新导入的赔率字典
            existing_odds: 已有的赔率字典（从 session_state 获取）

        Returns:
            合并后的赔率字典
        """
        if existing_odds is None:
            existing_odds = {}

        merged = dict(existing_odds)
        updated_count = 0
        added_count = 0

        for mid, data in new_odds.items():
            if mid in merged:
                # 更新已有比赛
                merged[mid].update(data)
                updated_count += 1
            else:
                # 新增比赛
                merged[mid] = data
                added_count += 1

        return merged, updated_count, added_count

    def get_import_summary(self, odds_dict: Dict[str, Dict]) -> Dict:
        """
        获取导入数据的摘要信息

        Returns:
            {
                "total": 总比赛数,
                "with_odds": 有赔率的场数,
                "with_intel": 有情报的场数,
                "teams": 涉及球队列表,
                "dates": 涉及日期列表,
            }
        """
        total = len(odds_dict)
        with_odds = sum(1 for d in odds_dict.values() if d.get("oh") or d.get("od") or d.get("oa"))
        with_intel = sum(1 for d in odds_dict.values() if d.get("intel"))
        teams = set()
        dates = set()

        for d in odds_dict.values():
            if d.get("home"):
                teams.add(d["home"])
            if d.get("away"):
                teams.add(d["away"])
            if d.get("date") and d["date"] != "nan":
                dates.add(str(d["date"])[:10])

        return {
            "total": total,
            "with_odds": with_odds,
            "with_intel": with_intel,
            "teams": sorted(teams),
            "dates": sorted(dates),
        }


def create_sample_excel(filepath: str, n_matches: int = 5):
    """
    创建示例 Excel 文件，展示支持的格式

    Args:
        filepath: 输出文件路径
        n_matches: 比赛数量
    """
    sample_data = {
        "主队": ["阿根廷", "巴西", "法国", "德国", "西班牙"][:n_matches],
        "客队": ["墨西哥", "美国", "加拿大", "日本", "韩国"][:n_matches],
        "主胜赔率": [1.85, 1.65, 1.45, 2.10, 1.75][:n_matches],
        "平局赔率": [3.40, 3.60, 4.20, 3.20, 3.50][:n_matches],
        "客胜赔率": [4.50, 5.20, 7.00, 3.40, 4.80][:n_matches],
        "日期": ["2026-06-21", "2026-06-21", "2026-06-22", "2026-06-22", "2026-06-23"][:n_matches],
        "情报": ["", "", "", "", ""][:n_matches],
    }
    df = pd.DataFrame(sample_data)
    df.to_excel(filepath, index=False)
    return filepath


def create_sample_csv(filepath: str, n_matches: int = 5):
    """创建示例 CSV 文件"""
    sample_data = {
        "Home Team": ["Argentina", "Brazil", "France", "Germany", "Spain"][:n_matches],
        "Away Team": ["Mexico", "USA", "Canada", "Japan", "Korea"][:n_matches],
        "1": [1.85, 1.65, 1.45, 2.10, 1.75][:n_matches],
        "X": [3.40, 3.60, 4.20, 3.20, 3.50][:n_matches],
        "2": [4.50, 5.20, 7.00, 3.40, 4.80][:n_matches],
        "Date": ["2026-06-21", "2026-06-21", "2026-06-22", "2026-06-22", "2026-06-23"][:n_matches],
    }
    df = pd.DataFrame(sample_data)
    df.to_csv(filepath, index=False, encoding="utf-8-sig")
    return filepath
