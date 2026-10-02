"""ProxyIP_51daili 爬虫调用封装

本模块在 sys.path 中注入 SpiderServices 目录后，导入 ProxyIP51Daili 进行包装:
- 每次调用创建新的爬虫实例（无状态、线程安全）
- 统一捕获异常，返回 (success, data_or_msg) 二元组

参数名沿用 51代理 官方提取链接里的写法（uid / accessName / accessPassword / packid / pid /
rid / qty / time / port / format / field / linePoolIndex），调用方可直接照抄控制台生成的
链接，不必做名字换算。其中 `pid` 是不限量套餐 ID，**本接口必填**（缺了上游回
「不限量套餐id不能为空」）。

⚠️ 数量参数是 `qty`（不是 `num`）：非白名单参数会被静默忽略、悄悄回退成 1 条，
调用方写错名字不会报错（巨量线路才是 `num`）。
"""
import os
import sys

# 注入 SpiderServices 到 sys.path，使相对导入正常工作
_SPIDER_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__),
    '..', '..', '..', '..', 'SpiderServices'))
if _SPIDER_ROOT not in sys.path:
    sys.path.insert(0, _SPIDER_ROOT)

from SpiderServices import relay_proxy

from ProxyIp.ProxyIP_51daili.home import ProxyIP51Daili

# 允许传给爬虫的参数白名单（视图按本表从 query 里取值，避免拼错名字后被静默忽略、
# 悄悄回退到平台 .env 凭据）
PARAM_NAMES = ('uid', 'accessName', 'accessPassword', 'packid', 'pid', 'rid',
               'qty', 'port', 'time', 'format', 'field', 'linePoolIndex')


def _attach_relay_proxy(result: dict) -> None:
    """给每条代理补上可直接使用的「中转形态」地址（未配置中转时原样返回）

    为什么要有它：51代理 的节点**只从中国内地网络可达** —— 海外服务器拿正确账密直连
    也一律 TCP 超时（实测 0/5），而接入项目基本都在海外，只给 ip/port 等于给了一串
    用不了的地址。故把「经国内中转」的形态一并下发：条目里的 `proxy` 可直接塞进
    requests 的 proxies（`{'http': proxy, 'https': proxy}`），由中转机去连 51代理 节点
    再回传数据；`ip`/`port` 仍保留，中国内地的调用方照旧可以直连。

    注意：中转形态的出口节点由中转机从**同一个 51代理 账号**实时取，与条目里的
    ip/port 不保证是同一条 —— ip/port/region 等字段描述的是「直连形态会拿到什么」。
    """
    if not relay_proxy.enabled():
        return
    entries = ((result or {}).get('data') or {}).get('proxies') or []
    for entry in entries:
        if isinstance(entry, dict):
            # 每条一个会话键 → 每条一个独立出口，保持「要 N 条就是 N 个出口」的语义
            entry['proxy'] = relay_proxy.build_url()


def get_51daili_proxies(params: dict) -> tuple:
    """获取 51代理动态 IP

    账号级参数（uid / accessName / accessPassword / packid / pid）成组使用：整组传入则用
    调用方的，整组不传则回退平台 .env（只传一部分会被拒绝）；rid 与其余参数未传则用默认值。

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
    except Exception as e:
        return False, f'get_51daili_proxies 调用异常: {e}'
    _attach_relay_proxy(result)
    return True, result
