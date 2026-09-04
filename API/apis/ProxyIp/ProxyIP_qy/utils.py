"""ProxyIP_qy 爬虫调用封装

本模块在 sys.path 中注入 SpiderServices 目录后，导入 ProxyIPQy 进行包装:
- 每次调用创建新的爬虫实例（无状态、线程安全）
- 统一捕获异常，返回 (success, data_or_msg) 二元组
"""
import sys
import os

# 注入 SpiderServices 到 sys.path，使相对导入正常工作
_SPIDER_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__),
    '..', '..', '..', '..', 'SpiderServices'))
if _SPIDER_ROOT not in sys.path:
    sys.path.insert(0, _SPIDER_ROOT)

from ProxyIp.ProxyIP_qy.home import ProxyIPQy


def get_qy_proxies(num: int = 1) -> tuple:
    """获取青雨动态代理IP

    每次调用创建新实例（Session 无状态）。订单号/账户 token 由平台侧 .env 唯一持有，
    调用方不可覆盖。

    :param num: 返回 IP 数量，默认 1，必须 >= 1
    :return: (True, dict) 或 (False, error_msg)
    """
    try:
        spider = ProxyIPQy()
        # get_proxies 参数签名为 (pages=1, page_size=None, **kwargs)
        result = spider.get_proxies(pages=1, page_size=None, num=num)
        return True, result
    except Exception as e:
        return False, f'get_qy_proxies 调用异常: {e}'
