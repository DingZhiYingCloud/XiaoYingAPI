"""问题反馈中心 完整测试（免签接口 + 对外反馈页 + 超管后台）

覆盖范围：
    第一轮  免签接口（POST /api/feedback/ticket、GET /api/feedback/contacts）
    第二轮  页面渲染（提交页 / 公开区 / 我的反馈 / 详情，含 404 与登录引导）
    第三轮  游客提交（图形验证码 / 类型校验 / 内容校验 / 附件上限 / IP 限流）
    第四轮  票据登录态（换票 → 消费 → 会话 → 我的反馈 → 详情跟帖）
    第五轮  公开区可见性（仅游客 + 过审；不含附件；关键词搜索）
    第六轮  项目隔离与权限（跨项目 404 / 非本人 404 / 停用项目 404）
    第七轮  AI 审核联动（关闭→待处理；开启→待审核或跳过）
    第八轮  超管后台 · 反馈管理（鉴权 / 筛选 / 详情 / 回复与 AI 提醒 / 强制发送 /
            送审 / 公开区隐藏 / 关闭重开 / 删除）
    第九轮  超管后台 · 反馈中心设置（开关与规则 / 类型字典 / 联系方式平台 / 项目联系方式）
    第十轮  官网页脚「联系我们」（后台没配则隐藏 / 配了则展示平台名、值与可点击链接）

运行方式（使用真实数据库，结束后自动清理测试数据并还原全局设置）：
    .venv\\Scripts\\python.exe scripts\\test_feedback.py
"""
import io
import itertools
import os
import random
import secrets
import sys
import time
from datetime import timedelta
from urllib.parse import urlencode

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'XiaoYingAPI.settings')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import django

django.setup()

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from API.apis.captcha_self import utils as captcha_utils
from API.apis.feedback.utils import serialize_contacts
from API.common.credential_crypto import hash_token
from API.models import (CaptchaChallenge, ContactPlatform, Feedback, FeedbackAttachment,
                        FeedbackAuditLog, FeedbackReply, FeedbackSetting, FeedbackTicket,
                        FeedbackType, ProjectContact, User, UserApp, UserToken)

_PREFIX = f'FB{int(time.time())}'
_stats = {'pass': 0, 'fail': 0}
_created_apps = []
_created_users = []
_created_feedback = []
_created_types = []
_created_platforms = []
_created_admins = []
_created_files = []
_setting_backup = {}
_seq = itertools.count()


def _check(name, cond, extra=''):
    if cond:
        _stats['pass'] += 1
        print(f'  [PASS] {name}')
    else:
        _stats['fail'] += 1
        print(f'  [FAIL] {name} {extra}')


def _create_app(name=None, active=True):
    obj = UserApp.objects.create(name=name or f'{_PREFIX}项目{len(_created_apps)}', status=active)
    _created_apps.append(obj)
    return obj


def _create_user(username=None):
    user = User.objects.create(
        account=str(random.randint(10000000, 99999999)),
        username=username or f'{_PREFIX}用户{len(_created_users)}',
        password=make_password('pass123456'),
        status=True,
    )
    _created_users.append(str(user.id))
    return user


def _issue_token(app, user, days=7):
    """签发绑定指定项目的 Token（user_token.token 落库存哈希）"""
    raw = secrets.token_hex(32)
    UserToken.objects.create(user=user, app=app, token=hash_token(raw),
                             expire_time=timezone.now() + timedelta(days=days))
    return raw


def _page(client, app, path='', **params):
    url = reverse('website:feedback', args=[app.app_id]) + path
    if params:
        url += '?' + urlencode(params)
    return client.get(url)


def _set_setting(**kwargs):
    setting = FeedbackSetting.get_solo()
    for key, value in kwargs.items():
        setattr(setting, key, value)
    setting.save()
    return setting


# ───────────────────────── 第一轮 免签接口 ─────────────────────────

def round_api(c, app, token):
    print('\n===== 第一轮 免签接口 =====')
    r = c.post('/api/feedback/ticket', {}).json()
    _check('ticket 缺 token 被拒', r['code'] == 20001, r)

    r = c.post('/api/feedback/ticket', {'token': 'f' * 64}).json()
    _check('ticket 伪造 token 被拒', r['code'] == 20010, r)

    r = c.post('/api/feedback/ticket', {'token': token}).json()
    ok = r['code'] == 10000 and r['data']['app_id'] == app.app_id and r['data']['ticket']
    _check('ticket 正常换票', ok, r)
    ticket_token = r['data']['ticket'] if ok else ''

    r = c.get('/api/feedback/contacts').json()
    _check('contacts 缺 app_id 被拒', r['code'] == 20001, r)

    r = c.get('/api/feedback/contacts', {'app_id': 'app_' + 'f' * 28}).json()
    _check('contacts 项目不存在被拒', r['code'] == 20030, r)

    r = c.get('/api/feedback/contacts', {'app_id': app.app_id}).json()
    _check('contacts 正常返回', r['code'] == 10000 and r['data']['app_id'] == app.app_id, r)
    return ticket_token


# ───────────────────────── 第二轮 页面渲染 ─────────────────────────

def round_pages(app):
    print('\n===== 第二轮 页面渲染 =====')
    c = Client()
    r = _page(c, app)
    body = r.content.decode()
    _check('提交页 200', r.status_code == 200, r.status_code)
    _check('提交页含类型选项', all(t.name in body for t in FeedbackType.objects.filter(enabled=True)),
           '缺少类型选项')
    _check('提交页含开发者联系方式', '开发者联系方式' in body)
    _check('提交页含联系方式的平台名', 'QQ' in body)

    r = _page(c, app, 'public/')
    _check('公开区 200', r.status_code == 200, r.status_code)

    # 游客访问「我的反馈」被引导回提交页
    r = _page(c, app, 'my/')
    _check('游客访问我的反馈被重定向', r.status_code == 302, r.status_code)

    r = _page(c, app, f'detail/{secrets.token_hex(16)}/')
    # 该 uuid 不存在 → 404
    _check('详情(不存在) 404', r.status_code == 404, r.status_code)

    r = Client().get(reverse('website:feedback', args=['app_' + 'f' * 28]) + '')
    _check('未知 APPID 404', r.status_code == 404, r.status_code)


# ───────────────────────── 第三轮 游客提交 ─────────────────────────

def _png_file(name='shot.png'):
    """造一张最小 PNG 作为上传文件（必须带文件名，否则上传会被判「文件名为空」）"""
    buf = io.BytesIO()
    Image.new('RGB', (6, 6), (12, 34, 56)).save(buf, 'PNG')
    return SimpleUploadedFile(name, buf.getvalue(), content_type='image/png')


def round_guest_submit(app, feedback_type):
    print('\n===== 第三轮 游客提交 =====')
    c = Client()
    submit_url = reverse('website:feedback', args=[app.app_id])

    # 3.1 未完成图形验证 → 拒绝且不入库
    _set_setting(captcha_required=True, rate_limit_hour=0, rate_limit_day=0)
    before = Feedback.objects.count()
    r = c.post(submit_url, {'type_id': str(feedback_type.id), 'content': '没有验证码的提交'})
    _check('缺图形验证被拒', Feedback.objects.count() == before and r.status_code == 200)

    # 3.2 内容为空 → 拒绝
    r = c.post(reverse('website:feedback', args=[app.app_id]),
               {'type_id': str(feedback_type.id), 'content': '   '})
    _check('空内容被拒', Feedback.objects.count() == before)

    # 3.3 类型非法 → 拒绝
    r = c.post(reverse('website:feedback', args=[app.app_id]),
               {'type_id': '99999999', 'content': '类型不存在'})
    _check('非法类型被拒', Feedback.objects.count() == before)

    # 3.4 正常提交（带图形验证 + 1 张图片）
    challenge = captcha_utils.create_challenge()
    answer = CaptchaChallenge.objects.get(id=challenge['captcha_id']).answer
    r = c.post(submit_url, {
        'type_id': str(feedback_type.id),
        'content': '游客提交的一条反馈：播放器在移动端点不开。',
        'contact_email': 'guest@example.com',
        'captcha_id': challenge['captcha_id'],
        'answer': answer,
        'images': _png_file(),
    }, follow=False)
    fb = Feedback.objects.filter(app=app).order_by('-create_time').first()
    _check('游客提交成功', fb is not None and fb.user_id is None, r.status_code)
    if fb is None:
        return None
    _created_feedback.append(str(fb.pk))
    _check('业务状态与审核状态一致',
           (fb.ai_status == 'pending' and fb.status == 'pending')
           or (fb.ai_status == 'skipped' and fb.status == 'processing'),
           f'{fb.status}/{fb.ai_status}')
    _check('游客不显示身份信息', fb.submitter_name == '匿名用户')

    att = FeedbackAttachment.objects.filter(feedback=fb).first()
    _check('附件已入库', att is not None)
    if att:
        _created_files.append(os.path.join(settings.MEDIA_ROOT, att.path))

    # 3.5 附件数量超限 → 整单驳回（不产生「提交成功但附件被丢掉」的错觉）
    _set_setting(max_images=1, captcha_required=False)
    count_before = Feedback.objects.count()
    r = c.post(submit_url, {
        'type_id': str(feedback_type.id), 'content': '带两张图但上限是一张',
        'images': [_png_file('a.png'), _png_file('b.png')],
    })
    _check('附件数量超限 → 整单驳回', r.status_code == 200
           and Feedback.objects.count() == count_before
           and '最多只能上传' in r.content.decode(), r.status_code)

    # 3.5b 单个附件超过大小上限 → 整单驳回
    _set_setting(max_images=3, max_image_mb=0)
    r = c.post(submit_url, {
        'type_id': str(feedback_type.id), 'content': '单张图超过大小上限',
        'images': [_png_file('big.png')],
    })
    _check('附件超大小上限 → 整单驳回', r.status_code == 200
           and Feedback.objects.count() == count_before
           and '超过大小上限' in r.content.decode(), r.status_code)
    _set_setting(max_image_mb=10)

    # 3.6 IP 限流：用一个专属 IP（走 XFF）避免与库里其它数据的同 IP 计数互相干扰
    rate_ip = '203.0.113.11'
    _set_setting(max_images=3, captcha_required=False, rate_limit_hour=1, rate_limit_day=0)
    ok1 = c.post(submit_url, {'type_id': str(feedback_type.id), 'content': '限流测试1'},
                 HTTP_X_FORWARDED_FOR=rate_ip)
    fb3 = Feedback.objects.filter(app=app).order_by('-create_time').first()
    if fb3 and str(fb3.pk) not in _created_feedback:
        _created_feedback.append(str(fb3.pk))
    n_after_1 = Feedback.objects.count()
    c.post(submit_url, {'type_id': str(feedback_type.id), 'content': '限流测试2'},
           HTTP_X_FORWARDED_FOR=rate_ip)
    _check('同 IP 超限被拦', ok1.status_code == 302 and Feedback.objects.count() == n_after_1
           and fb3.ip == rate_ip,
           f'{ok1.status_code} / ip={fb3.ip!r}')
    _set_setting(rate_limit_hour=0)
    return fb


# ───────────────────────── 第四轮 票据登录态 ─────────────────────────

def round_ticket(app, user, token, guest_fb):
    print('\n===== 第四轮 票据登录态 =====')
    # 打开图形验证：验证「登录用户不受验证码约束」这条规则确实生效
    _set_setting(captcha_required=True)
    c = Client()
    r = c.post('/api/feedback/ticket', {'token': token}).json()
    ticket = r['data']['ticket']

    url = reverse('website:feedback', args=[app.app_id]) + f'?ticket={ticket}'
    resp = c.get(url)
    _check('票据消费后 303 重定向', resp.status_code == 303, resp.status_code)
    _check('重定向目标不含票据', 'ticket=' not in resp.headers.get('Location', ''),
           resp.headers.get('Location'))

    # 票据只能消费一次
    resp2 = c.get(url)
    _check('票据不可重复消费', resp2.status_code == 200, resp2.status_code)
    _check('票据已标记使用', FeedbackTicket.objects.filter(token=ticket, used=True).exists())

    # 登录后提交：user 落库
    r = c.post(reverse('website:feedback', args=[app.app_id]), {
        'type_id': str(FeedbackType.objects.filter(enabled=True).first().id),
        'content': '登录用户提交的一条反馈：希望能加导出功能。',
    })
    fb = Feedback.objects.filter(app=app, user=user).order_by('-create_time').first()
    _check('登录用户提交成功且带 user', fb is not None and fb.user_id == user.id, r.status_code)
    if fb is None:
        return
    _created_feedback.append(str(fb.pk))
    _check('登录提交免图形验证', fb is not None)

    # 我的反馈列表能看到
    r = _page(c, app, 'my/')
    _check('我的反馈列出本人反馈', r.status_code == 200 and fb.display_title in r.content.decode())

    # 详情 + 跟帖
    detail_url = reverse('website:feedback_detail', args=[app.app_id, fb.pk])
    r = c.get(detail_url)
    _check('本人可看自己未过审的反馈', r.status_code == 200, r.status_code)

    c.post(detail_url, {'content': '补充：导出格式希望支持 Excel。'})
    _check('跟帖写入成功', FeedbackReply.objects.filter(
        feedback=fb, author_role='user', content__startswith='补充：').exists())
    fb.refresh_from_db()
    _check('跟帖后置位待处理提示', fb.admin_unread is True and fb.last_reply_time is not None)

    # 游客不能跟帖（非本人）
    guest_client = Client()
    r = guest_client.post(detail_url, {'content': '游客想跟帖'})
    _check('非本人不可跟帖', r.status_code == 404
           and not FeedbackReply.objects.filter(feedback=fb, content='游客想跟帖').exists(),
           r.status_code)

    # 已驳回状态不可跟帖
    fb.status = Feedback.Status.REJECTED
    fb.save(update_fields=['status', 'updated_time'])
    c.post(detail_url, {'content': '驳回后还想跟帖'})
    _check('驳回状态不可跟帖', not FeedbackReply.objects.filter(
        feedback=fb, content='驳回后还想跟帖').exists())


# ───────────────────────── 第五轮 公开区可见性 ─────────────────────────

def round_public(app, guest_fb, mine_fb):
    print('\n===== 第五轮 公开区可见性 =====')
    c = Client()

    # 把游客那条推到「已回复」，并给它挂一张图（公开区应不展示附件）
    guest_fb.status = Feedback.Status.REPLIED
    guest_fb.save(update_fields=['status', 'updated_time'])
    att = FeedbackAttachment.objects.filter(feedback=guest_fb).first()
    if att is None:
        att = FeedbackAttachment.objects.create(
            feedback=guest_fb, kind='image', path='uploads/images/tmp_public_check.png',
            original_name='x.png', size=1, ext='png')

    r = _page(c, app, 'public/')
    body = r.content.decode()
    _check('公开区列出游客已过审反馈', guest_fb.display_title in body)
    _check('公开区不展示附件地址', att.url not in body, att.url)

    # 登录用户（非游客）的反馈不进公开区
    r = _page(c, app, 'public/')
    _check('登录用户反馈不进公开区', mine_fb.display_title not in r.content.decode())

    # 关键词检索
    keyword = guest_fb.display_title[:6]
    r = _page(c, app, 'public/', q=keyword)
    _check('关键词命中', guest_fb.display_title in r.content.decode())

    r = _page(c, app, 'public/', q='绝不可能命中的关键词xyz')
    _check('关键词不命中时列表为空', r.status_code == 200
           and guest_fb.display_title not in r.content.decode())

    # 游客可见公开详情，但看不到附件
    r = c.get(reverse('website:feedback_detail', args=[app.app_id, guest_fb.pk]))
    _check('游客可看公开详情', r.status_code == 200, r.status_code)
    _check('公开详情不展示附件', att.url not in r.content.decode())

    # 待审核（未过审）的游客反馈不进公开区
    guest_fb.status = Feedback.Status.PENDING
    guest_fb.save(update_fields=['status', 'updated_time'])
    r = c.get(reverse('website:feedback_detail', args=[app.app_id, guest_fb.pk]))
    _check('未过审游客反馈对外 404', r.status_code == 404, r.status_code)

    # public_hidden 后撤下
    guest_fb.status = Feedback.Status.PROCESSING
    guest_fb.public_hidden = True
    guest_fb.save(update_fields=['status', 'public_hidden', 'updated_time'])
    r = c.get(reverse('website:feedback_detail', args=[app.app_id, guest_fb.pk]))
    _check('公开区隐藏后对外 404', r.status_code == 404, r.status_code)
    guest_fb.public_hidden = False
    guest_fb.save(update_fields=['public_hidden', 'updated_time'])


# ───────────────────────── 第六轮 项目隔离 ─────────────────────────

def round_isolation(app, other_app, feedback, token):
    print('\n===== 第六轮 项目隔离 =====')
    # 同一个反馈 ID 在另一个项目下访问 → 404
    r = Client().get(reverse('website:feedback_detail', args=[other_app.app_id, feedback.pk]))
    _check('跨项目详情 404', r.status_code == 404, r.status_code)

    # 其他项目的票据不能在本项目页面消费
    r = Client().post('/api/feedback/ticket', {'token': _issue_token(other_app, User.objects.get(
        pk=_created_users[0]))}).json()
    other_ticket = r['data']['ticket']
    r = Client().get(reverse('website:feedback', args=[app.app_id]) + f'?ticket={other_ticket}')
    _check('跨项目票据不被消费', r.status_code == 200
           and FeedbackTicket.objects.get(token=other_ticket).used is False, r.status_code)

    # 停用项目 → 404
    disabled = _create_app(active=False)
    r = Client().get(reverse('website:feedback', args=[disabled.app_id]))
    _check('停用项目 404', r.status_code == 404, r.status_code)

    # 关闭反馈中心总开关 → 提交页提示未开放
    _set_setting(enabled=False)
    r = Client().get(reverse('website:feedback', args=[app.app_id]))
    _check('总开关关闭时提示未开放', r.status_code == 200 and '暂未开放' in r.content.decode())
    _set_setting(enabled=True)


# ───────────────────────── 第七轮 AI 审核联动 ─────────────────────────

def round_ai_status(app, feedback_type):
    print('\n===== 第七轮 AI 审核联动 =====')
    c = Client()
    _set_setting(captcha_required=False, rate_limit_hour=0, rate_limit_day=0, ai_review_enabled=False)
    c.post(reverse('website:feedback', args=[app.app_id]),
           {'type_id': str(feedback_type.id), 'content': '关闭 AI 审核时的提交'})
    fb = Feedback.objects.filter(app=app).order_by('-create_time').first()
    _created_feedback.append(str(fb.pk))
    _check('关闭审核 → 待处理/未开启审核',
           fb.status == 'processing' and fb.ai_status == 'skipped', f'{fb.status}/{fb.ai_status}')

    _set_setting(ai_review_enabled=True)
    c.post(reverse('website:feedback', args=[app.app_id]),
           {'type_id': str(feedback_type.id), 'content': '开启 AI 审核时的提交'})
    fb2 = Feedback.objects.filter(app=app).order_by('-create_time').first()
    _created_feedback.append(str(fb2.pk))
    _check('开启审核 → 待审核或直接跳过（平台无可用模型）',
           (fb2.status == 'pending' and fb2.ai_status == 'pending')
           or (fb2.status == 'processing' and fb2.ai_status == 'skipped'),
           f'{fb2.status}/{fb2.ai_status}')
    _set_setting(ai_review_enabled=False)


# ───────────────────────── 第八轮 超管后台 · 反馈管理 ─────────────────────────

def _django_user(is_superuser=True):
    """建一个 Django 原生账号（超管页面鉴权用的就是这套账号体系）"""
    from django.contrib.auth.models import User as AdminUser
    username = f'{"super" if is_superuser else "plain"}{next(_seq)}'
    user = AdminUser.objects.create_user(username=username, password='adm123456',
                                         is_staff=is_superuser, is_superuser=is_superuser)
    _created_admins.append(username)
    return user


def _console_url(name, **params):
    url = reverse(f'website:{name}')
    return f'{url}?{urlencode(params)}' if params else url


def round_console(app, feedback_type):
    print('\n===== 第八轮 超管后台 · 反馈管理 =====')
    admin = _django_user()
    anonymous = Client()
    r = anonymous.get(reverse('website:console_feedback'))
    _check('未登录访问后台被重定向', r.status_code == 302, r.status_code)

    c = Client()
    c.force_login(admin)
    _set_setting(captcha_required=False, rate_limit_hour=0, rate_limit_day=0,
                 ai_review_enabled=False)

    # 造两条数据：一条游客（公开区可见）、一条登录用户
    fb = Feedback.objects.create(app=app, type=feedback_type,
                                 content='后台筛选用的游客反馈：导出按钮点了没反应。',
                                 status='processing', ai_status='passed', ip='127.0.0.1')
    fb2 = Feedback.objects.create(app=app, type=feedback_type,
                                  content='后台筛选用的第二条：希望支持夜间模式。',
                                  status='replied', ai_status='passed', ip='127.0.0.1')
    _created_feedback.extend([str(fb.pk), str(fb2.pk)])

    r = c.get(reverse('website:console_feedback'))
    body = r.content.decode()
    _check('后台列表 200', r.status_code == 200, r.status_code)
    _check('后台列表含反馈摘要', fb.display_title in body)
    _check('后台列表含筛选维度',
           all(x in body for x in ('全部项目', 'AI 审核', '关键词', '反馈中心设置')))
    _check('详情未展开时不含回复表单', 'fb-reply-form' not in body)

    r = c.get(_console_url('console_feedback', app=app.app_id, status='replied'))
    body = r.content.decode()
    _check('按项目+状态筛选生效', fb2.display_title in body and fb.display_title not in body)

    r = c.get(_console_url('console_feedback', q='夜间模式'))
    _check('关键词筛选生效', '夜间模式' in r.content.decode())

    r = c.get(_console_url('console_feedback', ai='passed'))
    _check('AI 状态筛选生效', fb.display_title in r.content.decode())

    # 详情（顺带清「有新回复」）
    fb.admin_unread = True
    fb.save(update_fields=['admin_unread', 'updated_time'])
    r = c.get(_console_url('console_feedback', detail=str(fb.pk)))
    detail_body = r.content.decode()
    _check('详情展开 200', r.status_code == 200 and fb.display_title in detail_body)
    _check('详情含回复表单与单条操作',
           'fb-reply-form' in detail_body and '立即送审' in detail_body)
    fb.refresh_from_db()
    _check('查看详情清除「有新回复」', fb.admin_unread is False)

    reply_url = reverse('website:console_feedback')

    # 回复（脚本预检 pass）→ 落库 + 留痕
    r = c.post(reply_url, {'action': 'reply', 'id': str(fb.pk), 'content': '已修复，请更新到最新版本。',
                           'ai_verdict': 'pass', 'ai_reason': ''}).json()
    _check('管理员回复成功', r['code'] == 10000 and FeedbackReply.objects.filter(
        feedback=fb, author_role='admin', content__startswith='已修复').exists(), r)
    fb.refresh_from_db()
    _check('回复后状态变已回复', fb.status == 'replied', fb.status)
    _check('回复留痕为通过',
           FeedbackAuditLog.objects.filter(feedback=fb, kind='reply', verdict='pass').exists())

    # 回复带附件
    r = c.post(reply_url, {'action': 'reply', 'id': str(fb.pk), 'content': '补一张示意图。',
                           'ai_verdict': 'pass', 'images': _png_file('reply.png')}).json()
    reply = FeedbackReply.objects.filter(feedback=fb, content='补一张示意图。').first()
    _check('回复可带附件', r['code'] == 10000 and reply is not None
           and reply.attachments.count() == 1, r)
    if reply and reply.attachments.exists():
        _created_files.append(os.path.join(settings.MEDIA_ROOT, reply.attachments.first().path))

    # AI 提醒：预检 warn 但未强制 → 不落库
    before = FeedbackReply.objects.filter(feedback=fb).count()
    r = c.post(reply_url, {'action': 'reply', 'id': str(fb.pk), 'content': '这问题你自己不会看文档吗',
                           'ai_verdict': 'warn', 'ai_reason': '语气偏强硬'}).json()
    _check('AI 提醒未强制时不落库', r['code'] == 30002
           and FeedbackReply.objects.filter(feedback=fb).count() == before, r)

    # 强制发送 → 落库 + 留痕 forced
    r = c.post(reply_url, {'action': 'reply', 'id': str(fb.pk), 'content': '这问题你自己不会看文档吗',
                           'ai_verdict': 'warn', 'ai_reason': '语气偏强硬', 'force': '1'}).json()
    _check('强制发送可落库', r['code'] == 10000 and FeedbackReply.objects.filter(
        feedback=fb, content__startswith='这问题你自己').exists(), r)
    _check('强制发送留痕 forced=True',
           FeedbackAuditLog.objects.filter(feedback=fb, kind='reply', verdict='warn',
                                          forced=True).exists())

    # 回复空内容 / 超长
    r = c.post(reply_url, {'action': 'reply', 'id': str(fb.pk), 'content': '  '}).json()
    _check('空回复被拒', r['code'] == 20001, r)
    r = c.post(reply_url, {'action': 'reply', 'id': str(fb.pk), 'content': 'x' * 5001}).json()
    _check('超长回复被拒', r['code'] == 20003, r)

    # 预检接口（关闭 AI 时返回 skip）
    r = c.post(reply_url, {'action': 'review_reply', 'id': str(fb.pk), 'content': '普通回复'}).json()
    _check('预检在 AI 不可用时返回 skip',
           r['code'] == 10000 and r['data']['verdict'] == 'skip', r)

    # 立即送审（AI 关闭 → 跳过审核，落到待处理）
    r = c.post(reply_url, {'action': 'resubmit', 'id': str(fb2.pk), 'next': '/console/feedback/'})
    fb2.refresh_from_db()
    _check('立即送审跑通', r.status_code == 302 and fb2.ai_status == 'skipped', fb2.ai_status)

    # 公开区隐藏切换
    c.post(reply_url, {'action': 'toggle_public', 'id': str(fb.pk), 'next': '/console/feedback/'})
    fb.refresh_from_db()
    _check('公开区隐藏切换', fb.public_hidden is True)
    c.post(reply_url, {'action': 'toggle_public', 'id': str(fb.pk), 'next': '/console/feedback/'})
    fb.refresh_from_db()
    _check('公开区恢复可见', fb.public_hidden is False)

    # 关闭 / 重新打开
    c.post(reply_url, {'action': 'close', 'id': str(fb.pk), 'next': '/console/feedback/'})
    fb.refresh_from_db()
    _check('关闭反馈', fb.status == 'closed', fb.status)
    c.post(reply_url, {'action': 'reopen', 'id': str(fb.pk), 'next': '/console/feedback/'})
    fb.refresh_from_db()
    _check('重新打开反馈', fb.status == 'processing', fb.status)

    # 已登录但不是超管 → 同样被拒
    plain = Client()
    plain.force_login(_django_user(is_superuser=False))
    r = plain.get(reverse('website:console_feedback'))
    _check('非超管访问后台被拒', r.status_code == 302, r.status_code)

    # 删除
    c.post(reply_url, {'action': 'delete', 'id': str(fb2.pk), 'next': '/console/feedback/'})
    _check('删除反馈', not Feedback.objects.filter(pk=fb2.pk).exists())
    _check('反馈不存在时回复返回 20030',
           c.post(reply_url, {'action': 'reply', 'id': str(fb2.pk), 'content': 'x'}).json()['code'] == 20030)


# ───────────────────────── 第九轮 超管后台 · 反馈中心设置 ─────────────────────────

def round_console_settings():
    print('\n===== 第九轮 超管后台 · 反馈中心设置 =====')
    admin = _django_user()
    c = Client()
    c.force_login(admin)
    url = reverse('website:console_feedback_settings')
    curl = reverse('website:console_contacts')

    r = c.get(url)
    body = r.content.decode()
    _check('设置页 200', r.status_code == 200, r.status_code)
    _check('设置页含各分区', all(x in body for x in ('功能与提交规则', 'AI 审核', '附件上限',
                                                '反馈类型')))
    _check('设置页已不含联系方式分区', not any(x in body for x in ('联系方式平台', '各项目开发者联系方式')))

    # 联系方式平台与各项目联系方式已独立成模块页
    r = c.get(curl)
    cbody = r.content.decode()
    _check('开发者联系方式页 200', r.status_code == 200, r.status_code)
    _check('联系方式页含两个分区', all(x in cbody for x in ('联系方式平台', '各项目开发者联系方式')))
    _check('设置页与联系方式页互相可达',
           curl in body and url in cbody)

    # 保存设置（并校验非法值被拒）
    r = c.post(url, {'action': 'save_setting', 'max_images': '3', 'max_videos': '1',
                     'max_image_mb': '10', 'max_video_mb': '50', 'rate_limit_hour': '5',
                     'rate_limit_day': '20', 'enabled': '1'})
    setting = FeedbackSetting.get_solo()
    _check('保存设置成功', r.status_code == 302 and setting.max_images == 3
           and setting.enabled is True and setting.captcha_required is False)
    r = c.post(url, {'action': 'save_setting', 'max_images': '99', 'max_videos': '1',
                     'max_image_mb': '10', 'max_video_mb': '50', 'rate_limit_hour': '5',
                     'rate_limit_day': '20'})
    _check('越界的附件上限被拒', FeedbackSetting.get_solo().max_images == 3)

    # 类型字典
    code = f'fbx{int(time.time()) % 100000}'
    c.post(url, {'action': 'type_create', 'code': code, 'name': '测试类型X', 'desc': '说明',
                 'icon': 'bug', 'sort': '9', 'enabled': '1'})
    new_type = FeedbackType.objects.filter(code=code).first()
    _check('新增反馈类型', new_type is not None and new_type.sort == 9)
    if new_type:
        _created_types.append(new_type)
        c.post(url, {'action': 'type_edit', 'id': str(new_type.pk), 'code': code,
                     'name': '测试类型Y', 'sort': '8', 'enabled': '1', 'is_default': '1'})
        new_type.refresh_from_db()
        _check('编辑反馈类型', new_type.name == '测试类型Y' and new_type.is_default is True)
        c.post(url, {'action': 'type_toggle', 'id': str(new_type.pk)})
        new_type.refresh_from_db()
        _check('停用反馈类型', new_type.enabled is False)
        c.post(url, {'action': 'type_create', 'code': code, 'name': '重复标识'})
        _check('类型标识重复被拒', FeedbackType.objects.filter(code=code).count() == 1)
        c.post(url, {'action': 'type_delete', 'id': str(new_type.pk)})
        _check('删除反馈类型', not FeedbackType.objects.filter(code=code).exists())

    # 联系方式平台（已独立到 /console/contacts/，故这一段的动作都打到 curl）
    pcode = f'pfx{int(time.time()) % 100000}'
    c.post(curl, {'action': 'platform_create', 'code': pcode, 'name': '测试平台',
                  'value_label': '账号', 'url_template': 'https://example.com/{value}',
                  'sort': '5', 'enabled': '1'})
    platform = ContactPlatform.objects.filter(code=pcode).first()
    _check('新增联系方式平台', platform is not None)
    if platform:
        _created_platforms.append(platform.pk)
        c.post(curl, {'action': 'platform_edit', 'id': str(platform.pk), 'code': pcode,
                      'name': '测试平台2', 'url_template': 'javascript:alert(1)', 'enabled': '1'})
        platform.refresh_from_db()
        _check('非法跳转模板被拒', platform.name == '测试平台'
               and platform.url_template == 'https://example.com/{value}')
        app = _create_app(name=f'{_PREFIX}联系方式项目')
        c.post(curl, {'action': 'contact_save', 'app_id': app.app_id,
                      f'contact_{platform.pk}': 'demo-value'})
        _check('保存项目联系方式', ProjectContact.objects.filter(
            app=app, platform=platform, value='demo-value').exists())
        c.post(curl, {'action': 'platform_delete', 'id': str(platform.pk)})
        _check('有绑定时的平台不可删除', ContactPlatform.objects.filter(pk=platform.pk).exists())
        c.post(curl, {'action': 'contact_save', 'app_id': app.app_id, f'contact_{platform.pk}': ''})
        _check('清空项目联系方式', not ProjectContact.objects.filter(
            app=app, platform=platform).exists())
        c.post(curl, {'action': 'platform_delete', 'id': str(platform.pk)})
        _check('清空后可删除平台', not ContactPlatform.objects.filter(pk=platform.pk).exists())

    # 两个分发器互不越界：平台动作打到设置页、设置动作打到联系方式页，都应被拒
    c.post(url, {'action': 'platform_create', 'code': 'shouldnotexist', 'name': '越界平台'})
    _check('平台动作不接受设置页提交',
           not ContactPlatform.objects.filter(code='shouldnotexist').exists())
    c.post(curl, {'action': 'save_setting', 'max_images': '1'})
    _check('设置动作不接受联系方式页提交', FeedbackSetting.get_solo().max_images == 3)


# ───────────────────────── 第十轮 官网页脚「联系我们」─────────────────────────

def round_footer_contacts():
    """官网页脚「联系我们」完全由后台「联系方式」模块驱动（前台不再硬编码账号）

    读的是**官网自身那个接入项目**（settings.WEB_APP_NAME）的数据，所以这里
    先把该项目已有的联系方式备份出来、清空做空态断言，再挂一条测试平台验证展示，
    最后无条件还原（与全局设置的备份/还原同一思路，绝不污染真实配置）。
    """
    print('\n===== 第十轮 官网页脚 · 联系我们 =====')
    from API.website.views import _web_app

    web_app = _web_app()
    backup = [(row.platform_id, row.value, row.sort)
              for row in ProjectContact.objects.filter(app=web_app)]
    stamp = str(int(time.time()) % 100000)
    platform = ContactPlatform.objects.create(
        code=f'fbfoot{stamp}', name=f'页脚平台{stamp}', icon='send', sort=999,
        url_template='https://t.me/{value}')
    _created_platforms.append(platform.pk)

    c = Client()
    try:
        ProjectContact.objects.filter(app=web_app).delete()
        body = c.get('/').content.decode()
        _check('官网没配联系方式时页脚整块隐藏', 'footer-title">联系我们' not in body)

        ProjectContact.objects.create(app=web_app, platform=platform, value=f'foot{stamp}')
        body = c.get('/').content.decode()
        _check('官网配了联系方式后页脚出现', 'footer-title">联系我们' in body)
        _check('页脚展示后台配的平台名', f'页脚平台{stamp}' in body)
        _check('页脚展示后台配的值', f'foot{stamp}' in body)
        _check('配了跳转模板的平台渲染成可点击链接', f'https://t.me/foot{stamp}' in body)
    finally:
        ProjectContact.objects.filter(app=web_app, platform=platform).delete()
        for platform_id, value, sort in backup:
            ProjectContact.objects.create(app=web_app, platform_id=platform_id,
                                          value=value, sort=sort)
    _check('页脚联系方式数据已还原', ProjectContact.objects.filter(app=web_app).count() == len(backup))


# ───────────────────────── 主流程 ─────────────────────────

def _setting_fields():
    """全局设置里需要备份 / 还原的字段（排除主键与自动时间戳）

    按模型字段枚举而不是手写清单：以后新增设置项不必改本脚本，也不会漏还原
    （后台表单会把未勾选的开关一起写成 False，漏还原就会污染真实配置）。
    """
    return [f.name for f in FeedbackSetting._meta.concrete_fields
            if f.name != 'id' and not getattr(f, 'auto_now', False)
            and not getattr(f, 'auto_now_add', False)]


def _backup_setting():
    setting = FeedbackSetting.get_solo()
    for field in _setting_fields():
        _setting_backup[field] = getattr(setting, field)
    return setting


def _restore_setting():
    setting = FeedbackSetting.get_solo()
    for field, value in _setting_backup.items():
        setattr(setting, field, value)
    setting.save()


def _cleanup():
    from django.contrib.auth.models import User as AdminUser
    Feedback.objects.filter(id__in=_created_feedback).delete()
    UserToken.objects.filter(user_id__in=_created_users).delete()
    User.objects.filter(id__in=_created_users).delete()
    for app in _created_apps:
        Feedback.objects.filter(app=app).delete()
        ProjectContact.objects.filter(app=app).delete()
        UserApp.objects.filter(pk=app.pk).delete()
    FeedbackType.objects.filter(pk__in=[t.pk for t in _created_types]).delete()
    ContactPlatform.objects.filter(pk__in=_created_platforms).delete()
    AdminUser.objects.filter(username__in=_created_admins).delete()
    # 未消费的验证码由 create_challenge 的惰性清理负责回收，这里不动
    for path in _created_files:
        try:
            os.remove(path)
        except OSError:
            pass


def run():
    _backup_setting()
    try:
        c = Client()
        app = _create_app()
        user = _create_user()
        token = _issue_token(app, user)
        other_app = _create_app()
        feedback_type = FeedbackType.objects.filter(enabled=True).first()
        if feedback_type is None:
            feedback_type = FeedbackType.objects.create(
                code=f'fbtest{int(time.time()) % 100000}', name='测试类型', enabled=True)
            _created_types.append(feedback_type)

        # 联系方式：给本项目挂一个 QQ（验证展示链路）
        platform = (ContactPlatform.objects.filter(code='qq').first()
                    or ContactPlatform.objects.create(code='qq', name='QQ', sort=0))
        ProjectContact.objects.create(app=app, platform=platform, value='12345678')
        _check('联系方式序列化', serialize_contacts(app)[0]['value'] == '12345678')

        ticket_token = round_api(c, app, token)
        _check('换票返回票据', bool(ticket_token))
        round_pages(app)
        guest_fb = round_guest_submit(app, feedback_type)
        if guest_fb is not None:
            round_ticket(app, user, token, guest_fb)
            mine_fb = (Feedback.objects.filter(app=app, user=user).order_by('-create_time').first()
                       or guest_fb)
            round_public(app, guest_fb, mine_fb)
            round_isolation(app, other_app, guest_fb, token)
            round_ai_status(app, feedback_type)
            round_console(app, feedback_type)
            round_console_settings()
            round_footer_contacts()
        else:
            _check('游客提交成功（后续轮次依赖此条）', False, '未创建反馈，跳过后续轮次')
    finally:
        _cleanup()
        _restore_setting()

    print(f'\n===== 结果: 通过 {_stats["pass"]} / 失败 {_stats["fail"]} =====')
    sys.exit(1 if _stats['fail'] else 0)


if __name__ == '__main__':
    run()
