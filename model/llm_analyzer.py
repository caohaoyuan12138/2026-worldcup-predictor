"""
大模型推理增强模块

支持的LLM：
1. OpenAI API (GPT-4, GPT-3.5等)
2. DeepSeek API (国产，便宜)
3. Anthropic API (Claude)
4. 本地模型 (Ollama)
5. 自定义模型（任何兼容OpenAI格式的API）

用途：
- 分析战报内容，提取关键信息
- 生成详细推理过程
- 理解用户上传的Excel战报
"""

import requests
import json
from typing import Dict, List, Optional

# LLM配置
LLM_CONFIG = {
    "provider": "deepseek",  # openai / deepseek / anthropic / ollama / custom
    "api_key": None,  # 用户配置
    "model": "deepseek-chat",  # 模型名称
    "base_url": None,  # 自定义API地址（可选）
    "api_type": "openai",  # openai格式 / anthropic格式
    # 预设的API地址
    "preset_urls": {
        "openai": "https://api.openai.com/v1",
        "deepseek": "https://api.deepseek.com/v1",
        "anthropic": "https://api.anthropic.com/v1",
        "ollama": "http://localhost:11434/v1",
        # 其他常见模型
        "moonshot": "https://api.moonshot.cn/v1",  # Kimi
        "zhipu": "https://open.bigmodel.cn/api/paas/v4",  # 智谱GLM
        "qwen": "https://dashscope.aliyuncs.com/api/v1",  # 通义千问
        "baichuan": "https://api.baichuan-ai.com/v1",  # 百川
        "minimax": "https://api.minimax.chat/v1",  # MiniMax
        "siliconflow": "https://api.siliconflow.cn/v1",  # SiliconFlow
        "deepinfra": "https://api.deepinfra.com/v1/openai",  # DeepInfra
        "together": "https://api.together.xyz/v1",  # Together AI
        "groq": "https://api.groq.com/openai/v1",  # Groq
        "perplexity": "https://api.perplexity.ai",  # Perplexity
    }
}


def set_llm_config(provider: str, api_key: str, model: str = None, base_url: str = None, api_type: str = None):
    """
    设置LLM配置
    
    Args:
        provider: 提供商名称（openai/deepseek/anthropic/ollama/custom）
        api_key: API密钥
        model: 模型名称（可选）
        base_url: 自定义API地址（可选，用于custom或覆盖预设）
        api_type: API格式（openai/anthropic，可选）
    """
    LLM_CONFIG["provider"] = provider
    LLM_CONFIG["api_key"] = api_key
    
    if model:
        LLM_CONFIG["model"] = model
    
    if base_url:
        LLM_CONFIG["base_url"] = base_url
    
    if api_type:
        LLM_CONFIG["api_type"] = api_type
    
    # 如果是预设provider，自动设置api_type
    if provider == "anthropic":
        LLM_CONFIG["api_type"] = "anthropic"
    elif provider in ["openai", "deepseek", "ollama", "moonshot", "zhipu", "qwen", 
                       "baichuan", "minimax", "siliconflow", "deepinfra", "together", 
                       "groq", "perplexity", "custom"]:
        LLM_CONFIG["api_type"] = "openai"


def get_base_url() -> str:
    """获取API地址"""
    # 优先使用自定义地址
    if LLM_CONFIG["base_url"]:
        return LLM_CONFIG["base_url"]
    
    # 使用预设地址
    provider = LLM_CONFIG["provider"]
    return LLM_CONFIG["preset_urls"].get(provider, "")


def call_llm(prompt: str, system_prompt: str = None) -> str:
    """
    调用LLM API（支持所有兼容OpenAI格式的模型）
    
    Args:
        prompt: 用户输入
        system_prompt: 系统提示（可选）
    
    Returns:
        LLM生成的文本
    """
    if not LLM_CONFIG["api_key"]:
        return "⚠️ 未配置LLM API Key"
    
    api_type = LLM_CONFIG.get("api_type", "openai")
    
    # Anthropic API格式不同
    if api_type == "anthropic":
        return call_anthropic(prompt, system_prompt)
    
    # OpenAI兼容格式（支持所有兼容OpenAI的API）
    return call_openai_compatible(prompt, system_prompt)


def call_openai_compatible(prompt: str, system_prompt: str = None) -> str:
    """
    调用OpenAI兼容格式的API
    
    支持所有兼容OpenAI格式的模型：
    - OpenAI (GPT-4, GPT-3.5)
    - DeepSeek
    - Moonshot (Kimi)
    - 智谱GLM
    - 通义千问
    - 百川
    - MiniMax
    - SiliconFlow
    - DeepInfra
    - Together AI
    - Groq
    - Perplexity
    - Ollama (本地)
    - 任何自定义OpenAI兼容API
    
    Args:
        prompt: 用户输入
        system_prompt: 系统提示
    
    Returns:
        LLM生成的文本
    """
    api_key = LLM_CONFIG["api_key"]
    model = LLM_CONFIG["model"]
    base_url = get_base_url()
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 1000,
    }
    
    try:
        r = requests.post(
            f"{base_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=60
        )
        
        if r.status_code == 200:
            data = r.json()
            return data["choices"][0]["message"]["content"]
        else:
            error_msg = r.json().get("error", {}).get("message", r.text[:100])
            return f"⚠️ API错误: {r.status_code} - {error_msg}"
    
    except requests.exceptions.Timeout:
        return "⚠️ API超时"
    except Exception as e:
        return f"⚠️ 调用失败: {str(e)[:50]}"


def call_anthropic(prompt: str, system_prompt: str = None) -> str:
    """
    调用Anthropic API (Claude)
    
    Anthropic API格式与OpenAI不同：
    - 使用x-api-key而非Authorization
    - system参数单独传递
    - 使用messages数组
    
    Args:
        prompt: 用户输入
        system_prompt: 系统提示
    
    Returns:
        Claude生成的文本
    """
    api_key = LLM_CONFIG["api_key"]
    model = LLM_CONFIG["model"] or "claude-3-opus-20240229"
    
    headers = {
        "x-api-key": api_key,
        "Content-Type": "application/json",
        "anthropic-version": "2023-06-01",  # Anthropic API版本
    }
    
    payload = {
        "model": model,
        "max_tokens": 1000,
        "messages": [{"role": "user", "content": prompt}],
    }
    
    # Anthropic的system参数单独传递
    if system_prompt:
        payload["system"] = system_prompt
    
    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers=headers,
            json=payload,
            timeout=60
        )
        
        if r.status_code == 200:
            data = r.json()
            # Anthropic返回格式: content[0].text
            return data["content"][0]["text"]
        else:
            error_msg = r.json().get("error", {}).get("message", r.text[:100])
            return f"⚠️ Anthropic API错误: {r.status_code} - {error_msg}"
    
    except requests.exceptions.Timeout:
        return "⚠️ Anthropic API超时"
    except Exception as e:
        return f"⚠️ Anthropic调用失败: {str(e)[:50]}"


def generate_match_analysis(
    home_team: str,
    away_team: str,
    elo_data: Dict,
    odds_data: Dict,
    injury_data: Dict,
    news_data: List[str],
    report_data: Dict,
) -> str:
    """
    使用LLM生成比赛分析
    
    Args:
        home_team: 主队名
        away_team: 客队名
        elo_data: Elo评分数据
        odds_data: 赔率数据
        injury_data: 伤病数据
        news_data: 新闻列表
        report_data: 战报数据
    
    Returns:
        LLM生成的分析文本
    """
    
    # 构建系统提示
    system_prompt = """你是一位专业的足球分析师，擅长分析世界杯比赛。
请基于提供的数据，生成详细的比赛预测分析。

分析要点：
1. Elo评分对比：分析两队实力差距
2. 赔率分析：解读市场赔率隐含的概率
3. 伤病影响：评估关键球员缺席的影响
4. 战报解读：理解首轮比赛表现和战术特点
5. 综合预测：给出比分预测和置信度

输出格式：
- 使用简洁的中文
- 每个要点用"•"开头
- 最后给出明确的预测结论"""
    
    # 构建用户输入
    user_prompt = f"""
请分析以下世界杯比赛：

【比赛】{home_team} vs {away_team}

【Elo评分】
- {home_team}: {elo_data.get('home_rating', 1500)} (FIFA排名 #{elo_data.get('home_fifa_rank', '?')})
- {away_team}: {elo_data.get('away_rating', 1500)} (FIFA排名 #{elo_data.get('away_fifa_rank', '?')})
- Elo差值: {elo_data.get('diff', 0):+d}

【市场赔率】
- 主胜: {odds_data.get('average_home', '?')} (隐含概率 {odds_data.get('implied_home', '?')})
- 平局: {odds_data.get('average_draw', '?')} (隐含概率 {odds_data.get('implied_draw', '?')})
- 客胜: {odds_data.get('average_away', '?')} (隐含概率 {odds_data.get('implied_away', '?')})

【伤病情况】
- {home_team}: {injury_data.get('home_summary', '无重大伤病')}
- {away_team}: {injury_data.get('away_summary', '无重大伤病')}
- 影响评分: {home_team} {injury_data.get('home_impact', 0)}/10, {away_team} {injury_data.get('away_impact', 0)}/10

【首轮战报】
- {home_team}: {report_data.get('home_report', '暂无')}
- {away_team}: {report_data.get('away_report', '暂无')}

【最新新闻】
{chr(10).join(news_data[:3]) if news_data else '暂无最新新闻'}

请生成详细分析，并给出预测结论（预测比分和置信度）。
"""
    
    return call_llm(user_prompt, system_prompt)


def extract_key_info_from_report(report_text: str) -> Dict:
    """
    使用LLM从战报中提取关键信息
    
    Args:
        report_text: 战报文本
    
    Returns:
        {"injuries": [...], "tactics": "...", "performance": "..."}
    """
    
    system_prompt = """你是一位足球数据分析助手。
请从战报文本中提取关键信息，输出JSON格式。"""
    
    user_prompt = f"""
请从以下战报中提取关键信息：

战报文本：
{report_text}

请提取以下信息（JSON格式）：
- injuries: 伤病球员列表
- tactics: 战术特点
- performance: 首轮表现评价
- key_players: 关键球员
"""
    
    result = call_llm(user_prompt, system_prompt)
    
    # 尝试解析JSON
    try:
        # 提取JSON部分
        if "{" in result and "}" in result:
            json_str = result[result.find("{"):result.rfind("}")+1]
            return json.loads(json_str)
    except:
        pass
    
    return {"raw": result}


# ──────────────────────────────────────────────
#  使用示例
# ──────────────────────────────────────────────

if __name__ == "__main__":
    # 配置DeepSeek API（便宜，国产）
    # set_llm_config("deepseek", "your-api-key", "deepseek-chat")
    
    # 配置OpenAI API
    # set_llm_config("openai", "your-api-key", "gpt-4")
    
    # 测试数据
    elo_data = {
        "home_rating": 1840,
        "away_rating": 1550,
        "diff": 290,
        "home_fifa_rank": 4,
        "away_fifa_rank": 48,
    }
    
    odds_data = {
        "average_home": 1.11,
        "average_draw": 8.92,
        "average_away": 23.01,
        "implied_home": "89.2%",
        "implied_draw": "11.2%",
        "implied_away": "4.3%",
    }
    
    injury_data = {
        "home_summary": "Fermin Lopez骨折缺席",
        "away_summary": "无重大伤病",
        "home_impact": 4,
        "away_impact": 0,
    }
    
    news_data = [
        "Spain vs Saudi Arabia injury list released",
        "Lamine Yamal confirmed to start",
    ]
    
    report_data = {
        "home_report": "首轮0-0佛得角，27射无果，亚马尔回归首发",
        "away_report": "首轮1-1乌拉圭，顽强防守",
    }
    
    # 生成分析（需要配置API Key）
    print("=== 大模型推理增强示例 ===")
    print("需要配置LLM API Key才能运行")
    print("支持的LLM: OpenAI, DeepSeek, Ollama")
    
    # 如果配置了API Key，可以这样调用：
    # analysis = generate_match_analysis(
    #     "西班牙", "沙特阿拉伯",
    #     elo_data, odds_data, injury_data, news_data, report_data
    # )
    # print(analysis)