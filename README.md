# ⚽ 2026世界杯预测系统 v3.0

[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://2026-worldcup-predictor.streamlit.app)

融合 **Elo 等级分 + 泊松分布(Dixon-Coles) + 经济学模型 + 赔率市场** 的四维足球预测引擎。

## 界面展示

Streamlit 版展示与 Node.js 本地版**完全一致的前端界面**，包含：
- 📊 **总览** — 小组积分榜、比分分布
- 📈 **预测** — 自定义预测（含赔率/让球盘口）+ 预测全部未赛
- 🏆 **出线形势** — 10000次蒙特卡洛出线模拟
- ⚙️ **球队数据** — 48队实力参数编辑
- 📋 **比赛管理** — 添加/查看比赛结果
- 🏅 **Elo排名** — 实时等级分排行榜
- 🏆 **晋级图** — 淘汰赛对阵树
- 📊 **复盘分析** — 模型准确率回测
- 📜 **预测日志** — 每次预测的完整记录（含 AI 推理报告）
- 🔧 **模型配置** — 权重参数调整

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

Node 版额外支持：
- 🧠 **AI 推理裁判** — 接入 deepseek-v4-flash 大模型生成比赛研判报告
- 🎯 **自定义预测日志持久化** — 含 AI 报告全文保存

### Streamlit 本地运行

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

## 模型

| 模型 | 权重 | 说明 |
|------|------|------|
| Elo等级分 | 25% | FIFA排名初始化，每场动态更新 |
| 泊松分布 | 30% | Dixon-Coles低比分修正 |
| 经济学 | 10% | GDP/人口/气候因子 |
| 赔率市场 | 35% | 含让球盘口调整 |

## 技术栈

- **Node.js 版**: `server.mjs` + `model/engine.mjs` + `public/` 前端
- **Streamlit 版**: `streamlit_app.py` — 嵌入 Node.js 前端 UI，Python 引擎
- **数据库**: `db/worldcup.json` — 48队/72组交锋/1494场历史数据

## 复盘

- 方向正确率: **68.8%** (33/48)
- 精确命中比分: **8场**
- 让球方向正确: **87.0%**

## 项目结构

```
football/
├── streamlit_app.py          # Streamlit 入口（嵌入前端）
├── server.mjs                # Node.js 后端服务器
├── model/
│   ├── engine.mjs            # 融合预测引擎
│   └── tactics.mjs           # 战术分析引擎
├── public/
│   ├── index.html            # 前端页面
│   ├── app.js                # 前端逻辑
│   └── style.css             # 前端样式
├── db/
│   └── worldcup.json         # 数据库
├── prediction_log.jsonl      # 预测日志
├── requirements.txt
└── README.md
```
