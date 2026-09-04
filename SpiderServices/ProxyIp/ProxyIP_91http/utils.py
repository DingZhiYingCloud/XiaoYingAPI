"""
91HTTP 代理 - 辅助工具模块

提供 91HTTP（api.91http.com）动态代理相关的常量配置。
订单号/密钥从 .env 读取（PROXY_91HTTP_TRADE_NO/PROXY_91HTTP_SECRET），禁止硬编码。
"""
import os

from dotenv import load_dotenv

load_dotenv()

# API 基础地址
API_URL = "http://api.91http.com/v1/get-ip"

# 默认参数（对应购买订单，从 .env 读取）
DEFAULT_TRADE_NO = os.getenv("PROXY_91HTTP_TRADE_NO", "") or ""
DEFAULT_SECRET = os.getenv("PROXY_91HTTP_SECRET", "") or ""

# 请求超时（秒）
REQUEST_TIMEOUT = 15
