# main.py
import json
import sys
import os
from datetime import datetime, date
from time import localtime
from requests import get, post
from zhdate import ZhDate


class WeChatNotifier:
    def __init__(self, config_path="config.txt"):
        self.config = self.load_config(config_path)
        self.access_token = self.get_access_token()

    def load_config(self, config_path):
        """加载配置文件"""
        try:
            with open(config_path, encoding="utf-8") as f:
                content = f.read().strip()
                lines = content.split('\n')
                json_lines = [line for line in lines if
                              not line.strip().startswith('//') and not line.strip().startswith('#')]
                json_content = '\n'.join(json_lines)
                return json.loads(json_content)
        except FileNotFoundError:
            print(f"推送消息失败，请检查{config_path}文件是否与程序位于同一路径")
            os.system("pause")
            sys.exit(1)
        except (json.JSONDecodeError, SyntaxError) as e:
            print(f"推送消息失败，请检查配置文件格式是否正确: {e}")
            os.system("pause")
            sys.exit(1)

    def get_access_token(self):
        """获取微信访问令牌"""
        app_id = self.config["app_id"]
        app_secret = self.config["app_secret"]
        url = f"https://api.weixin.qq.com/cgi-bin/token?grant_type=client_credential&appid={app_id}&secret={app_secret}"

        try:
            response = get(url)
            response.raise_for_status()
            data = response.json()
            return data['access_token']
        except (KeyError, ValueError) as e:
            print(f"获取access_token失败: {e}")
            os.system("pause")
            sys.exit(1)

    def get_weather_data(self, region):
        """获取简化天气数据，添加降水量信息和多种天气提示"""
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/103.0.0.0 Safari/537.36'
        }
        key = self.config["weather_key"]

        # 获取位置ID
        region_url = f"https://geoapi.qweather.com/v2/city/lookup?location={region}&key={key}"
        try:
            response = get(region_url, headers=headers)
            response.raise_for_status()
            data = response.json()

            if data["code"] == "404":
                raise ValueError("推送消息失败，请检查地区名是否有误！")
            elif data["code"] == "401":
                raise ValueError("推送消息失败，请检查和风天气key是否正确！")

            location_id = data["location"][0]["id"]
        except Exception as e:
            print(f"获取位置信息失败: {e}")
            os.system("pause")
            sys.exit(1)

        # 获取天气信息
        weather_url = f"https://devapi.qweather.com/v7/weather/3d?location={location_id}&key={key}"
        try:
            response = get(weather_url, headers=headers)
            response.raise_for_status()
            weather_data = response.json()
            daily_data = weather_data["daily"][0]

            # 整理简化天气数据，添加降水量信息
            weather_info = {
                "day_text": daily_data["textDay"],
                "night_text": daily_data["textNight"],
                "temp_max": f"{daily_data['tempMax']}°C",
                "temp_min": f"{daily_data['tempMin']}°C",
                "humidity": f"{daily_data['humidity']}%",
                "precip": f"{daily_data['precip']}mm",  # 添加降水量
                "temp_max_num": int(daily_data['tempMax']),  # 添加数值型温度用于判断
                "temp_min_num": int(daily_data['tempMin']),  # 添加数值型温度用于判断
            }

            # 高温提示
            temp_tips = []

            # 首先检查昼夜温差
            temp_diff = weather_info["temp_max_num"] - weather_info["temp_min_num"]
            if temp_diff > 12:
                temp_tips.append("昼夜温差大，注意及时增添衣物")
            else:
                # 如果没有大的温差，再检查高温和低温情况
                if weather_info["temp_max_num"] > 30:
                    temp_tips.append("今天高温，注意防暑降温")
                elif weather_info["temp_max_num"] > 25:
                    temp_tips.append("今天天气较热，建议穿轻薄衣物")

                if weather_info["temp_min_num"] < 0:
                    temp_tips.append("今天低温，注意防寒保暖")
                elif weather_info["temp_min_num"] < 10:
                    temp_tips.append("今天天气较冷，建议穿厚外套")

            # 如果没有生成任何提示，添加默认提示
            if not temp_tips:
                temp_tips.append("今天温度适宜，穿着舒适")

            weather_info["temp_tips"] = "；".join(temp_tips)

            # 生成天气状况提示
            weather_tips = []

            # 降水提示
            precip_value = float(daily_data['precip'])
            if precip_value > 0:
                if "雨" in daily_data["textDay"] or "雨" in daily_data["textNight"]:
                    weather_tips.append("今天有雨，出门记得带伞哦")
                elif "雪" in daily_data["textDay"] or "雪" in daily_data["textNight"]:
                    weather_tips.append("今天有雪，注意路面湿滑，防寒保暖")

            # 雾霾提示
            if "雾" in daily_data["textDay"] or "雾" in daily_data["textNight"] or "霾" in daily_data[
                "textDay"] or "霾" in daily_data["textNight"]:
                weather_tips.append("今天有雾霾，请戴好口罩，减少户外活动")

            # 大风提示
            if "风" in daily_data["textDay"] or "风" in daily_data["textNight"]:
                weather_tips.append("今天有大风，请注意防风")

            # 如果没有天气状况提示，添加一般性提示
            if not weather_tips:
                weather_tips.append("今天天气状况良好")

            weather_info["weather_tips"] = "；".join(weather_tips)

            return weather_info
        except Exception as e:
            print(f"获取天气信息失败: {e}")
            os.system("pause")
            sys.exit(1)

    def calculate_days_difference(self, target_date_str, is_lunar=False):
        """计算日期差，支持公历和农历"""
        today = date.today()

        try:
            # 处理农历日期
            if target_date_str.startswith("农历") or is_lunar:
                if target_date_str.startswith("农历"):
                    lunar_date_str = target_date_str[2:]  # 去掉"农历"前缀
                else:
                    lunar_date_str = target_date_str

                parts = lunar_date_str.split('-')
                lunar_month = int(parts[0])
                lunar_day = int(parts[1])

                # 计算今年的农历日期
                lunar_date = ZhDate(today.year, lunar_month, lunar_day)
                target_date = lunar_date.to_datetime().date()

                # 如果今年的农历日期已经过去，计算明年的
                if today > target_date:
                    lunar_date = ZhDate(today.year + 1, lunar_month, lunar_day)
                    target_date = lunar_date.to_datetime().date()
            else:
                # 解析公历日期
                parts = target_date_str.split('-')
                target_year = int(parts[0])
                target_month = int(parts[1])
                target_day = int(parts[2])

                # 创建日期对象
                target_date = date(target_year, target_month, target_day)

                # 如果今年的公历日期已经过去，计算明年的
                if today > target_date:
                    target_date = date(today.year + 1, target_month, target_day)

            days_diff = (target_date - today).days
            return days_diff
        except (ValueError, IndexError) as e:
            print(f"日期格式错误: {e}")
            return None

    def get_count_up_days(self, start_date_str):
        """计算正数计时天数"""
        try:
            start_year = int(start_date_str.split("-")[0])
            start_month = int(start_date_str.split("-")[1])
            start_day = int(start_date_str.split("-")[2])
            start_date = date(start_year, start_month, start_day)

            today = date.today()
            days_count = (today - start_date).days
            return days_count
        except (ValueError, IndexError) as e:
            print(f"正数计时日期格式错误: {e}")
            return None

    def get_ciba_data(self):
        """获取金山词霸每日一句"""
        url = "http://open.iciba.com/dsapi/"
        headers = {
            'Content-Type': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/103.0.0.0 Safari/537.36'
        }

        try:
            response = get(url, headers=headers)
            response.raise_for_status()
            data = response.json()

            note_en = data["content"]
            note_ch = data["note"]

            # 分割文本，使其更适合显示
            middle_en = len(note_en) // 2
            middle_ch = len(note_ch) // 2

            return {
                "en1": note_en[:middle_en],
                "en2": note_en[middle_en:],
                "ch1": note_ch[:middle_ch],
                "ch2": note_ch[middle_ch:]
            }
        except Exception as e:
            print(f"获取金山词霸数据失败: {e}")
            # 返回默认值
            return {
                "en1": "The best preparation for tomorrow is doing your best today.",
                "en2": "",
                "ch1": "对今天最好的准备就是今天做到最好",
                "ch2": ""
            }

    def send_message(self, to_user, region_name, weather_info, ciba_data):
        """发送消息"""
        url = f"https://api.weixin.qq.com/cgi-bin/message/template/send?access_token={self.access_token}"

        # 获取当前日期信息
        today = datetime.now()
        week_list = ["星期日", "星期一", "星期二", "星期三", "星期四", "星期五", "星期六"]
        week = week_list[today.weekday()]

        # 计算纪念日
        love_days_diff = self.calculate_days_difference(self.config["love_date"])
        if love_days_diff == 0:
            love_days_data = "今天是我们周年纪念日哦，祝宝贝纪念日快乐！"
        else:
            love_days_data = f"距离特殊周年纪念日还有 {love_days_diff} 天"
        day_of_year = today.timetuple().tm_yday

        # 计算在一起天数
        love_date_str = self.config["love_date"]
        love_year = int(love_date_str.split("-")[0])
        love_month = int(love_date_str.split("-")[1])
        love_day = int(love_date_str.split("-")[2])
        love_date = date(love_year, love_month, love_day)
        love_days = (date.today() - love_date).days

        # 计算正数计时
        count_up_days = self.get_count_up_days(self.config["count_up_date"])
        count_up_data = f"我们已经一起走过了 {count_up_days} 天"

        # 处理生日数据
        birthdays = {}
        for k, v in self.config.items():
            if k.startswith("birth"):
                birthdays[k] = v

        birthday_data = []
        for key, value in birthdays.items():
            # 假设生日是农历
            days_diff = self.calculate_days_difference(value["birthday"], is_lunar=True)
            if days_diff == 0:
                birthday_data.append({
                    "name": value['name'],
                    "days": f"今天是{value['name']}生日哦，祝{value['name']}生日快乐！"
                })
            else:
                birthday_data.append({
                    "name": value['name'],
                    "days": f"距离{value['name']}生日还有 {days_diff} 天"
                })

        # 确保至少有2个生日数据
        while len(birthday_data) < 2:
            birthday_data.append({"name": "", "days": ""})

        # 处理节日数据
        # 处理节日数据
        festival_data = []
        if "festivals" in self.config:
            # 1. 临时存储节日信息（包含名称和剩余天数）
            temp_festivals = []
            for festival in self.config["festivals"]:
                # 判断是否为农历节日
                lunar_festivals = ["春节", "元宵节", "端午节", "中秋节"]
                is_lunar = festival["name"] in lunar_festivals

                # 计算距离天数
                days_diff = self.calculate_days_difference(festival["date"], is_lunar=is_lunar)
                if days_diff is not None:  # 确保日期计算有效
                    temp_festivals.append({
                        "name": festival["name"],
                        "days_diff": days_diff
                    })

            # 2. 按剩余天数升序排序（最近的节日排在前面）
            temp_festivals.sort(key=lambda x: x["days_diff"])

            # 3. 取排序后的前3个节日，生成显示文本
            for fest in temp_festivals[:3]:
                if fest["days_diff"] == 0:
                    festival_data.append({
                        "name": fest["name"],
                        "days": f"今天是{fest['name']}！"
                    })
                else:
                    festival_data.append({
                        "name": fest["name"],
                        "days": f"距离{fest['name']}还有 {fest['days_diff']} 天"
                    })

        # 确保至少有3个显示项（不足时用空值填充）
        while len(festival_data) < 3:
            festival_data.append({"name": "", "days": ""})

        # 准备消息数据
        data = {
            "touser": to_user,
            "template_id": self.config["template_id"],
            "url": "http://weixin.qq.com/download",
            "topcolor": "#FF0000",
            "data": {
                "date": {"value": f"{today.strftime('%Y-%m-%d')} {week}"},
                "region": {"value": region_name},
                "weather_day": {"value": weather_info["day_text"]},
                "weather_night": {"value": weather_info["night_text"]},
                "temp_max": {"value": weather_info["temp_max"]},
                "temp_min": {"value": weather_info["temp_min"]},
                "precip": {"value": weather_info["precip"]},  # 添加降水量
                "temp_tips": {"value": weather_info["temp_tips"]},  # 添加温度提示
                "weather_tips": {"value": weather_info["weather_tips"]},  # 添加天气状况提示
                "love_day": {"value": str(love_days)},
                "love_day_data": {"value": love_days_data},
                "count_up_data": {"value": count_up_data},
                "day_of_year": {"value": str(day_of_year)},
                # 只发送days字段，因为它们已经包含了名称信息
                "birthday1_days": {"value": birthday_data[0]["days"]},
                "birthday2_days": {"value": birthday_data[1]["days"]},
                "festival1_days": {"value": festival_data[0]["days"]},
                "festival2_days": {"value": festival_data[1]["days"]},
                "festival3_days": {"value": festival_data[2]["days"]},
                "note_ch1": {"value": ciba_data["ch1"]},
                "note_ch2": {"value": ciba_data["ch2"]},
                "note_en1": {"value": ciba_data["en1"]},
                "note_en2": {"value": ciba_data["en2"]}
            }
        }

        # 发送请求
        headers = {
            'Content-Type': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/103.0.0.0 Safari/537.36'
        }

        try:
            response = post(url, headers=headers, json=data)
            response.raise_for_status()
            result = response.json()

            if result["errcode"] == 0:
                print("推送消息成功")
            else:
                error_codes = {
                    40037: "推送消息失败，请检查模板id是否正确",
                    40036: "推送消息失败，请检查模板id是否为空",
                    40003: "推送消息失败，请检查微信号是否正确"
                }
                error_msg = error_codes.get(result["errcode"], f"未知错误: {result}")
                print(error_msg)

        except Exception as e:
            print(f"发送消息失败: {e}")

    def run(self):
        """运行主程序"""
        users = self.config["user"]
        region = self.config["region"]

        # 获取天气数据
        weather_info = self.get_weather_data(region)

        # 获取金山词霸数据
        ciba_data = self.get_ciba_data()

        # 自定义笔记（如果配置中有）
        if "note_ch1" in self.config and self.config["note_ch1"]:
            ciba_data["ch1"] = self.config["note_ch1"]
        if "note_ch2" in self.config and self.config["note_ch2"]:
            ciba_data["ch2"] = self.config["note_ch2"]
        if "note_en1" in self.config and self.config["note_en1"]:
            ciba_data["en1"] = self.config["note_en1"]
        if "note_en2" in self.config and self.config["note_en2"]:
            ciba_data["en2"] = self.config["note_en2"]

        # 发送消息给每个用户
        for user in users:
            self.send_message(user, region, weather_info, ciba_data)


if __name__ == "__main__":
    notifier = WeChatNotifier()
    notifier.run()
    os.system("pause")
