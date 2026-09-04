"""ProxyIP_91http 爬虫调用封装

本模块在 sys.path 中注入 SpiderServices 目录后，导入 ProxyIP91http 进行包装:
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

from ProxyIp.ProxyIP_91http.home import ProxyIP91http


def get_91http_proxies(num: int = 10, protocol: int = None, auto_white: int = None,
                        time: int = None, username: str = None, password: str = None) -> tuple:
    """获取 91HTTP 动态代理IP

    每次调用创建新实例（Session 无状态）。订单号/密钥由平台侧 .env 唯一持有，
    调用方不可覆盖。

    :param num: 返回 IP 数量，默认 10，必须 >= 1
    :param protocol: 协议类型，1=HTTP 2=HTTPS 3=SOCKS5 4=HTTP(S)
    :param auto_white: 自动添加白名单，1=是 0=否
    :param time: 返回过期时间，1=是 0=否
    :param username: 认证用户名（账号密码认证，需与 password 同时传）
    :param password: 认证密码（账号密码认证，需与 username 同时传）
    :return: (True, dict) 或 (False, error_msg)
    """
    try:
        spider = ProxyIP91http()
        kwargs = {"num": num}
        if protocol is not None:
            kwargs["protocol"] = protocol
        if auto_white is not None:
            kwargs["auto_white"] = auto_white
        if time is not None:
            kwargs["time"] = time
        if username:
            kwargs["username"] = username
        if password:
            kwargs["password"] = password
        # get_proxies 参数签名为 (pages=1, page_size=None, **kwargs)
        result = spider.get_proxies(pages=1, page_size=None, **kwargs)
        return True, result
    except Exception as e:
        return False, f'get_91http_proxies 调用异常: {e}'
