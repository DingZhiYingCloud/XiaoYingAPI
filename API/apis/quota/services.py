"""被监控服务的注册表与取数实现

一个服务一个条目：显示名、单位、取数函数。**新增一个被监控服务 = 在本文件加一条**，
控制台页面与后台巡检线程都按本表遍历，别处不用改。

取数函数的统一契约：返回 `(True, Decimal)` 表示成功，`(False, 错误说明)` 表示失败。
凭据一律从 `.env` 读（与项目其它爬虫同一口径，禁止硬编码进代码库）。
"""
import logging
from decimal import Decimal, InvalidOperation

import requests

from API.apis.chaojiying.utils import get_score as chaojiying_get_score
from SpiderServices.ProxyIp.ProxyIP_51daili.utils import (
    DEFAULT_ACCESS_PASSWORD as PROXY_ACCESS_PASSWORD,
)
from SpiderServices.ProxyIp.ProxyIP_51daili.utils import DEFAULT_UID as PROXY_UID

logger = logging.getLogger('api.quota')

# 51代理「账号信息」接口：GET ?appkey=...，返回 data.currentScore = 账户余额（元）。
# appkey = 「提取密码 + 账号 uid」拼接（与该平台提取链接上的 appkey 同一口径）。
# 注意主机与提取接口不同（提取走 bapi.51daili.com），故不能复用 API_BASE。
BALANCE_URL_51DAILI = 'http://aapi.51daili.com/userapi'

# 单次取数超时（秒）
REQUEST_TIMEOUT = 15


def _to_decimal(value):
    """把上游返回的数值转成 Decimal

    :return: (True, Decimal) 或 (False, 说明)
    """
    try:
        return True, Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return False, f'返回值不是合法数值: {value!r}'


def fetch_51daili_balance():
    """51代理 账户余额（元）

    :return: (True, Decimal) 或 (False, 错误说明)
    """
    if not (PROXY_ACCESS_PASSWORD and PROXY_UID):
        return False, ('凭据未配置: 缺少 PROXY_51DAILI_ACCESS_PASSWORD / PROXY_51DAILI_UID，'
                       '请在 .env 中设置')
    appkey = f'{PROXY_ACCESS_PASSWORD}{PROXY_UID}'
    try:
        resp = requests.get(BALANCE_URL_51DAILI, params={'appkey': appkey},
                            timeout=REQUEST_TIMEOUT)
        resp.encoding = 'utf-8'
        payload = resp.json()
    except requests.RequestException as e:
        return False, f'请求 51代理余额接口失败: {e}'
    except ValueError:
        return False, '51代理余额接口返回内容不是合法 JSON'

    if not isinstance(payload, dict):
        return False, f'51代理余额接口返回格式异常: {payload!r}'
    if payload.get('code') != 0:
        return False, f'51代理余额接口返回错误: {payload.get("msg") or payload}'
    data = payload.get('data')
    if not isinstance(data, dict):
        return False, f'51代理余额接口返回格式异常: {data!r}'
    return _to_decimal(data.get('currentScore'))


def fetch_chaojiying_score():
    """超级鹰 题分余额

    官方「查询题分」接口（`GetScore.php`）直取，不需要登录网页；凭据见 .env 的
    CHAOJIYING_USER / CHAOJIYING_PASS。

    :return: (True, Decimal) 或 (False, 错误说明)
    """
    result = chaojiying_get_score()       # {code, message, data:{tifen, tifen_lock}}
    if result.get('code') != 0:
        return False, f'查询超级鹰题分失败: {result.get("message")}'
    data = result.get('data')
    if not isinstance(data, dict):
        return False, f'超级鹰返回格式异常: {data!r}'
    return _to_decimal(data.get('tifen'))


# 服务注册表：键即 QuotaService.code；字典顺序 = 控制台列表顺序
SERVICES = {
    'proxy_51daili': {
        'name': '51代理',
        'unit': '元',
        'fetch': fetch_51daili_balance,
    },
    'chaojiying': {
        'name': '超级鹰',
        'unit': '题分',
        'fetch': fetch_chaojiying_score,
    },
}
