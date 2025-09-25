from requests import get, post
import sys
import os
from datetime import datetime, date
from zhdate import ZhDate  # 导入农历处理库


def load_config():
    """加载配置文件并处理JSON格式"""
    try:
        with open("config.txt", encoding="utf-8") as f:
            # 移除注释行以符合JSON格式
            content = "\n".join([line.split("#")[0].strip() for line in f if line.split("#")[0].strip()])
            return eval(content)  # 生产环境建议用json.loads
    except FileNotFoundError:
        print("错误：未找到config.txt文件")
        os.system("pause")
        sys.exit(1)
    except Exception as e:
        print(f"配置文件错误：{e}")
        os.system("pause")
        sys.exit(1)


def get_access_token(config):
    """获取微信公众号access_token"""
    app_id = config["app_id"]
    app_secret = config["app_secret"]
    url = f"https://api.weixin.qq.com/cgi-bin/token?grant_type=client_credential&appid={app_id}&secret={app_secret}"
    try:
        access_token = get(url).json()["access_token"]
    except KeyError:
        print("获取access_token失败，请检查app_id和app_secret")
        os.system("pause")
        sys.exit(1)
    return access_token


def get_weather(config):
    """获取天气信息（精简版）"""
    region = config["region"]
    key = config["weather_key"]
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/103.0.0.0 Safari/537.36"
    }

    # 获取地区ID
    region_url = f"https://geoapi.qweather.com/v2/city/lookup?location={region}&key={key}"
    response = get(region_url, headers=headers).json()
    if response["code"] != "200":
        print(f"天气接口错误: {response['code']}")
        os.system("pause")
        sys.exit(1)
    location_id = response["location"][0]["id"]

    # 获取天气数据
    weather_url = f"https://devapi.qweather.com/v7/weather/3d?location={location_id}&key={key}"
    response = get(weather_url, headers=headers).json()
    daily = response["daily"][0]

    return {
        "text_day": daily["textDay"],
        "text_night": daily["textNight"],
        "temp_max": f"{daily['tempMax']}°C",
        "temp_min": f"{daily['tempMin']}°C",
        "precip": f"{daily['precip']}mm",
        "temp_tips": get_temp_tips(daily["tempMin"], daily["tempMax"]),
        "weather_tips": get_rain_tips(daily["precip"])
    }


def get_temp_tips(min_temp, max_temp):
    """生成温度温馨提示"""
    min_temp = int(min_temp)
    max_temp = int(max_temp)

    if max_temp >= 35:
        return "高温天气，注意防暑降温，多补充水分！"
    elif max_temp >= 30:
        return "天气较热，注意防晒，穿透气衣物~"
    elif min_temp <= 10:
        return "气温较低，记得添衣保暖，小心着凉~"
    elif max_temp - min_temp >= 10:
        return "昼夜温差大，建议穿脱方便的衣物~"
    else:
        return "温度适宜，体感舒适，适合正常出行~"


def get_rain_tips(precip):
    """生成降雨温馨提示"""
    precip = float(precip)
    if precip == 0:
        return "今日无雨，适合户外活动~"
    elif precip < 10:
        return "有小雨，出门记得带伞哦~"
    elif precip < 25:
        return "有中雨，外出请做好防雨措施~"
    else:
        return "有大雨，尽量减少外出，注意安全~"


def get_day_left(target_date_str, year, today):
    """计算距离目标日期的天数（支持阳历和农历）"""
    try:
        if target_date_str.startswith("L"):  # 处理农历日期（格式：LMM-DD）
            l_parts = target_date_str[1:].split("-")
            if len(l_parts) != 2:
                raise ValueError(f"农历日期格式错误，应为 LMM-DD，实际：{target_date_str}")
            l_month, l_day = map(int, l_parts)
            # 构造农历日期并转换为阳历
            l_date = ZhDate(year, l_month, l_day)
            target_date = l_date.to_datetime().date()
            # 若已过则计算下一年
            if target_date < today:
                l_date_next = ZhDate(year + 1, l_month, l_day)
                target_date = l_date_next.to_datetime().date()

        else:  # 处理阳历日期（格式：MM-DD）
            parts = target_date_str.split("-")
            if len(parts) != 2:
                raise ValueError(f"阳历日期格式错误，应为 MM-DD，实际：{target_date_str}")
            month, day = map(int, parts)
            target_date = date(year, month, day)
            # 若已过则计算下一年
            if target_date < today:
                target_date = date(year + 1, month, day)

        # 计算天数差
        days_diff = (target_date - today).days
        return days_diff if days_diff >= 0 else 0  # 确保非负

    except Exception as e:
        print(f"日期解析错误：{e}（目标日期：{target_date_str}）")
        return float('inf')  # 错误日期排在最后


def get_ciba():
    """获取金山词霸每日一句"""
    url = "http://open.iciba.com/dsapi/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/103.0.0.0 Safari/537.36"
    }
    try:
        response = get(url, headers=headers).json()
        note_en = response["content"]
        note_ch = response["note"]
        # 拆分文本（避免模板显示过长）
        middle_en = len(note_en) // 2
        middle_ch = len(note_ch) // 2
        return note_en[:middle_en], note_en[middle_en:], note_ch[:middle_ch], note_ch[middle_ch:]
    except Exception as e:
        print(f"获取每日一句失败：{e}")
        return "", "", "每日一句获取失败", ""


def send_message(to_user, access_token, config, weather_data, ciba_data):
    """发送模板消息"""
    # 解析参数
    note_en1, note_en2, note_ch1, note_ch2 = ciba_data

    # 基础信息
    week_list = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    today = date.today()
    year = today.year
    week = week_list[today.weekday()]
    day_of_year = today.timetuple().tm_yday  # 当年第几天
    
    # 农历日期计算
    lunar_today = ZhDate.from_datetime(datetime.now())
    lunar_str = f"{lunar_today.lunar_month}月{lunar_today.lunar_day}日"
    if hasattr(lunar_today, 'is_leap') and lunar_today.is_leap:
        lunar_str = f"闰{lunar_str}"

    # 纪念日计算（匹配模板love_day字段）
    love_date_str = config.get("love_date", "")
    try:
        if love_date_str:
            love_date = datetime.strptime(love_date_str, "%Y-%m-%d").date()
            love_days = (today - love_date).days  # 在一起的总天数
            love_day_text = f"我们在一起{的第love_days}天啦"
        else:
            love_day_text = ""
    except Exception as e:
        print(f"纪念日计算错误：{e}")
        love_day_text = "纪念日计算错误"

    # 生日计算（匹配模板birthday1_days和birthday2_days字段）
    birthdays = []
    for b_key in ["birthday1", "birthday2"]:
        if b_key in config and config[b_key]:
            b_info = config[b_key]
            b_name = b_info.get("name", "")
            b_lunar = b_info.get("birthday", "")
            if b_lunar:
                b_days_left = get_day_left(f"L{b_lunar}", year, today)
                if b_days_left == 0:
                    b_text = "今天生日哦！生日快乐！"
                else:
                    b_text = f"还有{b_days_left}天"
                birthdays.append({"name": b_name, "days": b_text})
            else:
                birthdays.append({"name": b_name, "days": "生日信息未设置"})
        else:
            birthdays.append({"name": "", "days": ""})
    while len(birthdays) < 2:
        birthdays.append({"name": "", "days": ""})

    # 节日计算（匹配模板festival字段，从config的festivals数组获取）
    festivals = config.get("festivals", [])  # 正确获取数组形式的节日
    festival_list = []
    for item in festivals:
        f_left = get_day_left(item["date"], year, today)
        if f_left == 0:
            status_text = "今天哦！"
        else:
            status_text = f"还有{f_left}天"
        festival_list.append({
            "name": item["name"],
            "days": status_text,
            "days_left": f_left
        })
    festival_list.sort(key=lambda x: x["days_left"])
    top_festivals = festival_list[:3]
    while len(top_festivals) < 3:
        top_festivals.append({"name": "", "days": "", "days_left": 0})

    # 模板消息数据（严格匹配你的模板字段）
    data = {
        "touser": to_user,
        "template_id": config["template_id"],
        "url": "http://weixin.qq.com/download",
        "topcolor": "#FF0000",
        "data": {
            "date": {"value": f"{today} {week}"},
            "lunar_date": {"value": lunar_str},
            "day_of_year": {"value": f"{year}年的第{day_of_year}天"},  # 补充"天"字
            "love_day": {"value": love_day_text},  # 匹配模板love_day字段
            "region": {"value": config["region"]},
            "weather_day": {"value": weather_data["text_day"]},
            "weather_night": {"value": weather_data["text_night"]},
            "temp_max": {"value": weather_data["temp_max"]},
            "temp_min": {"value": weather_data["temp_min"]},
            "temp_tips": {"value": weather_data["temp_tips"]},
            "precip": {"value": weather_data["precip"]},
            "weather_tips": {"value": weather_data["weather_tips"]},
            "birthday1_name": {"value": birthdays[0]["name"]},
            "birthday1_days": {"value": birthdays[0]["days"]},  # 匹配模板birthday1_days
            "birthday2_name": {"value": birthdays[1]["name"]},
            "birthday2_days": {"value": birthdays[1]["days"]},  # 匹配模板birthday2_days
            "festival1_name": {"value": top_festivals[0]["name"]},
            "festival1_days": {"value": top_festivals[0]["days"]},
            "festival2_name": {"value": top_festivals[1]["name"]},
            "festival2_days": {"value": top_festivals[1]["days"]},
            "festival3_name": {"value": top_festivals[2]["name"]},
            "festival3_days": {"value": top_festivals[2]["days"]},
            "note_ch1": {"value": config["note_ch1"] or note_ch1},
            "note_ch2": {"value": config["note_ch2"] or note_ch2},
            "note_en1": {"value": config["note_en1"] or note_en1},
            "note_en2": {"value": config["note_en2"] or note_en2}
        }
    }

    # 发送请求
    url = f"https://api.weixin.qq.com/cgi-bin/message/template/send?access_token={access_token}"
    headers = {"Content-Type": "application/json"}
    response = post(url, headers=headers, json=data).json()

    # 错误处理
    if response["errcode"] == 0:
        print(f"向用户 {to_user} 推送消息成功")
    else:
        print(f"向用户 {to_user} 推送消息失败：{response}")


if __name__ == "__main__":
    config = load_config()
    access_token = get_access_token(config)
    weather_data = get_weather(config)
    ciba_data = get_ciba()

    # 向所有用户发送消息
    for user in config["user"]:
        send_message(user, access_token, config, weather_data, ciba_data)

    os.system("pause")
