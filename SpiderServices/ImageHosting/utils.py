"""
图床服务 - 公共工具模块

提供统一的响应格式与请求头生成，供 home.py 及各线路子模块复用。
本模块不依赖任何业务逻辑，可被独立导入。
"""

from SpiderServices.common.user_agents import DESKTOP_UAS, get_desktop_headers, response_dict
