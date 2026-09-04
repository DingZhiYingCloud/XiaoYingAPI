"""
91HTTP 动态代理爬虫 - ProxyIP91http

从 91HTTP（api.91http.com）API 获取国内动态代理。

API 文档:
    URL: http://api.91http.com/v1/get-ip
    参数说明:
        trade_no    订单号，必填
        secret      密钥，必填
        num         单次返回 IP 数量，必填
        protocol    协议类型，1=HTTP 2=HTTPS 3=SOCKS5 4=HTTP(S)
        format      返回格式，json 或 text，默认 json
        sep         分隔符，1=换行 2=空格 3=逗号 4=回车
        auto_white  自动添加白名单，1=是 0=否
        time        返回过期时间，1=是 0=否

响应格式:
    {
      "code": 0,
      "msg": "OK",
      "data": {
        "count": 2,
        "filter_count": 0,
        "surplus_quantity": 0,
        "proxy_list": [
          {"expire_time": "2026-07-31 07:48:27", "ip": "220.161.240.6", "port": 33999}
        ]
      }
    }

使用示例:
    spider = ProxyIP91http()
    result = spider.get_proxies(count=5)
    # 自定义参数
    result = spider.get_proxies(count=10, trade_no="xxx", secret="xxx")
"""

import requests

from .utils import API_URL, DEFAULT_TRADE_NO, DEFAULT_SECRET, REQUEST_TIMEOUT
from ..utils import get_desktop_headers, response_dict


class ProxyIP91http:
    """91HTTP 动态代理爬虫"""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(get_desktop_headers())

    def get_proxies(self, pages: int = 1, page_size: int = None, **kwargs) -> dict:
        """
        从 91HTTP API 获取动态代理。

        :param pages: 忽略（API 无分页概念），使用 count 替代
        :param page_size: 忽略
        :param kwargs: 可选业务参数（凭据固定取 .env 配置，禁止调用方覆盖）:
            - num: int, 返回 IP 数量（默认 10）
            - protocol: int, 协议类型（默认 1=HTTP）
            - format: str, 返回格式（默认 json）
            - sep: int, 分隔符（默认 1=换行）
            - auto_white: int, 自动添加白名单（默认 1）
            - time: int, 返回过期时间（默认 1）
            - username: str, 认证用户名（账号密码认证，无需白名单）
            - password: str, 认证密码（账号密码认证，无需白名单）
        :return: dict 含:
            - code: 0 成功，1 失败
            - message: 描述信息
            - data: {
                proxies: [{ip, port, protocol, region, expire_time, proxy?}, ...],
                total: 返回总数,
                fetched: 返回数,
              }
            其中 proxy 仅在传入 username+password 时生成，
            格式: http://username:password@ip:port（可直接用于 requests proxies）
        """
        if not (DEFAULT_TRADE_NO and DEFAULT_SECRET):
            return response_dict(
                code=1,
                message="91HTTP 代理凭据未配置：请在 .env 设置 PROXY_91HTTP_TRADE_NO / PROXY_91HTTP_SECRET",
                data={"proxies": [], "total": 0, "fetched": 0},
            )
        # 构建请求参数（trade_no/secret 固定取 .env 配置，不接收调用方覆盖）
        params = {
            "trade_no": DEFAULT_TRADE_NO,
            "secret": DEFAULT_SECRET,
            "num": kwargs.get("num", 10),
            "protocol": kwargs.get("protocol", 1),
            "format": kwargs.get("format", "json"),
            "sep": kwargs.get("sep", 1),
            "auto_white": kwargs.get("auto_white", 1),
            "time": kwargs.get("time", 1),
        }
        # 账号密码认证参数（可选，传了则无需白名单）
        username = kwargs.get("username")
        password = kwargs.get("password")
        if username:
            params["username"] = username
        if password:
            params["password"] = password
        # num 确保整数且 >= 1
        try:
            params["num"] = max(1, int(params["num"]))
        except (ValueError, TypeError):
            params["num"] = 10

        try:
            resp = self.session.get(API_URL, params=params, timeout=REQUEST_TIMEOUT)
            resp.encoding = "utf-8"
            data = resp.json()
        except (requests.RequestException, ValueError) as e:
            return response_dict(
                code=1,
                message=f"请求 91HTTP API 失败: {e}",
                data={"proxies": [], "total": 0, "fetched": 0},
            )

        # 解析响应
        code = data.get("code")
        if code != 0:
            msg = data.get("msg", data.get("message", f"API 返回错误码 {code}"))
            return response_dict(
                code=1,
                message=msg,
                data={"proxies": [], "total": 0, "fetched": 0},
            )

        proxy_list = data.get("data", {}).get("proxy_list", [])
        proxies = self._parse_proxy_list(proxy_list, username=username, password=password)

        return response_dict(
            code=0,
            message=f"成功获取 {len(proxies)} 条动态代理",
            data={"proxies": proxies, "total": len(proxies), "fetched": len(proxies)},
        )

    @staticmethod
    def _parse_proxy_list(items: list, username: str = None, password: str = None) -> list:
        """
        解析 proxy_list 数组。

        字段格式: {"ip": "x.x.x.x", "port": xxxx, "expire_time": "..."}

        :param items: proxy_list 数组
        :param username: 认证用户名（可选）
        :param password: 认证密码（可选）
        :return: [{ip, port, protocol, region, expire_time, proxy?}, ...]
                 当 username+password 均传入时，额外生成 proxy 字段:
                 http://username:password@ip:port（账号密码认证，无需白名单）
        """
        # 账号密码认证：二者需同时存在才生成带认证的代理 URL
        has_auth = bool(username and password)
        proxies = []
        for item in items:
            if not isinstance(item, dict):
                continue
            ip = str(item.get("ip", "")).strip()
            port_raw = item.get("port", "")
            port = str(port_raw).strip() if port_raw else ""
            expire_time = str(item.get("expire_time", "")).strip()

            if not ip or not port:
                continue
            port = port.split(".")[0]

            proxy_item = {
                "ip": ip,
                "port": port,
                "protocol": "HTTP",
                "region": "国内动态",
                "expire_time": expire_time,
            }
            if has_auth:
                proxy_item["proxy"] = f"http://{username}:{password}@{ip}:{port}"

            proxies.append(proxy_item)
        return proxies
