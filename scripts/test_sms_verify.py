"""阿里云短信验证码认证 API 多轮测试

覆盖范围：
    第一轮 参数校验边界（缺失/格式/越界/非法枚举）
    第二轮 签名鉴权（无签名/错误签名/未注册/停用/过期）
    第三轮 Mock 返回映射（发送成功/失败、核验 PASS/UNKNOWN、异常、方法限制）
    第四轮 真实端到端（真实发送验证码到测试手机号并核验）

运行方式（使用真实数据库，测试结束后自动清理测试数据）：
    .venv\\Scripts\\python.exe scripts\\test_sms_verify.py

注意：
    - 第四轮会真实调用阿里云向测试手机号发送短信（产生 1 条短信费用）
    - 测试手机号在下方 TEST_PHONE 常量修改
"""
import os
import secrets
import sys
import time

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'XiaoYingAPI.settings')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import django

django.setup()

from django.conf import settings
from django.test import Client

from API.models import UserApp
from API.apis.sms_verify.aliyun import utils
from API.apis.user_center.sign import build_sign

# ───────────────────────── 测试基础设施 ─────────────────────────

BASE = '/api/sms_verify/aliyun'
# 真实端到端测试手机号（用户提供，发送会产生短信费用）
TEST_PHONE = '13712992620'
_PREFIX = f'SV{int(time.time())}'

_stats = {'pass': 0, 'fail': 0}
_round_title = ''
_created_apps = []   # (app_id, app_secret, UserApp)
_LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'test_sms_verify_result.log')


def _log(msg):
    print(msg)
    with open(_LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(msg + '\n')


def _section(title):
    global _round_title
    _round_title = title
    _log(f'\n===== {title} =====')


def _check(name, cond, extra=''):
    if cond:
        _stats['pass'] += 1
        _log(f'  [PASS] {name}')
    else:
        _stats['fail'] += 1
        _log(f'  [FAIL] {name} {extra}')


def _signed(app, extra=None, timestamp=None):
    """构造签名参数（可覆盖 timestamp 做时间窗测试；None 值参数自动剔除）"""
    extra = {k: v for k, v in (extra or {}).items() if v is not None}
    params = {
        'app_id': app[0],
        'timestamp': str(timestamp if timestamp is not None else int(time.time())),
        'nonce': secrets.token_hex(8),
    }
    if extra:
        params.update(extra)
    params['sign'] = build_sign(params, app[1])
    return params


def _create_app(name=None, status=True):
    """创建测试接入项目（密钥系统自动生成）"""
    obj = UserApp.objects.create(
        name=name or f'{_PREFIX}项目{len(_created_apps)}',
        status=status,
    )
    entry = (obj.app_id, obj.app_secret, obj)
    _created_apps.append(entry)
    return entry


def _post(app, path, extra=None, with_sign=True):
    """发送 POST 请求（form-urlencoded + 签名）"""
    params = _signed(app, extra) if with_sign else (extra or {})
    return Client().post(f'{BASE}{path}', params)


def _response(resp):
    """解析响应 JSON"""
    import json
    return json.loads(resp.content.decode('utf-8'))


# ───────────────────────── Mock 辅助 ─────────────────────────

_real_rpc_call = utils._rpc_call


def _mock_aliyun(handler):
    """临时替换阿里云 RPC 调用；handler(action, biz_params) -> (ok, data)"""
    utils._rpc_call = handler


def _restore_aliyun():
    utils._rpc_call = _real_rpc_call


def _ok_send(biz_id='biz_001', verify_code=None, out_id=''):
    """构造发送成功 Mock（校验 Action 名与参数）"""
    def handler(action, biz):
        assert action == 'SendSmsVerifyCode'
        assert biz.get('PhoneNumber'), '缺少 PhoneNumber'
        model = {'BizId': biz_id, 'OutId': out_id or biz.get('OutId')}
        if verify_code is not None:
            model['VerifyCode'] = verify_code
        return True, {'Code': 'OK', 'Message': '成功', 'Success': True, 'Model': model}
    return handler


def _ok_check(result='PASS', out_id=''):
    """构造核验成功 Mock"""
    def handler(action, biz):
        assert action == 'CheckSmsVerifyCode'
        assert biz.get('VerifyCode'), '缺少 VerifyCode'
        return True, {'Code': 'OK', 'Message': '成功', 'Success': True,
                      'Model': {'VerifyResult': result, 'OutId': out_id}}
    return handler


# ───────────────────────── 第一轮 参数校验边界 ─────────────────────────

def round1(app):
    _section('第一轮 参数校验边界（Mock）')
    _mock_aliyun(_ok_send())

    # phone 缺失
    r = _response(_post(app, '/send', {'code_length': '4'}))
    _check('发送-phone缺失返回20001', r['code'] == 20001, r)

    # phone 格式错误
    for bad in ['12345', '123456789012', '1380013800a']:
        r = _response(_post(app, '/send', {'phone': bad}))
        _check(f'发送-phone非法({bad})返回20002', r['code'] == 20002, r)

    # code_length 越界
    for bad in ['3', '9']:
        r = _response(_post(app, '/send', {'phone': TEST_PHONE, 'code_length': bad}))
        _check(f'发送-code_length越界({bad})返回20003', r['code'] == 20003, r)

    # 数值参数非整数
    r = _response(_post(app, '/send', {'phone': TEST_PHONE, 'valid_time': 'abc'}))
    _check('发送-valid_time非整数返回20002', r['code'] == 20002, r)

    # duplicate_policy 非法
    r = _response(_post(app, '/send', {'phone': TEST_PHONE, 'duplicate_policy': '3'}))
    _check('发送-duplicate_policy非法返回20003', r['code'] == 20003, r)

    # code_type 非法
    r = _response(_post(app, '/send', {'phone': TEST_PHONE, 'code_type': '0'}))
    _check('发送-code_type非法返回20003', r['code'] == 20003, r)

    # check 参数
    r = _response(_post(app, '/check', {'phone': TEST_PHONE}))
    _check('核验-verify_code缺失返回20001', r['code'] == 20001, r)
    r = _response(_post(app, '/check', {'verify_code': '1234'}))
    _check('核验-phone缺失返回20001', r['code'] == 20001, r)
    r = _response(_post(app, '/check', {'phone': TEST_PHONE, 'verify_code': '1234', 'case_auth_policy': '3'}))
    _check('核验-case_auth_policy非法返回20003', r['code'] == 20003, r)

    _restore_aliyun()


# ───────────────────────── 第二轮 签名鉴权 ─────────────────────────

def round2(app):
    _section('第二轮 签名鉴权')

    # 无签名参数
    r = _response(_post(app, '/send', {'phone': TEST_PHONE}, with_sign=False))
    _check('发送-无签名返回20011', r['code'] == 20011, r)

    # 错误签名
    params = _signed(app, {'phone': TEST_PHONE})
    params['sign'] = 'deadbeef'
    r = _response(Client().post(f'{BASE}/send', params))
    _check('发送-错误签名返回20011', r['code'] == 20011, r)

    # 未注册 app_id
    fake = _signed(('app_fake' + '0' * 24, 'sk_fake' + '0' * 58), {'phone': TEST_PHONE})
    r = _response(Client().post(f'{BASE}/send', fake))
    _check('发送-未注册项目返回20011', r['code'] == 20011, r)

    # 时间戳过期（超出 ±5 分钟窗口）
    params = _signed(app, {'phone': TEST_PHONE}, timestamp=int(time.time()) - 3600)
    r = _response(Client().post(f'{BASE}/send', params))
    _check('发送-时间戳过期返回20011', r['code'] == 20011, r)

    # 停用项目
    disabled = _create_app(status=False)
    r = _response(_post(disabled, '/send', {'phone': TEST_PHONE}))
    _check('发送-停用项目返回20011', r['code'] == 20011, r)


# ───────────────────────── 第三轮 Mock 返回映射 ─────────────────────────

def round3(app):
    _section('第三轮 Mock 返回映射')

    # 发送成功
    _mock_aliyun(_ok_send(biz_id='biz_001'))
    r = _response(_post(app, '/send', {'phone': TEST_PHONE}))
    _check('发送-成功返回10000', r['code'] == 10000, r)
    _check('发送-返回biz_id', r.get('data', {}).get('biz_id') == 'biz_001', r)

    # 发送成功 + 返回验证码
    _mock_aliyun(_ok_send(verify_code='5826'))
    r = _response(_post(app, '/send', {'phone': TEST_PHONE, 'return_verify_code': 'true'}))
    _check('发送-return_verify_code返回验证码', r.get('data', {}).get('verify_code') == '5826', r)

    # 发送失败（阿里云频控）
    _mock_aliyun(lambda action, biz: (False, '阿里云返回错误: ISV.SMS_SEND_INTERVAL_LIMIT 触发频控'))
    r = _response(_post(app, '/send', {'phone': TEST_PHONE}))
    _check('发送-阿里云失败返回40001', r['code'] == 40001, r)
    _check('发送-失败透传阿里云错误信息', '频控' in r.get('msg', ''), r)

    # 核验 PASS
    _mock_aliyun(_ok_check('PASS'))
    r = _response(_post(app, '/check', {'phone': TEST_PHONE, 'verify_code': '1234'}))
    _check('核验-PASS返回10000', r['code'] == 10000, r)
    _check('核验-PASS字段', r.get('data', {}).get('verify_result') == 'PASS', r)
    _check('核验-passed为true', r.get('data', {}).get('passed') is True, r)

    # 核验 UNKNOWN（接口仍成功，结果由调用方判断）
    _mock_aliyun(_ok_check('UNKNOWN'))
    r = _response(_post(app, '/check', {'phone': TEST_PHONE, 'verify_code': '0000'}))
    _check('核验-UNKNOWN仍返回10000', r['code'] == 10000, r)
    _check('核验-UNKNOWN字段', r.get('data', {}).get('verify_result') == 'UNKNOWN', r)
    _check('核验-passed为false', r.get('data', {}).get('passed') is False, r)

    # 核验时阿里云调用失败
    _mock_aliyun(lambda action, biz: (False, '阿里云接口请求失败: timeout'))
    r = _response(_post(app, '/check', {'phone': TEST_PHONE, 'verify_code': '1234'}))
    _check('核验-阿里云失败返回40001', r['code'] == 40001, r)

    # 方法限制：GET 调用 send/check（POST 接口）→ 认证通过后 Django 返回 405
    # （未带签名的请求会在认证层先被拦截返回 20011，故此处携带有效签名验证方法限制本身）
    resp = Client().get(f'{BASE}/send', _signed(app, {'phone': TEST_PHONE}))
    _check('方法限制-GET访问send返回405', resp.status_code == 405, resp.status_code)
    resp = Client().get(f'{BASE}/check', _signed(app, {'phone': TEST_PHONE, 'verify_code': '1234'}))
    _check('方法限制-GET访问check返回405', resp.status_code == 405, resp.status_code)

    _restore_aliyun()


# ───────────────────────── 第四轮 真实端到端 ─────────────────────────

def round4(app):
    _section('第四轮 真实端到端（真实发送短信）')
    _restore_aliyun()

    # 发送验证码（ReturnVerifyCode=true 由阿里云直接返回验证码，无需查收短信）
    # interval=10 缩短频控窗口，便于脚本连续运行（生产默认 60 秒）
    send_params = {
        'phone': TEST_PHONE,
        'code_length': '4',
        'return_verify_code': 'true',
        'interval': '10',
    }
    r = _response(_post(app, '/send', send_params))
    # 触发阿里云频控（发送间隔参数控制）时提示等待后重跑，不在脚本内长等待
    if r['code'] != 10000 and 'FREQUENCY' in r.get('msg', ''):
        _log('  [跳过] 触发阿里云频控，请等待 60 秒后重新运行本脚本')
        _check('真实发送-成功返回10000', False, r)
        return

    _check('真实发送-成功返回10000', r['code'] == 10000, r)
    data = r.get('data') or {}
    code = data.get('verify_code')
    _check('真实发送-返回验证码', bool(code), r)
    if code:
        _check('真实发送-验证码为4位数字', code.isdigit() and len(code) == 4, code)

    if not code:
        _log('  [跳过] 未获取到验证码，无法继续核验测试')
        return

    # 错误验证码核验（先于正确核验，避免核验成功后验证码失效）
    wrong = str((int(code) + 1) % 10000).zfill(4)
    if wrong == code:
        wrong = str((int(code) + 2) % 10000).zfill(4)
    r = _response(_post(app, '/check', {'phone': TEST_PHONE, 'verify_code': wrong}))
    _check('真实核验-错误验证码UNKNOWN',
           r['code'] == 10000 and r.get('data', {}).get('verify_result') == 'UNKNOWN', r)

    # 正确验证码核验
    r = _response(_post(app, '/check', {'phone': TEST_PHONE, 'verify_code': code}))
    _check('真实核验-正确验证码PASS',
           r['code'] == 10000 and r.get('data', {}).get('verify_result') == 'PASS', r)


# ───────────────────────── 主流程 ─────────────────────────

def main():
    # 清空旧日志
    if os.path.exists(_LOG_FILE):
        os.remove(_LOG_FILE)

    _log(f'阿里云短信验证码认证 API 测试开始（{time.strftime("%Y-%m-%d %H:%M:%S")}）')
    _log(f'阿里云配置检查: AccessKey={"已配置" if settings.ALIYUN_ACCESS_KEY_ID else "未配置"} | '
         f'SignName={utils.SMS_SIGN_NAME} | TemplateCode={utils.SMS_TEMPLATE_CODE}')

    app = _create_app()
    try:
        round1(app)
        round2(app)
        round3(app)
        round4(app)
    finally:
        # 清理测试数据
        deleted = UserApp.objects.filter(pk__in=[e[2].pk for e in _created_apps]).delete()
        _log(f'\n[清理] 删除测试项目 {deleted[0]} 个')

        _log('\n========== 测试汇总 ==========')
        _log(f'通过: {_stats["pass"]}  |  失败: {_stats["fail"]}  |  总计: {_stats["pass"] + _stats["fail"]}')
        _log('结论: ' + ('全部用例通过' if _stats['fail'] == 0 else '存在失败用例'))


if __name__ == '__main__':
    main()
