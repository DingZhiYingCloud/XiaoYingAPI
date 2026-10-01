"""ProxyIP_51daili 爬虫调用封装

本模块在 sys.path 中注入 SpiderServices 目录后，导入 ProxyIP51Daili 进行包装:
- 每次调用创建新的爬虫实例（无状态、线程安全）
- 统一捕获异常，返回 (success, data_or_msg) 二元组

参数名沿用 51代理 官方提取链接里的写法（uid / accessName / accessPassword / packid /
rid / qty / time / port / format / field / linePoolIndex），调用方可直接照抄控制台生成的
链接，不必做名字换算。
"""
import os
import sys

# 注入 SpiderServices 到 sys.path，使相对导入正常工作
_SPIDER_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__),
    '..', '..', '..', '..', 'SpiderServices'))
if _SPIDER_ROOT not in sys.path:
    sys.path.insert(0, _SPIDER_ROOT)

from ProxyIp.ProxyIP_51daili.home import ProxyIP51Daili

# 允许传给爬虫的参数白名单（视图按本表从 query 里取值，避免拼错名字后被静默忽略、
# 悄悄回退到平台 .env 凭据）
PARAM_NAMES = ('uid', 'accessName', 'accessPassword', 'packid', 'rid',
               'qty', 'port', 'time', 'format', 'field', 'linePoolIndex')


def get_51daili_proxies(params: dict) -> tuple:
    """获取 51代理动态 IP

    账号级参数（uid / accessName / accessPassword / packid / rid）优先取调用方传入，
    未传则回退平台 .env；其余参数未传则用服务层默认值。

    :param params: 请求参数字典，取值键见 PARAM_NAMES
    :return: (True, dict) 或 (False, error_msg)
    """
    unknown = [name for name in (params or {}) if name not in PARAM_NAMES]
    if unknown:
        return False, f'参数值非法: 不支持的参数 {" / ".join(unknown)}'
    try:
        spider = ProxyIP51Daili()
        # get_proxies 参数签名为 (pages=1, page_size=None, **kwargs)
        result = spider.get_proxies(pages=1, page_size=None, **(params or {}))
        return True, result
    except Exception as e:
        return False, f'get_51daili_proxies 调用异常: {e}'
