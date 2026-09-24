"""
青雨动态代理爬虫 - ProxyIPQy

从青雨代理（qydailiip.com）API 获取国内动态短期代理IP（存活 1-3 分钟）。

API 文档:
    URL: http://diy.qydailiip.com/api/ip/api
    参数说明:
        order   订单号，必填
        num     单次返回 IP 数量，必填
        sep     换行符，支持 \n \r\n | 三种，默认 \n
        type    返回格式，json 或 text，默认 json
        end_time 是否返回失效时间，1=返回 0=不返回，默认 1（仅 json 格式生效）
        apikey  账户 token，必填

使用示例:
    spider = ProxyIPQy()
    result = spider.get_proxies(pages=1)  # 返回 1 条（默认 num=1）
    result = spider.get_proxies(count=5)  # 返回 5 条
    # 调用方使用自己购买的订单（不传则用 .env 默认订单）
    result = spider.get_proxies(num=5, order="2026xxxx", apikey="xxxx")
"""

import requests

from .utils import API_URL, DEFAULT_ORDER, DEFAULT_APIKEY, REQUEST_TIMEOUT
from ..utils import get_desktop_headers, response_dict


class ProxyIPQy:
    """青雨动态代理爬虫（存活 1-3 分钟）"""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(get_desktop_headers())

    def get_proxies(self, pages: int = 1, page_size: int = None, **kwargs) -> dict:
        """
        从青雨代理 API 获取短期动态代理。

        :param pages: 忽略（API 无分页概念），使用 count 替代
        :param page_size: 忽略
        :param kwargs: 可选业务参数:
            - order: str, 青雨订单号（默认取 .env PROXY_QY_ORDER；调用方可传自己的订单）
            - apikey: str, 账户 token（默认取 .env PROXY_QY_APIKEY；与 order 必须成对出现）
            - num: int, 返回IP数量（默认 1）
            - sep: str, 换行符（默认 \\n）
            - type: str, 返回格式 json/text（默认 json）
            - end_time: int, 是否返回失效时间 1/0（默认 1）
        :return: dict 含:
            - code: 0 成功，1 失败
            - message: 描述信息
            - data: {
                proxies: [{ip, port, protocol, region, end_time}, ...],
                total: 返回总数,
                fetched: 返回数,
              }
        """
        # 订单号 / apikey 按「整对」处理：调用方都没传 → 用 .env 默认整对；
        # 只传一个 → 非法。允许调用方使用自己购买的订单。
        order = str(kwargs.get("order") or "").strip()
        apikey = str(kwargs.get("apikey") or "").strip()
        if not order and not apikey:
            order, apikey = DEFAULT_ORDER, DEFAULT_APIKEY
        elif not (order and apikey):
            return response_dict(
                code=1,
                message="参数缺失: order 和 apikey 必须同时传入",
                data={"proxies": [], "total": 0, "fetched": 0},
            )
        if not (order and apikey):
            return response_dict(
                code=1,
                message="青雨代理凭据未配置：请在 .env 设置 PROXY_QY_ORDER / PROXY_QY_APIKEY，"
                        "或由调用方传入 order / apikey",
                data={"proxies": [], "total": 0, "fetched": 0},
            )
        # 构建请求参数（调用方未传凭据时取 .env 默认订单）
        params = {
            "order": order,
            "num": kwargs.get("num", 1),
            "sep": kwargs.get("sep", "\\n"),
            "type": kwargs.get("type", "json"),
            "end_time": kwargs.get("end_time", 1),
            "apikey": apikey,
        }
        # num 确保整数且 >= 1
        try:
            params["num"] = max(1, int(params["num"]))
        except (ValueError, TypeError):
            params["num"] = 1

        try:
            resp = self.session.get(API_URL, params=params, timeout=REQUEST_TIMEOUT)
            resp.encoding = "utf-8"
            data = resp.json()
        except (requests.RequestException, ValueError) as e:
            return response_dict(
                code=1,
                message=f"请求青雨代理 API 失败: {e}",
                data={"proxies": [], "total": 0, "fetched": 0},
            )

        # 响应是直接 JSON 数组 [{"proxy":"ip:port","start":"...","end":"..."}, ...]
        if isinstance(data, list):
            proxies = self._parse_json_items(data)
        elif isinstance(data, dict):
            # 也兼容 {"code": 0, "data": [...]} 格式
            code = data.get("code", -1)
            msg = str(data.get("msg") or data.get("message") or "").strip()
            # 青雨在订单到期 / 凭据错误时仍返回 code=0，只在 msg 里以 ERROR 开头提示（data 为空），
            # 需按失败处理，否则调用方只会看到「成功获取 0 条」而拿不到真实原因
            if code != 0 or "ERROR" in msg.upper():
                detail = msg.split(":", 1)[-1].strip() if ":" in msg else msg
                return response_dict(
                    code=1,
                    message=detail or f"API 返回错误码 {code}",
                    data={"proxies": [], "total": 0, "fetched": 0},
                )
            items = data.get("data", data.get("list", []))
            proxies = self._parse_json_items(items)
        else:
            return response_dict(
                code=1,
                message=f"无法识别的 API 响应格式: {type(data).__name__}",
                data={"proxies": [], "total": 0, "fetched": 0},
            )

        return response_dict(
            code=0,
            message=f"成功获取 {len(proxies)} 条动态代理（存活 1-3 分钟）",
            data={"proxies": proxies, "total": len(proxies), "fetched": len(proxies)},
        )

    @staticmethod
    def _parse_json_items(items: list) -> list:
        """
        解析 JSON 数组中的代理项。

        支持三种格式:
            字段格式: {"proxy": "ip:port", "start": "...", "end": "..."}
            对象格式: {"ip": "x.x.x.x", "port": xxxx, "end_time": "..."}
            字符串格式: "x.x.x.x:xxxx"

        :param items: JSON 数组
        :return: [{ip, port, protocol, region, end_time}, ...]
        """
        proxies = []
        for item in items:
            if isinstance(item, dict):
                # 字段格式: {"proxy": "ip:port", ...}
                if item.get("proxy"):
                    parts = str(item["proxy"]).strip().split(":")
                    if len(parts) >= 2:
                        ip, port = parts[0], parts[1]
                        end_time = str(item.get("end", item.get("end_time", ""))).strip()
                    else:
                        continue
                else:
                    # 对象格式: {"ip": "x.x.x.x", "port": xxxx}
                    ip = str(item.get("ip", "")).strip()
                    port_raw = item.get("port", "")
                    port = str(port_raw).strip() if port_raw else ""
                    end_time = str(item.get("end_time", "")).strip()
            elif isinstance(item, str):
                parts = item.strip().split(":")
                if len(parts) == 2:
                    ip, port = parts
                    end_time = ""
                else:
                    continue
            else:
                continue

            if not ip or not port:
                continue
            # port 转为纯数字字符串
            port = port.split(".")[0]  # 处理浮点数端口（如 "8080.0"）

            proxies.append({
                "ip": ip,
                "port": port,
                "protocol": "HTTP",
                "region": "国内动态",
                "end_time": end_time,
            })
        return proxies
