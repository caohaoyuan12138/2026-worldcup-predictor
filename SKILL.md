---
name: worldcup-predictor
version: 1.0.0
description: "2026世界杯比分预测模型。当用户需要预测世界杯比赛比分、分析球队实力、获取实时赔率、查看伤病名单时使用。支持Elo评分、泊松模型、蒙特卡洛模拟、贝叶斯融合、大模型推理增强。"
metadata:
  requires:
    bins: ["python3"]
    packages: ["numpy", "scipy", "pandas", "requests", "feedparser"]
---

# 2026世界杯比分预测模型

四层融合架构：**Elo评分 + Dixon-Coles泊松 + 蒙特卡洛模拟 + 贝叶斯融合**

## 核心能力

| 能力 | 说明 |
|------|------|
| **Elo评分** | 48支球队实力评分，含FIFA排名 |
| **泊松模型** | Dixon-Coles调整，计算期望进球λ |
| **蒙特卡洛** | 50000次模拟，生成比分概率分布 |
| **贝叶斯融合** | 模型预测 + 市场赔率融合 |
| **实时数据** | BSD API赔率、伤病、阵容 |
| **新闻分析** | RSS新闻、WorldCupWiki伤病名单 |
| **大模型推理** | DeepSeek/OpenAI/Ollama增强分析 |

## 命令

### 1. 预测单场比赛

```bash
python3 -m worldcup_predictor predict \
  --home "西班牙" \
  --away "沙特阿拉伯" \
  --odds-home 1.83 \
  --odds-draw 4.00 \
  --odds-away 3.00 \
  [--use-llm] \
  [--llm-provider deepseek] \
  [--llm-key YOUR_API_KEY]
```

输出：
```json
{
  "match": "西班牙 vs 沙特阿拉伯",
  "elo_diff": 290,
  "lambda_home": 2.13,
  "lambda_away": 0.82,
  "mc_probs": {"home_win": 0.72, "draw": 0.18, "away_win": 0.10},
  "posterior_probs": {"home_win": 0.70, "draw": 0.22, "away_win": 0.08},
  "top_scores": [{"score": "2-0", "probability": 12.27}, {"score": "1-0", "probability": 11.5}],
  "prediction": "主胜（西班牙）",
  "confidence": 0.70
}
```

### 2. 批量预测多场比赛

```bash
python3 -m worldcup_predictor batch \
  --file matches.xlsx \
  [--output predictions.xlsx]
```

输入文件格式（Excel）：
| 主队 | 客队 | 主胜赔率 | 平局赔率 | 客胜赔率 | 主队战报 | 客队战报 |
|------|------|---------|---------|---------|---------|---------|
| 西班牙 | 沙特阿拉伯 | 1.83 | 4.00 | 3.00 | 27射无果 | 逼平乌拉圭 |

### 3. 获取实时数据

```bash
# 获取赔率
python3 -m worldcup_predictor odds \
  --home "西班牙" \
  --away "沙特阿拉伯"

# 获取伤病名单
python3 -m worldcup_predictor injuries \
  --team "西班牙"

# 获取新闻
python3 -m worldcup_predictor news \
  --team "西班牙"
```

### 4. 查看球队信息

```bash
python3 -m worldcup_predictor team \
  --name "西班牙"
```

输出：
```json
{
  "name": "西班牙",
  "elo": 1840,
  "fifa_ranking": 4,
  "group": "H组",
  "injuries": [{"player": "Fermin Lopez", "status": "out"}],
  "news": ["Spain vs Saudi Arabia injury list released"]
}
```

### 5. 启动Web服务

```bash
python3 -m worldcup_predictor serve \
  --port 8501
```

访问 `http://localhost:8501` 使用Streamlit界面。

## API接口（供其他AI调用）

### HTTP API

```bash
# 启动API服务
python3 -m worldcup_predictor api --port 8000
```

**端点：**

| 端点 | 方法 | 说明 |
|------|------|------|
| `/predict` | POST | 预测比赛 |
| `/teams` | GET | 获取球队列表 |
| `/team/{name}` | GET | 获取球队信息 |
| `/odds/{home}/{away}` | GET | 获取实时赔率 |
| `/injuries/{team}` | GET | 获取伤病名单 |
| `/news/{team}` | GET | 获取新闻 |

**示例：**
```bash
curl -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d '{"home":"西班牙","away":"沙特阿拉伯","odds_home":1.83,"odds_draw":4.00,"odds_away":3.00}'
```

### Python API

```python
from worldcup_predictor import Predictor

# 创建预测器
predictor = Predictor(
    bsd_api_key="YOUR_BSD_KEY",  # 可选
    llm_provider="deepseek",     # 可选
    llm_api_key="YOUR_LLM_KEY"   # 可选
)

# 预测比赛
result = predictor.predict(
    home="西班牙",
    away="沙特阿拉伯",
    odds_home=1.83,
    odds_draw=4.00,
    odds_away=3.00,
    use_llm=True  # 使用大模型增强
)

print(result.prediction)  # "主胜（西班牙）"
print(result.confidence)  # 0.70
print(result.top_scores)  # [{"score": "2-0", "probability": 12.27}]
```

## 配置

### BSD API Key（实时数据）

免费获取：https://sports.bzzoiro.com/register/

```bash
export BSD_API_KEY="your-api-key"
```

### LLM API Key（大模型推理）

**DeepSeek（推荐，便宜）：**
```bash
export LLM_PROVIDER="deepseek"
export LLM_API_KEY="your-deepseek-key"
```

**OpenAI：**
```bash
export LLM_PROVIDER="openai"
export LLM_API_KEY="your-openai-key"
```

**Ollama（本地免费）：**
```bash
# 先安装Ollama
ollama pull llama3
export LLM_PROVIDER="ollama"
```

## 安装

### 方式1：pip安装

```bash
pip install worldcup-predictor
```

### 方式2：从源码安装

```bash
git clone https://github.com/caohaoyuan12138/worldcup-predictor.git
cd worldcup-predictor
pip install -r requirements.txt
pip install -e .
```

### 方式3：Docker部署

```bash
docker pull worldcup-predictor:latest
docker run -p 8501:8501 -p 8000:8000 worldcup-predictor
```

## 数据来源

| 数据 | 来源 | 更新频率 |
|------|------|---------|
| Elo评分 | 本地teams.json | 预设 |
| 赔率 | BSD API | 实时 |
| 伤病 | WorldCupWiki | 每日 |
| 新闻 | Sports Mole RSS | 实时 |
| 阵容 | BSD API | 赛前1小时 |

## 输出格式

### 预测结果

```json
{
  "match": "主队 vs 客队",
  "elo_diff": 290,
  "elo_probs": {"home_win": 0.65, "draw": 0.25, "away_win": 0.10},
  "lambda_home": 2.13,
  "lambda_away": 0.82,
  "mc_probs": {"home_win": 0.72, "draw": 0.18, "away_win": 0.10},
  "market_probs": {"home_win": 0.48, "draw": 0.22, "away_win": 0.30},
  "posterior_probs": {"home_win": 0.70, "draw": 0.22, "away_win": 0.08},
  "top_scores": [
    {"score": "2-0", "probability": 12.27},
    {"score": "1-0", "probability": 11.5},
    {"score": "2-1", "probability": 9.8}
  ],
  "prediction": "主胜（主队名）",
  "confidence": 0.70,
  "llm_analysis": "大模型生成的深度分析（可选）"
}
```

## 错误处理

| 错误 | 说明 | 处理 |
|------|------|------|
| `球队未找到` | 球队名不在48支参赛队中 | 使用标准球队名 |
| `API Key无效` | BSD/LLM API Key错误 | 检查配置 |
| `赔率数据缺失` | 无法获取实时赔率 | 使用手动输入赔率 |

## 示例场景

### 场景1：预测单场比赛

用户："预测西班牙vs沙特阿拉伯的比分"

AI调用：
```bash
python3 -m worldcup_predictor predict --home "西班牙" --away "沙特阿拉伯"
```

### 场景2：获取实时赔率

用户："西班牙vs沙特阿拉伯的赔率是多少？"

AI调用：
```bash
python3 -m worldcup_predictor odds --home "西班牙" --away "沙特阿拉伯"
```

### 场景3：查看伤病名单

用户："西班牙有哪些伤病球员？"

AI调用：
```bash
python3 -m worldcup_predictor injuries --team "西班牙"
```

### 场景4：批量预测

用户上传Excel文件，AI调用批量预测：
```bash
python3 -m worldcup_predictor batch --file matches.xlsx --output predictions.xlsx
```

## 注意事项

1. **球队名称**：使用标准中文或英文名称（如"西班牙"或"Spain"）
2. **赔率输入**：如果未配置BSD API，需要手动输入赔率
3. **大模型**：LLM增强需要配置API Key，否则仅使用模型预测
4. **实时数据**：伤病/阵容数据赛前1小时才更新