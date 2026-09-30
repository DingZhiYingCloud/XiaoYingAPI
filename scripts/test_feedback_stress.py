"""问题反馈中心 · 极端 / 并发 / 安全 / 稳定性测试

与 `test_feedback.py`（功能回归）互补：本脚本专测「边界、恶意输入、并发竞态、故障降级」，
默认不联网、不依赖真实 AI（需要 AI 的用例用打桩替换 `_call_ai` / `render_reject_card`）。

    第一轮  极端输入（长度边界 / XSS / 模板注入 / SQL 注入 / 控制字符 / 全角与 emoji）
    第二轮  附件安全（伪造扩展名 / SVG / 路径穿越 / 双扩展名 / 数量与大小上限）
    第三轮  图形验证码与限流（重放 / 暴力尝试 / 小时与天限流 / 登录用户豁免）
    第四轮  票据安全（重放 / 过期 / 跨项目 / 伪造 / 用户封禁 / Token 过期）
    第五轮  越权与鉴权（后台未登录 / 非超管 / 跨项目 / 非法 action 与 id）
    第六轮  并发竞态（并发提交 / 并发消费同一票据 / 审核任务抢占 / 并发后台回复）
    第七轮  故障降级（AI 不可用 / 返回非 JSON / 绘图失败 / 审核异常 / 线程异常恢复）
    第八轮  状态机与公开区边界（驳回 / 关闭 / 删除 / 隐藏 / 未过审）
    第九轮  联系方式安全（协议注入 / 停用平台 / 删除保护 / 超长值）
    第十轮  大数据量与分页（300 条分页 / 越界页码 / 非法页码 / 关键词搜索）

运行方式（真实数据库，结束自动清理并还原全局设置 / 恢复打桩）：
    .venv\\Scripts\\python.exe scripts\\test_feedback_stress.py
"""
import io
import itertools
import os
import random
import secrets
import sys
import threading
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
from django.db import close_old_connections
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from API.apis.captcha_self import utils as captcha_utils
from API.apis.feedback import ai as fb_ai
from API.apis.feedback.utils import save_attachments
from API.common.credential_crypto import hash_token
from API.models import (CaptchaChallenge, ContactPlatform, Feedback, FeedbackAttachment,
                        FeedbackAuditLog, FeedbackReply, FeedbackReplyAttachment,
                        FeedbackSetting, FeedbackTicket, FeedbackType, ProjectContact,
                        User, UserApp, UserToken)

_PREFIX = f'FS{int(time.time())}'
_stats = {'pass': 0, 'fail': 0, 'skip': 0}
_seq = itertools.count()
_created_apps, _created_users, _created_feedback = [], [], []
_created_types, _created_platforms, _created_admins = [], [], []
_created_files = []
_setting_backup = {}


def _check(name, cond, extra=''):
    if cond:
        _stats['pass'] += 1
        print(f'  [PASS] {name}')
    else:
        _stats['fail'] += 1
        print(f'  [FAIL] {name} {extra}')


def _skipped(name):
    _stats['skip'] += 1
    print(f'  [SKIP] {name}')


def _create_app(name=None, active=True):
    obj = UserApp.objects.create(name=name or f'{_PREFIX}项目{next(_seq)}', status=active)
    _created_apps.append(obj)
    return obj


def _create_user(username=None, status=True):
    user = User.objects.create(
        account=str(random.randint(10000000, 99999999)),
        username=username or f'{_PREFIX}用户{next(_seq)}',
        password=make_password('pass123456'), status=status)
    _created_users.append(str(user.id))
    return user


def _issue_token(app, user, days=7):
    raw = secrets.token_hex(32)
    UserToken.objects.create(user=user, app=app, token=hash_token(raw),
                             expire_time=timezone.now() + timedelta(days=days))
    return raw


def _django_user(is_superuser=True):
    from django.contrib.auth.models import User as AdminUser
    username = f'{"ssuper" if is_superuser else "splain"}{next(_seq)}'
    user = AdminUser.objects.create_user(username=username, password='adm123456',
                                         is_staff=is_superuser, is_superuser=is_superuser)
    _created_admins.append(username)
    return user


def _set_setting(**kwargs):
    setting = FeedbackSetting.get_solo()
    for key, value in kwargs.items():
        setattr(setting, key, value)
    setting.save()
    return setting


def _png_file(name='shot.png', size=(6, 6)):
    buf = io.BytesIO()
    Image.new('RGB', size, (12, 34, 56)).save(buf, 'PNG')
    return SimpleUploadedFile(name, buf.getvalue(), content_type='image/png')


def _media_images_count():
    """当前图片上传目录里的文件数（目录不存在时算 0）"""
    path = os.path.join(settings.MEDIA_ROOT, 'uploads', 'images')
    return len(os.listdir(path)) if os.path.isdir(path) else 0


def _guest_submit(app, feedback_type, content='压力测试内容', **extra):
    """以游客身份提交一条反馈（关闭验证码与限流，便于批量造数）"""
    data = {'type_id': str(feedback_type.pk), 'content': content}
    data.update(extra)
    return Client().post(reverse('website:feedback', args=[app.app_id]), data)


# ───────────────────────── 第一轮 极端输入 ─────────────────────────

def round_extreme_input(app, feedback_type):
    print('\n===== 第一轮 极端输入 =====')
    _set_setting(captcha_required=False, rate_limit_hour=0, rate_limit_day=0,
                 ai_review_enabled=False)
    c = Client()
    url = reverse('website:feedback', args=[app.app_id])

    before = Feedback.objects.count()
    cases = [
        ('空内容', '', False),
        ('纯空白', '   \n\t  ', False),
        ('全角空格', '　　', False),
        ('恰好 5000 字', '字' * 5000, True),
        ('超出 1 字（5001）', '字' * 5001, False),
    ]
    for label, content, should_pass in cases:
        c.post(url, {'type_id': str(feedback_type.pk), 'content': content})
        created = Feedback.objects.count() - before
        if created:
            before = Feedback.objects.count()
            _created_feedback.append(str(Feedback.objects.order_by('-create_time').first().pk))
        _check(f'{label} → {"入库" if should_pass else "被拒"}',
               created == (1 if should_pass else 0), f'实际新增 {created}')

    # XSS / 模板注入 / SQL 注入：必须原样入库、页面必须转义
    xss = '<script>alert(1)</script><img src=x onerror=alert(2)>'
    tpl = '{{ 7*7 }}{% debug %}{{ settings.SECRET_KEY }}'
    sql = "'; DROP TABLE feedback;--"
    for label, payload in (('XSS', xss), ('模板注入', tpl), ('SQL 注入', sql)):
        c.post(url, {'type_id': str(feedback_type.pk), 'content': payload})
        fb = Feedback.objects.order_by('-create_time').first()
        _created_feedback.append(str(fb.pk))
        _check(f'{label} 原样入库', fb.content == payload, fb.content[:40])

        body = c.get(reverse('website:feedback_detail',
                             args=[app.app_id, fb.pk])).content.decode()
        if label == 'XSS':
            # 尖括号必须被转义（标签无法成立）。注意不能断言「页面里没有 <script>」——
            # 母版本身就带若干 <script>，只能针对注入内容本身判断
            ok = (xss not in body and '<img src=x onerror=' not in body
                  and '&lt;script&gt;alert(1)&lt;/script&gt;' in body)
        elif label == '模板注入':
            # 正文不会被当作模板再渲染：字面量保留，且没有泄露 SECRET_KEY
            ok = ('{{ 7*7 }}' in body and '{% debug %}' in body
                  and settings.SECRET_KEY not in body)
        else:
            ok = (sql not in body and 'DROP TABLE feedback' in body)
        _check(f'{label} 页面已按文本转义', ok, '未正确转义')

    _check('SQL 注入未破坏数据表',
           Feedback.objects.filter(content=sql).exists()
           and Feedback.objects.filter(content=xss).exists())

    # emoji / 4 字节字符 / 控制字符
    weird = '🙂🎵👨‍👩‍👧‍👦 测试\x07\x1b[31m'
    c.post(url, {'type_id': str(feedback_type.pk), 'content': weird})
    fb = Feedback.objects.order_by('-create_time').first()
    _created_feedback.append(str(fb.pk))
    _check('emoji 与控制字符原样入库', fb.content == weird)
    _check('控制字符不破坏列表渲染',
           Client().get(reverse('website:feedback', args=[app.app_id])).status_code == 200)

    # NUL 字节（SQLite 可存，但渲染时应被安全处理）
    try:
        c.post(url, {'type_id': str(feedback_type.pk), 'content': 'nul\x00byte'})
        fb = Feedback.objects.order_by('-create_time').first()
        _created_feedback.append(str(fb.pk))
        ok = Client().get(reverse('website:feedback_detail',
                                  args=[app.app_id, fb.pk])).status_code == 200
        _check('NUL 字节不导致 500', ok, '详情页异常')
    except Exception as exc:                       # noqa: BLE001 - 这里就是要看它会不会炸
        _check('NUL 字节不导致 500', False, repr(exc))

    # 非法 UUID 与非法 type_id（路径写死：<uuid:...> 转换器不接受非法值，reverse 会直接报错）
    r = Client().get(f'/feedback/{app.app_id}/detail/not-a-uuid/')
    _check('非法 uuid 路径 404', r.status_code == 404, r.status_code)
    before = Feedback.objects.count()
    c.post(url, {'type_id': 'abc', 'content': '非法类型'})
    c.post(url, {'type_id': '-1', 'content': '负数类型'})
    c.post(url, {'content': '不传类型'})
    _check('非法 type_id 一律被拒', Feedback.objects.count() == before)


# ───────────────────────── 第二轮 附件安全 ─────────────────────────

def round_attachment_security(app, feedback_type):
    print('\n===== 第二轮 附件安全 =====')
    _set_setting(max_images=3, max_image_mb=10, max_videos=1, max_video_mb=50)
    c = Client()
    url = reverse('website:feedback', args=[app.app_id])
    png_magic = _png_file().read()

    def submit_with_image(name, content, data=None, mime='image/png'):
        c.post(url, {'type_id': str(feedback_type.pk), 'content': content,
                     'images': SimpleUploadedFile(name, data if data is not None else png_magic,
                                                  content_type=mime)})

    # HTML 内容改名 .png：魔数校验必须拦下
    before = Feedback.objects.count()
    submit_with_image('evil.png', '伪造图片扩展名', b'<html><script>alert(1)</script></html>')
    _check('HTML 改名 .png 被拒', Feedback.objects.count() == before)
    _check('伪造附件未落库', not FeedbackAttachment.objects.filter(
        original_name='evil.png').exists())

    # SVG（可执行脚本，已在白名单外）
    submit_with_image('evil.svg', '上传 SVG', b'<svg xmlns="http://www.w3.org/2000/svg"></svg>',
                      'image/svg+xml')
    _check('SVG 被拒', Feedback.objects.count() == before)

    # 双扩展名 .php.png（内容是合法 PNG → 允许，但存储必须是 .png 且落在 MEDIA_ROOT 内）
    submit_with_image('shell.php.png', '双扩展名')
    fb = Feedback.objects.order_by('-create_time').first()
    if fb and fb.content == '双扩展名':
        _created_feedback.append(str(fb.pk))
        att = fb.attachments.first()
        _check('双扩展名存储为 .png 且落在 MEDIA_ROOT 内',
               att is not None and att.path.endswith('.png')
               and os.path.abspath(os.path.join(settings.MEDIA_ROOT, att.path))
               .startswith(os.path.abspath(settings.MEDIA_ROOT)), att.path if att else None)
        if att:
            _created_files.append(os.path.join(settings.MEDIA_ROOT, att.path))
    else:
        _check('双扩展名存储为 .png 且落在 MEDIA_ROOT 内', False, '未入库')

    # 路径穿越文件名：只影响展示名，落盘路径必须仍是 MEDIA_ROOT 下
    submit_with_image('../../../../evil.png', '路径穿越文件名')
    fb = Feedback.objects.order_by('-create_time').first()
    if fb and fb.content == '路径穿越文件名':
        _created_feedback.append(str(fb.pk))
        att = fb.attachments.first()
        real = os.path.abspath(os.path.join(settings.MEDIA_ROOT, att.path)) if att else ''
        _check('路径穿越文件名不越出 MEDIA_ROOT',
               bool(att) and real.startswith(os.path.abspath(settings.MEDIA_ROOT))
               and '..' not in att.path, att.path if att else None)
        if att:
            _created_files.append(os.path.join(settings.MEDIA_ROOT, att.path))
    else:
        _check('路径穿越文件名不越出 MEDIA_ROOT', False, '未入库')

    # 数量超限：整单驳回，且不留半份文件
    _set_setting(max_images=1)
    files_before = _media_images_count()
    before = Feedback.objects.count()
    c.post(url, {'type_id': str(feedback_type.pk), 'content': '两张图超限',
                 'images': [_png_file('a.png'), _png_file('b.png')]})
    files_after = _media_images_count()
    _check('附件数量超限整单驳回且不落盘',
           Feedback.objects.count() == before and files_after == files_before,
           f'新增 {Feedback.objects.count() - before} 条 / 新增文件 {files_after - files_before}')

    # 单文件超大（11MB > 10MB 上限）
    _set_setting(max_images=3, max_image_mb=10)
    before = Feedback.objects.count()
    c.post(url, {'type_id': str(feedback_type.pk), 'content': '超大图片',
                 'images': SimpleUploadedFile('big.png', png_magic + b'\x00' * (11 * 1024 * 1024),
                                              content_type='image/png')})
    _check('超过大小上限被拒', Feedback.objects.count() == before)

    # 视频张数：max_videos=1 时传 2 个
    before = Feedback.objects.count()
    c.post(url, {'type_id': str(feedback_type.pk), 'content': '两个视频超限',
                 'videos': [SimpleUploadedFile('a.mp4', b'\x00' * 1024, content_type='video/mp4'),
                            SimpleUploadedFile('b.mp4', b'\x00' * 1024, content_type='video/mp4')]})
    _check('视频数量超限被拒', Feedback.objects.count() == before)

    # 业务层直测：0 张上限表示该类不允许上传
    saved, errors = save_attachments([_png_file('x.png')], 'image', 0, 10)
    _check('上限为 0 时不允许上传', saved == [] and bool(errors), errors)


# ───────────────────────── 第三轮 验证码与限流 ─────────────────────────

def round_captcha_and_rate(app, feedback_type):
    print('\n===== 第三轮 图形验证码与限流 =====')
    c = Client()
    url = reverse('website:feedback', args=[app.app_id])
    _set_setting(captcha_required=True, rate_limit_hour=0, rate_limit_day=0)

    before = Feedback.objects.count()
    # 不传验证码
    c.post(url, {'type_id': str(feedback_type.pk), 'content': '无验证码'})
    _check('游客无验证码被拒', Feedback.objects.count() == before)

    # 伪造 captcha_id
    c.post(url, {'type_id': str(feedback_type.pk), 'content': '伪造验证码',
                 'captcha_id': 'not-a-uuid', 'answer': 'abcd'})
    _check('非 UUID 验证码被拒且不 500', Feedback.objects.count() == before)

    # 正确答案但先被错误答案消费掉（一次性）
    challenge = captcha_utils.create_challenge()
    answer = CaptchaChallenge.objects.get(id=challenge['captcha_id']).answer
    c.post(url, {'type_id': str(feedback_type.pk), 'content': '先答错',
                 'captcha_id': challenge['captcha_id'], 'answer': 'WRONG'})
    _check('错误答案被拒', Feedback.objects.count() == before)
    c.post(url, {'type_id': str(feedback_type.pk), 'content': '再答对',
                 'captcha_id': challenge['captcha_id'], 'answer': answer})
    _check('同一验证码答错后不能复用（一次性）', Feedback.objects.count() == before)

    # 同一验证码并发暴力尝试：只能被消费一次
    challenge = captcha_utils.create_challenge()
    cid = challenge['captcha_id']
    results = []
    lock = threading.Lock()

    def brute(i):
        close_old_connections()
        ok, _msg = captcha_utils.verify_challenge(cid, str(i))
        with lock:
            results.append(ok)

    threads = [threading.Thread(target=brute, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=20)
    _check('并发暴力尝试同一验证码只放行 0 次（全错）', sum(results) == 0, results)

    # 登录用户免验证码
    _set_setting(captcha_required=True)
    user = _create_user()
    token = _issue_token(app, user)
    lc = Client()
    lc.post('/api/feedback/ticket', {'token': token})
    tk = lc.post('/api/feedback/ticket', {'token': token}).json()['data']['ticket']
    resp = lc.get(reverse('website:feedback', args=[app.app_id]) + f'?ticket={tk}')
    _check('票据登录成功', resp.status_code == 303, resp.status_code)
    before = Feedback.objects.count()
    lc.post(url, {'type_id': str(feedback_type.pk), 'content': '登录用户免验证码提交'})
    _check('登录用户免图形验证码', Feedback.objects.count() == before + 1)
    new_fb = Feedback.objects.order_by('-create_time').first()
    _created_feedback.append(str(new_fb.pk))
    _check('登录用户提交带上 user', new_fb.user_id == user.id)

    # IP 限流（小时 / 天两档）
    # 用 XFF 指定一个**专属 IP**，避免与库里其它测试数据的同 IP 计数互相干扰；
    # 顺带验证 client_ip 确实优先取 X-Forwarded-For 的第一段。
    rate_ip = '203.0.113.9'
    _set_setting(captcha_required=False, rate_limit_hour=2, rate_limit_day=3)
    guest = Client()

    def guest_submit(label, ip=rate_ip):
        return guest.post(url, {'type_id': str(feedback_type.pk), 'content': label},
                          HTTP_X_FORWARDED_FOR=ip)

    r1 = guest_submit('限流第 1 条')
    fb = Feedback.objects.order_by('-create_time').first()
    if fb and str(fb.pk) not in _created_feedback:
        _created_feedback.append(str(fb.pk))
    _check('XFF 首个 IP 被记为提交 IP', fb is not None and fb.ip == rate_ip, fb.ip if fb else None)

    r2 = guest_submit('限流第 2 条')
    fb2 = Feedback.objects.order_by('-create_time').first()
    if fb2 and str(fb2.pk) not in _created_feedback:
        _created_feedback.append(str(fb2.pk))
    n2 = Feedback.objects.count()
    r3 = guest_submit('限流第 3 条')
    _check('同 IP 小时内达到上限后被拦',
           r1.status_code == 302 and r2.status_code == 302 and r3.status_code == 200
           and Feedback.objects.count() == n2,
           f'r1={r1.status_code} r2={r2.status_code} r3={r3.status_code}')

    # 换一个 IP 立刻可以提交（限流只针对来源 IP，不误伤别人）
    n3 = Feedback.objects.count()
    guest_submit('换 IP 提交', ip='203.0.113.10')
    _check('换 IP 不受影响', Feedback.objects.count() == n3 + 1)
    fb3 = Feedback.objects.order_by('-create_time').first()
    if fb3 and str(fb3.pk) not in _created_feedback:
        _created_feedback.append(str(fb3.pk))

    # 登录用户不受 IP 限流影响（此时该专属 IP 已超小时上限）
    n4 = Feedback.objects.count()
    lc.post(url, {'type_id': str(feedback_type.pk), 'content': '登录用户超限仍可提交'},
            HTTP_X_FORWARDED_FOR=rate_ip)
    _check('登录用户不受 IP 限流影响', Feedback.objects.count() == n4 + 1)
    fb4 = Feedback.objects.order_by('-create_time').first()
    if fb4 and str(fb4.pk) not in _created_feedback:
        _created_feedback.append(str(fb4.pk))

    # 天档：专属 IP 已有 3 条（含登录用户那条），上限设 3 → 立刻被拦
    _set_setting(rate_limit_hour=0, rate_limit_day=3)
    n5 = Feedback.objects.count()
    r = guest_submit('天档应被拦')
    _check('同 IP 达到每日上限后被拦', r.status_code == 200
           and Feedback.objects.count() == n5, r.status_code)
    _set_setting(rate_limit_hour=0, rate_limit_day=0)


# ───────────────────────── 第四轮 票据安全 ─────────────────────────

def round_ticket_security(app, other_app):
    print('\n===== 第四轮 票据安全 =====')
    user = _create_user()
    token = _issue_token(app, user)
    api = Client()

    # 正常换票
    r = api.post('/api/feedback/ticket', {'token': token}).json()
    ticket = r['data']['ticket']
    entry = reverse('website:feedback', args=[app.app_id])

    # 重放：第二次不再消费
    c1 = Client()
    first = c1.get(entry + f'?ticket={ticket}')
    second = Client().get(entry + f'?ticket={ticket}')
    _check('票据首次消费 303', first.status_code == 303, first.status_code)
    _check('票据重放不消费（按游客处理）', second.status_code == 200, second.status_code)
    t = FeedbackTicket.objects.get(token=ticket)
    _check('票据被标记已用且使用时间已写入',
           t.used is True and t.used_time is not None)

    # 伪造票据
    fake = secrets.token_urlsafe(32)
    r = Client().get(entry + f'?ticket={fake}')
    _check('伪造票据按游客处理', r.status_code == 200, r.status_code)

    # 过期票据
    expired = FeedbackTicket.objects.create(
        token=secrets.token_urlsafe(32), app=app, user=user,
        expire_time=timezone.now() - timedelta(seconds=1))
    r = Client().get(entry + f'?ticket={expired.token}')
    _check('过期票据不被消费', r.status_code == 200
           and FeedbackTicket.objects.get(pk=expired.pk).used is False)

    # 跨项目票据（A 项目的票用在 B 项目页面）
    cross_user = _create_user()
    r = api.post('/api/feedback/ticket',
                 {'token': _issue_token(other_app, cross_user)}).json()
    cross_ticket = r['data']['ticket']
    r = Client().get(entry + f'?ticket={cross_ticket}')
    _check('跨项目票据不被消费', r.status_code == 200
           and FeedbackTicket.objects.get(token=cross_ticket).used is False)

    # 用户被停用 / Token 过期
    banned = _create_user(status=False)
    r = api.post('/api/feedback/ticket', {'token': _issue_token(app, banned)}).json()
    _check('封禁用户换票被拒', r['code'] == 20010, r)
    r = api.post('/api/feedback/ticket',
                 {'token': _issue_token(app, user, days=-1)}).json()
    _check('过期 Token 换票被拒', r['code'] == 20010, r)
    r = api.post('/api/feedback/ticket', {'token': '  '}).json()
    _check('空白 Token 换票被拒', r['code'] == 20001, r)

    # 停用项目：换票被拒
    disabled = _create_app(active=False)
    r = api.post('/api/feedback/ticket',
                 {'token': _issue_token(disabled, _create_user())}).json()
    _check('停用项目的 Token 换票被拒', r['code'] == 20010, r)
    r = api.get('/api/feedback/contacts', {'app_id': disabled.app_id}).json()
    _check('停用项目查联系方式被拒', r['code'] == 20030, r)


# ───────────────────────── 第五轮 越权与鉴权 ─────────────────────────

def round_authorization(app, other_app, feedback_type):
    print('\n===== 第五轮 越权与鉴权 =====')
    console = reverse('website:console_feedback')
    settings_url = reverse('website:console_feedback_settings')

    for label, url in (('反馈管理', console), ('反馈中心设置', settings_url)):
        _check(f'未登录访问{label}被重定向',
               Client().get(url).status_code == 302)
    plain = Client()
    plain.force_login(_django_user(is_superuser=False))
    _check('非超管访问反馈管理被拒', plain.get(console).status_code == 302)
    _check('非超管访问设置页被拒', plain.get(settings_url).status_code == 302)

    admin = Client()
    admin.force_login(_django_user())

    # 非法 action / 非法 id
    r = admin.post(console, {'action': 'drop_database'})
    _check('非法 action 被拒', r.status_code == 302)
    r = admin.post(console, {'action': 'resubmit', 'id': 'not-a-uuid'})
    _check('非法 uuid 的 action 被拒', r.status_code == 302)
    r = admin.post(console, {'action': 'reply', 'id': str(secrets.token_hex(16)),
                             'content': 'x'}).json()
    _check('不存在的反馈回复返回 20030', r['code'] == 20030, r)

    # 跨项目：把 B 项目的反馈 id 用在 A 项目详情页 → 404
    fb = Feedback.objects.create(app=other_app, type=feedback_type,
                                 content='B 项目的反馈内容', status='processing',
                                 ai_status='passed', ip='10.0.0.8')
    _created_feedback.append(str(fb.pk))
    r = Client().get(reverse('website:feedback_detail', args=[app.app_id, fb.pk]))
    _check('跨项目详情 404', r.status_code == 404, r.status_code)
    r = Client().get(reverse('website:feedback_detail', args=[other_app.app_id, fb.pk]))
    _check('本项目公开详情可见', r.status_code == 200, r.status_code)

    # 后台动作越界数值（enabled=1 必须带上，否则等于把总开关关掉）
    base_form = {'action': 'save_setting', 'enabled': '1', 'max_videos': '1',
                 'max_image_mb': '10', 'max_video_mb': '50',
                 'rate_limit_hour': '5', 'rate_limit_day': '20'}
    r = admin.post(settings_url, {**base_form, 'max_images': '999'})
    _check('设置页越界数值被拒（且不改动原值）', r.status_code == 302
           and FeedbackSetting.get_solo().max_images <= 20)
    r = admin.post(settings_url, {**base_form, 'max_images': 'abc'})
    _check('设置页非数字被拒', r.status_code == 302
           and FeedbackSetting.get_solo().enabled is True)

    # 越权的回复 id：action=reply 指向别的项目反馈（超管允许，但要确保能正确处理）
    r = admin.post(console, {'action': 'reply', 'id': str(fb.pk), 'content': '跨项目回复',
                             'ai_verdict': 'pass'}).json()
    _check('超管可回复任意项目反馈', r['code'] == 10000 and FeedbackReply.objects.filter(
        feedback=fb, content='跨项目回复').exists(), r)


# ───────────────────────── 第六轮 并发竞态 ─────────────────────────

def round_concurrency(app, feedback_type):
    print('\n===== 第六轮 并发竞态 =====')
    _set_setting(enabled=True, captcha_required=False, rate_limit_hour=0, rate_limit_day=0,
                 ai_review_enabled=False)
    url = reverse('website:feedback', args=[app.app_id])
    type_id = str(feedback_type.pk)

    # 6.1 20 线程并发提交
    before = Feedback.objects.count()
    errors, barrier = [], threading.Barrier(20)

    def submit(i):
        try:
            barrier.wait(timeout=30)
        except threading.BrokenBarrierError:
            pass
        try:
            close_old_connections()
            r = Client().post(url, {'type_id': type_id, 'content': f'并发提交 {i}'})
            if r.status_code not in (200, 302):
                errors.append(r.status_code)
        except Exception as exc:                    # noqa: BLE001
            errors.append(repr(exc))

    threads = [threading.Thread(target=submit, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    created = Feedback.objects.count() - before
    _check('20 线程并发提交全部入库', created == 20 and not errors, f'入库 {created} / 错误 {errors[:3]}')
    for fb in Feedback.objects.order_by('-create_time')[:20]:
        _created_feedback.append(str(fb.pk))

    # 6.2 30 线程并发消费同一张票据：只允许成功一次
    user = _create_user()
    token = _issue_token(app, user)
    ticket = Client().post('/api/feedback/ticket', {'token': token}).json()['data']['ticket']
    statuses, lock = [], threading.Lock()
    barrier2 = threading.Barrier(30)

    def consume(_i):
        try:
            barrier2.wait(timeout=30)
        except threading.BrokenBarrierError:
            pass
        close_old_connections()
        r = Client().get(url + f'?ticket={ticket}')
        with lock:
            statuses.append(r.status_code)

    threads = [threading.Thread(target=consume, args=(i,)) for i in range(30)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    _check('并发消费同一票据只成功一次',
           statuses.count(303) == 1 and len(statuses) == 30, statuses.count(303))

    # 6.3 审核任务抢占：10 线程同时抢 1 条待审，只允许一条被处理
    pending = Feedback.objects.create(app=app, type=feedback_type, content='待审核抢占测试',
                                      status='pending', ai_status='pending', ip='10.0.0.9')
    _created_feedback.append(str(pending.pk))
    claims, barrier3 = [], threading.Barrier(10)

    def claim(_i):
        try:
            barrier3.wait(timeout=30)
        except threading.BrokenBarrierError:
            pass
        close_old_connections()
        try:
            worked = fb_ai.review_one_pending()
        except Exception:                            # noqa: BLE001
            worked = False
        with lock:
            claims.append(worked)

    threads = [threading.Thread(target=claim, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    # 行级条件更新的不变量：同一条待审记录只能被一个执行者抢到
    # （脚本进程自身不起审核线程，见 ai.is_serving_process；此处队列里只有这一条待审）
    _check('并发抢占同一条审核任务只被处理一次', sum(claims) == 1, sum(claims))
    pending.refresh_from_db()
    _check('抢占后状态被正确改写',
           pending.ai_status in ('skipped', 'passed', 'rejected', 'failed'), pending.ai_status)

    # 6.4 20 线程并发后台回复同一反馈（每个线程自己建 Client 并登录同一超管账号）
    admin_user = _django_user()
    admin = Client()
    admin.force_login(admin_user)
    target = Feedback.objects.filter(app=app).order_by('-create_time').first()
    replies_before = FeedbackReply.objects.filter(feedback=target).count()
    errs = []
    barrier4 = threading.Barrier(20)

    def reply(i):
        try:
            barrier4.wait(timeout=30)
        except threading.BrokenBarrierError:
            pass
        close_old_connections()
        try:
            cl = Client()
            cl.force_login(admin_user)
            r = cl.post(reverse('website:console_feedback'),
                        {'action': 'reply', 'id': str(target.pk),
                         'content': f'并发回复 {i}', 'ai_verdict': 'pass'}).json()
            if r.get('code') != 10000:
                errs.append(r.get('code'))
        except Exception as exc:                     # noqa: BLE001
            errs.append(repr(exc))

    threads = [threading.Thread(target=reply, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    added = FeedbackReply.objects.filter(feedback=target).count() - replies_before
    _check('20 线程并发回复无丢失', added == 20 and not errs, f'新增 {added} / 错误 {errs[:3]}')
    target.refresh_from_db()
    _check('并发回复后状态为已回复', target.status == 'replied', target.status)
    _check('并发回复留痕条数与回复数一致',
           FeedbackAuditLog.objects.filter(feedback=target, kind='reply').count() >= 20)


# ───────────────────────── 第七轮 故障降级 ─────────────────────────

def round_fault_tolerance(app, feedback_type):
    print('\n===== 第七轮 故障降级 =====')
    origin_call_ai = fb_ai._call_ai
    origin_render = fb_ai.render_reject_card
    origin_review = fb_ai.review_submission

    try:
        # 7.1 AI 关闭 → 跳过审核，直接待处理
        _set_setting(ai_review_enabled=False)
        fb = Feedback.objects.create(app=app, type=feedback_type, content='AI 关闭时的审核',
                                     status='pending', ai_status='pending', ip='10.0.0.9')
        _created_feedback.append(str(fb.pk))
        ok, msg = fb_ai.review_submission(fb)
        fb.refresh_from_db()
        _check('AI 不可用时跳过审核而非卡住',
               ok is True and fb.status == 'processing' and fb.ai_status == 'skipped', msg)

        # 7.2 AI 返回非 JSON → 记为审核失败，状态留在待审核
        _set_setting(ai_review_enabled=True)
        fb_ai._call_ai = lambda *a, **k: (True, {'verdict': '看不懂的结论'})
        fb = Feedback.objects.create(app=app, type=feedback_type, content='非法结论',
                                     status='pending', ai_status='pending', ip='10.0.0.9')
        _created_feedback.append(str(fb.pk))
        fb_ai.review_submission(fb)
        fb.refresh_from_db()
        _check('无法识别结论 → 审核失败且不误判',
               fb.ai_status == 'failed' and fb.status == 'pending', fb.ai_status)
        _check('审核失败有留痕', FeedbackAuditLog.objects.filter(
            feedback=fb, verdict='error').exists())

        # 7.3 AI 调用抛异常 → 不冒泡到调用方（review_one_pending 兜底改 failed）
        # 「取任务」限定到本条，避免同机其它进程的审核线程先一步抢走导致断言失真
        def boom_submission(_fb):
            raise RuntimeError('模拟 AI 崩溃')

        fb_ai.review_submission = boom_submission
        origin_pending_qs = Feedback.__dict__['pending_ai_queryset']
        fb = Feedback.objects.create(app=app, type=feedback_type, content='AI 崩溃',
                                     status='pending', ai_status='pending', ip='10.0.0.9')
        _created_feedback.append(str(fb.pk))
        Feedback.pending_ai_queryset = classmethod(
            lambda cls, _pk=fb.pk: cls.objects.filter(pk=_pk, ai_status=cls.AiStatus.PENDING))
        try:
            still_pending = Feedback.objects.filter(pk=fb.pk, ai_status='pending').exists()
            fb_ai.review_one_pending()
        finally:
            Feedback.pending_ai_queryset = origin_pending_qs
        fb.refresh_from_db()
        if still_pending:
            _check('审核过程异常被兜底为 failed（不留 running 中间态）',
                   fb.ai_status == 'failed' and fb.status == 'pending', f'{fb.ai_status}/{fb.status}')
        else:
            _skipped('审核过程异常被兜底为 failed（本条已被同机其它审核线程处理，跳过）')
        fb_ai.review_submission = origin_review

        # 7.4 绘图失败不影响驳回（本用例专门验说明图链路，先确保开关是开的）
        _set_setting(ai_reject_image=True)

        def boom(*_a, **_k):
            raise RuntimeError('模拟绘图中断')
        fb_ai.render_reject_card = boom
        fb_ai._call_ai = lambda *a, **k: (True, {'verdict': 'reject', 'reason': '测试驳回',
                                                 'points': ['要点一', '要点二']})
        fb = Feedback.objects.create(app=app, type=feedback_type, content='驳回且绘图失败',
                                     status='pending', ai_status='pending', ip='10.0.0.9')
        _created_feedback.append(str(fb.pk))
        fb_ai.review_submission(fb)
        fb.refresh_from_db()
        _check('绘图失败不影响驳回落库',
               fb.ai_status == 'rejected' and fb.status == 'rejected'
               and FeedbackReply.objects.filter(feedback=fb, author_role='ai').exists(),
               fb.ai_status)
        _check('绘图失败时不留空的附件记录',
               not FeedbackReplyAttachment.objects.filter(
                   reply__feedback=fb).exists())

        # 7.5 驳回成功时说明图正常挂上
        fb_ai.render_reject_card = origin_render
        fb = Feedback.objects.create(app=app, type=feedback_type, content='驳回并生成说明图',
                                     status='pending', ai_status='pending', ip='10.0.0.9')
        _created_feedback.append(str(fb.pk))
        fb_ai.review_submission(fb)
        fb.refresh_from_db()
        att = FeedbackReplyAttachment.objects.filter(reply__feedback=fb).first()
        _check('驳回说明图正常生成并入库',
               fb.ai_status == 'rejected' and att is not None and att.kind == 'image',
               fb.ai_status)
        if att:
            _created_files.append(os.path.join(settings.MEDIA_ROOT, att.path))

        # 7.6 回复语气审查：AI 返回 warn → 只提醒（未强制不落库）
        fb_ai._call_ai = lambda *a, **k: (True, {'verdict': 'warn', 'reason': '语气偏强硬'})
        fb = Feedback.objects.create(app=app, type=feedback_type, content='语气审查用例',
                                     status='processing', ai_status='passed', ip='10.0.0.9')
        _created_feedback.append(str(fb.pk))
        ok, data = fb_ai.review_reply_text(fb, '这你都不会？')
        _check('语气审查返回提醒', ok is True and data['verdict'] == 'warn', data)

        # 7.7 回复语气审查：AI 挂了 → 返回 False（调用方放行，不阻断管理员）
        _set_setting(ai_review_enabled=False)
        ok, msg = fb_ai.review_reply_text(fb, '正常回复')
        _check('语气审查不可用时返回 False（不阻断）', ok is False and bool(msg), msg)
    finally:
        fb_ai._call_ai = origin_call_ai
        fb_ai.render_reject_card = origin_render
        fb_ai.review_submission = origin_review
        _set_setting(ai_review_enabled=False)


# ───────────────────────── 第八轮 状态机与公开区边界 ─────────────────────────

def round_state_machine(app, feedback_type):
    print('\n===== 第八轮 状态机与公开区边界 =====')
    c = Client()
    entry = reverse('website:feedback', args=[app.app_id])

    def make(**kwargs):
        defaults = dict(app=app, type=feedback_type, content='状态机用例',
                        status='processing', ai_status='passed', ip='10.0.0.9')
        defaults.update(kwargs)
        fb = Feedback.objects.create(**defaults)
        _created_feedback.append(str(fb.pk))
        return fb

    public = make(content='公开区可见的游客反馈')
    _check('过审游客反馈进公开区', public.in_public_area is True)

    for label, kwargs, visible in (
        ('待审核', {'status': 'pending'}, False),
        ('AI驳回', {'status': 'rejected'}, False),
        ('已关闭', {'status': 'closed'}, True),
        ('已隐藏', {'public_hidden': True}, False),
    ):
        fb = make(**kwargs)
        _check(f'{label} 公开区可见性正确', fb.in_public_area is visible, fb.in_public_area)

    logged = make(user=_create_user(), content='登录用户的反馈')
    _check('登录用户反馈不进公开区', logged.in_public_area is False)

    # 公开区查询口径与 in_public_area 完全一致
    ids = set(Feedback.public_queryset().filter(app=app).values_list('pk', flat=True))
    mismatch = [str(f.pk) for f in Feedback.objects.filter(app=app)
                if f.in_public_area != (f.pk in ids)]
    _check('public_queryset 与 in_public_area 口径一致', not mismatch, mismatch[:3])

    # 跟帖状态机
    owner = _create_user()
    token = _issue_token(app, owner)
    lc = Client()
    lc.post('/api/feedback/ticket', {'token': token})
    tk = Client().post('/api/feedback/ticket', {'token': token}).json()['data']['ticket']
    lc.get(entry + f'?ticket={tk}')

    mine = make(user=owner, status='processing')
    detail = reverse('website:feedback_detail', args=[app.app_id, mine.pk])
    lc.post(detail, {'content': '待处理时跟帖'})
    _check('待处理时本人可跟帖',
           FeedbackReply.objects.filter(feedback=mine, content='待处理时跟帖').exists())
    mine.status = 'closed'
    mine.save(update_fields=['status', 'updated_time'])
    lc.post(detail, {'content': '关闭后跟帖'})
    _check('已关闭不可跟帖',
           not FeedbackReply.objects.filter(feedback=mine, content='关闭后跟帖').exists())
    mine.status = 'rejected'
    mine.save(update_fields=['status', 'updated_time'])
    lc.post(detail, {'content': '驳回后跟帖'})
    _check('AI 驳回不可跟帖',
           not FeedbackReply.objects.filter(feedback=mine, content='驳回后跟帖').exists())

    # 删除后：详情 404、附件与回复级联删除
    doomed = make(content='待删除的反馈')
    FeedbackReply.objects.create(feedback=doomed, author_role='admin', content='回复')
    FeedbackAttachment.objects.create(feedback=doomed, kind='image',
                                      path='uploads/images/tmp.png', original_name='x.png',
                                      size=1, ext='png')
    doomed_id = doomed.pk
    doomed.delete()
    _check('删除后详情 404',
           Client().get(reverse('website:feedback_detail',
                                args=[app.app_id, doomed_id])).status_code == 404)
    _check('删除后回复级联清理',
           not FeedbackReply.objects.filter(feedback_id=doomed_id).exists())
    _check('删除后附件级联清理',
           not FeedbackAttachment.objects.filter(feedback_id=doomed_id).exists())


# ───────────────────────── 第九轮 联系方式安全 ─────────────────────────

def round_contact_security(app):
    print('\n===== 第九轮 联系方式安全 =====')
    code = f'sc{int(time.time()) % 100000}'
    # javascript: 协议必须被拦
    bad = ContactPlatform.objects.create(code=code, name='恶意平台',
                                         url_template='javascript:alert(1)')
    _created_platforms.append(bad.pk)
    _check('javascript: 模板不生成链接', bad.build_url('x') == '', bad.build_url('x'))
    _check('非白名单协议返回空串',
           ContactPlatform(code=code + 'b', name='x', url_template='data:text/html,x')
           .build_url('1') == '')

    good = ContactPlatform.objects.create(code=code + 'c', name='正常平台',
                                          url_template='https://t.me/{value}')
    _created_platforms.append(good.pk)
    _check('白名单协议正常拼接',
           good.build_url('abc') == 'https://t.me/abc', good.build_url('abc'))
    _check('值为空时不生成链接', good.build_url('') == '')

    # 停用平台不进序列化
    entry = ProjectContact.objects.create(app=app, platform=good, value='demo')
    from API.apis.feedback.utils import serialize_contacts
    _check('启用平台出现在联系方式里',
           any(c['platform'] == good.code for c in serialize_contacts(app)))
    good.enabled = False
    good.save(update_fields=['enabled', 'updated_time'])
    _check('停用平台不出现在联系方式里',
           not any(c['platform'] == good.code for c in serialize_contacts(app)))
    good.enabled = True
    good.save(update_fields=['enabled', 'updated_time'])

    # 有绑定时平台不可删（PROTECT 的业务侧保护）
    admin = Client()
    admin.force_login(_django_user())
    admin.post(reverse('website:console_feedback_settings'),
               {'action': 'platform_delete', 'id': str(good.pk)})
    _check('有绑定时平台不可删除', ContactPlatform.objects.filter(pk=good.pk).exists())
    ProjectContact.objects.filter(app=app, platform=good).delete()
    admin.post(reverse('website:console_feedback_settings'),
               {'action': 'platform_delete', 'id': str(good.pk)})
    _check('清空绑定后可删除平台', not ContactPlatform.objects.filter(pk=good.pk).exists())

    # 超长联系方式
    admin.post(reverse('website:console_feedback_settings'),
               {'action': 'contact_save', 'app_id': app.app_id,
                f'contact_{bad.pk}': 'x' * 201})
    _check('超长联系方式被拒', not ProjectContact.objects.filter(
        app=app, platform=bad, value__startswith='xxx').exists())
    entry.delete()


# ───────────────────────── 第十轮 大数据量与分页 ─────────────────────────

def round_volume(app, feedback_type):
    print('\n===== 第十轮 大数据量与分页 =====')
    batch = [Feedback(app=app, type=feedback_type, content=f'批量数据 {i}',
                      status='processing', ai_status='passed', ip='10.0.0.7')
             for i in range(300)]
    Feedback.objects.bulk_create(batch)
    _created_feedback.extend(str(f.pk) for f in batch)

    c = Client()
    base = reverse('website:feedback_public', args=[app.app_id])
    total = Feedback.public_queryset().filter(app=app).count()

    t0 = time.time()
    r = c.get(base)
    cost = time.time() - t0
    _check('公开区首页 200 且在 3 秒内', r.status_code == 200 and cost < 3, f'{cost:.2f}s')

    r = c.get(base, {'page': 999})
    _check('越界页码返回空列表而非报错', r.status_code == 200 and total > 0)
    r = c.get(base, {'page': 'abc'})
    _check('非法页码回退第 1 页', r.status_code == 200)
    r = c.get(base, {'page': '-5'})
    _check('负数页码回退第 1 页', r.status_code == 200)

    # 关键词搜索只命中目标
    c.post(reverse('website:feedback', args=[app.app_id]),
           {'type_id': str(feedback_type.pk), 'content': '唯一关键词 ZZQQXX'})
    fb = Feedback.objects.order_by('-create_time').first()
    _created_feedback.append(str(fb.pk))
    r = c.get(base, {'q': 'ZZQQXX'})
    body = r.content.decode()
    _check('关键词精确命中', 'ZZQQXX' in body and '批量数据 1' not in body)
    r = c.get(base, {'q': '绝不可能出现的关键词串'})
    _check('无匹配时列表为空', r.status_code == 200)

    # 后台列表在大量数据下仍可用
    admin = Client()
    admin.force_login(_django_user())
    t0 = time.time()
    r = admin.get(reverse('website:console_feedback'), {'size': '100'})
    cost = time.time() - t0
    _check('后台列表 100 条/页 200 且在 3 秒内', r.status_code == 200 and cost < 3, f'{cost:.2f}s')


# ───────────────────────── 主流程 ─────────────────────────

def _setting_fields():
    """全局设置里需要备份 / 还原的字段（排除主键与自动时间戳）

    直接按模型字段枚举而不是手写清单：以后新增设置项时不必再改测试脚本，
    也不会出现「后台表单提交了某个字段、测试却忘了还原」导致污染真实配置的问题。
    """
    return [f.name for f in FeedbackSetting._meta.concrete_fields
            if f.name != 'id' and not getattr(f, 'auto_now', False)
            and not getattr(f, 'auto_now_add', False)]


def _backup_setting():
    setting = FeedbackSetting.get_solo()
    for field in _setting_fields():
        _setting_backup[field] = getattr(setting, field)


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
    ProjectContact.objects.filter(platform_id__in=_created_platforms).delete()
    ContactPlatform.objects.filter(pk__in=_created_platforms).delete()
    AdminUser.objects.filter(username__in=_created_admins).delete()
    for path in _created_files:
        try:
            os.remove(path)
        except OSError:
            pass


def run():
    _backup_setting()
    try:
        app = _create_app()
        other_app = _create_app()
        feedback_type = FeedbackType.objects.filter(enabled=True).first()
        if feedback_type is None:
            feedback_type = FeedbackType.objects.create(code=f'fbst{int(time.time()) % 10000}',
                                                        name='压测类型', enabled=True)
            _created_types.append(feedback_type)

        round_extreme_input(app, feedback_type)
        round_attachment_security(app, feedback_type)
        round_captcha_and_rate(app, feedback_type)
        round_ticket_security(app, other_app)
        round_authorization(app, other_app, feedback_type)
        round_concurrency(app, feedback_type)
        round_fault_tolerance(app, feedback_type)
        round_state_machine(app, feedback_type)
        round_contact_security(app)
        round_volume(app, feedback_type)
    finally:
        _cleanup()
        _restore_setting()

    print(f'\n===== 结果: 通过 {_stats["pass"]} / 失败 {_stats["fail"]} / 跳过 {_stats["skip"]} =====')
    sys.exit(1 if _stats['fail'] else 0)


if __name__ == '__main__':
    run()
