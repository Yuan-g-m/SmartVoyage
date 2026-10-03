#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
12306 官方公开余票/票价接口封装。

说明：
    - 12306 无第三方官方开放 API，本模块调用其公开查询页面使用的
      leftTicket/queryTicketPrice 接口，仅供项目学习研究使用。
    - 免登录、免 API Key；只做只读查询。
    - 站点名称/三字码通过 station_name.js 实时解析。
"""

import json
import re
from datetime import datetime, timedelta

import requests
from requests.packages.urllib3.exceptions import InsecureRequestWarning

from SmartVoyage.create_logger import logger


requests.packages.urllib3.disable_warnings(InsecureRequestWarning)


INIT_URL = "https://kyfw.12306.cn/otn/leftTicket/init"
STATION_URL = "https://kyfw.12306.cn/otn/resources/js/framework/station_name.js"
QUERY_ENDPOINTS = ("queryG", "queryO", "queryZ", "queryA")
QUERY_URL_TEMPLATE = "https://kyfw.12306.cn/otn/leftTicket/{endpoint}"
PRICE_URL = "https://kyfw.12306.cn/otn/leftTicket/queryTicketPrice"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/122.0 Safari/537.36",
    "Referer": "https://kyfw.12306.cn/otn/leftTicket/init",
    "Accept": "application/json, text/javascript, */*; q=0.01",
}

# 余票字段下标 -> 中文座席名。12306 返回的 result 中每个元素是以 | 分隔的数组。
SEAT_FIELD_MAP = {
    21: "高级软卧",
    23: "软卧",
    24: "软座",
    25: "特等座",
    26: "无座",
    28: "硬卧",
    29: "硬座",
    30: "二等座",
    31: "一等座",
    32: "商务座",
    33: "动卧",
}

# 票价接口返回的座席代码 -> 中文座席名
PRICE_KEY_MAP = {
    "O": "二等座",
    "M": "一等座",
    "P": "特等座",
    "9": "商务座",
    "A9": "商务座",
    "WZ": "无座",
    "1": "硬座",
    "A1": "硬座",
    "2": "软座",
    "A2": "软座",
    "3": "硬卧",
    "A3": "硬卧",
    "4": "软卧",
    "A4": "软卧",
    "6": "高级软卧",
    "A6": "高级软卧",
}


class RealtimeTrainTicketService:
    """查询 12306 实时火车票余票与票价。"""

    def __init__(self, timeout: int = 12):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.session.verify = False

        self._init_done = False
        self._station_name_to_code = {}
        self._station_code_to_name = {}
        self._stations_loaded = False

    def _ensure_init(self) -> None:
        if self._init_done:
            return
        try:
            response = self.session.get(INIT_URL, timeout=self.timeout)
            self._init_done = response.status_code == 200
        except Exception as exc:
            logger.warning(f"初始化 12306 会话失败：{exc}")
            self._init_done = False

    def _request_json(self, url: str, params: dict, retry: bool = True):
        """请求 JSON 接口；如果被反爬拦截则重新初始化会话并重试一次。"""
        self._ensure_init()
        try:
            response = self.session.get(url, params=params, timeout=self.timeout)
            content_type = response.headers.get("content-type", "")
            if "application/json" not in content_type and "<html" in response.text.lower():
                if retry:
                    self._init_done = False
                    return self._request_json(url, params, retry=False)
                return None
            return response.json()
        except Exception as exc:
            logger.warning(f"12306 接口请求失败：{url} {exc}")
            if retry:
                self._init_done = False
                return self._request_json(url, params, retry=False)
            return None

    def _ensure_stations(self) -> None:
        if self._stations_loaded:
            return
        try:
            response = self.session.get(STATION_URL, timeout=self.timeout)
            response.encoding = "utf-8"
            match = re.search(r"var\s+station_names\s*=\s*'([^']*)'", response.text, re.S)
            if not match:
                return
            raw_stations = match.group(1)
            for item in raw_stations.split("@"):
                if not item.strip():
                    continue
                fields = item.split("|")
                if len(fields) < 3 or not fields[1] or not fields[2]:
                    continue
                name = fields[1].strip()
                code = fields[2].strip()
                self._station_name_to_code[name] = code
                self._station_code_to_name[code] = name
            self._stations_loaded = bool(self._station_name_to_code)
        except Exception as exc:
            logger.error(f"加载 12306 车站信息失败：{exc}")

    def resolve_station_code(self, station_name: str) -> str:
        self._ensure_stations()
        if not station_name:
            return ""
        station_name = station_name.strip()
        if station_name in self._station_name_to_code:
            return self._station_name_to_code[station_name]
        if station_name.endswith("站"):
            station_name = station_name[:-1]
        return self._station_name_to_code.get(station_name, "")

    def resolve_station_name(self, station_code: str) -> str:
        self._ensure_stations()
        return self._station_code_to_name.get(station_code, station_code)

    def _parse_seat_availability(self, fields: list) -> dict:
        seats = {}
        for index, label in SEAT_FIELD_MAP.items():
            if index >= len(fields):
                continue
            value = fields[index].strip()
            if not value or value == "无":
                continue
            seats[label] = "有票" if value == "有" else value
        return seats

    @staticmethod
    def _parse_price(value) -> float | None:
        if value is None or value == "":
            return None
        if isinstance(value, (int, float)):
            return float(value)
        text = str(value).strip()
        if text.startswith("¥"):
            try:
                return float(text[1:])
            except ValueError:
                return None
        try:
            # 12306 非 A 前缀键通常以角为单位，例如 235 表示 23.5 元。
            return round(float(text) / 10.0, 2)
        except ValueError:
            return None

    def _fetch_prices(self, fields: list, train_date: str) -> dict:
        train_no = fields[2] if len(fields) > 2 else ""
        from_station_no = fields[16] if len(fields) > 16 else ""
        to_station_no = fields[17] if len(fields) > 17 else ""
        if not train_no or not from_station_no or not to_station_no:
            return {}

        has_high_speed_seat = any(
            index < len(fields) and fields[index].strip() not in ("", "无")
            for index in (25, 30, 31, 32)
        )
        seat_codes = "OMP9A9" if has_high_speed_seat else "1234WZ"
        payload = {
            "train_no": train_no,
            "from_station_no": from_station_no,
            "to_station_no": to_station_no,
            "seat_types": seat_codes,
            "train_date": train_date,
        }
        data = self._request_json(PRICE_URL, payload)
        if not data or not data.get("status"):
            return {}
        raw_prices = data.get("data") or {}
        prices = {}
        for key, value in raw_prices.items():
            if key == "OT" or key == "train_no":
                continue
            label = PRICE_KEY_MAP.get(key)
            if not label:
                continue
            price = self._parse_price(value)
            if price is not None:
                prices[label] = price
        return prices

    @staticmethod
    def _full_datetime(train_date: str, time_text: str, next_day: bool = False) -> str:
        try:
            day = datetime.strptime(train_date, "%Y-%m-%d")
            if next_day:
                day = day + timedelta(days=1)
            hour, minute = time_text.split(":")
            return day.replace(hour=int(hour), minute=int(minute)).strftime("%Y-%m-%d %H:%M")
        except Exception:
            return f"{train_date} {time_text}"

    def _query_left_rows(self, from_code: str, to_code: str, train_date: str) -> list | None:
        params = {
            "leftTicketDTO.train_date": train_date,
            "leftTicketDTO.from_station": from_code,
            "leftTicketDTO.to_station": to_code,
            "purpose_codes": "ADULT",
        }
        for endpoint in QUERY_ENDPOINTS:
            data = self._request_json(QUERY_URL_TEMPLATE.format(endpoint=endpoint), params)
            if not data:
                continue
            if str(data.get("httpstatus")) != "200":
                continue
            result_data = data.get("data") or {}
            rows = result_data.get("result") or []
            if rows:
                return rows
        return None

    def query(self, from_city: str, to_city: str, train_date: str, seat_type: str = "", max_trains: int = 8) -> str:
        """查询实时火车票，返回与数据库查询一致的 JSON 字符串。"""
        from_city = (from_city or "").strip()
        to_city = (to_city or "").strip()
        train_date = (train_date or "").strip()
        seat_type = (seat_type or "").strip()
        max_trains = max(1, min(int(max_trains), 12))

        if not from_city or not to_city or not train_date:
            return json.dumps(
                {"status": "error", "message": "实时火车票查询缺少出发城市、到达城市或日期。"},
                ensure_ascii=False,
            )

        from_code = self.resolve_station_code(from_city)
        to_code = self.resolve_station_code(to_city)
        if not from_code or not to_code:
            return json.dumps(
                {"status": "error", "message": "未能识别出发或到达车站，请使用更明确的站名，如“北京南”“上海虹桥”。"},
                ensure_ascii=False,
            )

        rows = self._query_left_rows(from_code, to_code, train_date)
        if rows is None:
            return json.dumps(
                {"status": "error", "message": "12306 实时余票接口暂时不可用，请稍后重试。"},
                ensure_ascii=False,
            )
        if not rows:
            return json.dumps(
                {"status": "no_data", "message": "12306 未查询到该日期、该区间的实时车票，请更换日期或车站。"},
                ensure_ascii=False,
            )

        result = []
        train_count = 0
        for row in rows:
            if train_count >= max_trains:
                break
            fields = row.split("|")
            if len(fields) < 34:
                continue
            train_count += 1
            seats = self._parse_seat_availability(fields)
            if not seats:
                continue

            from_station_code = fields[6]
            to_station_code = fields[7]
            from_station_name = self.resolve_station_name(from_station_code)
            to_station_name = self.resolve_station_name(to_station_code)
            departure_time = self._full_datetime(train_date, fields[8])
            arrival_time = self._full_datetime(train_date, fields[9], next_day=fields[9] < fields[8])

            base = {
                "departure_city": from_city,
                "arrival_city": to_city,
                "departure_time": departure_time,
                "arrival_time": arrival_time,
                "duration": fields[10],
                "train_number": fields[3],
                "from_station": from_station_name,
                "to_station": to_station_name,
                "source": "12306实时",
            }

            prices = self._fetch_prices(fields, train_date)
            available_seats = seats
            if seat_type:
                if seat_type not in seats:
                    continue
                available_seats = {seat_type: seats[seat_type]}

            for label, remaining in available_seats.items():
                record = dict(base)
                record["seat_type"] = label
                record["remaining_seats"] = remaining
                record["price"] = prices.get(label)
                result.append(record)

        if not result:
            message = f"12306 实时查询暂无“{seat_type}”余票。" if seat_type else "12306 实时查询暂无余票。"
            return json.dumps({"status": "no_data", "message": message}, ensure_ascii=False)

        return json.dumps(
            {
                "status": "success",
                "source": "12306实时",
                "message": "数据来源：12306 官方公开查询接口。",
                "data": result,
            },
            ensure_ascii=False,
        )


if __name__ == "__main__":
    service = RealtimeTrainTicketService()
    print(service.query("北京", "上海", "2026-10-04", "二等座", max_trains=2))
