#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
文件名: mcp_ticket_server.py
作者: ZZS
项目: LlmProject
创建日期: 2026/2/4
描述: 
"""
import mysql.connector
import json
import re
from datetime import date, datetime, timedelta
from decimal import Decimal
from mcp.server.fastmcp import FastMCP

from SmartVoyage.config import Config
from SmartVoyage.create_logger import logger
from SmartVoyage.utils.format import DateEncoder, default_encoder
from SmartVoyage.query_data.query1 import TicketService
from SmartVoyage.query_data.realtime_train_service import RealtimeTrainTicketService

conf = Config()
realtime_ticket_service = RealtimeTrainTicketService()


def _extract_train_query_params(sql: str) -> dict | None:
    """从票务 SQL 中提取火车票实时查询参数。"""
    if not sql or "train_tickets" not in sql.lower():
        return None

    def _get(pattern: str):
        match = re.search(pattern, sql, re.IGNORECASE)
        return match.group(1).strip() if match else None

    departure_city = _get(r"departure_city\s*=\s*['\"]([^'\"]*)['\"]")
    arrival_city = _get(r"arrival_city\s*=\s*['\"]([^'\"]*)['\"]")
    train_date = _get(r"DATE\s*\(\s*departure_time\s*\)\s*=\s*['\"]([^'\"]*)['\"]")
    if not train_date:
        train_date = _get(r"departure_time\s*(?:>=|>|=)\s*['\"]([^'\"]*)['\"]")
    seat_type = _get(r"seat_type\s*=\s*['\"]([^'\"]*)['\"]")

    if not departure_city or not arrival_city or not train_date:
        return None
    return {
        "from_city": departure_city,
        "to_city": arrival_city,
        "train_date": train_date,
        "seat_type": seat_type or "",
    }


# 创建票务MCP服务器
def create_ticket_mcp_server():
    # 创建FastMCP实例
    ticket_mcp = FastMCP(name="TicketTools",
                         instructions="票务查询工具。火车票优先走 12306 实时余票/票价接口；机票和演唱会票查询本地数据库。只支持查询。",
                         log_level="ERROR",
                         host="127.0.0.1", port=8001)

    # 实例化票务服务对象
    service = TicketService()

    @ticket_mcp.tool(
        name="query_tickets",
        description="查询票务数据，输入 SQL，如 'SELECT * FROM train_tickets WHERE departure_city = \"北京\" AND arrival_city = \"上海\"'"
    )
    def query_tickets(sql: str) -> str:
        train_params = _extract_train_query_params(sql)
        if train_params:
            logger.info(f"火车票查询切换为 12306 实时接口：{train_params}")
            return realtime_ticket_service.query(**train_params)
        logger.info(f"执行票务查询: {sql}")
        return service.execute_query(sql)

    @ticket_mcp.tool(
        name="query_realtime_tickets",
        description="实时查询 12306 火车票余票和票价。参数：from_city 出发城市，to_city 到达城市，train_date 日期（YYYY-MM-DD），seat_type 可选座席（如二等座、硬卧）。"
    )
    def query_realtime_tickets(from_city: str, to_city: str, train_date: str, seat_type: str = "") -> str:
        return realtime_ticket_service.query(
            from_city=from_city,
            to_city=to_city,
            train_date=train_date,
            seat_type=seat_type,
        )

    # 打印服务器信息
    logger.info("=== 票务MCP服务器信息 ===")
    logger.info(f"名称: {ticket_mcp.name}")
    logger.info(f"描述: {ticket_mcp.instructions}")

    # 运行服务器
    try:
        print("服务器已启动，请访问 http://127.0.0.1:8001/mcp")
        ticket_mcp.run(transport="streamable-http")  # 使用 streamable-http 传输方式
    except Exception as e:
        print(f"服务器启动失败: {e}")

create_ticket_mcp_server()
