"""超级鹰验证码识别服务回归测试

覆盖范围：
    A. 视图层参数校验：状态码约定（直接调视图，绕过中间件）
    B. 爬虫层解析与 md5 校验：err_no 映射、防篡改校验（离线，用桩数据）
    C. 真实上游调用（**按题分计费**）：用本站验证码引擎生成图片，端到端验证识别结果

用法：
    .venv\\Scripts\\python.exe scripts\\test_chaojiying.py

成本提示：C 段每张图片上传即扣题分（1902 约 10~15 题分 / 张，6001 为 15 题分），
默认跑 8 张字符图 + 2 张算术图，约 100~150 题分（≈0.1 元）。
仅当 .env 配置了 CHAOJIYING_USER / CHAOJIYING_PASS 时才执行 C 段，否则记为 SKIP。

说明：报错返分接口（/report-error）**不纳入本脚本的自动回归**——官方明确禁止对「识别正确」的
结果报错（对正确结果报错会被评估信用），故只能在确有识别错误的图上人工验证；本脚本只覆盖它的
参数校验（缺 pic_id → 20001）。
"""
import base64
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'XiaoYingAPI.settings')

import django  # noqa: E402

django.setup()

from django.core.files.uploadedfile import SimpleUploadedFile  # noqa: E402
from django.test import RequestFactory  # noqa: E402

import SpiderServices.Chaojiying.home as cj_home  # noqa: E402
import SpiderServices.Chaojiying.utils as cj_utils  # noqa: E402
from API.apis.chaojiying import request as cj_request  # noqa: E402
from SpiderServices.Captcha import generator  # noqa: E402

PASS = FAIL = SKIP = 0

# C 段张数（越小越省题分）
CHAR_COUNT = 8      # 字符验证码，codetype 1902（1~6 位英文数字）
ARITH_COUNT = 2     # 算术验证码，codetype 6001（返回计算结果）

_rf = RequestFactory()


def check(name, ok, extra=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print('PASS', name)
    else:
        FAIL += 1
        print('FAIL', name, extra)


def skip(name, why):
    global SKIP
    SKIP += 1
    print('SKIP', name, '—', why)


def body(resp):
    return json.loads(resp.content.decode('utf-8'))


# ==================== A. 视图层参数校验 ====================

def test_view_params():
    print('\n--- A. 视图层参数校验 ---')

    def code_of(data):
        return body(cj_request.ocr_view(_rf.post('/api/chaojiying/ocr', data)))['code']

    check('缺少 codetype → 20001', code_of({}) == 20001)
    check('codetype 非法 → 20003', code_of({'codetype': '9999'}) == 20003)
    check('缺少图片来源 → 20001', code_of({'codetype': '1902'}) == 20001)
    check('image 非合法 base64 → 20002',
          code_of({'codetype': '1902', 'image': '!!!not-base64!!!'}) == 20002)
    check('image 超过 2MB → 20003',
          code_of({'codetype': '1902', 'image': 'A' * (3 * 1024 * 1024)}) == 20003)
    check('image 为内网地址 → 20003（S-09 拒绝）',
          code_of({'codetype': '1902', 'image': 'http://127.0.0.1/captcha.png'}) == 20003)

    resp = body(cj_request.report_error_view(_rf.post('/api/chaojiying/report-error', {})))
    check('缺少 pic_id → 20001', resp['code'] == 20001)


# ==================== B. 解析与 md5 校验 ====================

def test_parse_and_md5():
    print('\n--- B. 解析与 md5 校验（离线） ---')
    service = cj_home.ChaojiyingService

    parsed = service._parse({'err_no': 0, 'err_str': 'OK', 'pic_id': '1',
                             'pic_str': '8vka', 'md5': 'abc'},
                            ['pic_id', 'pic_str', 'md5'])
    check('err_no=0 → code 0 且摘取业务字段',
          parsed['code'] == 0 and parsed['data'] == {'pic_id': '1', 'pic_str': '8vka', 'md5': 'abc'})

    parsed = service._parse({'err_no': 10016, 'err_str': '用户不存在'}, ['pic_id'])
    check('err_no≠0 → 保留平台错误码与中文说明',
          parsed['code'] == 10016 and parsed['message'] == '用户不存在' and parsed['data'] is None)

    old_id, old_key = cj_home.SOFT_ID, cj_home.SOFT_KEY
    try:
        # 未配置软件ID / 软件KEY → 跳过校验
        cj_home.SOFT_ID = cj_home.SOFT_KEY = ''
        check('未配置软件ID/KEY → 跳过 md5 校验',
              service._verify_md5({'pic_id': '1', 'pic_str': 'ab', 'md5': ''}) is True)

        # 已配置 → 官方算法 md5(软件ID,软件KEY,图片ID,图片结果)，半角逗号分隔
        cj_home.SOFT_ID, cj_home.SOFT_KEY = '984005', 'testkey'
        good = cj_utils.md5_hex('984005,testkey,123,8vka')
        check('md5 与返回一致 → 通过',
              service._verify_md5({'pic_id': '123', 'pic_str': '8vka', 'md5': good}) is True)
        check('md5 与返回不一致 → 拒绝',
              service._verify_md5({'pic_id': '123', 'pic_str': '8vka', 'md5': 'deadbeef'}) is False)
        check('md5 大小写不敏感',
              service._verify_md5({'pic_id': '123', 'pic_str': '8vka', 'md5': good.upper()}) is True)
    finally:
        cj_home.SOFT_ID, cj_home.SOFT_KEY = old_id, old_key


# ==================== C. 真实上游（端到端）====================

def recognize_via_view(png_bytes, codetype, use_file):
    """走完整的视图链路（与真实调用一致，仅绕过 HTTP 与中间件）

    :param use_file: True 走 multipart 文件上传，False 走 base64 文本
    """
    if use_file:
        data = {'codetype': codetype,
                'file': SimpleUploadedFile('captcha.png', png_bytes, content_type='image/png')}
    else:
        data = {'codetype': codetype,
                'image': 'data:image/png;base64,' + base64.b64encode(png_bytes).decode()}
    return body(cj_request.ocr_view(_rf.post('/api/chaojiying/ocr', data)))


def test_live():
    print('\n--- C. 真实上游（端到端识别） ---')
    if not (cj_utils.USER and cj_utils.PASSWORD):
        skip('真实上游识别', '未配置 CHAOJIYING_USER / CHAOJIYING_PASS')
        return

    # 先查余额，确认账号可用且有题分
    score = body(cj_request.score_view(_rf.get('/api/chaojiying/score')))
    if score['code'] != 10000:
        skip('真实上游识别', f'查询题分失败：{score["msg"]}')
        return
    print(f'  题分余额：{score["data"]}')

    # C1. 字符验证码（codetype 1902），首张走文件上传、其余走 base64
    ok_count = 0
    for i in range(CHAR_COUNT):
        length = 4 + i % 3                      # 4 / 5 / 6 位各覆盖
        png_bytes, answer = generator.new_char_captcha(length)
        resp = recognize_via_view(png_bytes, '1902', use_file=(i == 0))
        got = (resp.get('data') or {}).get('pic_str', '')
        hit = got.strip().upper() == answer.upper()
        ok_count += hit
        check(f'字符验证码[{i + 1}] 期望 {answer} 实际 {got!r}', hit, f'resp={resp}')
    print(f'  字符验证码识别率：{ok_count}/{CHAR_COUNT}')

    # C2. 算术验证码（codetype 6001）
    ok_arith = 0
    for i in range(ARITH_COUNT):
        png_bytes, answer = generator.new_arithmetic_captcha()
        resp = recognize_via_view(png_bytes, '6001', use_file=False)
        got = (resp.get('data') or {}).get('pic_str', '')
        hit = got.strip() == answer
        ok_arith += hit
        check(f'算术验证码[{i + 1}] 期望 {answer} 实际 {got!r}', hit, f'resp={resp}')
    print(f'  算术验证码识别率：{ok_arith}/{ARITH_COUNT}')


def main():
    print('=== 超级鹰验证码识别服务回归测试 ===')
    test_view_params()
    test_parse_and_md5()
    test_live()
    print(f'\n=== 汇总：PASS {PASS} / FAIL {FAIL} / SKIP {SKIP} ===')
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
