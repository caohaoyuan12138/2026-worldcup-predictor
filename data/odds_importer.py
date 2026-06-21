"""
赔率 & 情报 Excel 导入器

功能：
1. 解析用户上传的 Excel/CSV 文件
2. 支持灵活列名映射（中英文）
3. 转换为 match_odds 字典供 app.py 使用

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
from typing import Dict, Optional


# 列名映射（小写 → 标准名）
COLUMN_MAP = {
    # ID
    "id": "id", "match_id": "id", "编号": "id", "比赛id": "id", "比赛编号": "id",
    "game_id": "id", "matchid": "id",
    # 日期
    "date": "date", "match_date": "date", "日期": "date",
    "datetime": "date", "date_time": "date", "比赛日期": "date",
    "time": "date", "match_time": "date", "比赛时间": "date",
    # 主队
    "home_team": "home_team", "home": "home_team", "主队": "home_team",
    "主队名": "home_team", "主队名称": "home_team",
    "home team": "home_team", "hometeam": "home_team",
    "team_a": "home_team", "team a": "home_team", "a队": "home_team",
    "team1": "home_team", "team 1": "home_team", "队伍1": "home_team",
    "队伍一": "home_team", "第一队": "home_team",
    # 客队
    "away_team": "away_team", "away": "away_team", "客队": "away_team",
    "客队名": "away_team", "客队名称": "away_team",
    "away team": "away_team", "awayteam": "away_team",
    "team_b": "away_team", "team b": "away_team", "b队": "away_team",
    "team2": "away_team", "team 2": "away_team", "队伍2": "away_team",
    "队伍二": "away_team", "第二队": "away_team",
    # 主胜赔率
    "odds_home": "odds_home", "oh": "odds_home", "home_odds": "odds_home",
    "主胜赔率": "odds_home", "主胜": "odds_home", "主胜赔": "odds_home",
    "主队胜赔率": "odds_home", "主队胜": "odds_home",
    "win": "odds_home", "1": "odds_home", "胜": "odds_home",
    "home_win": "odds_home", "home odds": "odds_home",
    # 平局赔率
    "odds_draw": "odds_draw", "od": "odds_draw", "draw_odds": "odds_draw",
    "平局赔率": "odds_draw", "平局": "odds_draw", "平局赔": "odds_draw",
    "draw": "odds_draw", "x": "odds_draw", "平": "odds_draw",
    # 客胜赔率
    "odds_away": "odds_away", "oa": "odds_away", "away_odds": "odds_away",
    "客胜赔率": "odds_away", "客胜": "odds_away", "客胜赔": "odds_away",
    "客队胜赔率": "odds_away", "客队胜": "odds_away",
    "lose": "odds_away", "2": "odds_away", "负": "odds_away",
    "away_win": "odds_away", "away odds": "odds_away",
    # 情报
    "intel": "intel", "intelligence": "intel", "情报": "intel",
    "备注": "intel", "intel_": "intel", "note": "intel",
    "战报": "intel", "分析": "intel", "report": "intel",
    "preview": "intel", "preview": "intel",
}


class OddsImporter:
    """赔率文件导入器"""

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

    def _normalize_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """列名标准化 + 映射到标准名"""
        df.columns = [str(c).strip() for c in df.columns]
        rename = {}
        for col in df.columns:
            key = col.lower().strip()
            if key in COLUMN_MAP:
                rename[col] = COLUMN_MAP[key]
        return df.rename(columns=rename)

    def _fuzzy_match_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """模糊匹配列名 — 包含关键词即匹配，返回重命名后的 DataFrame"""
        keywords_home = ["home", "主队", "主队名", "队伍1", "team1", "team a", "a队", "第一队"]
        keywords_away = ["away", "客队", "客队名", "队伍2", "team2", "team b", "b队", "第二队"]
        keywords_odds_h = ["oh", "home_odds", "主胜", "win", "胜", "1"]
        keywords_odds_d = ["od", "draw_odds", "平局", "draw", "平", "x"]
        keywords_odds_a = ["oa", "away_odds", "客胜", "lose", "负", "2"]
        keywords_intel = ["intel", "情报", "备注", "战报", "分析", "note"]

        rename = {}
        for col in df.columns:
            key = col.lower().strip()
            if "home_team" not in df.columns and "home_team" not in rename.values() and any(k in key for k in keywords_home):
                rename[col] = "home_team"
            elif "away_team" not in df.columns and "away_team" not in rename.values() and any(k in key for k in keywords_away):
                rename[col] = "away_team"
            elif "odds_home" not in df.columns and "odds_home" not in rename.values() and any(k in key for k in keywords_odds_h):
                rename[col] = "odds_home"
            elif "odds_draw" not in df.columns and "odds_draw" not in rename.values() and any(k in key for k in keywords_odds_d):
                rename[col] = "odds_draw"
            elif "odds_away" not in df.columns and "odds_away" not in rename.values() and any(k in key for k in keywords_odds_a):
                rename[col] = "odds_away"
            elif "intel" not in df.columns and "intel" not in rename.values() and any(k in key for k in keywords_intel):
                rename[col] = "intel"
        return df.rename(columns=rename)

    def to_match_odds_dict(self, df: pd.DataFrame) -> Dict[str, Dict]:
        """
        将 DataFrame 转换为 {match_id: {oh, od, oa, home, away, intel}} 字典

        Args:
            df: 解析后的 DataFrame

        Returns:
            字典，key 为比赛 ID 字符串
        """
        result = {}
        for _, row in df.iterrows():
            # 生成 ID
            mid = str(row.get("id", "")).strip()
            if not mid or mid == "nan":
                # 用 主队_客队 作为备选 key
                ht = str(row.get("home_team", "")).strip()
                at = str(row.get("away_team", "")).strip()
                mid = f"{ht}_{at}" if ht and at else ""

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

            result[mid] = {
                "oh": oh,
                "od": od,
                "oa": oa,
                "home": str(row.get("home_team", "")).strip(),
                "away": str(row.get("away_team", "")).strip(),
                "intel": str(row.get("intel", "")).strip() if not pd.isna(row.get("intel")) else "",
            }

        return result
