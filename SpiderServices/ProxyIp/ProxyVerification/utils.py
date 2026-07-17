"""
代理IP验证 - 辅助工具模块

提供代理IP验证相关的常量配置和工具函数。
"""

# 验证测试 URL（能返回请求来源 IP 即可）
VERIFY_URL_HTTP = "http://httpbin.org/ip"
VERIFY_URL_HTTPS = "https://httpbin.org/ip"
VERIFY_URL_BACKUP = "https://api.ipify.org?format=json"

# 单次验证超时（秒）
VERIFY_TIMEOUT = 10

# 支持的代理协议
PROXY_PROTOCOLS = ("http", "https", "socks4", "socks5")
