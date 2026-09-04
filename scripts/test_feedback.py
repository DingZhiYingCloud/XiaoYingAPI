"""问题反馈中心 完整测试（冒烟 + 边缘化 + 并发 + 极限 + 安全）

覆盖范围：
    第一轮  签名与身份安全（无签名 / 伪造 Token / 无效 Token 拒绝）
    第二轮  正常流程（提交反馈 / 追加评论 / 列表分页 / 详情+评论树）
    评论树  嵌套回复（无限嵌套 / 站长回复 / 回复列表翻页接口 /replies）
    第三轮  数据隔离（子项目 B 无法查看子项目 A 的反馈）
    第四轮  基础参数校验（缺失 / 超长）
    第五轮  边缘化测试（非法分页参数 / 边界长度 / 非法 UUID / 非法状态筛选）
    第六轮  并发测试（多用户并发提交 / 同一反馈并发追加 / 并发嵌套回复）
    第七轮  极限测试（1000+ 一级分页 / 1000 条二级回复分页 / 50 层深嵌套取全 / 大文本 / 大列表）
    第八轮  安全测试（签名过期 / 篡改 / 未知 app_id / 停用项目 / 伪造与过期 Token / XSS）

分页策略：详情接口一级评论分页，每条内嵌二级评论首页（SUB_REPLY_FIRST_PAGE_SIZE 条，
取该一级评论全部子孙按时间正序前 N 条）；某条评论的全部二级评论通过
GET /api/feedback/replies 按 parent_id 分页获取（返回其全部子孙，无论嵌套多深，不分层级）。

运行方式（使用真实数据库，测试结束后自动清理测试数据）：
    .venv\\Scripts\\python.exe scripts\\test_feedback.py

前置条件：
- 已执行 migrate（feedback 表已建）
- 后台已将 /api/feedback/ 分类设为「需要认证」（auth）
"""
import json
import os
import random
import secrets
import sys
import threading
import time
from datetime import timedelta

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'XiaoYingAPI.settings')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import django

django.setup()

from django.contrib.auth.hashers import make_password
from django.test import Client
from django.utils import timezone

from API.apis.feedback.utils import SUB_REPLY_FIRST_PAGE_SIZE
from API.apis.user_center.sign import build_sign
from API.common.credential_crypto import hash_token
from API.models import Feedback, FeedbackReply, User, UserApp, UserToken

# ───────────────────────── 测试基础设施 ─────────────────────────

BASE = '/api/feedback'
_PREFIX = f'FT{int(time.time())}'
_CONC_PREFIX = 'FT_CONC'  # 并发测试用户前缀（单独清理）

_stats = {'pass': 0, 'fail': 0}
_created_apps = []      # (app_id, app_secret, UserApp)
_created_users = []     # user_id
_created_feedback = []  # feedback_id
_lock = threading.Lock()


def _check(name, cond, extra=''):
    with _lock:
        if cond:
            _stats['pass'] += 1
            print(f'  [PASS] {name}')
        else:
            _stats['fail'] += 1
            print(f'  [FAIL] {name} {extra}')


def _signed(app, extra=None):
    """构造签名参数"""
    extra = {k: v for k, v in (extra or {}).items() if v is not None}
    params = {
        'app_id': app[0],
        'timestamp': str(int(time.time())),
        'nonce': secrets.token_hex(8),
    }
    if extra:
        params.update(extra)
    params['sign'] = build_sign(params, app[1])
    return params


def _create_app(name=None, active=True):
    """创建测试项目（自动生成 APPID/APPSECRET）"""
    obj = UserApp.objects.create(name=name or f'{_PREFIX}项目{len(_created_apps)}', status=active)
    entry = (obj.app_id, obj.app_secret, obj)
    _created_apps.append(entry)
    return entry


def _create_user(name=None, prefix=None):
    """直接造用户"""
    user = User.objects.create(
        account=str(random.randint(10000000, 99999999)),
        username=name or f'{prefix or _PREFIX}用户{len(_created_users)}',
        password=make_password('pass123456'),
        status=True,
    )
    _created_users.append(str(user.id))
    return user


def _issue_token(app, user, days=7):
    """签发绑定指定项目的 Token（绕过登录接口）

    S-06: user_token.token 落库存哈希，此处与生产创建逻辑保持一致
    """
    raw_token = secrets.token_hex(32)
    UserToken.objects.create(
        user=user, app=app[2], token=hash_token(raw_token),
        expire_time=timezone.now() + timedelta(days=days),
    )
    return raw_token


def _response(resp):
    return json.loads(resp.content.decode('utf-8'))


def _cleanup():
    """清理测试数据（反馈 → 追加级联删除，再删用户/Token/项目）"""
    Feedback.objects.filter(id__in=_created_feedback).delete()
    UserToken.objects.filter(user_id__in=_created_users).delete()
    User.objects.filter(id__in=_created_users).delete()
    User.objects.filter(username__startswith=_CONC_PREFIX).delete()
    for _, _, obj in _created_apps:
        UserApp.objects.filter(pk=obj.pk).delete()


# ───────────────────────── 第一轮 签名与身份安全 ─────────────────────────

def round_basic_auth(c, app, token):
    print('\n===== 第一轮 签名与身份安全 =====')
    r = _response(c.post(f'{BASE}/create', {'title': 't', 'content': 'c', 'token': token}))
    _check('无签名被拒绝', r['code'] == 20011, r)
    r = _response(c.post(f'{BASE}/create', _signed(app, {'title': 't', 'content': 'c'})))
    _check('签名有效但缺 token 被拒', r['code'] == 20001, r)
    r = _response(c.post(f'{BASE}/create', _signed(app, {
        'title': 't', 'content': 'c', 'token': 'f' * 64,
    })))
    _check('伪造 token 被拒', r['code'] == 20010, r)


# ───────────────────────── 第二轮 正常流程 ─────────────────────────

def round_normal(c, app, token):
    print('\n===== 第二轮 正常流程 =====')
    r = _response(c.post(f'{BASE}/create', _signed(app, {
        'title': '登录页白屏', 'content': '点击登录后页面无响应', 'token': token,
    })))
    _check('提交反馈成功', r['code'] == 10000 and 'feedback_id' in r['data'], r)
    fb_id = r['data']['feedback_id']
    _created_feedback.append(fb_id)
    r = _response(c.post(f'{BASE}/reply', _signed(app, {
        'feedback_id': fb_id, 'content': '补充：Chrome 最新版', 'token': token,
    })))
    _check('追加评论成功', r['code'] == 10000, r)
    r = _response(c.get(f'{BASE}/list', _signed(app)))
    _check('列表查询成功', r['code'] == 10000 and r['data']['total'] == 1, r)
    r = _response(c.get(f'{BASE}/list', _signed(app, {'status': 'resolved'})))
    _check('状态筛选正确', r['code'] == 10000 and r['data']['total'] == 0, r)
    r = _response(c.get(f'{BASE}/detail', _signed(app, {'feedback_id': fb_id})))
    ok = r['code'] == 10000 and len(r['data']['replies']) == 1 \
        and r['data']['replies'][0]['author_role'] == 'user' \
        and r['data']['replies'][0]['replies'] == [] \
        and r['data']['replies'][0]['reply_total'] == 0 \
        and r['data']['replies'][0]['children_total'] == 0 \
        and r['data']['total'] == 1 and r['data']['total_pages'] == 1
    _check('详情含一级评论(树结构)', ok, r)
    r = _response(c.post(f'{BASE}/reply', _signed(app, {
        'feedback_id': '0' * 32, 'content': 'x', 'token': token,
    })))
    _check('追加到不存在反馈被拒', r['code'] == 20030, r)


# ───────────────────────── 评论树（嵌套回复）─────────────────────────

def round_tree(c, app, token):
    print('\n===== 评论树（嵌套回复）=====')
    # A 提问题
    r = _response(c.post(f'{BASE}/create', _signed(app, {
        'title': '评论树测试', 'content': 'A: 这是什么问题', 'token': token,
    })))
    fb_id = r['data']['feedback_id']
    _created_feedback.append(fb_id)
    # B 一级评论
    r = _response(c.post(f'{BASE}/reply', _signed(app, {
        'feedback_id': fb_id, 'content': 'B: 我遇到过', 'token': token,
    })))
    b_id = r['data']['reply_id']
    # C 回复 B（二级）
    r = _response(c.post(f'{BASE}/reply', _signed(app, {
        'feedback_id': fb_id, 'content': 'C: 怎么解决的', 'token': token, 'parent_id': b_id,
    })))
    c_id = r['data']['reply_id']
    # D 回复 C（三级，验证无限嵌套）
    r = _response(c.post(f'{BASE}/reply', _signed(app, {
        'feedback_id': fb_id, 'content': 'D: 重启就好了', 'token': token, 'parent_id': c_id,
    })))
    d_id = r['data']['reply_id']
    _check('三级嵌套回复成功', r['code'] == 10000, r)

    # detail 返回评论树：一级内嵌"二级评论首页"（B 的全部子孙按时间正序前 N 条，不分层级）
    r = _response(c.get(f'{BASE}/detail', _signed(app, {'feedback_id': fb_id})))
    replies = r['data']['replies']
    b = replies[0]
    ok = (r['code'] == 10000 and r['data']['total'] == 1
          and len(replies) == 1
          and b['reply_id'] == b_id
          and b['parent_id'] == ''          # 一级评论 parent 为空
          and b['reply_total'] == 2         # 二级评论总数 = 全部子孙（C、D）
          and b['children_total'] == 1      # 直接子回复数 = 仅 C
          and len(b['replies']) == 2        # 二级评论首页 = 全部子孙前 5 条
          and b['replies'][0]['reply_id'] == c_id
          and b['replies'][0]['parent_id'] == b_id   # C 回复了 B
          and b['replies'][0]['reply_total'] == 1
          and b['replies'][0]['children_total'] == 1
          and b['replies'][0]['replies'] == []
          and b['replies'][1]['reply_id'] == d_id
          and b['replies'][1]['parent_id'] == c_id)  # D 回复了 C，深层也算二级评论
    _check('详情内嵌二级评论首页(全部子孙,不分层级)', ok, r)

    # /replies 接口：查看 B 的二级评论 = B 的全部子孙（C、D 都在，不分层级）
    r = _response(c.get(f'{BASE}/replies', _signed(app, {
        'feedback_id': fb_id, 'parent_id': b_id,
    })))
    ok = (r['code'] == 10000 and r['data']['total'] == 2
          and len(r['data']['items']) == 2
          and r['data']['items'][0]['reply_id'] == c_id
          and r['data']['items'][0]['parent_id'] == b_id
          and r['data']['items'][1]['reply_id'] == d_id
          and r['data']['items'][1]['parent_id'] == c_id)
    _check('/replies返回全部子孙(含C的回复D)', ok, r)

    # /replies 接口：查看 C 的二级评论 = C 的全部子孙（D）
    r = _response(c.get(f'{BASE}/replies', _signed(app, {
        'feedback_id': fb_id, 'parent_id': c_id,
    })))
    ok = (r['code'] == 10000 and r['data']['total'] == 1
          and len(r['data']['items']) == 1
          and r['data']['items'][0]['reply_id'] == d_id
          and r['data']['items'][0]['parent_id'] == c_id)
    _check('/replies查看C的二级评论返回D', ok, r)

    # 站长可嵌套回复且身份正确（模拟后台写入：API 不提供 admin 角色）
    FeedbackReply.objects.create(feedback_id=fb_id, parent_id=b_id,
                                 author_role='admin', content='站长: 已定位')
    r = _response(c.get(f'{BASE}/detail', _signed(app, {'feedback_id': fb_id})))
    b_node = r['data']['replies'][0]
    ok = any(x['author_role'] == 'admin' and x['username'] == '站长'
             and x['reply_total'] == 0 for x in b_node['replies'])
    _check('站长可嵌套回复且身份正确', ok, r)

    # 父评论安全校验
    r = _response(c.post(f'{BASE}/reply', _signed(app, {
        'feedback_id': fb_id, 'content': 'x', 'token': token, 'parent_id': '0' * 32,
    })))
    _check('回复不存在的父评论被拒', r['code'] == 20030, r)
    # 父评论属于其他反馈 → 被拒
    r2 = _response(c.post(f'{BASE}/create', _signed(app, {
        'title': '另一个反馈', 'content': 'x', 'token': token,
    })))
    fb2_id = r2['data']['feedback_id']
    _created_feedback.append(fb2_id)
    r2 = _response(c.post(f'{BASE}/reply', _signed(app, {
        'feedback_id': fb2_id, 'content': 'B2', 'token': token,
    })))
    fb2_reply_id = r2['data']['reply_id']
    r = _response(c.post(f'{BASE}/reply', _signed(app, {
        'feedback_id': fb_id, 'content': 'x', 'token': token, 'parent_id': fb2_reply_id,
    })))
    _check('跨反馈回复被拒', r['code'] == 20030, r)

    # /replies 接口参数与归属校验
    r = _response(c.get(f'{BASE}/replies', _signed(app, {'feedback_id': fb_id})))
    _check('/replies缺parent_id被拒', r['code'] == 20001, r)
    r = _response(c.get(f'{BASE}/replies', _signed(app, {
        'feedback_id': fb_id, 'parent_id': '0' * 32,
    })))
    _check('/replies父评论不存在被拒', r['code'] == 20030, r)
    r = _response(c.get(f'{BASE}/replies', _signed(app, {
        'feedback_id': fb2_id, 'parent_id': b_id,  # b_id 属于 fb，不属于 fb2
    })))
    _check('/replies跨反馈父评论被拒', r['code'] == 20030, r)
    r = _response(c.get(f'{BASE}/replies', _signed(app, {
        'feedback_id': fb_id, 'parent_id': fb2_reply_id,  # fb2 的评论不属于 fb
    })))
    _check('/replies父评论跨反馈(双向)被拒', r['code'] == 20030, r)


# ───────────────────────── 第三轮 数据隔离 ─────────────────────────

def round_isolation(c, app2, fb_id):
    print('\n===== 第三轮 数据隔离 =====')
    r = _response(c.get(f'{BASE}/detail', _signed(app2, {'feedback_id': fb_id})))
    _check('跨项目详情隔离', r['code'] == 20030, r)
    r = _response(c.get(f'{BASE}/list', _signed(app2)))
    _check('跨项目列表隔离', r['code'] == 10000 and r['data']['total'] == 0, r)


# ───────────────────────── 第四轮 基础参数校验 ─────────────────────────

def round_param_base(c, app, token):
    print('\n===== 第四轮 基础参数校验 =====')
    r = _response(c.post(f'{BASE}/create', _signed(app, {'content': 'c', 'token': token})))
    _check('缺标题被拒', r['code'] == 20001, r)
    r = _response(c.post(f'{BASE}/create', _signed(app, {
        'title': 'x' * 101, 'content': 'c', 'token': token,
    })))
    _check('标题超长被拒', r['code'] == 20002, r)
    r = _response(c.post(f'{BASE}/reply', _signed(app, {
        'feedback_id': '3fa85f64-5717-4562-b3fc-2c963f66afa6', 'token': token,
    })))
    _check('追加缺内容被拒', r['code'] == 20001, r)


# ───────────────────────── 第五轮 边缘化测试 ─────────────────────────

def round_edge(c, app, token):
    print('\n===== 第五轮 边缘化测试 =====')
    # 标题恰好 100 字符（边界合法）
    r = _response(c.post(f'{BASE}/create', _signed(app, {
        'title': 'x' * 100, 'content': 'edge', 'token': token,
    })))
    _check('标题100字符边界通过', r['code'] == 10000, r)
    _created_feedback.append(r['data']['feedback_id'])

    # 非法分页参数归一化（列表）
    for pg, pgs in [(-1, 10), (0, 10), ('abc', 10), (1, 0), (1, 1000), (1, 'xyz')]:
        r = _response(c.get(f'{BASE}/list', _signed(app, {'page': pg, 'page_size': pgs})))
        ok = r['code'] == 10000 and r['data']['page'] >= 1 \
            and 1 <= r['data']['page_size'] <= 100
        _check(f'列表非法分页({pg},{pgs})归一化', ok, r)

    # 非法分页参数归一化（详情）：任一参数非法 → 整体回退默认(page=1, page_size=20)
    r = _response(c.get(f'{BASE}/detail', _signed(app, {
        'feedback_id': _created_feedback[-1], 'page': 'abc', 'page_size': -5,
    })))
    _check('详情非法分页回退默认', r['code'] == 10000 and r['data']['page'] == 1
           and r['data']['page_size'] == 20, r)
    # 仅 page_size 非法（page 合法）→ page_size 归一化为 1
    r = _response(c.get(f'{BASE}/detail', _signed(app, {
        'feedback_id': _created_feedback[-1], 'page': 1, 'page_size': -5,
    })))
    _check('详情page_size负数归一化1', r['code'] == 10000 and r['data']['page_size'] == 1, r)

    # 非法 status 筛选（不匹配则返回全部，不报错）
    r = _response(c.get(f'{BASE}/list', _signed(app, {'status': 'not_a_status'})))
    _check('非法status筛选不报错', r['code'] == 10000 and r['data']['total'] >= 1, r)

    # 非法 UUID 格式
    r = _response(c.get(f'{BASE}/detail', _signed(app, {'feedback_id': 'not-a-uuid'})))
    _check('非法UUID格式返回不存在', r['code'] == 20030, r)

    # /replies 非法分页归一化（评论树测试反馈的一级评论）
    fb_tree = _created_feedback[1]
    top = FeedbackReply.objects.filter(feedback_id=fb_tree, parent_id__isnull=True).first()
    r = _response(c.get(f'{BASE}/replies', _signed(app, {
        'feedback_id': fb_tree, 'parent_id': str(top.id),
        'page': 'abc', 'page_size': -5,
    })))
    _check('/replies非法分页回退默认', r['code'] == 10000 and r['data']['page'] == 1
           and r['data']['page_size'] == 20, r)

    # 追加空内容（纯空白）
    r = _response(c.post(f'{BASE}/reply', _signed(app, {
        'feedback_id': _created_feedback[-1], 'content': '   ', 'token': token,
    })))
    _check('纯空白追加被拒', r['code'] == 20001, r)


# ───────────────────────── 第六轮 并发测试 ─────────────────────────

def round_concurrent(app):
    print('\n===== 第六轮 并发测试 =====')

    # 6.1 多用户并发提交反馈（20 线程）
    results = []
    barrier = threading.Barrier(20)

    def worker_submit(i):
        try:
            barrier.wait(timeout=30)
        except threading.BrokenBarrierError:
            pass
        user = _create_user(name=f'{_CONC_PREFIX}提交{i}', prefix=_CONC_PREFIX)
        token = _issue_token(app, user)
        c = Client()
        r = _response(c.post(f'{BASE}/create', _signed(app, {
            'title': f'并发反馈{i}', 'content': f'内容{i}', 'token': token,
        })))
        results.append((i, r['code'], r['data'].get('feedback_id') if r.get('data') else None))

    threads = [threading.Thread(target=worker_submit, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    ok = len(results) == 20 and all(code == 10000 for _, code, _ in results)
    _check('20用户并发提交全部成功', ok, f'成功{len(results)}/20')
    for _, _, fid in results:
        if fid:
            _created_feedback.append(fid)

    # 6.2 同一反馈并发追加（30 线程，同一用户）
    fb = Feedback.objects.filter(app=app[2]).first()
    _created_feedback.append(str(fb.id))
    user = _create_user(name=f'{_CONC_PREFIX}追加者', prefix=_CONC_PREFIX)
    token = _issue_token(app, user)
    results2 = []
    barrier2 = threading.Barrier(30)

    def worker_reply(i):
        try:
            barrier2.wait(timeout=30)
        except threading.BrokenBarrierError:
            pass
        c = Client()
        r = _response(c.post(f'{BASE}/reply', _signed(app, {
            'feedback_id': str(fb.id), 'content': f'并发追加{i}', 'token': token,
        })))
        results2.append((i, r['code']))

    threads2 = [threading.Thread(target=worker_reply, args=(i,)) for i in range(30)]
    for t in threads2:
        t.start()
    for t in threads2:
        t.join(timeout=60)
    ok = len(results2) == 30 and all(code == 10000 for _, code in results2)
    _check('30线程并发追加全部成功', ok, f'成功{len(results2)}/30')

    # 并发后校验追加总数
    total = fb.replies.count()
    _check('并发追加无丢失', total == 30, f'实际{total}/30')

    # 6.3 30 线程并发嵌套回复同一评论（二级回复并发写）
    top_reply = FeedbackReply.objects.filter(feedback=fb, parent_id__isnull=True).first()
    results3 = []
    barrier3 = threading.Barrier(30)

    def worker_reply_nested(i):
        try:
            barrier3.wait(timeout=30)
        except threading.BrokenBarrierError:
            pass
        c = Client()
        r = _response(c.post(f'{BASE}/reply', _signed(app, {
            'feedback_id': str(fb.id), 'content': f'并发嵌套回复{i}',
            'token': token, 'parent_id': str(top_reply.id),
        })))
        results3.append((i, r['code']))

    threads3 = [threading.Thread(target=worker_reply_nested, args=(i,)) for i in range(30)]
    for t in threads3:
        t.start()
    for t in threads3:
        t.join(timeout=60)
    ok = len(results3) == 30 and all(code == 10000 for _, code in results3)
    _check('30线程并发嵌套回复全部成功', ok, f'成功{len(results3)}/30')
    nested_total = top_reply.children.count()
    _check('并发嵌套回复无丢失', nested_total == 30, f'实际{nested_total}/30')


# ───────────────────────── 第七轮 极限测试 ─────────────────────────

def round_stress(c, app, token):
    print('\n===== 第七轮 极限测试 =====')
    # 7.1 单反馈 1050 条追加的分页正确性（bulk_create 快速造数）
    fb = Feedback.objects.create(app=app[2], user=User.objects.filter(id__in=_created_users).first(),
                                 title='极限追加', content='stress')
    _created_feedback.append(str(fb.id))
    now = timezone.now()
    FeedbackReply.objects.bulk_create([
        FeedbackReply(feedback=fb, user_id=_created_users[0], author_role='user',
                      content=f'r{i}', create_time=now + timedelta(seconds=i))
        for i in range(1050)
    ])
    r = _response(c.get(f'{BASE}/detail', _signed(app, {
        'feedback_id': str(fb.id), 'page': 1, 'page_size': 100,
    })))
    ok = r['code'] == 10000 and r['data']['total'] == 1050 \
        and r['data']['total_pages'] == 11 and len(r['data']['replies']) == 100
    _check('1050追加分页(total/pages/首页)', ok, r)
    r = _response(c.get(f'{BASE}/detail', _signed(app, {
        'feedback_id': str(fb.id), 'page': 11, 'page_size': 100,
    })))
    _check('1050追加最后一页50条', r['code'] == 10000 and len(r['data']['replies']) == 50, r)
    r = _response(c.get(f'{BASE}/detail', _signed(app, {
        'feedback_id': str(fb.id), 'page': 99, 'page_size': 100,
    })))
    _check('越界页码返回空列表', r['code'] == 10000 and r['data']['replies'] == [], r)

    # 7.2 大文本内容（10KB）
    big = '内容' * 5000
    r = _response(c.post(f'{BASE}/create', _signed(app, {
        'title': '大文本', 'content': big, 'token': token,
    })))
    _check('10KB大文本提交成功', r['code'] == 10000, r)
    fb_big_id = r['data']['feedback_id']
    _created_feedback.append(fb_big_id)
    r = _response(c.get(f'{BASE}/detail', _signed(app, {'feedback_id': fb_big_id})))
    _check('10KB大文本原样返回', r['code'] == 10000 and r['data']['content'] == big, r)

    # 7.3 大列表分页（150 条反馈，page_size=100）
    first_user = User.objects.filter(id__in=_created_users).first()
    batch = Feedback.objects.bulk_create([
        Feedback(app=app[2], user=first_user, title=f'批量{i}', content='x')
        for i in range(150)
    ])
    _created_feedback.extend(str(f.id) for f in batch)
    r = _response(c.get(f'{BASE}/list', _signed(app, {'page': 2, 'page_size': 100})))
    # 总条数 = 前面各轮累计 + 150；第 2 页条数 = total - 100
    expect = r['data']['total'] - 100
    _check('大列表第2页分页正确', r['code'] == 10000
           and len(r['data']['items']) == expect > 0, r)

    # 7.4 单条一级评论下 1000 条回复（详情只内嵌二级首页，/replies 分页可取全）
    first_user = User.objects.filter(id__in=_created_users).first()
    fb_huge = Feedback.objects.create(app=app[2], user=first_user, title='海量回复', content='x')
    _created_feedback.append(str(fb_huge.id))
    top = FeedbackReply.objects.create(feedback=fb_huge, user_id=_created_users[0],
                                       author_role='user', content='top')
    now = timezone.now()
    FeedbackReply.objects.bulk_create([
        FeedbackReply(feedback=fb_huge, parent_id=top.id, user_id=_created_users[0],
                      author_role='user', content=f'sub{i}',
                      create_time=now + timedelta(seconds=i))
        for i in range(1000)
    ])
    r = _response(c.get(f'{BASE}/detail', _signed(app, {'feedback_id': str(fb_huge.id)})))
    node = r['data']['replies'][0] if r['data']['replies'] else {}
    ok = (r['code'] == 10000 and r['data']['total'] == 1
          and node.get('reply_total') == 1000
          and node.get('children_total') == 1000
          and len(node.get('replies', [])) == SUB_REPLY_FIRST_PAGE_SIZE
          and all(x['replies'] == [] for x in node.get('replies', [])))
    _check('详情1000回复仅内嵌二级首页', ok, r)
    # /replies 分页取全 1000 条（page_size=100，翻 10 页）
    ids = []
    for pg in range(1, 11):
        r = _response(c.get(f'{BASE}/replies', _signed(app, {
            'feedback_id': str(fb_huge.id), 'parent_id': str(top.id),
            'page': pg, 'page_size': 100,
        })))
        ids.extend(x['reply_id'] for x in r['data']['items'])
    _check('/replies分页取全1000条回复', len(ids) == 1000, f'实际{len(ids)}')

    # 7.5 50 层深嵌套（详情内嵌全部子孙首页；/replies 一次返回全部子孙，不分层级）
    fb_deep = Feedback.objects.create(app=app[2], user=first_user, title='深嵌套', content='x')
    _created_feedback.append(str(fb_deep.id))
    prev = None
    for i in range(50):
        prev = FeedbackReply.objects.create(
            feedback=fb_deep, parent=prev, user_id=_created_users[0],
            author_role='user', content=f'level{i}',
            create_time=now + timedelta(seconds=i),
        )
    r = _response(c.get(f'{BASE}/detail', _signed(app, {'feedback_id': str(fb_deep.id)})))
    root = r['data']['replies'][0]
    ok = (r['code'] == 10000 and r['data']['total'] == 1
          and len(r['data']['replies']) == 1
          and len(root['replies']) == SUB_REPLY_FIRST_PAGE_SIZE   # 二级评论首页 = 全部子孙前 5 条
          and root['replies'][0]['content'] == 'level1'
          and root['replies'][0]['parent_id'] == root['reply_id']
          and all(x['replies'] == [] for x in root['replies']))   # 内嵌不再递归嵌套
    _check('详情深嵌套内嵌全部子孙首页', ok, r)
    # /replies 一次返回全部 49 个子孙（level1~level49，不分层级），无深度限制
    r = _response(c.get(f'{BASE}/replies', _signed(app, {
        'feedback_id': str(fb_deep.id), 'parent_id': root['reply_id'], 'page_size': 100,
    })))
    items = r['data']['items']
    ok = (r['code'] == 10000 and r['data']['total'] == 49
          and len(items) == 49
          and items[0]['content'] == 'level1'
          and items[0]['parent_id'] == root['reply_id']
          and items[-1]['content'] == 'level49')
    _check('50层深嵌套一次取全部子孙(level1~level49)', ok, r)
    # 查看最深层 level49 的二级评论 → 空
    r = _response(c.get(f'{BASE}/replies', _signed(app, {
        'feedback_id': str(fb_deep.id), 'parent_id': items[-1]['reply_id'],
    })))
    _check('最深层评论无二级评论', r['code'] == 10000 and r['data']['total'] == 0
           and r['data']['items'] == [], r)


# ───────────────────────── 第八轮 安全测试 ─────────────────────────

def round_security(c, app, token):
    print('\n===== 第八轮 安全测试 =====')

    # 8.1 签名过期（-6 分钟）
    stale = _signed(app, {'title': 't', 'content': 'c', 'token': token})
    stale['timestamp'] = str(int(time.time()) - 360)
    stale['sign'] = build_sign(stale, app[1])
    r = _response(c.post(f'{BASE}/create', stale))
    _check('签名过期被拒', r['code'] == 20011, r)

    # 8.2 签名篡改（改参数不改 sign）
    tampered = _signed(app, {'title': 't', 'content': 'c', 'token': token})
    tampered['content'] = 'tampered'
    r = _response(c.post(f'{BASE}/create', tampered))
    _check('签名与参数不匹配被拒', r['code'] == 20011, r)

    # 8.3 未知 app_id（假签名）
    fake = {'app_id': 'app_' + 'f' * 28, 'timestamp': str(int(time.time())),
            'nonce': 'n' * 16, 'title': 't', 'content': 'c', 'token': token}
    fake['sign'] = build_sign(fake, 'sk_' + 'f' * 60)
    r = _response(c.post(f'{BASE}/create', fake))
    _check('未知app_id被拒', r['code'] == 20011, r)

    # 8.4 停用项目（status=False）
    app_disabled = _create_app(active=False)
    r = _response(c.get(f'{BASE}/list', _signed(app_disabled)))
    _check('停用项目被拒', r['code'] == 20011, r)

    # 8.5 跨项目 token（A 的 token 用于 B）
    app_b = _create_app()
    r = _response(c.post(f'{BASE}/create', _signed(app_b, {
        'title': 't', 'content': 'c', 'token': token,
    })))
    _check('跨项目token被拒', r['code'] == 20010, r)

    # 8.6 过期 token
    expired_user = _create_user(prefix=_CONC_PREFIX)
    expired_token = _issue_token(app, expired_user, days=-1)
    r = _response(c.post(f'{BASE}/create', _signed(app, {
        'title': 't', 'content': 'c', 'token': expired_token,
    })))
    _check('过期token被拒', r['code'] == 20010, r)

    # 8.7 XSS 内容原样存储返回（服务端不转义不落富文本，前端负责转义）
    xss = '<script>alert(1)</script><img src=x onerror=alert(2)>'
    r = _response(c.post(f'{BASE}/create', _signed(app, {
        'title': 'xss', 'content': xss, 'token': token,
    })))
    _check('XSS内容提交成功', r['code'] == 10000, r)
    fb_xss_id = r['data']['feedback_id']
    _created_feedback.append(fb_xss_id)
    r = _response(c.get(f'{BASE}/detail', _signed(app, {'feedback_id': fb_xss_id})))
    _check('XSS内容原样返回', r['code'] == 10000 and r['data']['content'] == xss, r)


# ───────────────────────── 主流程 ─────────────────────────

def run():
    c = Client()
    app = _create_app()
    user = _create_user()
    token = _issue_token(app, user)
    app2 = _create_app()

    round_basic_auth(c, app, token)
    round_normal(c, app, token)
    round_tree(c, app, token)
    fb_id = _created_feedback[0]
    round_isolation(c, app2, fb_id)
    round_param_base(c, app, token)
    round_edge(c, app, token)
    round_concurrent(app)
    round_stress(c, app, token)
    round_security(c, app, token)

    _cleanup()
    print(f'\n===== 结果: 通过 {_stats["pass"]} / 失败 {_stats["fail"]} =====')
    sys.exit(1 if _stats['fail'] else 0)


if __name__ == '__main__':
    run()
