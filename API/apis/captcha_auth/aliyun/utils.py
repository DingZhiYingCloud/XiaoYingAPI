"""阿里云图形认证集成 - 二次校验调用封装

阿里云图形认证（Captcha）服务端集成：
    用户在客户端（H5 页面）完成图形验证后，客户端生成验证参数
    （lot_number / captcha_output / pass_token / gen_time），
    服务端上传这些参数到二次校验接口确认用户本次验证的有效性。

二次校验接口: POST https://captcha.alicaptcha.com/validate
    - 请求格式: application/x-www-form-urlencoded
    - sign_token = HMAC-SHA256(appKey, lot_number)
    - captcha_id 为 appId，拼接在 URL 后便于日志定位

凭据: appId（公开标识）/ appKey（机密签名密钥）均为代码层常量写死，
      不占用 .env 资源；appKey 仅用于服务端生成签名，绝不下发客户端。

对外统一返回 (success, data_or_err) 二元组:
    - 成功: (True, dict) 已映射为业务字段（result / passed / reason / captcha_args）
    - 失败: (False, err_msg) 人类可读错误信息
"""
import hashlib
import hmac

import requests

# ── 阿里云图形认证配置（代码层写死，不占用 .env 资源） ──
# appId：图形认证方案管理控制台创建方案后生成（公开标识，config 接口下发前端）
CAPTCHA_APP_ID = '296d0fabf47beeacfe50cbc01f8cd4d7'
# appKey：与 appId 配套的签名密钥（机密，仅服务端生成 sign_token 用）
CAPTCHA_APP_KEY = '37abedd5e523708f667cbe9db257908e'

# 二次校验接口地址
CAPTCHA_VALIDATE_URL = 'https://captcha.alicaptcha.com/validate'
REQUEST_TIMEOUT = 10  # 秒


def sign_token(lot_number):
    """生成二次校验签名：HMAC-SHA256(appKey, lot_number) 小写 hex

    签名使用用户当前完成验证的流水号 lot_number 作为原始消息，
    与阿里云官方接入规范一致。
    """
    return hmac.new(
        CAPTCHA_APP_KEY.encode(),
        lot_number.encode(),
        hashlib.sha256,
    ).hexdigest()


def _post_validate(query):
    """调用二次校验接口（可被测试替换）

    :param query: 完整校验参数字典（含 captcha_id / sign_token）
    :return: (True, dict 响应) 或 (False, err_msg)
    """
    url = f'{CAPTCHA_VALIDATE_URL}?captcha_id={CAPTCHA_APP_ID}'
    try:
        resp = requests.post(url, data=query, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        return False, f'图形认证服务请求失败: {e}'
    except ValueError:
        return False, f'图形认证服务返回非 JSON 内容 (HTTP {resp.status_code}): {resp.text[:200]}'
    return True, data


def verify_captcha(lot_number, captcha_output, pass_token, gen_time):
    """二次校验：确认用户在客户端完成的图形验证是否有效

    :param lot_number: 验证流水号
    :param captcha_output: 验证输出信息
    :param pass_token: 验证通过标识
    :param gen_time: 验证通过时间戳
    :return: (True, {result, passed, reason, captcha_args}) 或 (False, err_msg)
        result: success=校验通过 fail=校验失败（如 pass_token expire）
        passed: result 的布尔等价；captcha_args: 阿里云返回的验证输出参数
    """
    query = {
        'lot_number': lot_number,
        'captcha_output': captcha_output,
        'pass_token': pass_token,
        'gen_time': gen_time,
        'captcha_id': CAPTCHA_APP_ID,
        'sign_token': sign_token(lot_number),
    }
    ok, data = _post_validate(query)
    if not ok:
        return False, data

    # status=error 表示接口异常（参数非法、验证id异常等），属于调用失败
    if data.get('status') == 'error':
        return False, f"图形认证服务返回错误: {data.get('code')} {data.get('msg', '')}".strip()

    # 正常响应: {status: success, result: success/fail, reason, captcha_args}
    result = data.get('result')
    return True, {
        'result': result,                      # success / fail
        'passed': result == 'success',         # 布尔等价
        'reason': data.get('reason', ''),      # 失败原因（如 pass_token expire）
        'captcha_args': data.get('captcha_args') or {},  # 验证输出参数（风控信息）
    }
