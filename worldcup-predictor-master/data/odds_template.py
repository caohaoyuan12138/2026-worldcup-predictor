"""
赔率导入模板生成器

生成标准 Excel 模板，用户填写后上传即可导入。
"""
import pandas as pd
import os


def generate_template(output_path: str = None,
                      schedule: list = None):
    """
    生成赔率导入模板

    Args:
        output_path: 输出文件路径
        schedule: 赛程列表，如果提供则预填比赛
    """
    if output_path is None:
        output_path = os.path.join(os.path.expanduser("~"), "Desktop", "世界杯赔率导入模板.xlsx")
    if schedule:
        rows = []
        for m in schedule:
            rows.append({
                "比赛ID": m.get("id", ""),
                "日期": m.get("date", ""),
                "主队": m.get("host_team_name", ""),
                "客队": m.get("guest_team_name", ""),
                "主队胜赔率": "",
                "平局赔率": "",
                "客队胜赔率": "",
                "情报": "",
            })
    else:
        # 示例数据
        rows = [
            {"比赛ID": "36", "日期": "2026-06-21", "主队": "突尼斯", "客队": "日本",
             "主队胜赔率": 3.5, "平局赔率": 3.3, "客队胜赔率": 2.1, "情报": ""},
            {"比赛ID": "37", "日期": "2026-06-22", "主队": "西班牙", "客队": "沙特阿拉伯",
             "主队胜赔率": 1.3, "平局赔率": 5.0, "客队胜赔率": 12.0, "情报": ""},
        ]

    df = pd.DataFrame(rows)

    # 使用 xlsxwriter 写入，添加说明
    with pd.ExcelWriter(output_path, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="赔率数据")

        # 获取 workbook 和 worksheet
        workbook = writer.book
        worksheet = writer.sheets["赔率数据"]

        # 添加说明工作表
        instructions = pd.DataFrame({
            "字段说明": [
                "比赛ID — 可选，用于精确匹配",
                "日期 — 比赛日期",
                "主队 — 主队中文名",
                "客队 — 客队中文名",
                "主队胜赔率 — 小数赔率（如 2.50）",
                "平局赔率 — 小数赔率（如 3.40）",
                "客队胜赔率 — 小数赔率（如 2.80）",
                "情报（可选）— 球队动态/伤病/阵容等",
            ]
        })
        instructions.to_excel(writer, index=False, sheet_name="填写说明")

        # 设置列宽
        worksheet.set_column("A:A", 10)
        worksheet.set_column("B:B", 14)
        worksheet.set_column("C:C", 12)
        worksheet.set_column("D:D", 12)
        worksheet.set_column("E:E", 14)
        worksheet.set_column("F:F", 12)
        worksheet.set_column("G:G", 14)
        worksheet.set_column("H:H", 40)

    return output_path


if __name__ == "__main__":
    path = generate_template("odds_template.xlsx")
    print(f"模板已生成: {os.path.abspath(path)}")
