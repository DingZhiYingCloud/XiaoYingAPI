"""
51代理 爬虫 - ProxyIP51Daili

从 51代理（51daili.com）「getapi2」提取接口获取国内动态代理 IP。

API 文档: https://m.51daili.com/wap/api/apinote.html
    请求方式: GET
    参数说明:
        packid         套餐 ID（账号级，默认取 .env）
        qty            获取 IP 数量
        time           稳定使用时长（官方文档标注 1-6，本线路默认 31）
        port           代理协议 1=HTTP/HTTPS 2=Socks5
        format         返回格式 txt / json / html（本线路只用 json 或 txt）
        field          返回字段，英文逗号分隔（如 ipport,expiretime,regioncode,isptype）
        linePoolIndex  线路池索引，-1=不限
        rid / uid / accessName / accessPassword   账号凭据（默认取 .env）
    响应（json）:
        {"msg":"", "code":0, "success":"true",
         "data":[{"ip":"1.2.3.4:8080", "expireTime":"2026-10-01 13:26:28",
                  "expireTimeMillis":"1790832388118", "ipaddress":"451200",
                  "IpAddressName":"贺州市", "isp":"电信"}]}
        注：field 不含 ipport 时，ip 与 port 会拆成两个字段返回（ip 里没有端口）。
    响应（txt）: 每行 `ip:port|地区码+地区名|过期时间|运营商`

使用示例:
    spider = ProxyIP51Daili()
    # 1) 用平台 .env 默认凭据
    result = spider.get_proxies(qty=5)
    # 2) 取 Socks5 出口
    result = spider.get_proxies(qty=1, port="2")
    # 3) 调用方自己的账号（uid/accessName/accessPassword/packid 必须整组传）
    result = spider.get_proxies(qty=1, uid="76385", accessName="xiaoyingapi",
                                accessPassword="xxxxxxxx", packid="2")
"""

import json
import re

import requests

from .utils import (ALLOWED_FORMATS, API_URL, CRED_FIELDS, DEFAULT_ACCESS_NAME,
                    DEFAULT_ACCESS_PASSWORD, DEFAULT_FIELD, DEFAULT_FORMAT,
                    DEFAULT_LINE_POOL_INDEX, DEFAULT_PACKID, DEFAULT_PORT,
                    DEFAULT_QTY, DEFAULT_RID, DEFAULT_TIME, DEFAULT_UID,
                    FORMAT_JSON, MAX_QTY, PROTOCOL_MAP, REQUEST_TIMEOUT, TEXT_FORMATS)
from ..utils import get_desktop_headers, response_dict

# 无数据时的统一 data 结构
_EMPTY = {"proxies": [], "total": 0, "fetched": 0}

# txt 格式中的「地区码+地区名」，如 "530300曲靖市" → 码 530300 / 名 曲靖市
_TEXT_REGION_RE = re.compile(r'^(\d*)(.*)$')

# 合法 IPv4（txt 每行首段必须是 ip:port，用来挡掉「平台其实回的是 JSON 错误体」那种情况）
_IPV4_RE = re.compile(r'^\d{1,3}(?:\.\d{1,3}){3}$')


class ProxyIP51Daili:
    """51代理（getapi2 提取接口）动态 IP 提取"""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(get_desktop_headers())

    def get_proxies(self, pages: int = 1, page_size: int = None, **kwargs) -> dict:
        """
        从 51代理提取接口获取动态代理 IP。

        :param pages: 忽略（接口无分页概念），用 qty 指定数量
        :param page_size: 忽略
        :param kwargs: 可选业务参数（未传时用平台默认）:
            - uid / accessName / accessPassword / packid: str, 账号三件套 + 套餐 ID，
              **整组**使用：调用方全传则用调用方的，全不传则回退 .env；
              只传其中一部分按「参数缺失」拒绝（混用两个账号的凭据没有意义）
            - rid: str, 提取链接上的标识（可选，默认取 .env）
            - qty: int, 提取数量（默认 1，最大 MAX_QTY）
            - port: str, 代理协议 1=HTTP/HTTPS 2=Socks5（默认 1）
            - time: str, 稳定使用时长（默认 31）
            - format: str, 返回格式 json / txt（默认 json；html 无法解析，不接受）
            - field: str, 返回字段，英文逗号分隔（默认见 DEFAULT_FIELD）
            - linePoolIndex: str, 线路池索引（默认 -1）
        :return: dict 含:
            - code: 0 成功，1 失败
            - message: 描述信息
            - data: {
                proxies: [{ip, port, protocol, region, region_code, isp, end_time}, ...],
                total: 返回总数,
                fetched: 返回数,
              }
        """
        # ── 账号级参数：整组使用（调用方全传 → 用调用方的；全不传 → 用 .env）──
        supplied = {name: str(kwargs.get(name) or '').strip() for name in CRED_FIELDS}
        if any(supplied.values()):
            missing = [name for name, value in supplied.items() if not value]
            if missing:
                return response_dict(
                    code=1,
                    message='参数缺失: ' + ' / '.join(missing)
                            + ' 未传入（uid / accessName / accessPassword / packid 必须整组传入）',
                    data=dict(_EMPTY),
                )
            uid = supplied['uid']
            access_name = supplied['accessName']
            access_password = supplied['accessPassword']
            packid = supplied['packid']
        else:
            uid, access_name = DEFAULT_UID, DEFAULT_ACCESS_NAME
            access_password, packid = DEFAULT_ACCESS_PASSWORD, DEFAULT_PACKID

        missing = [name for name, value in (('uid', uid), ('accessName', access_name),
                                            ('accessPassword', access_password),
                                            ('packid', packid)) if not value]
        if missing:
            return response_dict(
                code=1,
                message='凭据未配置: 缺少 ' + ' / '.join(missing)
                        + '，请在 .env 设置 PROXY_51DAILI_UID / PROXY_51DAILI_ACCESS_NAME / '
                          'PROXY_51DAILI_ACCESS_PASSWORD / PROXY_51DAILI_PACKID，'
                          '或由调用方整组传入',
                data=dict(_EMPTY),
            )

        # ── 数量 ──
        try:
            qty = int(str(kwargs.get('qty', DEFAULT_QTY)).strip() or DEFAULT_QTY)
        except (TypeError, ValueError):
            return response_dict(code=1, message='参数格式错误: qty 必须为整数', data=dict(_EMPTY))
        if qty < 1:
            return response_dict(code=1, message='参数值非法: qty 必须大于 0', data=dict(_EMPTY))
        if qty > MAX_QTY:
            return response_dict(
                code=1, message=f'参数值非法: qty 最大为 {MAX_QTY}', data=dict(_EMPTY)
            )

        # ── 协议 / 返回格式 ──
        port = str(kwargs.get('port') or DEFAULT_PORT).strip()
        if port not in PROTOCOL_MAP:
            return response_dict(
                code=1,
                message='参数值非法: port 仅支持 1(HTTP/HTTPS) / 2(Socks5)',
                data=dict(_EMPTY),
            )

        fmt = str(kwargs.get('format') or DEFAULT_FORMAT).strip().lower()
        if fmt not in ALLOWED_FORMATS:
            return response_dict(
                code=1,
                message='参数值非法: format 仅支持 json / txt（html 无法解析出 ip:port）',
                data=dict(_EMPTY),
            )

        # ── 组装请求参数 ──
        params = {
            'packid': packid,
            'qty': str(qty),
            'time': str(kwargs.get('time') or DEFAULT_TIME).strip(),
            'port': port,
            'format': fmt,
            'field': str(kwargs.get('field') or DEFAULT_FIELD).strip(),
            'linePoolIndex': str(kwargs.get('linePoolIndex')
                                 or DEFAULT_LINE_POOL_INDEX).strip(),
            'uid': uid,
            'accessName': access_name,
            'accessPassword': access_password,
        }
        rid = str(kwargs.get('rid') or DEFAULT_RID).strip()
        if rid:
            params['rid'] = rid

        # ── 请求 ──
        try:
            resp = self.session.get(API_URL, params=params, timeout=REQUEST_TIMEOUT)
            resp.encoding = 'utf-8'
            text = (resp.text or '').strip()
        except requests.RequestException as e:
            return response_dict(code=1, message=f'请求 51代理 API 失败: {e}', data=dict(_EMPTY))

        protocol = PROTOCOL_MAP[port]
        if fmt in TEXT_FORMATS:
            proxies = self._parse_text_items(text, protocol)
            # 文本模式拿不到结构化错误码；平台在参数 / 地域 / 频率出错时**即使 format=txt 也回 JSON**，
            # 故解析不出代理时先按 JSON 信封取原因（否则调用方只会看到一句无信息量的「未返回可解析的代理」）
            if not proxies:
                return response_dict(
                    code=1,
                    message=(self._json_error(text, access_name) or text
                             or '51代理接口未返回可解析的代理'),
                    data=dict(_EMPTY),
                )
        else:
            proxies, error = self._parse_json_payload(text, protocol, access_name)
            if error:
                return response_dict(code=1, message=error, data=dict(_EMPTY))

        return response_dict(
            code=0,
            message=f'成功获取 {len(proxies)} 条动态代理',
            data={'proxies': proxies, 'total': len(proxies), 'fetched': len(proxies)},
        )

    @staticmethod
    def _envelope_error(payload: dict, access_name: str) -> str:
        """从失败信封里取可读原因

        平台两种字段名都用过：常见为 ``msg``，但「地域不符」这类错误用的是 ``message``
        （``{"code":501,"message":"当前ip:x.x.x.x,地区为美国,请更换为内地ip"}``），
        只认 msg 会让调用方看到无信息量的「返回错误码 501」，故两个都取。
        失败 msg 常带 ``<accessName>:`` 前缀（会暴露账号名），这里按已知的账号名剥掉。
        """
        message = str(payload.get('msg') or payload.get('message') or '').strip()
        prefix = f'{access_name}:'
        if message.startswith(prefix):
            message = message[len(prefix):].strip()
        return message or f'51代理接口返回错误码 {payload.get("code")}'

    @staticmethod
    def _json_error(text: str, access_name: str) -> str:
        """文本模式下，若平台实际回的是 JSON 失败信封则取出原因；不是则返回空串"""
        try:
            payload = json.loads(text)
        except ValueError:
            return ''
        if not isinstance(payload, dict):
            return ''
        if payload.get('code') == 0 and str(payload.get('success')).lower() == 'true':
            return ''
        return ProxyIP51Daili._envelope_error(payload, access_name)

    @staticmethod
    def _parse_json_payload(text: str, protocol: str, access_name: str) -> tuple:
        """解析 JSON 响应

        成功：``{"code":0,"success":"true","data":[...]}``
        失败：``{"code":10102,"msg":"<账号>:账号密码验证失败!","data":""}``
              ``{"code":501,"message":"当前ip:x.x.x.x,地区为美国,请更换为内地ip"}``

        平台未给中文说明时不能让调用方只看到「获取失败」，故一律把原因带出去。

        :return: (代理条目列表, 错误信息)；错误信息非空表示失败
        """
        try:
            payload = json.loads(text)
        except ValueError:
            return [], f'无法解析 51代理响应: {text[:200]}'
        if not isinstance(payload, dict):
            return [], f'无法识别的 51代理响应格式: {type(payload).__name__}'

        # success 是字符串 "true"/"false"，不能直接用真值判断（"false" 也是真）
        success = str(payload.get('success')).lower() == 'true'
        if payload.get('code') != 0 or not success:
            return [], ProxyIP51Daili._envelope_error(payload, access_name)

        items = payload.get('data')
        if not isinstance(items, list):
            return [], ''
        return ProxyIP51Daili._parse_json_items(items, protocol), ''

    @staticmethod
    def _parse_json_items(items: list, protocol: str) -> list:
        """解析 JSON 的 data 数组

        field 含 ipport 时 ``ip`` 是 ``ip:port``；不含时 ``ip`` / ``port`` 分成两个字段。
        两种形状都按有端口处理，其余字段（地区名 / 地区码 / 运营商 / 过期时间）按平台给的原样带出。

        :return: [{ip, port, protocol, region, region_code, isp, end_time}, ...]
        """
        proxies = []
        for item in items:
            if not isinstance(item, dict):
                continue
            raw_ip = str(item.get('ip') or '').strip()
            if not raw_ip:
                continue
            if item.get('port'):
                ip, port = raw_ip, str(item.get('port')).strip()
            elif ':' in raw_ip:
                ip, _, port = raw_ip.partition(':')
                ip, port = ip.strip(), port.strip()
            else:
                continue
            if not ip or not port:
                continue
            proxies.append({
                'ip': ip,
                'port': port,
                'protocol': protocol,
                'region': str(item.get('IpAddressName') or '').strip(),
                'region_code': str(item.get('ipaddress') or '').strip(),
                'isp': str(item.get('isp') or '').strip(),
                'end_time': str(item.get('expireTime') or '').strip(),
            })
        return proxies

    @staticmethod
    def _parse_text_items(text: str, protocol: str) -> list:
        """解析 txt 格式：每行 ``ip:port|地区码+地区名|过期时间|运营商``

        分隔符与字段集由上游 ``field`` 决定，故除第一段外都按「有则取、无则空」处理。

        **首段必须是合法的 IPv4:port**：平台在出错时即使 format=txt 也回 JSON，
        而 JSON 文本里到处是冒号，若不做校验就会被解析成 `ip={"code"` 这种假条目、
        并当成「成功获取 N 条」返回给调用方（静默给垃圾数据）。

        :return: 同 _parse_json_items
        """
        proxies = []
        for line in re.split(r'[\r\n]+', text or ''):
            line = line.strip()
            if not line or ':' not in line:
                continue
            parts = [p.strip() for p in line.split('|')]
            ip, _, port = parts[0].partition(':')
            ip, port = ip.strip(), port.strip()
            if not _IPV4_RE.match(ip) or not port.isdigit() or not 0 < int(port) < 65536:
                continue
            region_code = region = ''
            if len(parts) > 1:
                matched = _TEXT_REGION_RE.match(parts[1])
                region_code, region = matched.group(1), matched.group(2)
            proxies.append({
                'ip': ip,
                'port': port,
                'protocol': protocol,
                'region': region,
                'region_code': region_code,
                'isp': parts[3] if len(parts) > 3 else '',
                'end_time': parts[2] if len(parts) > 2 else '',
            })
        return proxies
