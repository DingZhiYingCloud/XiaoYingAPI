"""ProxyIP_juliang 爬虫调用封装

本模块在 sys.path 中注入 SpiderServices 目录后，导入 ProxyIPJuliang 进行包装:
- 每次调用创建新的爬虫实例（无状态、线程安全）
- 统一捕获异常，返回 (success, data_or_msg) 二元组
- 透传参数表复用爬虫层定义（utils.PASSTHROUGH_ENUM / PASSTHROUGH_TEXT），避免两处维护
"""
import sys
import os

# 注入 SpiderServices 到 sys.path，使相对导入正常工作
_SPIDER_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__),
    '..', '..', '..', '..', 'SpiderServices'))
if _SPIDER_ROOT not in sys.path:
    sys.path.insert(0, _SPIDER_ROOT)

from ProxyIp.ProxyIP_juliang.home import ProxyIPJuliang
from ProxyIp.ProxyIP_juliang.utils import (MAX_NUM, PASSTHROUGH_ENUM,
                                           PASSTHROUGH_TEXT)


def get_juliang_proxies(trade_no: str = None, key: str = None, sign: str = None,
                        num: int = None, extras: dict = None, username: str = None,
                        password: str = None) -> tuple:
    """获取巨量代理动态 IP

    凭据优先取调用方传入（trade_no / key / sign），未传则回退平台 .env。
    key 模式由服务端代算签名（可自由传其它业务参数）；sign 模式参数原样透传。

    :param trade_no: 业务编号（可选）
    :param key: 业务密钥（可选，与 sign 二选一）
    :param sign: 调用方自算签名（可选，与 key 二选一）
    :param num: 提取数量（可选，最大 100）
    :param extras: 透传业务参数（pt/split/auto_white/area/isp/filter 等）
    :param username: 代理认证账号（可选，与 password 成对）
    :param password: 代理认证密码（可选，与 username 成对）
    :return: (True, dict) 或 (False, error_msg)
    """
    try:
        spider = ProxyIPJuliang()
        # get_proxies 参数签名为 (pages=1, page_size=None, **kwargs)
        result = spider.get_proxies(pages=1, page_size=None, trade_no=trade_no, key=key,
                                    sign=sign, num=num, username=username, password=password,
                                    **(extras or {}))
        return True, result
    except Exception as e:
        return False, f'get_juliang_proxies 调用异常: {e}'
