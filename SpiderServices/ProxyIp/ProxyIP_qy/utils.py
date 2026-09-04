"""
青雨代理 - 辅助工具模块

提供青雨（qydailiip.com）动态短期代理相关的常量配置。
订单号/账户 token 从 .env 读取（PROXY_QY_ORDER/PROXY_QY_APIKEY），禁止硬编码。
"""
import os

from dotenv import load_dotenv

load_dotenv()

# API 基础地址
API_URL = "http://diy.qydailiip.com/api/ip/api"

# 默认参数（对应购买订单，从 .env 读取）
DEFAULT_ORDER = os.getenv("PROXY_QY_ORDER", "") or ""
DEFAULT_APIKEY = os.getenv("PROXY_QY_APIKEY", "") or ""

# 请求超时（秒）
REQUEST_TIMEOUT = 15
