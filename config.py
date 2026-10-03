#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
文件名: config.py
描述: 配置管理。敏感信息（API Key、数据库密码）从 .env 读取，
      非敏感配置从 config.ini 读取，并保留旧版属性名以兼容现有代码。
"""

import os
import configparser

from dotenv import load_dotenv

# 项目根目录（config.py 所在目录，即 SmartVoyage 包目录）
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

# 优先加载 .env 中的敏感配置
load_dotenv(os.path.join(PROJECT_ROOT, '.env'))

# 非敏感配置兜底文件
CONFIG_FILE = os.path.join(PROJECT_ROOT, 'config.ini')


class Config:
    """统一的配置访问入口，保持与旧版 Config 相同的属性名。"""

    def __init__(self, config_file=CONFIG_FILE):
        self.config = configparser.ConfigParser()
        if os.path.exists(config_file):
            self.config.read(config_file, encoding='utf-8')

        # 大模型配置：敏感项优先取环境变量，其次取 config.ini，最后取默认值
        self.base_url = os.getenv('LLM_BASE_URL', self._get('llm', 'base_url', 'https://api.deepseek.com'))
        self.api_key = os.getenv('LLM_API_KEY', self._get('llm', 'api_key', ''))
        self.model_name = os.getenv('LLM_MODEL', self._get('llm', 'model', 'deepseek-chat'))
        self.temperature = float(self._get('llm', 'temperature', '0.1'))

        # 数据库配置
        self.host = os.getenv('MYSQL_HOST', self._get('mysql', 'host', 'localhost'))
        self.port = int(os.getenv('MYSQL_PORT', self._get('mysql', 'port', '3306')))
        self.user = os.getenv('MYSQL_USER', self._get('mysql', 'user', 'root'))
        self.password = os.getenv('MYSQL_PASSWORD', self._get('mysql', 'password', ''))
        self.database = os.getenv('MYSQL_DATABASE', self._get('mysql', 'database', 'travel_rag'))

        # 日志配置
        self.log_file = os.getenv('LOG_FILE', os.path.join(PROJECT_ROOT, 'logs', 'app.log'))

        # 票务查询的12306接口地址（预留）
        self.url_123 = ""

        # 意图到代理的映射
        self.intent = {
            "weather": "WeatherQueryAssistant",
            "flight": "TicketQueryAssistant",
            "train": "TicketQueryAssistant",
            "concert": "TicketQueryAssistant",
            "order": "TicketOrderAssistant"
        }

    def _get(self, section, key, fallback=''):
        """读取 config.ini 指定项，缺失时返回默认值。"""
        return self.config.get(section, key, fallback=fallback)

    def get_mysql_config(self, env='test'):
        """按环境返回数据库配置，兼容旧接口（当前统一从 .env/config.ini 读取）。"""
        return self.host, self.user, self.password, self.database


if __name__ == '__main__':
    conf = Config()
    print('log_file:', conf.log_file)
    print('mysql:', conf.get_mysql_config())
