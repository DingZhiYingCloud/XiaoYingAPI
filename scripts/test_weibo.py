"""微博服务回归脚本（频道分类 / 按频道取内容 / 凭据校验）

覆盖范围：
    A. 参数校验：channel / limit / since_id 的格式与范围（视图层）
    B. 无可用账号：业务层给出「尚未配置」提示，视图映射成 50002
    C. 上游响应判定：ok=-100（未登录）→ 凭据失效；其它非 1 → 普通失败
    D. 纯函数：地址拼装 / 时间解析 / 翻页游标解析 / 图片挑尺寸 / 去 HTML
    E. 条目归一：正文（长文展开）/ 图片 / 视频 / 转发 / 作者 / 计数 / 时间
    F. 分类与取数归一：只取「频道」组、过滤空频道、containerid 解析、翻页游标
    G. 业务编排：取托管账号 → 调爬虫 → 凭据失效时回写「已过期」（爬虫用桩替代，不发起真实请求）
    H. 账号托管：微博校验器已注册（后台据此显示「校验」按钮）
    I. 文档页：/docs/weibo/ 渲染 + 端点与本机凭据声明
    J. 视频代理播放：时效令牌签发 / 校验 / 过期、feed 补 stream_url、免签直连与 Range 透传
    K. 真实上游：仅当库里存在有效托管账号时才执行（否则记为 SKIP）

用法：
    .venv\\Scripts\\python.exe scripts\\test_weibo.py

说明：脚本会自动创建临时平台账号并在结束时清理；期间对爬虫与校验器打桩，
因此默认不产生任何真实网络请求。
"""
import json
import os
import sys
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'XiaoYingAPI.settings')

import django  # noqa: E402

django.setup()

from django.contrib.auth import get_user_model            # noqa: E402
from django.test import Client, RequestFactory          # noqa: E402

from API.apis.weibo import request as weibo_request, utils as weibo_utils  # noqa: E402
from API.common import StatusCode, platform_accounts     # noqa: E402
from API.models import AccountStatus, PlatformAccount    # noqa: E402
from SpiderServices.weibo import utils as spider_utils   # noqa: E402
from SpiderServices.weibo.main import (                  # noqa: E402
    WeiboCredentialExpired,
    WeiboError,
    WeiboSpider as RealWeiboSpider,
)

PASS = FAIL = SKIP = 0
# 本脚本创建的临时数据一律带这个前缀，异常中断后下次运行会先自愈清理
PREFIX = '_regress_weibo_'
COOKIE = 'SUB=_2A25REGRESS; SUBP=regress; XSRF-TOKEN=regress'
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


def exc_of(fn):
    try:
        fn()
    except Exception as error:      # noqa: BLE001 —— 测试就是要抓异常做判定
        return error
    return None


def cleanup():
    """清掉本脚本可能留下的临时数据（开头与结尾各跑一次，避免上次中断导致本次跑挂）"""
    PlatformAccount.objects.filter(account__startswith=PREFIX).delete()


cleanup()

# ==================== A. 参数校验 ====================
r = body(weibo_request.feed_view(RF.post('/api/weibo/feed', {'channel': 'abc'})))
check('channel 非数字 → 20003', r['code'] == StatusCode.PARAM_VALUE_INVALID, r)
r = body(weibo_request.feed_view(RF.post('/api/weibo/feed', {'limit': '999'})))
check('limit 高于上界 → 20003', r['code'] == StatusCode.PARAM_VALUE_INVALID, r)
r = body(weibo_request.feed_view(RF.post('/api/weibo/feed', {'limit': '0'})))
check('limit 低于下界 → 20003', r['code'] == StatusCode.PARAM_VALUE_INVALID, r)
r = body(weibo_request.feed_view(RF.post('/api/weibo/feed', {'limit': 'abc'})))
check('limit 非整数 → 20002', r['code'] == StatusCode.PARAM_FORMAT_ERROR, r)
r = body(weibo_request.feed_view(RF.post('/api/weibo/feed', {'since_id': 'x'})))
check('since_id 非整数 → 20002', r['code'] == StatusCode.PARAM_FORMAT_ERROR, r)

# ==================== C. 上游响应判定 ====================
_verdict = RealWeiboSpider._check_payload
err = exc_of(lambda: _verdict({'ok': -100, 'url': 'https://weibo.com/login.php'}))
check('响应判定：ok=-100（未登录）→ 凭据失效',
      isinstance(err, WeiboCredentialExpired), err)
err = exc_of(lambda: _verdict({'ok': 0, 'message': '出错了'}))
check('响应判定：ok=0 → 普通失败且带上原文',
      isinstance(err, WeiboError) and not isinstance(err, WeiboCredentialExpired)
      and '出错了' in str(err), err)
err = exc_of(lambda: _verdict(['not-a-dict']))
check('响应判定：非字典结构 → 普通失败',
      isinstance(err, WeiboError) and not isinstance(err, WeiboCredentialExpired), err)
check('响应判定：ok=1 原样返回', _verdict({'ok': 1}) == {'ok': 1})

# ==================== D. 纯函数 ====================
check('地址拼装：微博 / 主页 / 频道页',
      spider_utils.status_url('1', 'AbC') == 'https://weibo.com/1/AbC'
      and spider_utils.status_url('', 'AbC') == ''
      and spider_utils.profile_url('1') == 'https://weibo.com/u/1'
      and spider_utils.channel_page_url('102803') == 'https://weibo.com/hot/weibo/102803')
check('去 HTML：标签与实体都还原',
      spider_utils.strip_html('<a href="#">@张三</a>&quot;你好&quot;') == '@张三"你好"'
      and spider_utils.strip_html(None) == '')
_ts = spider_utils.parse_created_at('Fri Oct 02 19:47:22 +0800 2026')
check('时间解析：微博时间文案 → Unix 秒',
      isinstance(_ts, int) and _ts > 0
      and spider_utils.parse_created_at('Fri Oct 2 09:00:00 +0800 2026') is not None
      and spider_utils.parse_created_at('') is None
      and spider_utils.parse_created_at('乱七八糟') is None, _ts)
check('翻页游标：从内嵌 JSON 串里取 since_id',
      spider_utils.next_since_id(
          {'since_id': '{"ul_sid":"","ul_hid":"","since_id":"123"}'}) == '123'
      and spider_utils.next_since_id({'since_id': '{"ul_sid":"","ul_hid":""}'}) == ''
      and spider_utils.next_since_id({'since_id': '456'}) == '456'
      and spider_utils.next_since_id({}) == '')
check('图片挑尺寸：大图优先、无图返回空串',
      spider_utils.pick_pic_url({'large': {'url': 'B'}, 'largest': {'url': 'A'}}) == 'A'
      and spider_utils.pick_pic_url({'thumbnail': {'url': 'T'}}) == 'T'
      and spider_utils.pick_pic_url({}) == '')
check('媒体地址升级：http → https，https / 空串原样',
      spider_utils.https_url('http://f.video.weibocdn.com/a.mp4')
      == 'https://f.video.weibocdn.com/a.mp4'
      and spider_utils.https_url('https://x/a.mp4') == 'https://x/a.mp4'
      and spider_utils.https_url('') == '' and spider_utils.https_url(None) == '')

# ==================== E. 条目归一 ====================
spider = RealWeiboSpider(cookie='x')
# 长文展开打桩（不发起真实请求）；返回值可切换，同时记录是否被调用
called = {'long': 0}
long_result = {'value': ('展开后的完整正文内容', '<p>展开后的完整正文内容</p>')}


def fake_long_text(status_id):
    called['long'] += 1
    return long_result['value']


spider._get_long_text = fake_long_text

norm = spider._norm_status({
    'idstr': '123', 'mid': '123', 'mblogid': 'AbC',
    'text_raw': '正文', 'text': '<a>正文</a>', 'isLongText': False, 'textLength': 2,
    'user': {'idstr': '999', 'screen_name': '甲', 'avatar_hd': 'a.jpg', 'verified': True},
    'pic_ids': ['p1'], 'pic_infos': {'p1': {'largest': {'url': 'P1'}}},
    'reposts_count': 1, 'comments_count': 2, 'attitudes_count': 3,
    'created_at': 'Fri Oct 02 19:47:22 +0800 2026', 'source': 'iPhone客户端',
    'region_name': '北京', 'isAd': False,
})
check('条目归一：地址 / 正文 / 作者 / 计数 / 时间 / 地区',
      norm['url'] == 'https://weibo.com/999/AbC' and norm['content'] == '正文'
      and norm['content_html'] == '<a>正文</a>' and norm['author']['name'] == '甲'
      and norm['author']['url'] == 'https://weibo.com/u/999'
      and norm['author']['verified'] is True
      and (norm['reposts_count'], norm['comments_count'], norm['attitudes_count'])
      == (1, 2, 3)
      and isinstance(norm['created_at'], int) and norm['region'] == '北京'
      and norm['is_ad'] is False and norm['video'] is None and norm['retweeted'] is None,
      norm)
check('条目归一：图片地址抽出（大图优先）', norm['images'] == ['P1'], norm['images'])

called['long'] = 0
long_norm = spider._norm_status({
    'idstr': '1', 'mblogid': 'L', 'text_raw': '被截断的短文本', 'text': 'x',
    'isLongText': True, 'user': {'idstr': '9'},
})
check('条目归一：长文 → 自动展开为全文',
      long_norm['content'] == '展开后的完整正文内容'
      and long_norm['content_html'] == '<p>展开后的完整正文内容</p>'
      and long_norm['is_long_text'] is True and called['long'] == 1,
      (long_norm['content'], called))

# 上游取不到全文（isLongText 对短微博也可能为 true）→ 保留原文，不覆盖成空
called['long'] = 0
long_result['value'] = ('', '')
short_norm = spider._norm_status({
    'idstr': '2', 'mblogid': 'S', 'text_raw': '短微博原文', 'text': '短微博原文',
    'isLongText': True, 'user': {'idstr': '9'},
})
check('条目归一：isLongText 但取不到全文 → 保留原文',
      short_norm['content'] == '短微博原文' and called['long'] == 1,
      short_norm['content'])

# 非长文：完全不去回源
called['long'] = 0
plain_norm = spider._norm_status({
    'idstr': '3', 'mblogid': 'N', 'text_raw': '普通微博', 'text': '普通微博',
    'isLongText': False, 'user': {'idstr': '9'},
})
check('条目归一：非长文 → 不回源取全文',
      plain_norm['content'] == '普通微博' and called['long'] == 0, called)
long_result['value'] = ('展开后的完整正文内容', '<p>展开后的完整正文内容</p>')

video = spider._norm_video({
    'object_type': 'video', 'page_pic': 'http://wx3.sinaimg.cn/c.jpg', 'page_title': '视频标题',
    'media_info': {'stream_url_hd': 'http://f.video.weibocdn.com/hd.mp4',
                   'stream_url': 'http://f.video.weibocdn.com/sd.mp4', 'duration': 12,
                   'h5_url': 'https://video.weibo.com/show?fid=1'},
})
check('视频归一：高清优先 + http 升级为 https + 封面 / 标题 / 时长 / 页地址',
      video == {'url': 'https://f.video.weibocdn.com/hd.mp4',
                'cover': 'https://wx3.sinaimg.cn/c.jpg', 'title': '视频标题',
                'duration': 12, 'page_url': 'https://video.weibo.com/show?fid=1'}, video)
check('视频归一：非视频 / 空 → None',
      spider._norm_video({'object_type': 'topic'}) is None
      and spider._norm_video({}) is None and spider._norm_video(None) is None)

retweeted = spider._norm_retweeted({
    'idstr': '9', 'mblogid': 'Rt', 'text_raw': '原微博', 'text': '<b>原微博</b>',
    'user': {'idstr': '8', 'screen_name': '乙'}, 'pic_ids': [],
    'reposts_count': 1, 'comments_count': 2, 'attitudes_count': 3,
    'created_at': 'Fri Oct 02 19:47:22 +0800 2026',
})
check('转发归一：原微博地址 / 正文 / 原作者',
      retweeted['url'] == 'https://weibo.com/8/Rt' and retweeted['content'] == '原微博'
      and retweeted['author']['name'] == '乙' and retweeted['images'] == [],
      retweeted)
check('转发归一：无转发 → None', spider._norm_retweeted(None) is None)

# ==================== F. 分类与取数归一 ====================
spider._get_json = lambda *a, **k: {'ok': 1, 'groups': [
    {'title': '默认分组', 'group_type': 0, 'group': [{'gid': '1', 'title': '关注'}]},
    {'title': '我的频道', 'group_type': 1, 'group': [
        {'gid': '102803', 'title': '热门', 'containerid': '102803'},
        {'gid': '', 'title': '空频道'}]},
    {'title': '频道推荐', 'group_type': 1, 'group': [
        {'gid': '1028034288', 'title': '明星', 'containerid': 'CID'}]},
]}
groups = spider.get_channels()
check('分类归一：只取「频道」组（不取关注分组）、过滤空频道',
      [g['section'] for g in groups] == ['我的频道', '频道推荐']
      and groups[0]['count'] == 1 and groups[1]['channels'][0]['name'] == '明星', groups)
check('分类归一：频道带 id / containerid / 网页地址',
      groups[0]['channels'][0]['id'] == '102803'
      and groups[0]['channels'][0]['containerid'] == '102803'
      and groups[0]['channels'][0]['url'] == 'https://weibo.com/hot/weibo/102803')

# 只给 channel 时按分类解析 containerid
def fake_get_json(url, params=None, referer=None):
    if url == spider_utils.ALL_GROUPS_API:
        return {'ok': 1, 'groups': [{'title': '我的频道', 'group_type': 1, 'group': [
            {'gid': '1028034288', 'title': '明星', 'containerid': 'CID'}]}]}
    return {'ok': 1, 'statuses': [], 'since_id': '{"since_id":""}', 'total_number': 0}


spider._get_json = fake_get_json
r = spider.get_feed(channel='1028034288', limit=1)
check('取数归一：只给 channel → 自动解析出 containerid', r['containerid'] == 'CID', r)
err = exc_of(lambda: spider.get_feed(channel='999', limit=1))
check('取数归一：频道不存在 → 抛「未找到该频道」',
      isinstance(err, WeiboError) and '未找到该频道' in str(err), err)

spider._get_json = lambda *a, **k: {
    'ok': 1, 'statuses': [{'idstr': '1', 'mblogid': 'A', 'text_raw': 't',
                           'user': {'idstr': '2'}}],
    'since_id': '{"ul_sid":"","ul_hid":"","since_id":"77"}', 'total_number': 100}
r = spider.get_feed(channel='102803', containerid='102803', limit=5, since_id='0')
check('取数归一：条数本地截断 + 游标 / 总数透传',
      r['count'] == 1 and r['total'] == 100 and r['since_id'] == '0'
      and r['next_since_id'] == '77' and r['has_more'] is True, r)

spider._get_json = lambda *a, **k: {
    'ok': 1, 'statuses': [{'idstr': '1', 'mblogid': 'A', 'text_raw': 't',
                           'user': {'idstr': '2'}}],
    'since_id': '{"ul_sid":"","ul_hid":"","since_id":"5"}', 'total_number': 100}
r = spider.get_feed(channel='102803', containerid='102803', limit=5, since_id='5')
check('取数归一：游标未推进 → 视为没有下一页',
      r['next_since_id'] is None and r['has_more'] is False, r)

spider._get_json = lambda *a, **k: {
    'ok': 1, 'statuses': [], 'since_id': '{"since_id":"9"}', 'total_number': 0}
r = spider.get_feed(channel='102803', containerid='102803', limit=5)
check('取数归一：空结果 → 没有下一页',
      r['count'] == 0 and r['next_since_id'] is None and r['has_more'] is False, r)

# ==================== B. 无可用账号 ====================
_real_get = platform_accounts.get_available_account
platform_accounts.get_available_account = lambda platform: None
try:
    ok, msg = weibo_utils.get_channels()
    check('无可用账号 → get_channels 返回失败 + 未配置提示',
          not ok and '尚未配置' in msg, msg)
    r = body(weibo_request.channels_view(RF.get('/api/weibo/channels')))
    check('无可用账号 → 视图映射成 50002 服务不可用',
          r['code'] == StatusCode.SERVICE_UNAVAILABLE and '尚未配置' in r['msg'], r)
finally:
    platform_accounts.get_available_account = _real_get

# ==================== G. 业务编排（爬虫打桩） ====================
class FakeSpider:
    """替身爬虫：按构造参数决定返回或抛错，用来验证编排逻辑"""

    behavior = 'ok'
    seen = []

    def __init__(self, cookie='', timeout=None):
        self.cookie = cookie
        FakeSpider.seen.append(cookie)

    def _maybe_fail(self):
        if FakeSpider.behavior == 'expired':
            raise WeiboCredentialExpired('微博登录凭据已过期或无效，请重新登录后更新 Cookie')
        if FakeSpider.behavior == 'error':
            raise WeiboError('微博返回异常：上游抽风')

    def get_channels(self):
        self._maybe_fail()
        return [{'section': '我的频道', 'count': 1, 'channels': [
            {'id': '102803', 'name': '热门', 'containerid': '102803',
             'url': 'https://weibo.com/hot/weibo/102803'}]}]

    def get_feed(self, channel='102803', containerid='', limit=20, since_id='0'):
        self._maybe_fail()
        return {'channel': channel, 'containerid': containerid or channel, 'count': 1,
                'total': 1, 'since_id': since_id, 'next_since_id': None,
                'has_more': False,
                'list': [{'id': '5345502107275373', 'mblogid': 'AbC',
                          'video': {'url': 'https://f.video.weibocdn.com/a.mp4',
                                    'cover': '', 'title': '视频', 'duration': 1,
                                    'page_url': ''},
                          'retweeted': None}]}

    def check_cookie(self):
        if FakeSpider.behavior == 'expired':
            return False, '微博登录凭据已过期或无效，请重新登录后更新 Cookie'
        if FakeSpider.behavior == 'error':
            return False, '微博返回异常：上游抽风'
        return True, '凭据有效'


record = PlatformAccount.objects.create(platform='weibo', account=f'{PREFIX}spider')
record.credential = COOKIE
record.save()

_real_spider = weibo_utils.WeiboSpider
_real_get2 = platform_accounts.get_available_account
_real_checker = platform_accounts._load_checker
weibo_utils.WeiboSpider = FakeSpider
platform_accounts.get_available_account = lambda platform: record
# 平台托管的「校验」走真实校验器（会外呼），这里打桩避免真实请求
platform_accounts._load_checker = lambda platform: (lambda cookie: (True, '回归桩：凭据有效'))
try:
    FakeSpider.behavior = 'ok'
    ok, data = weibo_utils.get_channels()
    check('取托管账号 → 分类返回分组列表', ok and data[0]['section'] == '我的频道', data)
    ok, data = weibo_utils.get_feed('102803', '102803', 3, '0')
    check('取托管账号 → 内容返回结构齐全',
          ok and {'channel', 'containerid', 'count', 'total', 'since_id',
                  'next_since_id', 'has_more', 'list'} <= set(data), data)

    FakeSpider.behavior = 'expired'
    record.status = AccountStatus.VALID
    record.save(update_fields=['status', 'updated_time'])
    ok, msg = weibo_utils.get_feed('102803', '102803', 3, '0')
    record.refresh_from_db()
    check('爬虫报凭据过期 → 取内容失败并回传原因', not ok and '过期' in msg, msg)
    check('爬虫报凭据过期 → 账号被顺手标记为 expired',
          record.status == AccountStatus.EXPIRED, record.status)

    FakeSpider.behavior = 'error'
    ok, msg = weibo_utils.get_feed('102803', '102803', 3, '0')
    check('上游普通异常 → 失败但状态不被改写',
          not ok and '上游抽风' in msg and record.status == AccountStatus.EXPIRED, msg)

    FakeSpider.behavior = 'ok'
    FakeSpider.seen = []
    r = body(weibo_request.feed_view(RF.post('/api/weibo/feed', {
        'channel': '102803', 'containerid': '102803', 'limit': '3',
        'since_id': '0', 'cookie': 'CALLER_COOKIE'})))
    check('自带 Cookie → 透传给爬虫且返回成功',
          r['code'] == StatusCode.SUCCESS and FakeSpider.seen[-1] == 'CALLER_COOKIE',
          (r['code'], FakeSpider.seen))
    r = body(weibo_request.feed_view(RF.get('/api/weibo/feed', {'limit': '2'})))
    check('GET 也可用（参数走 query 串）',
          r['code'] == StatusCode.SUCCESS and FakeSpider.seen[-1] == COOKIE,
          (r['code'], FakeSpider.seen))
    resp = weibo_request.feed_view(RF.put('/api/weibo/feed'))
    check('只接受 GET / POST，其它方法 405', resp.status_code == 405, resp.status_code)

    # 自带 Cookie 失效：如实报错，但**不得**去改平台账号的状态
    FakeSpider.behavior = 'expired'
    record.status = AccountStatus.VALID
    record.save(update_fields=['status', 'updated_time'])
    ok, msg = weibo_utils.get_feed('102803', '102803', 3, '0', cookie='CALLER')
    record.refresh_from_db()
    check('自带 Cookie 失效 → 上报失败但平台账号状态不变',
          not ok and '过期' in msg and record.status == AccountStatus.VALID,
          (ok, msg, record.status))

    ok, result = weibo_utils.check_credential(cookie='CALLER')
    record.refresh_from_db()
    check('/check 自带 Cookie → valid=False、account 为空、平台账号状态不变',
          ok and result['valid'] is False and result['account'] == ''
          and record.status == AccountStatus.VALID, result)
    FakeSpider.behavior = 'ok'
    ok, result = weibo_utils.check_credential(cookie='CALLER')
    check('/check 自带 Cookie 有效 → valid=True', ok and result['valid'] is True, result)

    r = body(weibo_request.check_view(RF.post('/api/weibo/check', {})))
    check('/check 未带 Cookie → 校验平台托管的账号并带上账号标识',
          r['code'] == StatusCode.SUCCESS and r['data']['account'] == f'{PREFIX}spider',
          r)
finally:
    weibo_utils.WeiboSpider = _real_spider
    platform_accounts.get_available_account = _real_get2
    platform_accounts._load_checker = _real_checker
    PlatformAccount.objects.filter(account=f'{PREFIX}spider').delete()

# ==================== H. 账号托管 ====================
check('微博校验器已注册（后台据此显示「校验」按钮）',
      platform_accounts.has_checker('weibo')
      and callable(platform_accounts._load_checker('weibo')))

client = Client()
su = get_user_model().objects.filter(is_superuser=True).first()
tmp_user = None
if su is None:
    su = tmp_user = get_user_model().objects.create_superuser(
        f'{PREFIX}su', 'regress-weibo@example.com', 'x')
client.force_login(su)
html = client.get(CONSOLE).content.decode('utf-8')
check('后台账号管理页：微博是可选平台、且已接入「校验」',
      'weibo' in html and '微博' in html and '校验' in html)

# ==================== I. 文档页 ====================
docs_html = client.get('/docs/weibo/').content.decode('utf-8')
check('文档页 /docs/weibo/ 渲染成功',
      '微博' in docs_html and '/api/weibo/feed' in docs_html)
check('右侧栏出现「本机凭据」卡且含 Cookie 字段',
      'docs-local-card' in docs_html and '微博登录 Cookie' in docs_html)
check('三个带凭据的端点都声明了本机凭据参数（调试时自动带上）',
      docs_html.count('data-local-params="cookie "') == 3,
      docs_html.count('data-local-params="cookie "'))
check('端点对外展示为 POST（长 Cookie 走表单体）',
      docs_html.count('>POST<') >= 3, docs_html.count('>POST<'))
check('四个端点都已登记到文档',
      all(p in docs_html for p in ('/api/weibo/channels', '/api/weibo/feed',
                                   '/api/weibo/video', '/api/weibo/check')),
      [p for p in ('/api/weibo/channels', '/api/weibo/feed', '/api/weibo/video',
                   '/api/weibo/check') if p not in docs_html])

# ==================== J. 视频代理播放 ====================
token = weibo_utils.make_video_token('5345502107275373')
sid, error = weibo_utils.parse_video_token(token)
check('播放令牌：签发 → 解析回同一个微博 id',
      sid == '5345502107275373' and error is None, (sid, error))
check('播放令牌：缺失 / 伪造 → 都报错',
      weibo_utils.parse_video_token('')[0] is None
      and '缺少' in weibo_utils.parse_video_token('')[1]
      and weibo_utils.parse_video_token('bad-token')[0] is None)

_real_ttl = weibo_utils.VIDEO_TOKEN_TTL
weibo_utils.VIDEO_TOKEN_TTL = 0          # 让令牌立刻过期，验证过期分支
try:
    sid, error = weibo_utils.parse_video_token(token)
    check('播放令牌：过期 → 提示重新获取', sid is None and '过期' in error, (sid, error))
finally:
    weibo_utils.VIDEO_TOKEN_TTL = _real_ttl

_real_spider2 = weibo_utils.WeiboSpider
weibo_utils.WeiboSpider = FakeSpider       # feed 用桩爬虫，不联网
try:
    FakeSpider.behavior = 'ok'
    r = body(weibo_request.feed_view(
        RF.post('/api/weibo/feed', {'limit': '1', 'cookie': 'X'})))
    stream_url = r['data']['list'][0]['video']['stream_url']
    check('feed：给带视频的条目补上 video.stream_url（本站代理 + 令牌）',
          r['code'] == StatusCode.SUCCESS and '/api/weibo/video?token=' in stream_url,
          stream_url[:90])
finally:
    weibo_utils.WeiboSpider = _real_spider2

resp = client.get('/api/weibo/video')
check('代理播放：缺令牌 → 403，且不是「需签名」被拦（免签名单生效）',
      resp.status_code == 403 and body(resp)['code'] != StatusCode.AUTH_FAILED,
      (resp.status_code, body(resp)['code']))
check('代理播放：令牌无效 → 403',
      client.get('/api/weibo/video', {'token': 'bad'}).status_code == 403)


class FakeUpstream:
    """替身上游视频流：固定 206 + 10 字节，用来验证响应头透传"""

    status_code = 206
    headers = {'Content-Type': 'video/mp4', 'Content-Range': 'bytes 0-9/100',
               'Content-Length': '10', 'Accept-Ranges': 'bytes'}

    def iter_content(self, chunk_size=8192):
        yield b'0123456789'

    def close(self):
        pass


_real_open = weibo_utils.open_video
weibo_utils.open_video = lambda *a, **k: (True, FakeUpstream())
try:
    resp = client.get('/api/weibo/video', {'token': token}, HTTP_RANGE='bytes=0-9')
    check('代理播放：透传 206 / Content-Range / 类型 / Accept-Ranges',
          resp.status_code == 206 and resp['Content-Type'] == 'video/mp4'
          and resp['Content-Range'] == 'bytes 0-9/100'
          and resp['Accept-Ranges'] == 'bytes',
          (resp.status_code, dict(resp.headers)))
    check('代理播放：二进制流原样转发',
          b''.join(resp.streaming_content) == b'0123456789')
finally:
    weibo_utils.open_video = _real_open

# ==================== K. 真实上游（可选） ====================
real_account = (PlatformAccount.objects.filter(platform='weibo')
                .exclude(credential='').exclude(account__startswith=PREFIX)
                .order_by('-updated_time').first())
live_ok = False
if real_account is not None:
    real_ok, real_msg = platform_accounts.check_account(real_account)
    live_ok = real_ok
    if not real_ok:
        print('   托管账号校验未通过：', real_msg)
if not live_ok:
    skip('真实上游（分类 / 内容 / 凭据校验）',
         '库里没有可用的微博托管账号，或凭据已失效（与本脚本无关，后台录入有效 Cookie 后自动覆盖）')
else:
    ok, groups = weibo_utils.get_channels()
    check('真实调用频道分类成功', ok and bool(groups), groups if not ok else '')
    if ok:
        sections = [g['section'] for g in groups]
        check('真实分类含「我的频道」与「频道推荐」',
              '我的频道' in sections and '频道推荐' in sections, sections)
        channels = [c for g in groups for c in g['channels']]
        check('真实分类：热门(102803) 在列表里',
              any(c['id'] == '102803' for c in channels), channels[:3])
        check('真实分类：每个频道都给出 containerid 与网页地址',
              all(c['containerid'] and c['url'].startswith('https://weibo.com/')
                  for c in channels), channels[:1])

    ok, feed = weibo_utils.get_feed('102803', '102803', 5, '0')
    check('真实调用「热门」频道内容成功', ok, feed if not ok else '')
    if ok:
        check('内容：返回结构与分页字段齐全',
              {'channel', 'containerid', 'count', 'total', 'since_id',
               'next_since_id', 'has_more', 'list'} <= set(feed), sorted(feed))
        check('内容：每条都有正文与可打开的网页地址',
              bool(feed['list']) and all(item['content'] for item in feed['list'])
              and all(item['url'].startswith('https://weibo.com/') for item in feed['list']),
              feed['list'][:1])
        check('内容：作者字段齐全',
              all({'id', 'name', 'url', 'avatar'} <= set(item['author'])
                  for item in feed['list']), feed['list'][0]['author'])
        check('内容：视频直链为 https 且非空（http 会导致页面混合内容被拦）',
              all(item['video']['url'].startswith('https://')
                  for item in feed['list'] if item['video']),
              [item['video'] for item in feed['list'] if item['video']][:1])

    ok, result = weibo_utils.check_credential()
    check('真实凭据校验通过', ok and result['valid'] is True, result)

    # 视频代理播放：拿一条真视频，按 id 现场解析并流式转发
    video_item = next((item for item in feed['list'] if item['video']), None) if ok else None
    if video_item is None:
        skip('真实视频代理播放', '本轮 5 条里没有视频条目')
    else:
        probe_token = weibo_utils.make_video_token(video_item['id'])
        resp = client.get('/api/weibo/video', {'token': probe_token})
        check('真实代理播放：免签名直连 → 200/206 且是 video/*',
              resp.status_code in (200, 206)
              and resp['Content-Type'].startswith('video/'), resp.status_code)
        if resp.status_code == 200:
            resp.close()
        resp = client.get('/api/weibo/video', {'token': probe_token},
                          HTTP_RANGE='bytes=0-1023')
        chunk = b''.join(resp.streaming_content)
        check('真实代理播放：Range 请求 → 206 + 1024 字节且是合法 MP4 头',
              resp.status_code == 206 and len(chunk) == 1024 and b'ftyp' in chunk[:16],
              (resp.status_code, len(chunk), chunk[:12]))

# ==================== 清理 ====================
cleanup()
if tmp_user is not None:
    tmp_user.delete()

print(f'\n=== PASS {PASS} / FAIL {FAIL} / SKIP {SKIP} ===')
sys.exit(1 if FAIL else 0)
