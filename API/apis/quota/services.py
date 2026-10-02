"""被监控服务的注册表与取数实现

一个服务一个条目：显示名、单位、取数函数。**新增一个被监控服务 = 在本文件加一条**，
控制台页面与后台巡检线程都按本表遍历，别处不用改。

取数函数的统一契约：返回 `(True, Decimal)` 表示成功，`(False, 错误说明)` 表示失败。
凭据一律从 `.env` 读（与项目其它爬虫同一口径，禁止硬编码进代码库）；
唯一例外是 DeepSeek —— 它的 Key 与上游地址由后台「AI 模型」维护在库里（见厂商表），
故该条目的取数函数从数据库读凭据。
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

# DeepSeek 余额接口路径（拼在厂商 base_url 之后，见 https://api-docs.deepseek.com/zh-cn/api/get-user-balance）
DEEPSEEK_BALANCE_PATH = '/user/balance'

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


def _deepseek_credentials():
    """取 DeepSeek 的 (base_url, api_key)

    凭据由后台「AI 模型」维护在 `AiProvider` 表里（见本模块说明），`api_key` 是加密字段，
    读取时自动解密。

    :return: ((base_url, api_key), '') 或 (None, 错误说明)
    """
    from API.models import AiProvider

    provider = AiProvider.objects.filter(code='deepseek').first()
    if provider is None:
        return None, '未配置 DeepSeek 厂商：请到控制台「AI 模型」新建 code=deepseek 的厂商并填 API Key'
    base_url = (provider.base_url or '').strip().rstrip('/')
    api_key = (provider.api_key or '').strip()
    if not (base_url and api_key):
        return None, 'DeepSeek 未配置完整的 API Key / 上游地址：请到控制台「AI 模型」补填'
    return (base_url, api_key), ''


def fetch_deepseek_balance():
    """DeepSeek 账户余额（元）

    官方接口 `GET {base_url}/user/balance`，请求头带 `Authorization: Bearer <API Key>`；
    应答形如 `{"is_available": true, "balance_infos": [{"currency": "CNY",
    "total_balance": "110.00", ...}]}`，取第一条的 `total_balance`。

    :return: (True, Decimal) 或 (False, 错误说明)
    """
    credentials, error = _deepseek_credentials()
    if credentials is None:
        return False, error
    base_url, api_key = credentials

    try:
        resp = requests.get(f'{base_url}{DEEPSEEK_BALANCE_PATH}',
                            headers={'Authorization': f'Bearer {api_key}',
                                     'Accept': 'application/json'},
                            timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        payload = resp.json()
    except requests.HTTPError as e:
        # 401/403 几乎必然是 Key 失效（实测连免费的 /models 都拒），直接给出可操作的提示，
        # 免得页面上只有一句「401 Client Error」看不出要改什么
        status = e.response.status_code if e.response is not None else 0
        if status in (401, 403):
            return False, ('DeepSeek API Key 无效或已失效（%s）：请到控制台「AI 模型」更新 '
                           'deepseek 厂商的 Key' % status)
        return False, f'请求 DeepSeek 余额接口失败: {e}'
    except requests.RequestException as e:
        return False, f'请求 DeepSeek 余额接口失败: {e}'
    except ValueError:
        return False, 'DeepSeek 余额接口返回内容不是合法 JSON'

    if not isinstance(payload, dict):
        return False, f'DeepSeek 余额接口返回格式异常: {payload!r}'
    infos = payload.get('balance_infos')
    if not isinstance(infos, list) or not infos or not isinstance(infos[0], dict):
        return False, f'DeepSeek 余额接口未返回余额信息: {payload!r}'
    return _to_decimal(infos[0].get('total_balance'))


# 服务注册表：键即 QuotaService.code；字典顺序 = 控制台列表顺序
# default_threshold：首次为该服务建行时写入的默认告警阈值（之后以控制台页面上的值为准）
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
    'deepseek': {
        'name': 'DeepSeek',
        'unit': '元',
        'fetch': fetch_deepseek_balance,
        'default_threshold': Decimal('10'),
    },
}
