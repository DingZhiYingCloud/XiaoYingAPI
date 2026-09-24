"""ProxyIP_qy_res 爬虫调用封装

本模块在 sys.path 中注入 SpiderServices 目录后，导入 ProxyIPQyRes 进行包装:
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

from ProxyIp.ProxyIP_qy_res.home import ProxyIPQyRes


def get_qy_res_proxies(host: str = None, port: str = None, username: str = None,
                       password: str = None, verify: bool = False) -> tuple:
    """获取青雨住宅长效代理地址

    连接主机 / 端口 / 账号 / 密码优先取调用方传入（用户自己购买的节点），
    均未传则回退平台 .env 默认值。

    :param host: 连接主机（可选）
    :param port: 端口（可选）
    :param username: 账号（可选，与 password 成对）
    :param password: 密码（可选，与 username 成对）
    :param verify: 是否真实经代理发一次请求验证可用性（默认 False）
    :return: (True, dict) 或 (False, error_msg)
    """
    try:
        spider = ProxyIPQyRes()
        # get_proxies 参数签名为 (pages=1, page_size=None, **kwargs)
        result = spider.get_proxies(pages=1, page_size=None, host=host, port=port,
                                    username=username, password=password, verify=verify)
        return True, result
    except Exception as e:
        return False, f'get_qy_res_proxies 调用异常: {e}'
