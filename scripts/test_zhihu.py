"""知乎服务回归脚本（热榜 / 凭据校验 / 通用账号托管底层）

覆盖范围：
    A. 参数校验：limit 的缺省、格式与范围（视图 + 纯函数两层）
    B. 无可用账号：业务层给出「尚未配置」提示，视图映射成 50002（服务不可用）
    C. 后台 /console/accounts/：平台账号的增删改查、凭据加密落库与不回显、一键校验
    D. 业务编排：取托管账号 → 调爬虫 → 凭据失效时回写「已过期」（爬虫用桩替代，不发起真实请求）
    D2. 调用方自带 Cookie：优先用调用方的、不碰平台账号；GET / POST 都接受，其它方法 405
    E. 签名 HTTP：走完整中间件链，验证新服务 /api/zhihu/ 默认需签名（fail-closed）
    F. 文档页：右侧栏「本机凭据」卡与端点声明（调试时自动带上 Cookie）
    G. 内容详情与综合搜索：问题 / 文章 / 搜索的入参归一、结构归一（驼峰→下划线、图片、子评论）与视图校验编排
    H. 真实上游：仅当库里存在有效托管账号时才执行（否则记为 SKIP）

用法：
    .venv\\Scripts\\python.exe scripts\\test_zhihu.py

说明：脚本会自动创建临时超管 / 接入项目 / 平台账号，并在结束时清理；
期间对爬虫与校验器打桩，因此默认不产生任何真实网络请求。
"""
import json
import os
import secrets
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'XiaoYingAPI.settings')

import django  # noqa: E402

django.setup()

from django.contrib.auth import get_user_model            # noqa: E402
from django.db import connection                         # noqa: E402
from django.test import Client, RequestFactory          # noqa: E402

from API.apis.user_center.sign import build_sign         # noqa: E402
from API.common import StatusCode, platform_accounts     # noqa: E402
from API.apis.zhihu import request as zhihu_request, utils as zhihu_utils  # noqa: E402
from API.models import AccountStatus, Platform, PlatformAccount, UserApp  # noqa: E402
from SpiderServices.zhihu import utils as spider_utils   # noqa: E402
from SpiderServices.zhihu.main import (                  # noqa: E402
    ZhihuCredentialExpired,
    ZhihuError,
    ZhihuSpider as RealZhihuSpider,
)

PASS = FAIL = SKIP = 0
# 本脚本创建的临时数据一律带这个前缀，异常中断后下次运行会先自愈清理
PREFIX = '_regress_zhihu_'
COOKIE = '_xsrf=regress; d_c0=REGRESSCOOKIE123; z_c0=zzz'
# 真实上游用例用的示例专栏文章（需求方给的示例）；若被作者删除，该项只 SKIP 不算失败
ARTICLE_ID = '608180793'
CONSOLE = '/console/accounts/'
RF = RequestFactory()


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


def cleanup():
    """清掉本脚本可能留下的临时数据（开头与结尾各跑一次，避免上次中断导致本次跑挂）"""
    PlatformAccount.objects.filter(account__startswith=PREFIX).delete()
    UserApp.objects.filter(name__startswith=PREFIX).delete()


cleanup()

# ==================== A. 参数校验 ====================
val, err = zhihu_request._optional_int(None, 'limit', 50, 1, 50)
check('limit 不传 → 取默认 50', val == 50 and err is None, (val, err))
val, err = zhihu_request._optional_int('  ', 'limit', 50, 1, 50)
check('limit 空白串 → 取默认 50', val == 50 and err is None, (val, err))
val, err = zhihu_request._optional_int('7', 'limit', 50, 1, 50)
check('limit 合法整数 → 原样使用', val == 7 and err is None, (val, err))

_, err = zhihu_request._optional_int('abc', 'limit', 50, 1, 50)
check('limit 非整数 → 20002 参数格式错误',
      err is not None and body(err)['code'] == StatusCode.PARAM_FORMAT_ERROR)
_, err = zhihu_request._optional_int('1.5', 'limit', 50, 1, 50)
check('limit 小数 → 20002 参数格式错误',
      err is not None and body(err)['code'] == StatusCode.PARAM_FORMAT_ERROR)
_, err = zhihu_request._optional_int('0', 'limit', 50, 1, 50)
check('limit 低于下界 → 20003 参数值非法',
      err is not None and body(err)['code'] == StatusCode.PARAM_VALUE_INVALID)
_, err = zhihu_request._optional_int('51', 'limit', 50, 1, 50)
check('limit 高于上界 → 20003 参数值非法',
      err is not None and body(err)['code'] == StatusCode.PARAM_VALUE_INVALID)

r = body(zhihu_request.hot_view(RF.get('/api/zhihu/hot', {'limit': 'abc'})))
check('视图: limit=abc → 20002', r['code'] == StatusCode.PARAM_FORMAT_ERROR and r['data'] is None, r)
r = body(zhihu_request.hot_view(RF.get('/api/zhihu/hot', {'limit': '999'})))
check('视图: limit=999 → 20003', r['code'] == StatusCode.PARAM_VALUE_INVALID, r)


# ---- 上游响应判定：凭据失效 vs 风控（别把瞬时风控误判成「凭据过期」） ----
class _FakeResp:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


def exc_of(fn):
    try:
        fn()
    except Exception as error:      # noqa: BLE001 —— 测试就是要抓异常做判定
        return error
    return None


_verdict = RealZhihuSpider._raise_for_response
err = exc_of(lambda: _verdict(_FakeResp(
    401, {'error': {'code': 100, 'message': 'ERR_TICKET_NOT_EXIST'}})))
check('响应判定：401 且 code=100 → 凭据失效', isinstance(err, ZhihuCredentialExpired), err)
err = exc_of(lambda: _verdict(_FakeResp(
    403, {'error': {'code': 40362, 'message': '您当前请求存在异常，暂时限制本次访问'}})))
check('响应判定：403 且 code=40362（风控）→ 普通失败，不当作凭据失效',
      isinstance(err, ZhihuError) and not isinstance(err, ZhihuCredentialExpired), err)
err = exc_of(lambda: _verdict(_FakeResp(
    403, {'error': {'code': 10003, 'message': '请求参数异常，请升级客户端后重试。'}})))
check('响应判定：403 且 code=10003 → 普通失败并带上知乎原文',
      isinstance(err, ZhihuError) and not isinstance(err, ZhihuCredentialExpired)
      and '请求参数异常' in str(err), err)
err = exc_of(lambda: _verdict(_FakeResp(200, {'data': []})))
check('响应判定：200 不抛异常', err is None, err)

# ==================== B. 无可用账号 ====================
_real_get = platform_accounts.get_available_account
platform_accounts.get_available_account = lambda platform: None
try:
    spider, account, error = zhihu_utils._usable_spider()
    check('无可用账号 → _usable_spider 返回「尚未配置」提示',
          spider is None and account is None and error == zhihu_utils.NO_ACCOUNT_MESSAGE, error)
    ok, msg = zhihu_utils.get_hot(5)
    check('无可用账号 → get_hot 返回失败 + 未配置提示',
          not ok and '尚未配置' in msg, msg)
    r = body(zhihu_request.hot_view(RF.get('/api/zhihu/hot')))
    check('无可用账号 → 视图映射成 50002 服务不可用',
          r['code'] == StatusCode.SERVICE_UNAVAILABLE and '尚未配置' in r['msg'], r)
finally:
    platform_accounts.get_available_account = _real_get

# ==================== C. 后台账号管理页 ====================
AuthUser = get_user_model()
su = AuthUser.objects.filter(is_superuser=True).first()
tmp_user = None
if su is None:
    su = tmp_user = AuthUser.objects.create_superuser(f'{PREFIX}su', 'regress-zhihu@example.com', 'x')
client = Client()
client.force_login(su)

NAME = f'{PREFIX}acct'
# 先建一个「未接入校验器」的平台账号（百家号），用来验证「暂不支持校验」的展示分支
# （注意：微博已接入校验器，不能再拿它当反例）
client.post(CONSOLE, {'action': 'save', 'platform': 'baijiahao', 'account': f'{PREFIX}nochk'})
html = client.get(CONSOLE).content.decode('utf-8')
check('后台页 200 且含标题与新增表单',
      '账号管理' in html and 'name="credential"' in html and 'con-panel' in html)
check('平台下拉含全部平台选项',
      all(value in html for value, _label in Platform.choices), Platform.choices)
check('未接入校验器的平台显示「暂不支持校验」', '暂不支持校验' in html)
PlatformAccount.objects.filter(account=f'{PREFIX}nochk').delete()

client.post(CONSOLE, {'action': 'save', 'platform': 'zhihu', 'account': NAME,
                      'credential': COOKIE, 'remark': '回归'})
record = PlatformAccount.objects.filter(platform='zhihu', account=NAME).first()
check('后台新增账号成功', record is not None)
check('新账号凭据状态为「未校验」', record is not None and record.status == AccountStatus.UNKNOWN)
check('新账号记一笔最近登录时间', record is not None and record.last_login_time is not None)
with connection.cursor() as cur:
    # Django 原始 SQL 用 %s 占位（sqlite 后端在驱动层转 ?）
    cur.execute('SELECT credential FROM platform_account WHERE account = %s', [NAME])
    stored = cur.fetchone()[0]
check('凭据落库为 enc:v1: 密文（不含明文）',
      str(stored).startswith('enc:v1:') and COOKIE not in str(stored), str(stored)[:40])
check('字段层透明解密，取回明文一致',
      record is not None and platform_accounts.credential_of(record) == COOKIE)

html = client.get(CONSOLE).content.decode('utf-8')
check('列表页不回显凭据明文', COOKIE not in html and NAME in html)

client.post(CONSOLE, {'action': 'save', 'id': str(record.pk), 'platform': 'zhihu',
                      'account': NAME, 'credential': '', 'remark': '回归-改备注'})
record.refresh_from_db()
check('编辑时凭据留空 → 保持原值不变',
      platform_accounts.credential_of(record) == COOKIE and record.remark == '回归-改备注')

client.post(CONSOLE, {'action': 'save', 'platform': 'zhihu', 'account': NAME,
                      'credential': 'x=1'})
check('同一平台下账号标识重复 → 拒绝且不覆盖',
      PlatformAccount.objects.filter(platform='zhihu', account=NAME).count() == 1
      and platform_accounts.credential_of(
          PlatformAccount.objects.get(platform='zhihu', account=NAME)) == COOKIE)

client.post(CONSOLE, {'action': 'save', 'platform': 'not-a-platform', 'account': f'{PREFIX}x'})
check('非法平台取值被拒', not PlatformAccount.objects.filter(account=f'{PREFIX}x').exists())
client.post(CONSOLE, {'action': 'save', 'platform': 'zhihu', 'account': '   '})
check('空账号标识被拒', PlatformAccount.objects.filter(platform='zhihu', account='').count() == 0)

# 「校验」动作：给校验器打桩，避免真实外呼；同时验证结果会回写状态
_real_load = platform_accounts._load_checker
platform_accounts._load_checker = (
    lambda platform: (lambda cookie: (True, '回归桩：凭据有效（登录用户：regress）')))
try:
    client.post(CONSOLE, {'action': 'check', 'id': str(record.pk)})
    record.refresh_from_db()
    check('「校验」把结果回写账号状态（valid）',
          record.status == AccountStatus.VALID and '回归桩' in record.check_message,
          record.check_message)
    check('「校验」记录最近校验时间', record.last_check_time is not None)
finally:
    platform_accounts._load_checker = _real_load

client.post(CONSOLE, {'action': 'delete', 'id': str(record.pk)})
check('后台删除账号', not PlatformAccount.objects.filter(account=NAME).exists())

# ==================== D. 业务编排（爬虫打桩，不发起真实请求） ====================
class FakeSpider:
    """替身爬虫：按构造参数决定返回或抛错，用来验证编排逻辑"""

    behavior = 'ok'

    def __init__(self, cookie='', timeout=None):
        self.cookie = cookie

    def get_hot(self, limit=50):
        if FakeSpider.behavior == 'expired':
            raise ZhihuCredentialExpired('知乎登录凭据已过期或无效，请重新登录后再试')
        if FakeSpider.behavior == 'error':
            raise ZhihuError('上游返回异常')
        return [{'rank': i + 1, 'title': f'标题{i + 1}', 'url': f'https://www.zhihu.com/question/{i}',
                 'excerpt': '', 'hot': '1370 万热度', 'answer_count': i, 'question_id': i,
                 'cover': ''} for i in range(limit)]

    def check_cookie(self):
        # 与真实实现一致：凭据问题**返回** (False, 说明)，而不是抛异常
        if FakeSpider.behavior == 'expired':
            return False, '知乎登录凭据已过期或无效，请重新登录后再试'
        if FakeSpider.behavior == 'error':
            return False, '上游返回异常'
        return True, '凭据有效（登录用户：regress）'


record = PlatformAccount.objects.create(platform='zhihu', account=f'{PREFIX}spider')
record.credential = COOKIE
record.save()


def stub_check(cookie):
    """替身校验器：行为跟随 FakeSpider.behavior，避免真实外呼"""
    if FakeSpider.behavior == 'expired':
        return False, '知乎登录凭据已过期或无效，请重新登录后再试'
    return True, '凭据有效（登录用户：regress）'


_real_spider = zhihu_utils.ZhihuSpider
_real_get2 = platform_accounts.get_available_account
_real_checker = platform_accounts._load_checker
zhihu_utils.ZhihuSpider = FakeSpider
# 固定取到本段临时账号、并用替身校验器，确保不受库里真实账号与网络状态影响
platform_accounts.get_available_account = lambda platform: record
platform_accounts._load_checker = lambda platform: stub_check
try:
    FakeSpider.behavior = 'ok'
    ok, data = zhihu_utils.get_hot(5)
    check('取托管账号 → 热榜返回请求条数', ok and len(data) == 5, data if not ok else len(data))
    check('热榜条目字段齐全（rank/title/url/hot/answer_count/question_id）',
          ok and {'rank', 'title', 'url', 'hot', 'answer_count', 'question_id'} <= set(data[0]))

    ok, result = zhihu_utils.check_credential()
    check('校验凭据：有效 → valid=True 并带上账号标识',
          ok and result['valid'] is True and result['account'] == f'{PREFIX}spider', result)
    record.refresh_from_db()
    check('校验后账号状态回写为 valid', record.status == AccountStatus.VALID)

    FakeSpider.behavior = 'expired'
    record.status = AccountStatus.VALID
    record.save(update_fields=['status', 'updated_time'])
    ok, msg = zhihu_utils.get_hot(5)
    record.refresh_from_db()
    check('爬虫报凭据过期 → get_hot 失败并回传原因', not ok and '过期' in msg, msg)
    check('爬虫报凭据过期 → 账号被顺手标记为 expired',
          record.status == AccountStatus.EXPIRED and record.last_check_time is not None)

    FakeSpider.behavior = 'error'
    ok, msg = zhihu_utils.get_hot(5)
    check('上游普通异常 → get_hot 失败但状态不被改写',
          not ok and '上游' in msg and record.status == AccountStatus.EXPIRED, msg)
finally:
    zhihu_utils.ZhihuSpider = _real_spider
    platform_accounts.get_available_account = _real_get2
    platform_accounts._load_checker = _real_checker
    PlatformAccount.objects.filter(account=f'{PREFIX}spider').delete()

# ==================== D2. 调用方自带 Cookie（优先，且不碰平台账号） ====================
record = PlatformAccount.objects.create(platform='zhihu', account=f'{PREFIX}caller')
record.credential = COOKIE
record.save()


class RecordingSpider(FakeSpider):
    """记录每次构造时收到的 cookie，用来验证参数确实透传到了爬虫"""

    seen = []

    def __init__(self, cookie='', timeout=None):
        super().__init__(cookie, timeout)
        RecordingSpider.seen.append(cookie)


_real_spider = zhihu_utils.ZhihuSpider
_real_get = platform_accounts.get_available_account
zhihu_utils.ZhihuSpider = RecordingSpider
platform_accounts.get_available_account = lambda platform: record
try:
    spider, account, error = zhihu_utils._usable_spider('CALLER_COOKIE')
    check('自带 Cookie → 直接用调用方凭据、不取平台账号',
          spider.cookie == 'CALLER_COOKIE' and account is None and error is None,
          (spider.cookie, account, error))
    spider, account, error = zhihu_utils._usable_spider('')
    check('不带 Cookie → 回落到平台托管的账号',
          account is record and spider.cookie == COOKIE and error is None)

    RecordingSpider.seen = []
    FakeSpider.behavior = 'ok'
    r = body(zhihu_request.hot_view(RF.get('/api/zhihu/hot', {'cookie': 'FROM_GET'})))
    r2 = body(zhihu_request.hot_view(RF.post('/api/zhihu/hot',
                                             {'cookie': 'FROM_POST', 'limit': '3'})))
    check('GET 传 cookie → 透传给爬虫', r['code'] == StatusCode.SUCCESS
          and RecordingSpider.seen[-2] == 'FROM_GET', (r['code'], RecordingSpider.seen))
    check('POST 表单体传 cookie → 透传给爬虫', r2['code'] == StatusCode.SUCCESS
          and RecordingSpider.seen[-1] == 'FROM_POST', (r2['code'], RecordingSpider.seen))
    check('不带 cookie 的请求 → 爬虫拿到的是平台账号凭据',
          zhihu_request.hot_view(RF.get('/api/zhihu/hot')) and RecordingSpider.seen[-1] == COOKIE)

    resp = zhihu_request.hot_view(RF.put('/api/zhihu/hot'))
    check('只接受 GET / POST，其它方法返回 405', resp.status_code == 405, resp.status_code)

    # 自带 Cookie 失效：接口如实报错，但**不得**去改平台账号的状态
    FakeSpider.behavior = 'expired'
    record.status = AccountStatus.VALID
    record.save(update_fields=['status', 'updated_time'])
    ok, msg = zhihu_utils.get_hot(5, cookie='CALLER_COOKIE')
    record.refresh_from_db()
    check('自带 Cookie 失效 → 上报失败但平台账号状态不变',
          not ok and '过期' in msg and record.status == AccountStatus.VALID,
          (ok, msg, record.status))

    ok, result = zhihu_utils.check_credential(cookie='CALLER_COOKIE')
    record.refresh_from_db()
    check('/check 自带 Cookie → valid=False、account 为空、平台账号状态不变',
          ok and result['valid'] is False and result['account'] == ''
          and record.status == AccountStatus.VALID, result)
    FakeSpider.behavior = 'ok'
    ok, result = zhihu_utils.check_credential(cookie='CALLER_COOKIE')
    check('/check 自带 Cookie 有效 → valid=True', ok and result['valid'] is True, result)
finally:
    zhihu_utils.ZhihuSpider = _real_spider
    platform_accounts.get_available_account = _real_get
    PlatformAccount.objects.filter(account=f'{PREFIX}caller').delete()

# ==================== E. 签名 HTTP（走完整中间件链） ====================
app = UserApp.objects.create(name=f'{PREFIX}app', token_expire_days=7, status=True)


def signed_params(extra=None):
    params = {'app_id': app.app_id, 'timestamp': str(int(time.time())),
              'nonce': secrets.token_hex(8)}
    if extra:
        params.update(extra)
    params['sign'] = build_sign(params, app.app_secret)
    return params


r = body(client.get('/api/zhihu/hot'))
check('新服务默认需签名：无签名 → 20011', r['code'] == StatusCode.AUTH_FAILED, r)

r = body(client.get('/api/zhihu/hot', signed_params({'limit': '5'})))
check('带正确签名可进入业务（不再返回 20011）',
      r['code'] != StatusCode.AUTH_FAILED, r)
check('签名通过后确实到达业务层（成功 / 未配置 / 上游失败 三者之一）',
      r['code'] in (StatusCode.SUCCESS, StatusCode.SERVICE_UNAVAILABLE,
                    StatusCode.EXTERNAL_API_FAILED), r)

r = body(client.post('/api/zhihu/hot', signed_params({'limit': '3'})))
check('POST 表单体同样走签名认证并到达业务层',
      r['code'] in (StatusCode.SUCCESS, StatusCode.SERVICE_UNAVAILABLE,
                    StatusCode.EXTERNAL_API_FAILED), r)

r = body(client.get('/api/zhihu/hot', {'limit': '5', 'app_id': app.app_id,
                                       'timestamp': str(int(time.time())),
                                       'nonce': secrets.token_hex(8), 'sign': 'deadbeef'}))
check('签名错误 → 20011', r['code'] == StatusCode.AUTH_FAILED, r)

r = body(client.get('/api/zhihu/hot', signed_params({'limit': 'abc'})))
check('签名通过后仍走参数校验（limit=abc → 20002）',
      r['code'] == StatusCode.PARAM_FORMAT_ERROR, r)

# ==================== F. 文档页「本机凭据」卡 ====================
docs_html = client.get('/docs/zhihu/').content.decode('utf-8')
check('文档页 /docs/zhihu/ 渲染成功',
      '知乎' in docs_html and '/api/zhihu/hot' in docs_html)
check('右侧栏出现「本机凭据」卡且含 Cookie 字段',
      'docs-local-card' in docs_html and '知乎登录 Cookie' in docs_html)
check('五个端点都声明了本机凭据参数（调试时自动带上）',
      docs_html.count('data-local-params="cookie "') == 5,
      docs_html.count('data-local-params="cookie "'))
check('端点对外展示为 POST（长 Cookie 走表单体）',
      docs_html.count('>POST<') >= 5, docs_html.count('>POST<'))
check('问题详情 / 专栏文章 / 综合搜索端点都已登记到文档',
      '/api/zhihu/question' in docs_html and '/api/zhihu/article' in docs_html
      and '/api/zhihu/search' in docs_html)

# ==================== G. 内容详情（问题 / 专栏文章） ====================
check('问题 ID 归一：纯数字',
      spider_utils.question_id_of('2089437755591713926') == '2089437755591713926')
check('问题 ID 归一：问题网页地址（带查询串也可）',
      spider_utils.question_id_of('https://www.zhihu.com/question/2089437755591713926?x=1')
      == '2089437755591713926')
check('问题 ID 归一：取不到 ID → 空串', spider_utils.question_id_of('abc') == '')
check('网页地址拼装',
      spider_utils.answer_url('1', '2') == 'https://www.zhihu.com/question/1/answer/2'
      and spider_utils.question_url('1') == 'https://www.zhihu.com/question/1')
check('搜索页地址带编码', 'search?type=content&q=' in spider_utils.search_url('a b'))
check('正文图片抽取：data-original 优先、去重、保序',
      spider_utils.extract_images(
          '<img data-original="A" src="a"><img src="B"><img src="A"><img>') == ['A', 'B'],
      spider_utils.extract_images('<img data-original="A" src="a">'))

spider = RealZhihuSpider(cookie='x')
question = spider._norm_question('123', {
    'id': '123', 'title': '标题', 'detail': '<p>正文</p><img src="pic">',
    'excerpt': '摘要', 'topics': [{'id': '9', 'name': '体育'}],
    'answerCount': 7, 'followerCount': 8, 'commentCount': 9, 'visitCount': 10,
    'created': 111, 'updatedTime': 222,
})
check('问题归一：驼峰计数映射为下划线', question['answer_count'] == 7
      and question['follower_count'] == 8 and question['comment_count'] == 9
      and question['visit_count'] == 10, question)
check('问题归一：正文图片与话题',
      question['images'] == ['pic'] and question['topics'][0]['name'] == '体育'
      and question['topics'][0]['url'].endswith('/topic/9'), question['topics'])
check('问题归一：网页地址按问题 ID 拼', question['url'].endswith('/question/123'))

comment = spider._norm_comment({
    'id': 5, 'content': '评论', 'author': {'name': '甲', 'url_token': 'jia'},
    'like_count': 3, 'child_comment_count': 9, 'reply_author_tag': {'name': '乙'},
    'child_comments': [{'id': i, 'content': f'c{i}'} for i in range(5)],
})
check('评论归一：字段映射与作者主页',
      comment['id'] == '5' and comment['author']['name'] == '甲'
      and comment['author']['url'].endswith('/people/jia') and comment['like_count'] == 3
      and comment['child_comment_count'] == 9 and comment['reply_to_author'] == '乙', comment)
check('评论归一：子评论最多 3 条且不再向下展开',
      len(comment['child_comments']) == 3
      and comment['child_comments'][0]['child_comments'] == [], comment['child_comments'])
check('作者归一：兼容 v4 的 {member, role} 结构',
      spider._norm_author({'member': {'name': '丙'}, 'role': 'normal'})['name'] == '丙')

# ---- 专栏文章：入参与结构归一 ----
check('文章 ID 归一：文章网页地址 / 纯数字 / 无效',
      spider_utils.article_id_of('https://zhuanlan.zhihu.com/p/608180793') == '608180793'
      and spider_utils.article_id_of('608180793') == '608180793'
      and spider_utils.article_id_of('abc') == '')
check('文章网页地址拼装',
      spider_utils.article_url('608180793') == 'https://zhuanlan.zhihu.com/p/608180793')
check('作者归一：兼容文章实体的驼峰字段（urlToken / avatarUrl）',
      spider._norm_author({'name': '甲', 'urlToken': 'jia', 'avatarUrl': 'http://a.png'})
      == {'name': '甲', 'url_token': 'jia', 'headline': '', 'avatar_url': 'http://a.png',
          'url': 'https://www.zhihu.com/people/jia'},
      spider._norm_author({'name': '甲', 'urlToken': 'jia', 'avatarUrl': 'http://a.png'}))
check('作者归一：无 urlToken 时用相对主页地址兜底',
      spider._norm_author({'name': '乙', 'url': '/people/abc'})['url']
      == 'https://www.zhihu.com/people/abc')

article = spider._norm_article('608180793', {
    'id': '608180793', 'title': '文章标题',
    'content': '<p>正文</p><img data-original="P1" src="p1"><img src="P2">',
    'excerpt': '摘要', 'topics': [{'id': '9', 'name': '话题'}],
    'author': {'name': '甲', 'urlToken': 'jia'},
    'voteupCount': 172, 'commentCount': 11, 'likedCount': 13, 'favlistsCount': 98,
    'contentNeedTruncated': False, 'created': 1676964938, 'updated': 1676968241,
})
check('文章归一：计数与时间映射',
      article['voteup_count'] == 172 and article['comment_count'] == 11
      and article['liked_count'] == 13 and article['favlists_count'] == 98
      and article['created_time'] == 1676964938 and article['updated_time'] == 1676968241,
      article)
check('文章归一：正文图片抽取、作者与话题',
      article['images'] == ['P1', 'P2'] and article['author']['name'] == '甲'
      and article['topics'][0]['name'] == '话题' and article['content_truncated'] is False,
      article)
check('文章归一：网页地址按文章 ID 拼',
      article['url'] == 'https://zhuanlan.zhihu.com/p/608180793')
check('文章归一：contentNeedTruncated=True 时如实标识',
      spider._norm_article('1', {'contentNeedTruncated': True})['content_truncated'] is True)

# ---- 综合搜索：纯函数与条目归一 ----
check('搜索去标签：去掉 <em> 高亮并还原实体',
      spider_utils.strip_html('<em>学生妹</em>真&quot;香&quot;') == '学生妹真"香"')
check('搜索去标签：空值 / 无标签 → 空串或原样',
      spider_utils.strip_html(None) == '' and spider_utils.strip_html('纯文本') == '纯文本')
check('搜索条目地址：answer 需带问题 ID 才能拼',
      spider_utils.search_result_url('answer', '2', '1')
      == 'https://www.zhihu.com/question/1/answer/2'
      and spider_utils.search_result_url('article', '9')
      == 'https://zhuanlan.zhihu.com/p/9'
      and spider_utils.search_result_url('zvideo', '7')
      == 'https://www.zhihu.com/zvideo/7')
check('搜索条目地址：缺 kind / id → 空串',
      spider_utils.search_result_url('', '') == '')

search_item = spider._norm_search_item({
    'object': {
        'type': 'answer', 'id': 123456, 'title': '看完<em>学生妹</em>的&quot;帖&quot;',
        'content': '<p>正文</p><img data-original="P1"><img src="P2">',
        'excerpt': '<em>摘要</em>', 'author': {'name': '甲', 'url_token': 'jia'},
        'voteup_count': 5, 'comment_count': 6, 'created_time': 11, 'updated_time': 22,
        'question': {'id': 999, 'name': '问题标题'},
    },
}, 3)
check('搜索条目归一：标题 / 摘要去高亮标签与实体',
      search_item['title'] == '看完学生妹的"帖"' and search_item['excerpt'] == '摘要',
      search_item)
check('搜索条目归一：回答地址按所属问题拼、正文图片抽出',
      search_item['url'] == 'https://www.zhihu.com/question/999/answer/123456'
      and search_item['images'] == ['P1', 'P2'] and search_item['type'] == 'answer',
      search_item)
check('搜索条目归一：回答带上所属问题',
      search_item['question'] == {'id': '999', 'title': '问题标题',
                                  'url': 'https://www.zhihu.com/question/999'},
      search_item['question'])
check('搜索条目归一：序号即传入的 index',
      search_item['index'] == 3 and search_item['comment_count'] == 6)
check('搜索条目归一：文章走专栏地址、无正文的视频 content 为空',
      spider._norm_search_item({'object': {'type': 'article', 'id': 456}}, 1)['url']
      == 'https://zhuanlan.zhihu.com/p/456'
      and spider._norm_search_item({'object': {'type': 'zvideo', 'id': 789}}, 1)
      ['content'] == '')

# 翻页：next_offset 由 offset + 本页条数算出；到底（is_end）或空结果时为 null
_paged = RealZhihuSpider(cookie='x')
_paged._get_json = lambda *a, **k: {'data': [{'object': {'type': 'article', 'id': 1}},
                                             {'object': {'type': 'article', 'id': 2}}],
                                    'paging': {'is_end': False}}
_paged._get_hot_search = lambda *a, **k: []
_pager = _paged.get_search('kw', 20, 5)
check('搜索翻页：next_offset = offset + 本页条数',
      _pager['count'] == 2 and _pager['is_end'] is False
      and _pager['next_offset'] == 7, _pager)
_paged._get_json = lambda *a, **k: {'data': [{'object': {'type': 'article', 'id': 1}}],
                                    'paging': {'is_end': True}}
check('搜索翻页：is_end 为真 → next_offset 为 null',
      _paged.get_search('kw', 20, 0)['next_offset'] is None)
_paged._get_json = lambda *a, **k: {'data': [], 'paging': {'is_end': False}}
check('搜索翻页：空结果 → next_offset 为 null',
      _paged.get_search('kw', 20, 0)['next_offset'] is None)


class FakeDetailSpider(FakeSpider):
    """替身详情爬虫：记录调用参数并返回最小结构，供视图层用例断言"""

    last = {}

    def get_question(self, question_id, answer_limit=5, comment_limit=3,
                     question_comment_limit=10):
        FakeDetailSpider.last = {'qid': question_id, 'answers': answer_limit,
                                 'comments': comment_limit,
                                 'question_comments': question_comment_limit,
                                 'cookie': self.cookie}
        if FakeDetailSpider.behavior == 'expired':
            raise ZhihuCredentialExpired('知乎登录凭据已过期或无效，请重新登录后再试')
        return {'question': {'id': question_id, 'comments': []}, 'answers': [],
                'related_questions': [], 'hot_searches': []}

    def get_article(self, article_id, comment_limit=10):
        FakeDetailSpider.last = {'aid': article_id, 'comments': comment_limit,
                                 'cookie': self.cookie}
        if FakeDetailSpider.behavior == 'expired':
            raise ZhihuCredentialExpired('知乎登录凭据已过期或无效，请重新登录后再试')
        return {'article': {'id': article_id, 'comments': []}, 'hot_searches': []}

    def get_search(self, keyword, limit=20, offset=0):
        FakeDetailSpider.last = {'kw': keyword, 'limit': limit, 'offset': offset,
                                 'cookie': self.cookie}
        if FakeDetailSpider.behavior == 'expired':
            raise ZhihuCredentialExpired('知乎登录凭据已过期或无效，请重新登录后再试')
        return {'count': 0, 'is_end': True, 'next_offset': None, 'list': [],
                'hot_searches': []}


detail_record = PlatformAccount.objects.create(platform='zhihu', account=f'{PREFIX}detail')
detail_record.credential = COOKIE
detail_record.save()

_real_spider = zhihu_utils.ZhihuSpider
_real_get = platform_accounts.get_available_account
zhihu_utils.ZhihuSpider = FakeDetailSpider
platform_accounts.get_available_account = lambda platform: detail_record
try:
    r = body(zhihu_request.question_view(RF.post('/api/zhihu/question', {})))
    check('详情：question_id 缺失 → 20003', r['code'] == StatusCode.PARAM_VALUE_INVALID, r)
    r = body(zhihu_request.question_view(
        RF.post('/api/zhihu/question', {'question_id': 'abc'})))
    check('详情：question_id 非法 → 20003', r['code'] == StatusCode.PARAM_VALUE_INVALID, r)
    r = body(zhihu_request.question_view(
        RF.post('/api/zhihu/question', {'question_id': '1', 'answer_limit': '99'})))
    check('详情：answer_limit 越界 → 20003', r['code'] == StatusCode.PARAM_VALUE_INVALID, r)
    r = body(zhihu_request.question_view(
        RF.post('/api/zhihu/question', {'question_id': '1', 'comment_limit': '-1'})))
    check('详情：comment_limit 为负 → 20003', r['code'] == StatusCode.PARAM_VALUE_INVALID, r)

    FakeDetailSpider.behavior = 'ok'
    r = body(zhihu_request.question_view(RF.post('/api/zhihu/question', {
        'question_id': 'https://www.zhihu.com/question/2089437755591713926',
        'answer_limit': '2', 'comment_limit': '1', 'question_comment_limit': '4'})))
    check('详情：网页地址入参被归一成问题 ID 并透传',
          r['code'] == StatusCode.SUCCESS
          and FakeDetailSpider.last == {'qid': '2089437755591713926', 'answers': 2,
                                        'comments': 1, 'question_comments': 4,
                                        'cookie': COOKIE}, FakeDetailSpider.last)
    check('详情：默认条数（回答 5 / 回答评论 3 / 问题评论 10）',
          body(zhihu_request.question_view(
              RF.post('/api/zhihu/question', {'question_id': '1'})))['code'] == StatusCode.SUCCESS
          and (FakeDetailSpider.last['answers'], FakeDetailSpider.last['comments'],
               FakeDetailSpider.last['question_comments']) == (5, 3, 10),
          FakeDetailSpider.last)
    check('详情：comment_limit=0 合法（不取评论）',
          body(zhihu_request.question_view(
              RF.post('/api/zhihu/question',
                      {'question_id': '1', 'comment_limit': '0'})))['code'] == StatusCode.SUCCESS
          and FakeDetailSpider.last['comments'] == 0)
    check('详情：调用方自带 Cookie 优先',
          body(zhihu_request.question_view(
              RF.post('/api/zhihu/question',
                      {'question_id': '1', 'cookie': 'CALLER'})))['code'] == StatusCode.SUCCESS
          and FakeDetailSpider.last['cookie'] == 'CALLER', FakeDetailSpider.last)
    body(zhihu_request.question_view(RF.post('/api/zhihu/question', {'question_id': '1'})))
    check('详情：不带 Cookie → 用平台账号凭据', FakeDetailSpider.last['cookie'] == COOKIE)

    resp = zhihu_request.question_view(RF.put('/api/zhihu/question'))
    check('详情：只接受 GET / POST，其它方法 405', resp.status_code == 405, resp.status_code)
    check('详情：GET 也可用',
          body(zhihu_request.question_view(
              RF.get('/api/zhihu/question', {'question_id': '1'})))['code'] == StatusCode.SUCCESS)

    # ---- 专栏文章 ----
    r = body(zhihu_request.article_view(RF.post('/api/zhihu/article', {})))
    check('文章：article_id 缺失 → 20003', r['code'] == StatusCode.PARAM_VALUE_INVALID, r)
    r = body(zhihu_request.article_view(
        RF.post('/api/zhihu/article', {'article_id': 'abc'})))
    check('文章：article_id 非法 → 20003', r['code'] == StatusCode.PARAM_VALUE_INVALID, r)
    r = body(zhihu_request.article_view(
        RF.post('/api/zhihu/article', {'article_id': '1', 'comment_limit': '99'})))
    check('文章：comment_limit 越界 → 20003', r['code'] == StatusCode.PARAM_VALUE_INVALID, r)

    r = body(zhihu_request.article_view(RF.post('/api/zhihu/article', {
        'article_id': 'https://zhuanlan.zhihu.com/p/608180793', 'comment_limit': '4'})))
    check('文章：网页地址入参被归一成文章 ID 并透传',
          r['code'] == StatusCode.SUCCESS
          and FakeDetailSpider.last == {'aid': '608180793', 'comments': 4,
                                        'cookie': COOKIE}, FakeDetailSpider.last)
    check('文章：默认评论数 10',
          body(zhihu_request.article_view(
              RF.post('/api/zhihu/article', {'article_id': '1'})))['code'] == StatusCode.SUCCESS
          and FakeDetailSpider.last['comments'] == 10, FakeDetailSpider.last)
    check('文章：comment_limit=0 合法（不取评论）',
          body(zhihu_request.article_view(
              RF.post('/api/zhihu/article',
                      {'article_id': '1', 'comment_limit': '0'})))['code'] == StatusCode.SUCCESS
          and FakeDetailSpider.last['comments'] == 0)
    check('文章：调用方自带 Cookie 优先',
          body(zhihu_request.article_view(
              RF.post('/api/zhihu/article',
                      {'article_id': '1', 'cookie': 'CALLER'})))['code'] == StatusCode.SUCCESS
          and FakeDetailSpider.last['cookie'] == 'CALLER', FakeDetailSpider.last)
    body(zhihu_request.article_view(RF.post('/api/zhihu/article', {'article_id': '1'})))
    check('文章：不带 Cookie → 用平台账号凭据', FakeDetailSpider.last['cookie'] == COOKIE)
    resp = zhihu_request.article_view(RF.put('/api/zhihu/article'))
    check('文章：只接受 GET / POST，其它方法 405', resp.status_code == 405, resp.status_code)
    check('文章：GET 也可用',
          body(zhihu_request.article_view(
              RF.get('/api/zhihu/article', {'article_id': '1'})))['code'] == StatusCode.SUCCESS)

    # 托管凭据失效：如实报错并回写账号状态
    FakeDetailSpider.behavior = 'expired'
    detail_record.status = AccountStatus.VALID
    detail_record.save(update_fields=['status', 'updated_time'])
    r = body(zhihu_request.question_view(
        RF.post('/api/zhihu/question', {'question_id': '1'})))
    detail_record.refresh_from_db()
    check('详情：托管凭据失效 → 40001 且账号被标 expired',
          r['code'] == StatusCode.EXTERNAL_API_FAILED
          and detail_record.status == AccountStatus.EXPIRED, r)

    detail_record.status = AccountStatus.VALID
    detail_record.save(update_fields=['status', 'updated_time'])
    r = body(zhihu_request.question_view(
        RF.post('/api/zhihu/question', {'question_id': '1', 'cookie': 'CALLER'})))
    detail_record.refresh_from_db()
    check('详情：调用方自带 Cookie 失效 → 不改平台账号状态',
          r['code'] == StatusCode.EXTERNAL_API_FAILED
          and detail_record.status == AccountStatus.VALID, r)

    r = body(zhihu_request.article_view(
        RF.post('/api/zhihu/article', {'article_id': '1'})))
    detail_record.refresh_from_db()
    check('文章：托管凭据失效 → 40001 且账号被标 expired',
          r['code'] == StatusCode.EXTERNAL_API_FAILED
          and detail_record.status == AccountStatus.EXPIRED, r)

    detail_record.status = AccountStatus.VALID
    detail_record.save(update_fields=['status', 'updated_time'])
    r = body(zhihu_request.article_view(
        RF.post('/api/zhihu/article', {'article_id': '1', 'cookie': 'CALLER'})))
    detail_record.refresh_from_db()
    check('文章：调用方自带 Cookie 失效 → 不改平台账号状态',
          r['code'] == StatusCode.EXTERNAL_API_FAILED
          and detail_record.status == AccountStatus.VALID, r)

    # ---- 综合搜索 ----
    r = body(zhihu_request.search_view(RF.post('/api/zhihu/search', {})))
    check('搜索：q 缺失 → 20003', r['code'] == StatusCode.PARAM_VALUE_INVALID, r)
    r = body(zhihu_request.search_view(RF.post('/api/zhihu/search', {'q': '   '})))
    check('搜索：q 全空白 → 20003', r['code'] == StatusCode.PARAM_VALUE_INVALID, r)
    r = body(zhihu_request.search_view(RF.post('/api/zhihu/search', {'q': 'a', 'limit': '21'})))
    check('搜索：limit 越界 → 20003', r['code'] == StatusCode.PARAM_VALUE_INVALID, r)
    r = body(zhihu_request.search_view(
        RF.post('/api/zhihu/search', {'q': 'a', 'offset': '1001'})))
    check('搜索：offset 越界 → 20003', r['code'] == StatusCode.PARAM_VALUE_INVALID, r)
    r = body(zhihu_request.search_view(RF.post('/api/zhihu/search', {'q': 'a', 'limit': 'x'})))
    check('搜索：limit 非整数 → 20002', r['code'] == StatusCode.PARAM_FORMAT_ERROR, r)

    FakeDetailSpider.behavior = 'ok'
    r = body(zhihu_request.search_view(RF.post('/api/zhihu/search', {
        'q': '学生妹', 'limit': '5', 'offset': '10'})))
    check('搜索：关键词与翻页参数透传',
          r['code'] == StatusCode.SUCCESS
          and FakeDetailSpider.last == {'kw': '学生妹', 'limit': 5, 'offset': 10,
                                        'cookie': COOKIE}, FakeDetailSpider.last)
    check('搜索：默认 limit=20 / offset=0',
          body(zhihu_request.search_view(
              RF.post('/api/zhihu/search', {'q': 'a'})))['code'] == StatusCode.SUCCESS
          and (FakeDetailSpider.last['limit'], FakeDetailSpider.last['offset']) == (20, 0),
          FakeDetailSpider.last)
    check('搜索：调用方自带 Cookie 优先',
          body(zhihu_request.search_view(
              RF.post('/api/zhihu/search', {'q': 'a', 'cookie': 'CALLER'})))['code']
          == StatusCode.SUCCESS and FakeDetailSpider.last['cookie'] == 'CALLER',
          FakeDetailSpider.last)
    body(zhihu_request.search_view(RF.post('/api/zhihu/search', {'q': 'a'})))
    check('搜索：不带 Cookie → 用平台账号凭据', FakeDetailSpider.last['cookie'] == COOKIE)
    resp = zhihu_request.search_view(RF.put('/api/zhihu/search'))
    check('搜索：只接受 GET / POST，其它方法 405', resp.status_code == 405, resp.status_code)
    check('搜索：GET 也可用（参数走 query 串）',
          body(zhihu_request.search_view(
              RF.get('/api/zhihu/search', {'q': 'a'})))['code'] == StatusCode.SUCCESS
          and FakeDetailSpider.last['kw'] == 'a', FakeDetailSpider.last)

    # 托管凭据失效 / 自带 Cookie 失效
    FakeDetailSpider.behavior = 'expired'
    detail_record.status = AccountStatus.VALID
    detail_record.save(update_fields=['status', 'updated_time'])
    r = body(zhihu_request.search_view(RF.post('/api/zhihu/search', {'q': 'a'})))
    detail_record.refresh_from_db()
    check('搜索：托管凭据失效 → 40001 且账号被标 expired',
          r['code'] == StatusCode.EXTERNAL_API_FAILED
          and detail_record.status == AccountStatus.EXPIRED, r)

    detail_record.status = AccountStatus.VALID
    detail_record.save(update_fields=['status', 'updated_time'])
    r = body(zhihu_request.search_view(
        RF.post('/api/zhihu/search', {'q': 'a', 'cookie': 'CALLER'})))
    detail_record.refresh_from_db()
    check('搜索：调用方自带 Cookie 失效 → 不改平台账号状态',
          r['code'] == StatusCode.EXTERNAL_API_FAILED
          and detail_record.status == AccountStatus.VALID, r)

    platform_accounts.get_available_account = lambda platform: None
    r = body(zhihu_request.question_view(
        RF.post('/api/zhihu/question', {'question_id': '1'})))
    check('详情：无可用账号且未带 Cookie → 50002', r['code'] == StatusCode.SERVICE_UNAVAILABLE, r)
    r = body(zhihu_request.article_view(
        RF.post('/api/zhihu/article', {'article_id': '1'})))
    check('文章：无可用账号且未带 Cookie → 50002', r['code'] == StatusCode.SERVICE_UNAVAILABLE, r)
    r = body(zhihu_request.search_view(RF.post('/api/zhihu/search', {'q': 'a'})))
    check('搜索：无可用账号且未带 Cookie → 50002', r['code'] == StatusCode.SERVICE_UNAVAILABLE, r)
finally:
    zhihu_utils.ZhihuSpider = _real_spider
    platform_accounts.get_available_account = _real_get
    PlatformAccount.objects.filter(account=f'{PREFIX}detail').delete()

# ==================== H. 真实上游（可选） ====================
real_account = (PlatformAccount.objects.filter(platform='zhihu')
                .exclude(credential='').exclude(account__startswith=PREFIX)
                .order_by('-updated_time').first())
live_ok = False
if real_account is not None:
    real_ok, real_msg = platform_accounts.check_account(real_account)
    live_ok = real_ok
    if not real_ok:
        print('   托管账号校验未通过：', real_msg)
if not live_ok:
    skip('真实上游热榜（含凭据校验）',
         '库里没有可用的知乎托管账号，或凭据已失效（与本脚本无关，后台录入有效 Cookie 后自动覆盖）')
else:
    ok, data = zhihu_utils.get_hot(5)
    check('真实调用知乎热榜成功', ok and len(data) == 5, data if not ok else len(data))
    if ok:
        check('真实热榜条目含可打开的网页地址',
              data[0]['url'].startswith('https://www.zhihu.com/'), data[0]['url'])
    ok, result = zhihu_utils.check_credential()
    check('真实凭据校验通过', ok and result['valid'] is True, result)

    # 问题详情：从真实热榜里挑一个问题（保证一定存在），验证完整链路
    question_id = (next((item.get('question_id') for item in data
                         if item.get('question_id')), None)
                   if ok else None)
    if not question_id:
        skip('真实问题详情', '热榜里没有可用的 question_id')
    else:
        ok, detail = zhihu_utils.get_question(question_id, 1, 1, 1)
        check('真实调用问题详情成功', ok, detail if not ok else '')
        if ok:
            check('详情：返回四个模块',
                  {'question', 'answers', 'related_questions', 'hot_searches'}
                  <= set(detail), sorted(detail))
            detail_question = detail['question']
            check('详情：问题标题 / 网页地址解析正常',
                  bool(detail_question['title'])
                  and detail_question['url'].startswith('https://www.zhihu.com/question/'),
                  detail_question.get('title'))
            check('详情：回答带正文与可打开的地址',
                  bool(detail['answers']) and bool(detail['answers'][0]['content'])
                  and detail['answers'][0]['url'].startswith('https://www.zhihu.com/'),
                  detail['answers'][:1])
            check('详情：问题评论已归一（含作者与点赞数）',
                  all({'id', 'content', 'author', 'like_count'} <= set(c)
                      for c in detail_question['comments']))
            check('详情：大家都在搜带搜索页地址',
                  bool(detail['hot_searches'])
                  and 'search?' in detail['hot_searches'][0]['url'])

    # 专栏文章详情（示例文章若被作者删除 → 只跳过，不算失败）
    ok_article, article_data = zhihu_utils.get_article(ARTICLE_ID, 2)
    if not ok_article and '不存在' in str(article_data):
        skip('真实专栏文章详情', '示例文章已不可见（可能被作者删除）')
    else:
        check('真实调用专栏文章详情成功', ok_article, article_data if not ok_article else '')
        if ok_article:
            detail_article = article_data['article']
            check('文章：返回两个模块（正文 / 大家都在搜）',
                  {'article', 'hot_searches'} <= set(article_data), sorted(article_data))
            check('文章：标题与完整正文解析正常',
                  bool(detail_article['title']) and bool(detail_article['content']),
                  detail_article.get('title'))
            check('文章：正文里的图片被抽出',
                  '<img' not in detail_article['content']
                  or bool(detail_article['images']), detail_article['images'][:2])
            check('文章：作者主页地址可打开',
                  detail_article['author']['url'].startswith('https://www.zhihu.com/people/'),
                  detail_article['author'])
            check('文章：评论已归一（含作者与点赞数）',
                  all({'id', 'content', 'author', 'like_count'} <= set(c)
                      for c in detail_article['comments']))
            check('文章：大家都在搜带搜索页地址',
                  bool(article_data['hot_searches'])
                  and 'search?' in article_data['hot_searches'][0]['url'])

    # 综合搜索（需求方给的示例关键词；命中结果应自带完整正文）
    ok_search, search_data = zhihu_utils.get_search('学生妹', 3, 0)
    if not ok_search and '风控' in str(search_data):
        skip('真实综合搜索', '知乎风控拦截（临时限流），与本脚本无关')
    else:
        check('真实调用综合搜索成功', ok_search, search_data if not ok_search else '')
        if ok_search:
            check('搜索：返回结构与分页字段齐全',
                  {'count', 'is_end', 'next_offset', 'list', 'hot_searches'}
                  <= set(search_data), sorted(search_data))
            check('搜索：命中结果自带完整正文（视频除外）',
                  all(item['content'] for item in search_data['list']
                      if item['type'] != 'zvideo'), search_data['list'][:1])
            check('搜索：每条地址都是可打开的网页地址',
                  all(item['url'].startswith('https://') for item in search_data['list']),
                  [item['url'] for item in search_data['list']])
            check('搜索：大家都在搜带搜索页地址',
                  bool(search_data['hot_searches'])
                  and 'search?' in search_data['hot_searches'][0]['url'])
            if search_data['is_end']:
                check('搜索：已到末页时 next_offset 为 null',
                      search_data['next_offset'] is None, search_data['next_offset'])
            else:
                check('搜索：next_offset = offset + 本页条数',
                      search_data['next_offset'] == search_data['count'],
                      search_data['next_offset'])

# ==================== 清理 ====================
cleanup()
if tmp_user is not None:
    tmp_user.delete()

print(f'\n=== PASS {PASS} / FAIL {FAIL} / SKIP {SKIP} ===')
sys.exit(1 if FAIL else 0)
