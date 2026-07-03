#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
⚽ 足球预测 - AI 推理裁判

从 Node.js 后端接收因子向量, 组装 Prompt, 调用大模型进行推理分析
"""

import requests
import json
import sys
import os

# Agnes AI API 配置 (从环境变量读取, 由 Node.js 传入)
API_KEY = os.environ.get('SENSENOVA_KEY', os.environ.get('AGNES_API_KEY', 'sk-6FqQ8pmPLUuouABzdDihaUkUG730w7ADT6zxySDodQUFuGGe'))
API_BASE = os.environ.get('SENSENOVA_BASE', os.environ.get('AGNES_BASE_URL', 'https://apihub.agnes-ai.com/v1'))
MODEL = os.environ.get('REASONING_MODEL', 'agnes-2.0-flash')

def build_prompt(factors):
    """组装推理 Prompt"""
    h = factors.get('home', '?')
    a = factors.get('away', '?')
    elo = factors.get('elo', {})
    poisson = factors.get('poisson', {})
    economic = factors.get('economic', {})
    odds = factors.get('odds', {})
    h2h = factors.get('headToHead', {})
    standings = factors.get('standings', {})
    momentum = factors.get('momentum', {})
    dq = factors.get('dongqiudi', {})
    is_knockout = factors.get('matchType') == '世界杯淘汰赛'

    # 懂球帝数据格式化
    def fmt_team_dq(dq_data, label):
        if not dq_data:
            return f"- {label}: 无数据"
        return f"""- {label}:
  - 进球/助攻/射门/射正: {dq_data.get('goals', '?')}/{dq_data.get('assists', '?')}/{dq_data.get('shots', '?')}/{dq_data.get('onTarget', '?')}
  - 射正率/传球成功率: {dq_data.get('shotAccuracy', '?')} / {dq_data.get('passAccuracy', '?')}
  - 抢断/拦截/解围: {dq_data.get('tackles', '?')}/{dq_data.get('interceptions', '?')}/{dq_data.get('clearances', '?')}
  - 评分/身价: {dq_data.get('rating', '?')} / {dq_data.get('marketValue', '?')}"""

    # 懂球帝数据章节
    dq_section = ""
    if dq.get('home') or dq.get('away'):
        dq_section = f"""
## 7. 懂球帝球队实战数据（世界杯实时统计）
{fmt_team_dq(dq.get('home'), h)}
{fmt_team_dq(dq.get('away'), a)}

### 射手榜
- {h} Top射手: {dq.get('homeScorers', '无数据')}
- {a} Top射手: {dq.get('awayScorers', '无数据')}

### 助攻榜
- {h} Top助攻: {dq.get('homeAssisters', '无数据')}
- {a} Top助攻: {dq.get('awayAssisters', '无数据')}
"""

    # 让球盘口描述
    handicap_val = odds.get('handicap')
    try:
        handicap_val = float(handicap_val) if handicap_val is not None else None
    except (ValueError, TypeError):
        handicap_val = None
    
    if handicap_val is not None:
        if handicap_val > 0:
            handicap_desc = f"+{handicap_val}（主队让{handicap_val}球，主队是强方/让球方，客队是弱方/受让方）"
        elif handicap_val < 0:
            handicap_desc = f"{handicap_val}（客队让{abs(handicap_val)}球，客队是强方/让球方，主队是弱方/受让方）"
        else:
            handicap_desc = "0（平手盘，无让球）"
    else:
        handicap_desc = "未提供"

    # 比赛性质与战意
    if is_knockout:
        match_context = f"""## 4. 比赛性质与战意
### ⚠️ 这是淘汰赛（输球即淘汰）
- 无小组赛积分，无净胜球优势，90分钟（含伤停补时）定胜负
- 90分钟打平 → 30分钟加时赛（分上下半场各15分钟）
- 加时赛仍平 → 点球大战（5球制，进球多者胜，若仍平则进入突然死亡一轮一轮踢）
- 淘汰赛特性：双方更保守，防守优先，进球预期降低，平局概率上升（进入加时/点球）
- 战意：双方都必须赢，无退路，但强队可能更耐心，弱队可能蹲坑反击"""
    else:
        match_context = f"""## 4. 晋级形势与战意
### 小组赛形势
- 主队：{standings.get('home', '信息不足')}
- 客队：{standings.get('away', '信息不足')}"""

    # 特别注意（淘汰赛额外规则）
    knockout_note = """
5. **淘汰赛特殊规则**：
   - 这是淘汰赛，90分钟（含伤停补时）定胜负，进球数倾向于比小组赛更少（防守更保守）
   - 如果90分钟打平，进入30分钟加时赛（加时赛进球也算进比分）
   - 加时赛仍平，进入点球大战（5球制）
   - 在比分预测中，需要区分"90分钟内比分"和"最终含加时/点球的晋级结果"
   - 建议：Top5比分主要预测90分钟（含伤停补时）的结果，但需额外说明加时赛/点球的可能性
   - 淘汰赛中，1-0、0-1、0-0（进入加时）的概率比小组赛更高""" if is_knockout else ""

    prompt = f"""# 角色设定
你是一名世界顶级的足球比赛分析专家，拥有20年实战研判经验。你的特长是综合多维度信息进行逻辑推演，最终给出有理有据的比赛结论。

# 输入信息

## 1. 基础数据
- 对阵双方：{h} vs {a}
- 比赛性质：{factors.get('matchType', '世界杯小组赛')}
- 比赛时间：{factors.get('matchDate', '待定')}

## 2. 数学模型输出（我的底层模型计算结果）
- Elo评分：主队 {elo.get('home', '?')}，客队 {elo.get('away', '?')}，差值 {elo.get('diff', '?')}
- 泊松模型预期进球：主队 {poisson.get('lambdaHome', '?')}，客队 {poisson.get('lambdaAway', '?')}
- 经济学模型：主队 GDP ${economic.get('gdpHome', '?')}，客队 GDP ${economic.get('gdpAway', '?')}，东道主 {economic.get('host', '无')}
- **原始比分概率Top5**：{poisson.get('top5', 'N/A')}
- 融合模型胜率：主胜 {factors.get('fusionWinPct', '?')}%，平 {factors.get('fusionDrawPct', '?')}%，客胜 {factors.get('fusionAwayPct', '?')}%

## 3. 赔率与市场信息
- 胜平负赔率：主胜 {odds.get('home', '未提供')}，平 {odds.get('draw', '未提供')}，客胜 {odds.get('away', '未提供')}
- 让球盘口数值：{handicap_desc}
- 赔率隐含概率：主胜 {odds.get('impliedHome', '?')}%，平 {odds.get('impliedDraw', '?')}%，客胜 {odds.get('impliedAway', '?')}%

### ⚠️ 让球方向铁律（必须严格遵守，这是亚洲盘核心规则）
**让球盘口数值 > 0 = 主队让球 = 主队是强方（让球方），客队是弱方（受让方）**
- 例：盘口 +1 = 主队让1球 = 主队强，主队需赢2球以上才算赢盘
**让球盘口数值 < 0 = 客队让球 = 客队是强方（让球方），主队是弱方（受让方）**
- 例：盘口 -1 = 客队让1球 = 客队强，主队受让1球，主队输1球以内算赢盘
{match_context}

## 5. 历史交锋
- 总交手：{h2h.get('total', '无数据')} 次
- 主队胜 {h2h.get('homeWins', '?')}，平 {h2h.get('draws', '?')}，客队胜 {h2h.get('awayWins', '?')}

## 6. 近10场状态
- 主队：{momentum.get('home', '信息不足')}
- 客队：{momentum.get('away', '信息不足')}
{dqSection(dq, h, a) if False else dq_section}
---

# 推理分析要求

## 第一步：因子重要性排序
评估以上因子中，对本场比赛影响最大的3个因子，说明理由。

## 第二步：进攻/防守效率推演
- 主队最可能的进球方式
- 客队最可能的进球方式
- 双方各自最容易被对手利用的防守漏洞

## 第三步：比赛节奏与进球分布预测
- 全场进球数的合理区间及理由
- 上半场/下半场的进球分布预判
- 是否存在"特定时间段"进球高发

## 第四步：比分概率重校准
基于推理，对数学模型输出的原始比分概率进行调整，给出：
- **调整后的Top 5比分及概率**
- 每个比分对应的发生场景描述

## 第五步：最终结论
- 最可能比分
- 次可能比分
- 进球数倾向：大/小
- 胜负倾向：胜/平/负

---

# 特别注意
1. 不要和稀泥。如果原始模型输出全是1-0、0-0，要明确指出"数学模型过于保守"，基于赔率和战意给出修正方向。
2. 比分可以出现2-1、3-1等，但要给出合理场景。
3. 如果数据不足，明确指出并给出假设。
4. 以赔率市场作为重要参考。如果赔率显示主胜概率>55%，请强制在Top3中至少包含一个主队进2球及以上的比分。
{knockout_note}
# 输出格式
用以下结构化格式：

# 🏆 比赛研判报告：{h} vs {a}

## 一、核心因子分析
...

## 二、战术推演与节奏预判
...

## 三、比分概率重校准
| 排名 | 比分 | 调整后概率 | 发生场景 |
|------|------|-----------|---------|
| 1 | X-X | XX% | ... |

## 四、最终结论
- **推荐比分**：X-X
- **进球数倾向**：
- **胜负倾向**：
- **核心逻辑一句话总结**：
"""
    return prompt


def call_model(prompt):
    """调用 deepseek-v4-flash (通过 sensenova)"""
    url = f"{API_BASE}/chat/completions"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": "你是一个专业的足球比赛分析专家，擅长多因子推理分析。"},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.3,
        "max_tokens": 4096,
        "stream": False
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        return data['choices'][0]['message']['content']
    except Exception as e:
        return f"❌ AI 推理调用失败: {str(e)}"


def main():
    # 从 stdin 读取 JSON 因子向量
    try:
        factors = json.loads(sys.stdin.read())
    except Exception as e:
        print(json.dumps({"error": f"无法解析输入: {e}"}))
        sys.exit(1)

    prompt = build_prompt(factors)
    result = call_model(prompt)

    # 输出 JSON 给 Node.js
    output = {
        "prompt_length": len(prompt),
        "report": result,
        "factors_used": list(factors.keys())
    }
    print(json.dumps(output, ensure_ascii=False))


if __name__ == "__main__":
    main()
