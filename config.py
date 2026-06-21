"""
全局配置文件 - 2026 美加墨世界杯比分预测模型
"""

# ==================== API 配置 ====================
# API keys are loaded from environment variables or Streamlit secrets
# Do NOT hardcode secrets in source code
OPENWEATHER_API_KEY = ""

# ==================== Elo 评分系统配置 ====================
ELO_INITIAL_RATING = 1500          # 初始评分
ELO_K_BASE = 20                   # K 值基础（小组赛）
ELO_K_MAX = 80                    # K 值上限
ELO_HOME_ADVANTAGE = 60            # 主场优势加分

# K 值按比赛阶段区分
ELO_K_GROUP_STAGE = 20             # 小组赛 K 值
ELO_K_ROUND_OF_16 = 30             # 1/16 决赛 K 值
ELO_K_QUARTER_FINAL = 35           # 1/4 决赛 K 值
ELO_K_SEMI_FINAL = 40              # 半决赛 K 值
ELO_K_FINAL = 50                   # 决赛 K 值

# FIFA 排名对应初始评分范围
ELO_TOP_10_RANGE = (1750, 1850)    # 前 10 名
ELO_MID_RANGE = (1550, 1650)       # 中游球队
ELO_BOTTOM_RANGE = (1400, 1450)    # 垫底球队

# 世界杯专项修正
ELO_CHAMPION_BONUS = 30            # 卫冕冠军加成
ELO_SEMI_FINAL_BONUS = 15         # 上届四强加成
ELO_FIRST_TIME_PENALTY = -25       # 首次参赛惩罚
ELO_CONTINENT_BONUS = 20           # 洲际加成（英格兰除外）

# 2026 美加墨三国东道主加成（不影响K值更新，只影响初始评分）
ELO_HOST_BONUS = 15                # 东道主身份加分
HOST_NATIONS = ["Mexico", "USA", "Canada"]  # 东道主国家（英文）

# 东道主球队 ID（从 teams.json 中识别）
HOST_TEAM_IDS = [1, 13, 5]         # 墨西哥/美国/加拿大（按 FIFA 编号）

# ==================== Dixon-Coles 泊松模型配置 ====================
DC_ALPHA = 0.3                     # 预期进球调节项权重
DC_BETA = 0.2                      # 预期进球调节项权重
DC_RHO_DEFAULT = -0.12             # 低比分修正参数（典型值）
DC_SIM_MATCHES = 10                # 近期比赛场次

# Elo 分差映射：每 100 分差 ≈ ±0.25 球
ELO_TO_GOAL_DIFF = 0.25 / 100

# 进球期望按阶段调整
AVG_GOALS_GROUP_STAGE = 1.3        # 小组赛基准场均进球
AVG_GOALS_KNOCKOUT = 1.0           # 淘汰赛基准场均进球（更保守）
AVG_GOALS_FINAL = 0.9              # 决赛基准场均进球

# 小组赛末轮动机因子
MOTIVATION_ELIMINATED = 0.7        # 已淘汰球队（战意低）
MOTIVATION_QUALIFIED = 0.85        # 已出线球队（可能轮换）
MOTIVATION_GROUP_DECIDER = 1.2     # 小组出线关键战（战意高）
MOTIVATION_NORMAL = 1.0            # 正常比赛

# ==================== 蒙特卡洛模拟配置 ====================
MC_SIMULATIONS = 10000             # 模拟次数
MC_SEED = None                     # 随机种子（None = 随机）

# ==================== 贝叶斯融合配置 ====================
# 不同阶段权重：(模型权重, 市场权重)
BAYESIAN_WEIGHTS = {
    "group_stage":    (0.70, 0.30),   # 小组赛：模型权重更高（市场噪音大）
    "round_of_16":    (0.55, 0.45),   # 1/16 决赛
    "quarter_final":  (0.50, 0.50),   # 1/4 决赛
    "semi_final":     (0.40, 0.60),   # 半决赛
    "final":          (0.35, 0.65),   # 决赛：市场深度足够
}

# ==================== 环境修正因子 ====================
# 跨国转场影响
INTER_NATIONAL_REST_PENALTY = -0.04    # 休息 < 4 天且跨国 > 1000km
DOMESTIC_LONG_DISTANCE_PENALTY = -0.03   # 美国境内东西海岸转场
ALTITUDE_MEXICO_CITY = 2240              # 墨西哥城海拔（米）
ALTITUDE_PENALTY_THRESHOLD = 2000        # 高海拔惩罚阈值
ALTITUDE_PENALTY = -0.06                 # 低海拔球队体能影响
ALTITUDE_TECH_PENALTY = -0.02            # 技术影响

# 天气因素
HIGH_TEMP_THRESHOLD = 30                # 高温阈值（°C）
HIGH_TEMP_TECH_PENALTY = -0.03          # 技术型球队
HIGH_TEMP_PHYSICAL_BONUS = 0.02         # 体能型球队
RAIN_SHOT_PENALTY = -0.02               # 控球型球队
RAIN_LONG_BONUS = 0.02                   # 长传冲吊型球队

# 2026 世界杯特有：强制补水机制（上下半场 30 分钟后）
WATER_BREAK_THRESHOLD_TEMP = 25         # 气温 > 25°C 触发补水
WATER_BREAK_BONUS = 0.03                # 补水后下半场表现提升

# 时区跨度影响（美加墨三国 6 小时时差）
TIMEZONE_PENALTY_THRESHOLD = 3           # 时差 > 3 小时
TIMEZONE_PENALTY = -0.03                 # 体能影响

# 人员伤停
STAR_PLAYER_MISSING = -0.07             # 核心球员（身价 > 8000 万欧）缺阵
GOALIE_MISSING = -0.05                  # 主力门将缺阵
MULTIPLE_MISSING = -0.10                # 3 名以上主力缺阵
RED_CARD_PENALTY = -0.15                # 红牌少赛一人
SUSPENSION_PENALTY = -0.12               # 停赛关键球员

# 战术风格克制
TACTICAL_PRESSURE_WEAK = 0.05           # 高位逼抢 vs 后场出球弱队
TACTICAL_COUNTER = 0.04                 # 防守反击 vs 控球压迫型
TACTICAL_SET_PIECE = 0.03               # 定位球强队 vs 防空弱队

# 裁判执法风格
REFEREE_CARD_STRICT = 0.03              # 严格裁判（黄牌多 → 影响进攻）
REFEREE_CARD_LENIENT = -0.02            # 宽松裁判

# 历史对战（H2H）
H2H_MAX_IMPACT = 0.08                   # H2H 最大影响 ±8%
H2H_MIN_SAMPLES = 3                      # 最少需要 3 次交手

# 阵容深度（替补实力影响）
BENCH_DEPTH_FACTOR = 0.05               # 阵容深度影响（淘汰赛后期疲劳修正）

# Elo 时间衰减
ELO_RECENCY_WEIGHT = 0.7                 # 近 3 场权重
ELO_HISTORY_WEIGHT = 0.3                # 远 7 场权重

# ==================== Kelly 仓位管理配置 ====================
KELLY_FRACTION = 0.5                   # 半凯利策略
KELLY_MAX_STAKE = 0.05                 # 单场最大仓位（总资金 5%）
KELLY_LOW_CONFIDENCE_MAX = 0.015        # C 级联赛/数据不足时上限

# ==================== 市场赔率配置 ====================
# 去 Vig 方法
VIG_REMOVAL_METHOD = "proportional"    # proportional / shin

# 实时赔率窗口
ODDS_WINDOW_START = 120                 # 赛前 2 小时（分钟）
ODDS_WINDOW_END = 15                   # 赛前 15 分钟
ODDS_CHANGE_THRESHOLD = 0.05            # 赔率变动 > 5% 触发权重调整
LARGE_BET_THRESHOLD = 0.08              # 偏差 ≥ 8% 为高价值

# 数据抓取源
ODDSLOT_URL = "https://oddslot.com/odds/"
ODDSFILTER_URL = "https://oddsfilter.com/"
FETCH_INTERVAL = 600                    # 抓取间隔（秒）= 10 分钟

# ==================== 数据源配置 ====================
# worldcup2026 数据源（GitHub 仓库，CSV 格式）
WORLDCUP2026_RAW = "https://raw.githubusercontent.com/rezarahiminia/worldcup2026/main"

# OpenWeatherMap 举办城市
HOST_CITIES = [
    "Mexico City", "New York/Newark", "Los Angeles", "Houston",
    "Miami", "Dallas", "Toronto", "Vancouver",
    "Boston", "Philadelphia", "Atlanta", "Chicago",
    "Denver", "Seattle", "San Francisco", "Monterrey",
    "Guadalajara", "Mexico City"
]
