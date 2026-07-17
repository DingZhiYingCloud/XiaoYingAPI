"""ProxyIP 代理IP服务 API 调用封装

本模块在 sys.path 中注入 SpiderServices 目录后，导入 ProxyIPService 进行包装:
- 每次调用创建新的服务实例（无状态、线程安全）
- 统一捕获异常，返回 (success, data_or_msg) 二元组
"""
import sys
import os

# 注入 SpiderServices 到 sys.path，使相对导入正常工作
_SPIDER_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__),
    '..', '..', '..', '..', 'SpiderServices'))
if _SPIDER_ROOT not in sys.path:
    sys.path.insert(0, _SPIDER_ROOT)

from ProxyIp.home import ProxyIPService


def get_available_proxies(count: int = 10, sources: list = None, verify: bool = True) -> tuple:
    """获取可用的代理IP列表

    :param count: 需要返回的代理数量（默认 10）
    :param sources: 代理源名称列表（默认 ["66daili"]）
    :param verify: 是否验证代理可用性（默认 True）
    :return: (True, dict) 或 (False, error_msg)
    """
    service = ProxyIPService()
    try:
        result = service.get_available_proxies(count=count, sources=sources, verify=verify)
        return True, result
    except Exception as e:
        return False, f'get_available_proxies 调用异常: {e}'
