"""
巨量代理爬虫 - ProxyIPJuliang

从巨量代理（juliangip.com）「独享代理」提取接口获取国内动态代理 IP。

API 文档:
    URL:      http://v2.api.juliangip.com/unlimited/getips
              （可用 .env 的 PROXY_JULIANG_API_BASE 覆盖：巨量只向国内 IP 提供提取服务，
                海外部署需指向国内中转，路径与参数不变，签名不受影响）
    请求方式: GET / POST（本线路用 GET）
    参数说明:
        trade_no  业务编号，必填
        num       单次提取数量，必填，最大 100
        pt        代理类型 1=HTTP（默认）2=SOCKS
        result_type 返回格式 text/json/xml（本线路只用 json 或 text）
        split     文本模式分隔符 1=\\r\\n（默认）2=\\n 3=空格 4=|
        auto_white 提取时自动把调用方 IP 加入白名单 1=是
        area / isp 按地区 / 运营商筛选
        filter    过滤今天已提取过的 IP 1=是
        city_name / city_code / ip_remain / auth_info 附带城市 / 邮编 / 剩余时长 / 账密
        sign      加密签名，必填（见 utils.build_sign）
    响应（json）:
        {"code":200,"msg":"成功","data":{"count":1,"filter_count":0,
         "surplus_quantity":0,"proxy_list":["27.28.167.190:36629"]}}

签名与自定义参数（两种模式，二选一）:
    - key 模式：调用方传自己的 API Key（业务密钥），服务端按官方规则代算 sign，
      因此可自由传 num / area / isp / filter 等任意参数（本模式固定用 json 返回）；
    - sign 模式：调用方传自己算好的 sign，参数原样透传、服务端不补任何默认值
      （官方签名与参数集严格绑定，改任何参数都会 401）。

使用示例:
    spider = ProxyIPJuliang()
    # 1) 用平台 .env 默认凭据（key 模式）
    result = spider.get_proxies(num=5)
    # 2) 调用方自己的业务编号 + API Key
    result = spider.get_proxies(trade_no="1483587531995538", key="xxxx",
                                num=10, area="北京,上海", pt="1")
    # 3) 调用方自己算好的 sign（参数原样透传）
    result = spider.get_proxies(trade_no="1483587531995538", num=1, sign="xxxx")
"""

import json
import re
from urllib.parse import quote

import requests

from .utils import (API_URL, DEFAULT_KEY, DEFAULT_PASSWORD, DEFAULT_TRADE_NO,
                    DEFAULT_USERNAME, MAX_NUM, PASSTHROUGH_ENUM, PASSTHROUGH_TEXT,
                    PROTOCOL_HTTP, PROTOCOL_SOCKS, REGION, REQUEST_TIMEOUT,
                    build_sign)
from ..utils import get_desktop_headers, response_dict

# 无数据时的统一 data 结构
_EMPTY = {"proxies": [], "total": 0, "fetched": 0}


class ProxyIPJuliang:
    """巨量代理（独享代理产品）动态 IP 提取"""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(get_desktop_headers())

    def get_proxies(self, pages: int = 1, page_size: int = None, **kwargs) -> dict:
        """
        从巨量代理提取接口获取动态代理 IP。

        :param pages: 忽略（接口无分页概念），用 num 指定数量
        :param page_size: 忽略
        :param kwargs: 可选业务参数:
            - trade_no: str, 业务编号（默认取 .env PROXY_JULIANG_TRADE_NO）
            - key: str, 业务密钥（默认取 .env PROXY_JULIANG_KEY）；与 sign 二选一
            - sign: str, 调用方自算签名；与 key 二选一
            - num: int, 提取数量（默认 1，最大 100）
            - username / password: str, 代理认证账密（默认取 .env），
              成对提供时返回结果附带可直接使用的 proxy 字段
            - 其余透传参数见 utils.PASSTHROUGH_ENUM / PASSTHROUGH_TEXT
        :return: dict 含:
            - code: 0 成功，1 失败
            - message: 描述信息
            - data: {
                proxies: [{ip, port, protocol, region[, extra][, username, password, proxy]}, ...],
                total: 返回总数,
                fetched: 返回数,
              }
        """
        trade_no = str(kwargs.get("trade_no") or DEFAULT_TRADE_NO).strip()
        caller_key = str(kwargs.get("key") or "").strip()
        sign = str(kwargs.get("sign") or "").strip()

        if caller_key and sign:
            return response_dict(
                code=1,
                message="参数值非法: key 与 sign 只能二选一（key=服务端代算签名，sign=参数原样透传）",
                data=dict(_EMPTY),
            )

        sign_mode = bool(sign)
        key = caller_key or ("" if sign_mode else DEFAULT_KEY)

        if not trade_no:
            return response_dict(
                code=1,
                message="参数缺失: trade_no(业务编号)，或平台未配置 PROXY_JULIANG_TRADE_NO",
                data=dict(_EMPTY),
            )
        if not sign and not key:
            return response_dict(
                code=1,
                message="参数缺失: key 与 sign 至少传一个，或平台未配置 PROXY_JULIANG_KEY",
                data=dict(_EMPTY),
            )

        # ── 组装业务参数：sign 模式原样透传（只带调用方显式传入的），key 模式补齐默认值 ──
        params = {}
        for name in list(PASSTHROUGH_ENUM) + list(PASSTHROUGH_TEXT):
            value = kwargs.get(name)
            value = str(value).strip() if value is not None else ""
            if value:
                params[name] = value

        num_raw = kwargs.get("num")
        if sign_mode:
            if num_raw not in (None, ""):
                params["num"] = str(num_raw)
        else:
            try:
                num = 1 if num_raw in (None, "") else int(num_raw)
            except (TypeError, ValueError):
                return response_dict(code=1, message="参数格式错误: num 必须为整数", data=dict(_EMPTY))
            if num < 1:
                return response_dict(code=1, message="参数值非法: num 必须大于 0", data=dict(_EMPTY))
            if num > MAX_NUM:
                return response_dict(
                    code=1, message=f"参数值非法: num 最大为 {MAX_NUM}", data=dict(_EMPTY)
                )
            params["num"] = str(num)
            # 本线路需要结构化解析；调用方未指定返回格式时用 json
            params.setdefault("result_type", "json")

        params["trade_no"] = trade_no
        if sign_mode:
            params["sign"] = sign
        else:
            params["sign"] = build_sign(params, key)

        # ── 请求 ──
        try:
            resp = self.session.get(API_URL, params=params, timeout=REQUEST_TIMEOUT)
            resp.encoding = "utf-8"
            text = (resp.text or "").strip()
        except requests.RequestException as e:
            return response_dict(code=1, message=f"请求巨量代理 API 失败: {e}", data=dict(_EMPTY))

        # ── 解析：JSON 优先，其次按文本模式（ip:port 行）解析 ──
        raw_items = []
        try:
            payload = json.loads(text)
        except ValueError:
            payload = None

        if isinstance(payload, dict):
            code = payload.get("code")
            message = str(payload.get("msg") or "").strip()
            if code != 200:
                return response_dict(
                    code=1,
                    message=message or f"巨量接口返回错误码 {code}",
                    data=dict(_EMPTY),
                )
            data = payload.get("data")
            if isinstance(data, dict):
                raw_items = data.get("proxy_list") or []
            elif isinstance(data, list):
                raw_items = data
        elif isinstance(payload, list):
            raw_items = payload
        elif payload is not None:
            return response_dict(
                code=1,
                message=f"无法识别的 API 响应格式: {type(payload).__name__}",
                data=dict(_EMPTY),
            )
        else:
            # 非 JSON：文本模式；失败时为 ERROR(xxx):原因
            if text.upper().startswith("ERROR"):
                return response_dict(code=1, message=text, data=dict(_EMPTY))
            raw_items = re.split(r"[\r\n]+", text)

        if isinstance(raw_items, str):
            raw_items = re.split(r"[\r\n]+", raw_items)

        username = str(kwargs.get("username") or DEFAULT_USERNAME).strip()
        password = str(kwargs.get("password") or DEFAULT_PASSWORD).strip()
        if not username or not password:
            username = password = ""

        protocol = PROTOCOL_SOCKS if params.get("pt") == "2" else PROTOCOL_HTTP
        proxies = self._parse_items(raw_items, protocol, username, password)

        return response_dict(
            code=0,
            message=f"成功获取 {len(proxies)} 条动态代理",
            data={"proxies": proxies, "total": len(proxies), "fetched": len(proxies)},
        )

    @staticmethod
    def _parse_items(raw_items, protocol: str, username: str, password: str) -> list:
        """把 ["ip:port", "ip:port,江苏徐州"] 解析为代理条目列表

        官方在带 city_name / ip_remain 等参数时会在 ip:port 后追加附加列，
        统一放入 extra 字段，不影响 ip / port 解析。

        :return: [{ip, port, protocol, region[, extra][, username, password, proxy]}, ...]
        """
        proxies = []
        for raw in (raw_items or []):
            text = str(raw).strip()
            if not text:
                continue
            parts = [p.strip() for p in text.split(",")]
            addr = parts[0]
            if ":" not in addr:
                continue
            ip, _, port = addr.partition(":")
            ip, port = ip.strip(), port.strip()
            if not ip or not port:
                continue
            entry = {"ip": ip, "port": port, "protocol": protocol, "region": REGION}
            extra = ",".join(parts[1:]).strip()
            if extra:
                entry["extra"] = extra
            if username and password:
                entry["username"] = username
                entry["password"] = password
                entry["proxy"] = (f"http://{quote(username, safe='')}:"
                                  f"{quote(password, safe='')}@{ip}:{port}")
            proxies.append(entry)
        return proxies
