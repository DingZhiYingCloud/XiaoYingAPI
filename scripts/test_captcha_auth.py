"""阿里云图形认证集成 API 多轮测试

覆盖范围：
    第一轮 config 接口（appId 下发正确性/方法限制）
    第二轮 参数校验边界（缺失/格式非法）
    第三轮 sign_token 签名正确性（HMAC-SHA256 对拍）
    第四轮 Mock 返回映射（校验通过/失败/接口异常/请求异常）

运行方式（Mock 测试，不依赖真实图形验证，无需清理数据）：
    .venv\\Scripts\\python.exe scripts\\test_captcha_auth.py

真实联调说明：二次校验必须由真实用户完成一次图形验证后才能产生验证参数
（lot_number/captcha_output/pass_token/gen_time），因此本脚本仅做 Mock 测试；
真实联调需前端完成验证后，用这四个参数调用 verify 接口手动验证。
"""
import hashlib
import hmac
import json
import os
import sys
import time

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'XiaoYingAPI.settings')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import django

django.setup()

from django.test import Client

from API.apis.captcha_auth.aliyun import utils

# ───────────────────────── 测试基础设施 ─────────────────────────

BASE = '/api/captcha_auth/aliyun'
_stats = {'pass': 0, 'fail': 0}
_LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'test_captcha_auth_result.log')


def _log(msg):
    print(msg)
    with open(_LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(msg + '\n')


def _section(title):
    _log(f'\n===== {title} =====')


def _check(name, cond, extra=''):
    if cond:
        _stats['pass'] += 1
        _log(f'  [PASS] {name}')
    else:
        _stats['fail'] += 1
        _log(f'  [FAIL] {name} {extra}')


def _response(resp):
    """解析响应 JSON"""
    return json.loads(resp.content.decode('utf-8'))


# 有效的验证参数样本（格式与阿里云前端回调一致，仅用于 Mock 测试）
_LOT_NUMBER = '4dc3cfc2cdff448cad8d13107198d473'  # 32 位 hex 流水号
_VALID_PARAMS = {
    'lot_number': _LOT_NUMBER,
    'captcha_output': 'OjqKf5J8...',
    'pass_token': 'd6a2f1e8b4c9...',
    'gen_time': str(int(time.time() * 1000)),
}


# ───────────────────────── Mock 辅助 ─────────────────────────

_real_post_validate = utils._post_validate


def _mock_validate(handler):
    """临时替换二次校验调用；handler(query) -> (ok, data)"""
    utils._post_validate = handler


def _restore_validate():
    utils._post_validate = _real_post_validate


def _ok_result(result='success', reason='', captcha_args=None):
    """构造二次校验正常响应（阿里云 status=success）"""
    def handler(query):
        assert query['captcha_id'] == utils.CAPTCHA_APP_ID, 'captcha_id 应为配置的 appId'
        assert query['sign_token'] == utils.sign_token(query['lot_number']), 'sign_token 生成错误'
        return True, {
            'status': 'success',
            'result': result,
            'reason': reason,
            'captcha_args': captcha_args or {
                'used_type': 'icon',
                'user_ip': '127.0.0.1',
                'lot_number': query['lot_number'],
                'scene': '反爬虫',
            },
        }
    return handler


# ───────────────────────── 第一轮 config 接口 ─────────────────────────

def round1():
    _section('第一轮 config 接口')

    r = _response(Client().get(f'{BASE}/config'))
    _check('config-返回10000', r['code'] == 10000, r)
    _check('config-返回真实appId', r.get('data', {}).get('app_id') == utils.CAPTCHA_APP_ID, r)
    _check('config-appId为32位', len(utils.CAPTCHA_APP_ID) == 32, utils.CAPTCHA_APP_ID)

    resp = Client().post(f'{BASE}/config', {})
    _check('config-方法限制POST返回405', resp.status_code == 405, resp.status_code)


# ───────────────────────── 第二轮 参数校验边界 ─────────────────────────

def round2():
    _section('第二轮 参数校验边界')
    _mock_validate(_ok_result())

    # 参数缺失
    for missing_key in ['lot_number', 'captcha_output', 'pass_token', 'gen_time']:
        params = dict(_VALID_PARAMS)
        del params[missing_key]
        r = _response(Client().post(f'{BASE}/verify', params))
        _check(f'verify-{missing_key}缺失返回20001', r['code'] == 20001, r)

    # lot_number 格式非法（空字符串属于缺失场景，已在缺失用例覆盖）
    for bad in ['abc', '4dc3cfc2cdff448cad8d13107198d473' + '0', '4dc3cfc2cdff448cad8d13107198d47!']:
        params = dict(_VALID_PARAMS)
        params['lot_number'] = bad
        r = _response(Client().post(f'{BASE}/verify', params))
        _check(f'verify-lot_number非法({bad!r})返回20002', r['code'] == 20002, r)

    _restore_validate()


# ───────────────────────── 第三轮 sign_token 签名正确性 ─────────────────────────

def round3():
    _section('第三轮 sign_token 签名正确性')

    lot_number = _LOT_NUMBER
    expected = hmac.new(
        utils.CAPTCHA_APP_KEY.encode(),
        lot_number.encode(),
        hashlib.sha256,
    ).hexdigest()
    actual = utils.sign_token(lot_number)
    _check('sign_token与标准HMAC-SHA256一致', actual == expected, actual)
    _check('sign_token为64位小写hex', len(actual) == 64 and all(c in '0123456789abcdef' for c in actual), actual)
    _check('不同lot_number生成不同签名', utils.sign_token(lot_number) != utils.sign_token('4dc3cfc2cdff448cad8d13107198d474'))

    _log(f'  签名样本: sign_token({lot_number[:8]}...) = {actual}')


# ───────────────────────── 第四轮 Mock 返回映射 ─────────────────────────

def round4():
    _section('第四轮 Mock 返回映射')

    # 校验通过
    _mock_validate(_ok_result('success'))
    r = _response(Client().post(f'{BASE}/verify', _VALID_PARAMS))
    _check('verify-通过返回10000', r['code'] == 10000, r)
    _check('verify-result为success', r.get('data', {}).get('result') == 'success', r)
    _check('verify-passed为true', r.get('data', {}).get('passed') is True, r)
    _check('verify-返回captcha_args', isinstance(r.get('data', {}).get('captcha_args'), dict), r)

    # 校验失败（如 pass_token 过期）
    _mock_validate(_ok_result('fail', reason='pass_token expire'))
    r = _response(Client().post(f'{BASE}/verify', _VALID_PARAMS))
    _check('verify-失败仍返回10000', r['code'] == 10000, r)
    _check('verify-result为fail', r.get('data', {}).get('result') == 'fail', r)
    _check('verify-passed为false', r.get('data', {}).get('passed') is False, r)
    _check('verify-透传失败原因', r.get('data', {}).get('reason') == 'pass_token expire', r)

    # 接口异常（status=error）
    _mock_validate(lambda query: (True, {'status': 'error', 'code': '-50005', 'msg': 'illegal gen_time'}))
    r = _response(Client().post(f'{BASE}/verify', _VALID_PARAMS))
    _check('verify-接口异常返回40001', r['code'] == 40001, r)
    _check('verify-透传阿里云错误信息', 'illegal gen_time' in r.get('msg', ''), r)

    # 请求异常（网络失败）
    _mock_validate(lambda query: (False, '图形认证服务请求失败: timeout'))
    r = _response(Client().post(f'{BASE}/verify', _VALID_PARAMS))
    _check('verify-请求失败返回40001', r['code'] == 40001, r)
    _check('verify-请求失败透传原因', 'timeout' in r.get('msg', ''), r)

    # 方法限制
    resp = Client().get(f'{BASE}/verify')
    _check('方法限制-GET访问verify返回405', resp.status_code == 405, resp.status_code)

    _restore_validate()


# ───────────────────────── 主流程 ─────────────────────────

def main():
    if os.path.exists(_LOG_FILE):
        os.remove(_LOG_FILE)

    _log(f'阿里云图形认证集成 API 测试开始（{time.strftime("%Y-%m-%d %H:%M:%S")}）')
    _log(f'图形认证配置: appId={utils.CAPTCHA_APP_ID}')

    round1()
    round2()
    round3()
    round4()

    _log('\n========== 测试汇总 ==========')
    _log(f'通过: {_stats["pass"]}  |  失败: {_stats["fail"]}  |  总计: {_stats["pass"] + _stats["fail"]}')
    _log('结论: ' + ('全部用例通过' if _stats['fail'] == 0 else '存在失败用例'))
    _log('\n[提示] 真实联调需前端完成图形验证后提供验证参数，再调 verify 接口手动验证')


if __name__ == '__main__':
    main()
