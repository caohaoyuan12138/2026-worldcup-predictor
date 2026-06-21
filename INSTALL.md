# 安装指南

## 方式1：pip安装（推荐）

```bash
pip install worldcup-predictor
```

## 方式2：从GitHub安装

```bash
pip install git+https://github.com/caohaoyuan12138/worldcup-predictor.git
```

## 方式3：从源码安装

```bash
git clone https://github.com/caohaoyuan12138/worldcup-predictor.git
cd worldcup-predictor
pip install -r requirements.txt
pip install -e .
```

## 方式4：Docker部署

```bash
docker build -t worldcup-predictor .
docker run -p 8501:8501 -p 8000:8000 worldcup-predictor
```

---

## 配置

### BSD API Key（实时数据）

免费获取：https://sports.bzzoiro.com/register/

```bash
export BSD_API_KEY="your-api-key"
```

或在Python中配置：
```python
from worldcup_predictor import set_bsd_api_key
set_bsd_api_key("your-api-key")
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

**Anthropic（Claude）：**
```bash
export LLM_PROVIDER="anthropic"
export LLM_API_KEY="your-anthropic-key"
export LLM_MODEL="claude-3-opus-20240229"
```

**Ollama（本地免费）：**
```bash
ollama pull llama3
export LLM_PROVIDER="ollama"
```

---

## 使用示例

### CLI命令行

```bash
# 预测比赛
worldcup-predictor predict --home "西班牙" --away "沙特阿拉伯"

# 获取实时赔率
worldcup-predictor odds --home "西班牙" --away "沙特阿拉伯"

# 获取伤病名单
worldcup-predictor injuries --team "西班牙"

# 获取新闻
worldcup-predictor news --team "西班牙"

# 查看球队信息
worldcup-predictor team --name "西班牙"
```

### Python API

```python
from worldcup_predictor import Predictor

# 创建预测器
predictor = Predictor(
    bsd_api_key="your-bsd-key",  # 可选
    llm_provider="deepseek",     # 可选
    llm_api_key="your-llm-key"   # 可选
)

# 预测比赛
result = predictor.predict(
    home="西班牙",
    away="沙特阿拉伯",
    odds_home=1.83,
    odds_draw=4.00,
    odds_away=3.00,
    use_llm=True
)

print(result.prediction)  # "主胜（西班牙）"
print(result.confidence)  # 0.70
print(result.top_scores)  # [{"score": "2-0", "probability": 12.27}]
```

### HTTP API

```bash
# 启动API服务
worldcup-predictor api --port 8000

# 调用API
curl -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d '{"home":"西班牙","away":"沙特阿拉伯","odds_home":1.83,"odds_draw":4.00,"odds_away":3.00}'
```

---

## 其他AI工具集成

### OpenClaude / Claude

将 `SKILL.md` 放入Claude的skills目录，Claude会自动识别并调用。

### Cursor / VS Code

在项目根目录创建 `.cursorrules`：
```
当用户需要预测世界杯比赛时，调用 worldcup-predictor CLI：
worldcup-predictor predict --home "主队" --away "客队"
```

### 其他AI工具

参考 `SKILL.md` 文档，将CLI命令集成到你的AI工具中。

---

## 依赖

| 包 | 版本 | 说明 |
|---|------|------|
| numpy | >=1.24.0 | 数值计算 |
| scipy | >=1.10.0 | 科学计算 |
| pandas | >=2.0.0 | 数据处理 |
| requests | >=2.28.0 | HTTP请求 |
| feedparser | >=6.0.10 | RSS解析 |
| streamlit | >=1.28.0 | Web界面（可选） |

---

## 测试安装

```bash
# 测试CLI
worldcup-predictor teams

# 测试Python API
python -c "from worldcup_predictor import Predictor; p = Predictor(); print(p.list_teams())"
```

---

## 常见问题

### Q: 球队名未找到？
A: 使用标准中文或英文名称，如"西班牙"或"Spain"

### Q: API Key无效？
A: 检查BSD/LLM API Key是否正确配置

### Q: 赔率数据缺失？
A: 配置BSD API Key，或手动输入赔率

### Q: 大模型不工作？
A: 配置LLM API Key，并设置正确的provider