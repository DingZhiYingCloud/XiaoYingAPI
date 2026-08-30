"""阿里云短信验证码认证 - 阿里云 Dypnsapi RPC 调用封装

使用阿里云号码认证服务（Dypnsapi 2017-05-25）的两个接口:
    SendSmsVerifyCode - 发送短信验证码（验证码由阿里云系统生成）
    CheckSmsVerifyCode - 核验短信验证码

调用方式: 阿里云 RPC 风格接口（GET + HMAC-SHA1 签名），依赖 requests，零第三方 SDK。
凭据: settings.ALIYUN_ACCESS_KEY_ID / ALIYUN_ACCESS_KEY_SECRET（.env 配置，账号级通用）。
短信专用配置: 代码层常量（SMS_SIGN_NAME / SMS_TEMPLATE_CODE），
      非重要配置不占用 .env 资源。

对外统一返回 (success, data_or_err) 二元组:
    - 成功: (True, dict) 已映射为业务字段
    - 失败: (False, err_msg) 人类可读错误信息
"""
import base64
import hashlib
import hmac
import json
import urllib.parse
import uuid
from datetime import datetime, timezone

import requests
from django.conf import settings

# 阿里云 Dypnsapi 接口地址与版本
DYPNS_ENDPOINT = 'https://dypnsapi.aliyuncs.com/'
API_VERSION = '2017-05-25'
REQUEST_TIMEOUT = 10  # 秒

# ── 阿里云短信认证配置（代码层写死，不占用 .env 资源） ──
# 签名名称：号码认证控制台赠送签名；模板 CODE：赠送模板（必须搭配使用）
SMS_SIGN_NAME = '北京恒创联众'
SMS_TEMPLATE_CODE = '100001'

# 验证码位置用 ##code## 占位符，由阿里云系统生成并完成校验；
# min 为模板变量「有效期分钟」，与 valid_time 联动。
_DEFAULT_TEMPLATE_PARAM = {'code': '##code##'}


def _percent_encode(value):
    """阿里云 RPC 规范 PercentEncode：A-Za-z0-9 与 ~ 不编码，其余按 UTF-8 字节 %XX"""
    return urllib.parse.quote(str(value), safe='~')


def _sign_string(params):
    """构造 StringToSign：参数按 key ASCII 升序排序，PercentEncode 后拼接"""
    items = sorted((k, str(v)) for k, v in params.items() if v not in (None, ''))
    canonical = '&'.join(f'{_percent_encode(k)}={_percent_encode(v)}' for k, v in items)
    return 'GET&%2F&' + _percent_encode(canonical)


def _sign(params, access_key_secret):
    """HMAC-SHA1 计算签名（Base64），密钥为 AccessKeySecret + '&'"""
    string_to_sign = _sign_string(params)
    key = (access_key_secret + '&').encode('utf-8')
    digest = hmac.new(key, string_to_sign.encode('utf-8'), hashlib.sha1).digest()
    return base64.b64encode(digest).decode('utf-8')


def _rpc_call(action, biz_params):
    """调用阿里云 RPC 接口（GET + 签名）

    :param action: 接口 Action 名（如 SendSmsVerifyCode）
    :param biz_params: 业务参数 dict
    :return: (True, dict 阿里云完整响应) 或 (False, err_msg)
    """
    access_key_id = settings.ALIYUN_ACCESS_KEY_ID
    access_key_secret = settings.ALIYUN_ACCESS_KEY_SECRET
    if not (access_key_id and access_key_secret):
        return False, '未配置阿里云 AccessKey，请在 .env 配置 ALIYUN_ACCESS_KEY_ID / ALIYUN_ACCESS_KEY_SECRET'

    params = {
        'Action': action,
        'Version': API_VERSION,
        'Format': 'JSON',
        'AccessKeyId': access_key_id,
        'SignatureMethod': 'HMAC-SHA1',
        'SignatureVersion': '1.0',
        'SignatureNonce': uuid.uuid4().hex,
        'Timestamp': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
    }
    params.update(biz_params)
    params['Signature'] = _sign(params, access_key_secret)

    try:
        resp = requests.get(DYPNS_ENDPOINT, params=params, timeout=REQUEST_TIMEOUT)
    except requests.RequestException as e:
        return False, f'阿里云接口请求失败: {e}'

    try:
        data = resp.json()
    except ValueError:
        return False, f'阿里云返回非 JSON 内容 (HTTP {resp.status_code}): {resp.text[:200]}'

    # HTTP 非 200 处理：核验失败时阿里云可能返回 400 但带 Model.VerifyResult=UNKNOWN，
    # 此时属于业务结果（验证码不匹配）而非请求错误，应作为成功透传。
    if resp.status_code != 200:
        if (data.get('Model') or {}).get('VerifyResult'):
            return True, data
        code = data.get('Code')
        if code:
            return False, f"阿里云返回错误: {code} {data.get('Message', '')}".strip()
        return False, f'阿里云接口请求失败: HTTP {resp.status_code}'

    # 请求级失败：Code != OK（接口请求成功不代表短信核验成功，核验结果以 Model.VerifyResult 为准）
    if data.get('Code') and data.get('Code') != 'OK':
        return False, f"阿里云返回错误: {data.get('Code')} {data.get('Message', '')}".strip()
    return True, data


# ==================== 对外接口封装 ====================

def send_verify_code(phone, code_length=4, valid_time=300, duplicate_policy=1,
                     interval=60, code_type=1, return_verify_code=False,
                     scheme_name='', out_id=''):
    """发送短信验证码（验证码由阿里云系统动态生成）

    :param phone: 手机号（必填）
    :param code_length: 验证码长度 4-8，默认 4
    :param valid_time: 验证码有效时长（秒），默认 300
    :param duplicate_policy: 重复发送处理 1=覆盖旧码 2=保留，默认 1
    :param interval: 发送间隔（秒），用于频控，默认 60
    :param code_type: 验证码类型 1-7（1=纯数字），默认 1
    :param return_verify_code: 是否在响应中返回验证码（仅测试场景建议开启），默认 False
    :param scheme_name: 方案名称，留空使用阿里云默认方案
    :param out_id: 外部流水号（透传）
    :return: (True, {biz_id, out_id, verify_code}) 或 (False, err_msg)
    """
    sign_name = SMS_SIGN_NAME
    template_code = SMS_TEMPLATE_CODE

    template_param = dict(_DEFAULT_TEMPLATE_PARAM)
    template_param['min'] = str(max(1, valid_time // 60))  # 模板变量 min 为有效期分钟

    biz = {
        'PhoneNumber': phone,
        'SignName': sign_name,
        'TemplateCode': template_code,
        'TemplateParam': json.dumps(template_param),
        'CodeLength': code_length,
        'ValidTime': valid_time,
        'DuplicatePolicy': duplicate_policy,
        'Interval': interval,
        'CodeType': code_type,
        'ReturnVerifyCode': 'true' if return_verify_code else 'false',
    }
    if scheme_name:
        biz['SchemeName'] = scheme_name
    if out_id:
        biz['OutId'] = out_id

    ok, data = _rpc_call('SendSmsVerifyCode', biz)
    if not ok:
        return False, data

    model = data.get('Model') or {}
    return True, {
        'biz_id': model.get('BizId'),
        'out_id': model.get('OutId'),
        # 仅 return_verify_code=true 时阿里云才会返回验证码
        'verify_code': model.get('VerifyCode'),
    }


def check_verify_code(phone, verify_code, case_auth_policy=1, scheme_name='', out_id=''):
    """核验短信验证码

    :param phone: 手机号（必填）
    :param verify_code: 验证码（必填）
    :param case_auth_policy: 大小写核验策略 1=不区分 2=区分，默认 1
    :param scheme_name: 方案名称（必须与发送时一致），留空使用默认方案
    :param out_id: 外部流水号
    :return: (True, {verify_result, passed, out_id}) 或 (False, err_msg)
        verify_result: PASS=核验成功 UNKNOWN=核验失败；passed 为其布尔等价
    """
    biz = {
        'PhoneNumber': phone,
        'VerifyCode': verify_code,
        'CaseAuthPolicy': case_auth_policy,
    }
    if scheme_name:
        biz['SchemeName'] = scheme_name
    if out_id:
        biz['OutId'] = out_id

    ok, data = _rpc_call('CheckSmsVerifyCode', biz)
    if not ok:
        # 验证码核验失败：阿里云返回 HTTP 400 + isv.ValidateFail（验证码错误/过期），
        # 属于业务结果而非请求错误，映射为 UNKNOWN 返回，与 PASS 语义统一。
        if 'isv.ValidateFail' in str(data):
            return True, {
                'verify_result': 'UNKNOWN',
                'passed': False,
                'out_id': out_id,
            }
        return False, data

    model = data.get('Model') or {}
    result = model.get('VerifyResult')
    return True, {
        'verify_result': result,        # PASS / UNKNOWN
        'passed': result == 'PASS',     # 布尔等价，便于调用方判断
        'out_id': model.get('OutId'),
    }
