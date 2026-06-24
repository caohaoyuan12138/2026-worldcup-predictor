# ⚽ 2026世界杯预测系统 v3.0

[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://2026-worldcup-predictor.streamlit.app)

融合 **Elo 等级分 + 泊松分布(Dixon-Coles) + 经济学模型 + 赔率市场** 的四维足球预测引擎。

## 功能

- 🎯 **实时预测**: 选择球队、输入赔率/让球盘口，秒级出结果
- 📊 **48场复盘**: 小组赛全面回测，偏差计算
- 🏆 **晋级图**: 12组出线形势 + 淘汰赛对阵树
- 🏅 **Elo排名**: 48队实时等级分

## 部署

### 一键部署到 Streamlit Cloud

1. Fork 这个仓库
2. 在 [Streamlit Cloud](https://streamlit.io/cloud) 选择仓库
3. 设置入口文件为 `streamlit_app.py`
4. 部署完成 ✅

### 本地运行

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

### Node.js 版 (本地完整版)

```bash
node server.mjs
# 浏览器打开 http://localhost:3000
```

## 模型

| 模型 | 权重 | 说明 |
|------|------|------|
| Elo等级分 | 25% | FIFA排名初始化 |
| 泊松分布 | 30% | Dixon-Coles修正 |
| 经济学 | 10% | GDP/人口/气候 |
| 赔率市场 | 35% | 含让球盘口 |

## 复盘

- 方向正确率: **68.8%** (33/48)
- 精确命中比分: **8场**
- 让球方向正确: **87.0%**
