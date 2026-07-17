"""
静态代理IP - 辅助工具模块

提供静态代理IP相关的常量配置。
"""

import os

# 默认 JSON 文件路径（相对于本模块目录）
DEFAULT_JSON = os.path.join(os.path.dirname(__file__), "proxies.json")
