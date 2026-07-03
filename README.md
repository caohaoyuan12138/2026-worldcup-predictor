# ⚽ 2026世界杯预测系统 v3.0

> 2026美加墨世界杯 · 四维融合预测引擎 · 淘汰赛专项优化

融合 **Elo等级分 + 泊松分布(Dixon-Coles) + 经济学模型 + 赔率市场** 的四维足球预测引擎。

## ✨ v3.0 新增功能

| 功能 | 说明 |
|------|------|
| 🔄 实时Elo更新 | 每场比赛后自动更新球队Elo评分，含大胜过热限制 |
| 📊 战力反哺 | 基于近5场实际比赛结果，EMA混合更新 attackBase/defenseBase |
| 🎯 淘汰赛专项引擎 | 独立参数体系：低进球(×0.85)、高平率(30%)、点球模拟(15%) |
| ⚖️ 动态模型权重 | 根据比赛阶段和模型近期表现自动调整 Elo/Poisson/Market 权重 |
| ⚠️ 冷门检测 | 7维风险评估（热门概率/平率/模型分歧/排名赔率矛盾/低λ/历史交锋/战意差） |
| 📈 置信度校准 | 100分制，基于模型一致性、赔率质量、数据完整度 |
| 🔍 赔率验证 | 隐含概率检查、方向检测、质量评分、去水计算 |
| 📋 赛后回测 | 方向准确率 + Top3比分命中率 + 逐场明细 |
| 📝 预测日志 | 每次预测完整持久化到 JSONL |

## 部署

### Streamlit Cloud（一键部署）

[![Deploy to Streamlit](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://streamlit.io/cloud)

1. Fork 这个仓库
2. 在 [Streamlit Cloud](https://streamlit.io/cloud) 选择仓库
3. 入口文件: `streamlit_app.py`
4. 部署完成 ✅

### Node.js 本地版（完整功能）

```bash
node server.mjs
# 浏览器打开 http://localhost:3000
```

### Streamlit 本地运行

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

## 模型

| 模型 | 权重(默认) | 说明 |
|------|-----------|------|
| Elo等级分 | 18-25% | FIFA排名初始化，每场动态更新，含大胜过热限制 |
| 泊松分布 | 28-32% | Dixon-Coles低比分修正 + 对数正态采样 + 近10场动量 |
| 经济学 | 9-10% | GDP/人口/气候因子 |
| 赔率市场 | 35-44% | 含让球盘口调整 + 质量验证 + 去水计算 |

## 技术栈

- **Node.js 版**: `server.mjs` + `model/engine.mjs` + `public/` 前端
- **Streamlit 版**: `streamlit_app.py` — 嵌入 Node.js 前端 UI，Python 完整引擎
- **数据库**: `db/worldcup.json` — 48队/12组/78场已赛/32场淘汰赛
- **新引擎**: `model/knockout_engine.mjs` + `model/elo_updater.mjs` + `model/odds_validator.mjs`

## 复盘

| 指标 | 值 |
|------|------|
| 方向正确率 | 68.8% (33/48) |
| 精确命中比分 | 8场 |
| 让球方向正确 | 87.0% |
| Top3比分命中 | ~25% |

## 项目结构

```
football/
├── streamlit_app.py          # Streamlit 入口（完整Python引擎）
├── server.mjs                # Node.js 后端服务器
├── integrated_engine.mjs     # 统一CLI入口（集成所有优化）
├── model/
│   ├── engine.mjs            # 融合预测引擎（Node.js版）
│   ├── knockout_engine.mjs   # 淘汰赛专项引擎（v3.0新增）
│   ├── elo_updater.mjs       # Elo实时更新+战力反哺（v3.0新增）
│   ├── odds_validator.mjs    # 赔率验证器（v3.0新增）
│   ├── tactics.mjs           # 战术分析引擎
│   └── ...                   # Python引擎模块
├── public/
│   ├── index.html            # 前端页面（10个Tab）
│   ├── app.js                # 前端逻辑
│   └── style.css             # 前端样式
├── db/
│   └── worldcup.json         # 数据库
├── predictions/              # 预测结果存储
├── prediction_log.jsonl      # 预测日志
├── requirements.txt
└── README.md
```

## CLI 用法

```bash
# 单场预测
node integrated_engine.mjs predict 西班牙 奥地利 --odds 1.19 5.15 10.50 -h -1

# 预测所有剩余淘汰赛
node integrated_engine.mjs all

# 更新球队Elo和战力
node integrated_engine.mjs update

# 回测历史淘汰赛
node integrated_engine.mjs backtest
```
