"""
天气API模块 - 获取比赛场地实时环境信息

使用OpenWeatherMap API获取：
- 实时气温
- 海拔信息
- 时差信息
- 天气状况（雨天/晴天）

比赛场地：
- 墨西哥城（海拔2240m）
- 洛杉矶
- 纽约
- 休斯顿
- 迈阿密
- 多伦多
- 温哥华
等16个举办城市
"""

import requests
import json
from typing import Dict, Optional
from datetime import datetime
import pytz

# OpenWeatherMap API配置
# 免费API Key（用户可自行申请：https://openweathermap.org/api）
OPENWEATHER_API_KEY = ""  # 需要配置

# 2026世界杯举办城市信息
HOST_CITIES_INFO = {
    "Mexico City": {
        "country": "Mexico",
        "timezone": "America/Mexico_City",
        "altitude": 2240,  # 高海拔！
        "coordinates": {"lat": 19.4326, "lon": -99.1332},
    },
    "Los Angeles": {
        "country": "USA",
        "timezone": "America/Los_Angeles",
        "altitude": 93,
        "coordinates": {"lat": 34.0522, "lon": -118.2437},
    },
    "New York/Newark": {
        "country": "USA",
        "timezone": "America/New_York",
        "altitude": 10,
        "coordinates": {"lat": 40.7128, "lon": -74.0060},
    },
    "Houston": {
        "country": "USA",
        "timezone": "America/Chicago",
        "altitude": 15,
        "coordinates": {"lat": 29.7604, "lon": -95.3698},
    },
    "Miami": {
        "country": "USA",
        "timezone": "America/New_York",
        "altitude": 2,
        "coordinates": {"lat": 25.7617, "lon": -80.1918},
    },
    "Dallas": {
        "country": "USA",
        "timezone": "America/Chicago",
        "altitude": 137,
        "coordinates": {"lat": 32.7767, "lon": -96.7970},
    },
    "Toronto": {
        "country": "Canada",
        "timezone": "America/Toronto",
        "altitude": 76,
        "coordinates": {"lat": 43.6532, "lon": -79.3832},
    },
    "Vancouver": {
        "country": "Canada",
        "timezone": "America/Vancouver",
        "altitude": 0,
        "coordinates": {"lat": 49.2827, "lon": -123.1207},
    },
    "Boston": {
        "country": "USA",
        "timezone": "America/New_York",
        "altitude": 6,
        "coordinates": {"lat": 42.3601, "lon": -71.0589},
    },
    "Philadelphia": {
        "country": "USA",
        "timezone": "America/New_York",
        "altitude": 12,
        "coordinates": {"lat": 39.9526, "lon": -75.1652},
    },
    "Atlanta": {
        "country": "USA",
        "timezone": "America/New_York",
        "altitude": 320,
        "coordinates": {"lat": 33.7490, "lon": -84.3880},
    },
    "Seattle": {
        "country": "USA",
        "timezone": "America/Los_Angeles",
        "altitude": 0,
        "coordinates": {"lat": 47.6062, "lon": -122.3321},
    },
    "San Francisco": {
        "country": "USA",
        "timezone": "America/Los_Angeles",
        "altitude": 10,
        "coordinates": {"lat": 37.7749, "lon": -122.4194},
    },
    "Denver": {
        "country": "USA",
        "timezone": "America/Denver",
        "altitude": 1609,  # 高海拔！
        "coordinates": {"lat": 39.7392, "lon": -104.9903},
    },
    "Monterrey": {
        "country": "Mexico",
        "timezone": "America/Monterrey",
        "altitude": 540,
        "coordinates": {"lat": 25.6866, "lon": -100.3161},
    },
    "Guadalajara": {
        "country": "Mexico",
        "timezone": "America/Mexico_City",
        "altitude": 1567,
        "coordinates": {"lat": 20.6597, "lon": -103.3497},
    },
}


def set_weather_api_key(api_key: str):
    """设置OpenWeatherMap API Key"""
    global OPENWEATHER_API_KEY
    OPENWEATHER_API_KEY = api_key


def get_city_weather(city_name: str) -> Dict:
    """
    获取城市实时天气信息
    
    Args:
        city_name: 城市名称
    
    Returns:
        {
            "temperature": 气温（摄氏度）,
            "humidity": 湿度,
            "weather": 天气状况,
            "is_rain": 是否下雨,
            "altitude": 海拔（米）,
            "timezone": 时区,
            "timezone_diff": 与北京时间时差（小时）,
        }
    """
    # 获取城市信息
    city_info = HOST_CITIES_INFO.get(city_name)
    
    if not city_info:
        return {
            "temperature": 22,
            "humidity": 50,
            "weather": "未知",
            "is_rain": False,
            "altitude": 0,
            "timezone": "UTC",
            "timezone_diff": 0,
            "error": f"城市 '{city_name}' 未找到",
        }
    
    # 如果有API Key，获取实时天气
    if OPENWEATHER_API_KEY:
        try:
            lat = city_info["coordinates"]["lat"]
            lon = city_info["coordinates"]["lon"]
            
            url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={OPENWEATHER_API_KEY}&units=metric"
            
            r = requests.get(url, timeout=10)
            
            if r.status_code == 200:
                data = r.json()
                
                temperature = data["main"]["temp"]
                humidity = data["main"]["humidity"]
                weather_main = data["weather"][0]["main"]
                is_rain = weather_main in ["Rain", "Drizzle", "Thunderstorm"]
                
                return {
                    "temperature": round(temperature, 1),
                    "humidity": humidity,
                    "weather": weather_main,
                    "is_rain": is_rain,
                    "altitude": city_info["altitude"],
                    "timezone": city_info["timezone"],
                    "timezone_diff": _calc_timezone_diff(city_info["timezone"]),
                    "source": "OpenWeatherMap API",
                }
        except Exception as e:
            pass
    
    # 无API Key或获取失败，返回预设数据
    # 根据城市特点返回合理的默认值
    default_temp = _estimate_temperature(city_name)
    
    return {
        "temperature": default_temp,
        "humidity": 50,
        "weather": "Clear",
        "is_rain": False,
        "altitude": city_info["altitude"],
        "timezone": city_info["timezone"],
        "timezone_diff": _calc_timezone_diff(city_info["timezone"]),
        "source": "预设数据（无API Key）",
    }


def _estimate_temperature(city_name: str) -> float:
    """根据城市和季节估算气温（2026年6月世界杯）"""
    # 2026世界杯在6-7月举行，北半球夏季
    
    # 墨西哥城：高海拔，气温适中
    if city_name == "Mexico City":
        return 22  # 高海拔，夏季凉爽
    
    # 美国南部城市：炎热
    if city_name in ["Houston", "Miami", "Dallas", "Monterrey"]:
        return 32  # 夏季炎热
    
    # 美国西海岸：温和
    if city_name in ["Los Angeles", "San Francisco", "Seattle", "Vancouver"]:
        return 24
    
    # 美国东海岸：温暖
    if city_name in ["New York/Newark", "Boston", "Philadelphia", "Atlanta", "Toronto"]:
        return 28
    
    # 高海拔城市：凉爽
    if city_name in ["Denver", "Guadalajara"]:
        return 25
    
    return 22  # 默认


def _calc_timezone_diff(city_timezone: str) -> int:
    """计算与北京时间的时差（小时）"""
    try:
        beijing = pytz.timezone("Asia/Shanghai")
        city_tz = pytz.timezone(city_timezone)
        
        now = datetime.now(beijing)
        city_now = now.astimezone(city_tz)
        
        diff = (city_now.hour - now.hour)
        if diff > 12:
            diff -= 24
        elif diff < -12:
            diff += 24
        
        return diff
    except:
        return 0


def get_match_environment(home_team: str, away_team: str, venue_city: str = None) -> Dict:
    """
    获取比赛环境信息
    
    Args:
        home_team: 主队名
        away_team: 客队名
        venue_city: 比赛场地城市（可选）
    
    Returns:
        环境信息字典
    """
    # 如果未指定场地，根据主队推断
    if not venue_city:
        venue_city = _infer_venue_from_team(home_team)
    
    # 获取场地天气
    weather = get_city_weather(venue_city)
    
    return {
        "venue_city": venue_city,
        "temperature": weather["temperature"],
        "altitude": weather["altitude"],
        "is_rain": weather["is_rain"],
        "timezone": weather["timezone"],
        "timezone_diff": weather["timezone_diff"],
        "humidity": weather.get("humidity", 50),
        "weather": weather.get("weather", "Clear"),
        "source": weather.get("source", "预设数据"),
    }


def _infer_venue_from_team(team_name: str) -> str:
    """根据球队推断比赛场地"""
    # 墨西哥球队 -> 墨西哥城或瓜达拉哈拉
    if team_name in ["墨西哥", "Mexico"]:
        return "Mexico City"
    
    # 加拿大球队 -> 多伦多或温哥华
    if team_name in ["加拿大", "Canada"]:
        return "Toronto"
    
    # 美国球队 -> 洛杉矶或纽约
    if team_name in ["美国", "USA"]:
        return "Los Angeles"
    
    # 其他球队默认使用洛杉矶
    return "Los Angeles"


# 测试
if __name__ == "__main__":
    print("=== 天气API测试 ===")
    
    # 测试各城市
    for city in ["Mexico City", "Los Angeles", "Houston", "Denver", "Toronto"]:
        weather = get_city_weather(city)
        print(f"\n{city}:")
        print(f"  气温: {weather['temperature']}°C")
        print(f"  海拔: {weather['altitude']}m")
        print(f"  时差: {weather['timezone_diff']}小时")
        print(f"  来源: {weather['source']}")