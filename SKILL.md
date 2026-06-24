# ⚽ 2026世界杯预测系统 - Streamlit Skill

name: 2026-worldcup-predictor
version: 3.0.0
description: 2026世界杯预测系统 - Elo/泊松/经济学/赔率四维融合模型 + Streamlit前端
author: caohaoyuan12138
deploy: streamlit

## 能力说明

融合 Elo 等级分 + 泊松分布(Dixon-Coles) + 经济学模型 + 赔率市场 的四维足球预测引擎。

### 核心模型
- **Elo等级分**: 48队FIFA排名初始化，按已赛结果更新
- **泊松分布**: 含Dixon-Coles低比分修正+近10场+历史交锋
- **经济学模型**: GDP/人口/气候因子
- **赔率市场**: 手动输入赔率/让球盘口/隐含赔率

### 特殊功能
- 让球盘口联动λ（盘口深度影响预期进球）
- 末轮战意修正（出线形势→λ调整）
- 动态Dixon-Coles ρ（实力接近ρ=0.05, 悬殊ρ=0.01）
- 48场赔率复盘（68.8%方向准确率）
- 晋级图可视化（12组+淘汰赛对阵树）

## 部署方式

### Streamlit Cloud
[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://2026-worldcup-predictor.streamlit.app)

```bash
# 本地运行
pip install -r requirements.txt
streamlit run streamlit_app.py
```

### 传统Node.js部署
```bash
node server.mjs
# 浏览器打开 http://localhost:3000
```

## 数据来源
- 48队FIFA排名/ELO评分
- 72组历史交锋/479条近10场战绩
- 48场完整赔率数据(含让球盘口)
- 48国经济学数据

## 复盘结果
| 指标 | 值 |
|------|------|
| 方向正确率 | 68.8% (33/48) |
| 有赔率比赛 | 70.3% |
| 精确命中比分 | 8场 |
| 让球方向正确 | 87.0% |
