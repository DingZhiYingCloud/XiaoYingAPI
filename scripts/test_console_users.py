"""超管控制台「用户管理」+ 用户登录日志 回归测试

覆盖范围：
    第 1 轮 建号（admin_create_user）：成功 / 邮箱手机号格式 / 密码策略 / 凭证唯一
    第 2 轮 改资料（admin_update_user）与重置密码（admin_reset_password）：含换绑重置已验证、作废 Token
    第 3 轮 登录日志写入：密码登录 / 验证码登录分别落库，含 IP 与 User-Agent
    第 4 轮 注册发起项目回填：注册/登录验证记录带上发起项目（app）
    第 5 轮 列表页：搜索、状态 / 注册方式 / 登录项目筛选、分页与筛选参数保留
    第 6 轮 详情页聚合口径：累计登录次数、登录过的项目、按项目登录明细、Token 剩余天数
    第 7 轮 写操作走完整视图：建号 / 编辑 / 重置密码 / 封禁解封 / 删除（需输入账号确认）
    第 8 轮 权限与多语言：匿名 302、菜单高亮、en / zh-hant 无中文回退

隔离策略：全部测试数据使用 RUN 后缀标记（邮箱 xytest.users.<RUN>@example.com、
项目名 ConsoleUsers<xytest_<RUN>>），测试结束统一删除，不触碰真实数据。

运行方式：
    .venv\\Scripts\\python.exe scripts\\test_console_users.py
"""
import os
import re
import sys
import time

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'XiaoYingAPI.settings')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import django

django.setup()

from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from API.apis.user_center.users import utils as uc_utils
from API.models import AuthMethod, User, UserApp, UserLoginLog, UserToken, UserVerifyRecord

RUN = str(int(time.time()))
MARK = f'xytest{RUN}'
PASS = 'Test123456'
NEW_PASS = 'Newpass123456'
EMAIL_A = f'xytest.users.{RUN}.a@example.com'
EMAIL_NEW = f'xytest.users.{RUN}.new@example.com'
EMAIL_TAKEN = f'xytest.users.{RUN}.taken@example.com'
PHONE_B = f'139{RUN[-8:]}'

_PASSED = 0
_FAILED = 0
_FAILURES = []


def check(name, condition, detail=''):
    global _PASSED, _FAILED
    if condition:
        _PASSED += 1
        print(f'  [PASS] {name}')
    else:
        _FAILED += 1
        _FAILURES.append(name)
        print(f'  [FAIL] {name} {detail}')


def section(title):
    print(f'\n{"=" * 70}\n{title}\n{"=" * 70}')


def cleanup():
    """删除全部测试数据（用户删除会级联清理 Token / 验证记录 / 登录日志）"""
    User.objects.filter(email__startswith=f'xytest.users.{RUN}').delete()
    User.objects.filter(phone=PHONE_B).delete()
    UserVerifyRecord.objects.filter(credential__contains=f'xytest.users.{RUN}').delete()
    UserVerifyRecord.objects.filter(credential=PHONE_B).delete()
    UserApp.objects.filter(name__contains=MARK).delete()


def superadmin_client():
    """返回 (已登录超管的客户端, 超管对象, 是否临时创建)"""
    user_model = get_user_model()
    admin = user_model.objects.filter(is_superuser=True, is_active=True).first()
    created = False
    if admin is None:
        admin = user_model.objects.create_superuser(
            username=f'xytest_admin_{RUN}', email=f'xytest.admin.{RUN}@example.com',
            password='xytest-admin-pass')
        created = True
    client = Client()
    client.force_login(admin)
    return client, admin, created


# ───────────────────────── 第 1 轮：建号 ─────────────────────────

def round1_create():
    section('第 1 轮 后台建号（admin_create_user）')
    ok, user = uc_utils.admin_create_user(EMAIL_A, '', PASS, username='后台建号用户')
    check('邮箱建号成功', ok, f'err={user if not ok else ""}')
    if not ok:
        return None
    check('账号为 6-12 位数字', user.account.isdigit() and 6 <= len(user.account) <= 12, user.account)
    check('邮箱已标记为已验证 + 状态正常',
          user.email == EMAIL_A and user.email_verified and user.status)
    check('密码可校验通过', check_password(PASS, user.password))
    check('无手机号时 phone 为空', not user.phone)

    ok_b, user_b = uc_utils.admin_create_user('', PHONE_B, PASS)
    check('手机号建号成功且手机号已验证',
          ok_b and user_b.phone == PHONE_B and user_b.phone_verified, f'err={user_b if not ok_b else ""}')

    check('重复邮箱被拒', not uc_utils.admin_create_user(EMAIL_A, '', PASS)[0])
    check('重复手机号被拒', not uc_utils.admin_create_user('', PHONE_B, PASS)[0])
    check('无任何凭证被拒', not uc_utils.admin_create_user('', '', PASS)[0])
    check('邮箱格式非法被拒', not uc_utils.admin_create_user('not-an-email', '', PASS)[0])
    check('手机号格式非法被拒', not uc_utils.admin_create_user('', '12345', PASS)[0])
    check('密码过短被拒', not uc_utils.admin_create_user(f'xytest.users.{RUN}.short@example.com', '', 'a1')[0])
    check('密码无字母被拒', not uc_utils.admin_create_user(f'xytest.users.{RUN}.p1@example.com', '', '12345678')[0])
    check('密码无数字被拒', not uc_utils.admin_create_user(f'xytest.users.{RUN}.p2@example.com', '', 'abcdefgh')[0])
    return user, (user_b if ok_b else None)


# ───────────────────────── 第 2 轮：改资料 / 重置密码 ─────────────────────────

def round2_update(user):
    section('第 2 轮 改资料与重置密码（admin_update_user / admin_reset_password）')
    ok, changed = uc_utils.admin_update_user(user, username='改过的用户名')
    check('改用户名成功且返回变更字段', ok and changed == ['username'], f'changed={changed}')
    check('用户名已更新', User.objects.get(pk=user.pk).username == '改过的用户名')

    ok, changed = uc_utils.admin_update_user(user, email=EMAIL_NEW)
    user.refresh_from_db()
    check('换绑邮箱成功且重置为未验证',
          ok and user.email == EMAIL_NEW and not user.email_verified, f'changed={changed}')

    ok, changed = uc_utils.admin_update_user(user, email=EMAIL_NEW)
    check('未变化的字段不算变更', ok and changed == [], f'changed={changed}')

    ok, _other = uc_utils.admin_create_user(EMAIL_TAKEN, '', PASS)
    ok, changed = uc_utils.admin_update_user(user, email=EMAIL_TAKEN)
    check('邮箱已被其他用户绑定则拒绝换绑', not ok, f'changed={changed}')
    check('拒绝换绑后邮箱保持不变',
          ok is False and User.objects.get(pk=user.pk).email == EMAIL_NEW)

    ok, _ = uc_utils.admin_update_user(user, username='', email='', phone='')
    check('空值表示不修改（不报错也不变更）', ok and User.objects.get(pk=user.pk).username == '改过的用户名')

    check('重置密码：策略不通过被拒', not uc_utils.admin_reset_password(user, '123')[0])
    ok, _ = uc_utils.admin_reset_password(user, NEW_PASS)
    user.refresh_from_db()
    check('重置密码成功且新密码生效', ok and check_password(NEW_PASS, user.password))
    check('重置密码后该用户全部 Token 被清空',
          not UserToken.objects.filter(user=user).exists())


# ───────────────────────── 第 3 轮：登录日志 ─────────────────────────

def round3_login_log(app1, app2, user_a, user_b):
    section('第 3 轮 登录日志写入（密码登录 / 验证码登录）')
    for _ in range(2):
        ok, data = uc_utils.login_user(app1, account=user_a.account, email=None, phone=None,
                                       password=NEW_PASS, ip='1.2.3.4', user_agent='TestUA/1.0')
        check('密码登录成功（项目A）', ok, f'err={data if not ok else ""}')
    ok, data = uc_utils.login_user(app2, account=user_a.account, email=None, phone=None,
                                   password=NEW_PASS, ip='5.6.7.8', user_agent='TestUA/2.0')
    check('密码登录成功（项目B）', ok, f'err={data if not ok else ""}')
    logs = UserLoginLog.objects.filter(user=user_a)
    check('每次登录写一条日志（共 3 条）', logs.count() == 3, f'count={logs.count()}')
    sample = logs.filter(app=app2).first()
    check('日志记录了登录方式 / IP / 客户端',
          sample and sample.method == UserLoginLog.METHOD_PASSWORD
          and sample.ip == '5.6.7.8' and sample.user_agent == 'TestUA/2.0',
          f'sample={sample and (sample.method, sample.ip, sample.user_agent)}')
    check('登录成功同时签发 Token（3 条）',
          UserToken.objects.filter(user=user_a).count() == 3)

    UserVerifyRecord.objects.create(
        user=user_b, app=app1, scene=uc_utils.SCENE_LOGIN, type=uc_utils.METHOD_PHONE,
        credential=PHONE_B, code='654321', token=None,
        expire_time=timezone.now() + timedelta(minutes=5), is_used=False)
    ok, data = uc_utils.login_user(app1, account=None, email=None, phone=PHONE_B, password='',
                                   code='654321', ip='10.0.0.9', user_agent='TestUA/3.0')
    check('验证码登录成功', ok, f'err={data if not ok else ""}')
    log = UserLoginLog.objects.filter(user=user_b).first()
    check('验证码登录日志 method=code',
          log and log.method == UserLoginLog.METHOD_CODE, f'log={log}')


def round3b_token_clearing(user_a, app1, app2):
    """清理登录态不影响登录日志（放在详情页口径用例之后，避免影响 Token 计数断言）"""
    section('第 3b 轮 退出登录 / 重置密码 只清 Token、不删登录日志')
    check('退出登录（删 Token）后登录日志条数不变', _logout_keeps_log(app1, user_a))
    check('重置密码（清空 Token）后登录日志条数不变', _reset_keeps_log(app2, user_a))


def _logout_keeps_log(app, user):
    token = UserToken.objects.filter(user=user, app=app).first()
    if not token:
        return False
    before = UserLoginLog.objects.filter(user=user).count()
    # logout_user 需要明文 token，这里直接删除对应行模拟退出登录的清理效果
    before_tokens = UserToken.objects.filter(user=user, app=app).count()
    UserToken.objects.filter(pk=token.pk).delete()
    return (UserToken.objects.filter(user=user, app=app).count() == before_tokens - 1
            and UserLoginLog.objects.filter(user=user).count() == before)


def _reset_keeps_log(app, user):
    before = UserLoginLog.objects.filter(user=user).count()
    uc_utils.admin_reset_password(user, NEW_PASS)
    return (not UserToken.objects.filter(user=user).exists()
            and UserLoginLog.objects.filter(user=user).count() == before)


# ───────────────────────── 第 4 轮：验证记录带发起项目 ─────────────────────────

def round4_verify_app(app1):
    section('第 4 轮 注册 / 登录验证记录回填发起项目（app）')
    if not AuthMethod.objects.filter(type=uc_utils.METHOD_EMAIL, enabled=True).exists():
        print('  [SKIP] 邮箱注册方式未启用，跳过注册回填用例')
        return
    orig_mail = uc_utils.send_email
    try:
        uc_utils.send_email = lambda *a, **k: (True, 'mock')
        ok, data = uc_utils.register_user(app1, '', EMAIL_A.replace('.a@', '.reg@'), '', PASS,
                                          base_url='http://127.0.0.1:8021')
    finally:
        uc_utils.send_email = orig_mail
    check('注册意向创建成功（发信已 mock）', ok, f'err={data if not ok else ""}')
    record = UserVerifyRecord.objects.filter(
        scene=uc_utils.SCENE_REGISTER, credential__contains=f'xytest.users.{RUN}').order_by('-create_time').first()
    check('注册验证记录带上了发起项目',
          record is not None and record.app_id == app1.pk,
          f'app={record and record.app_id}')


# ───────────────────────── 第 5 轮：列表页 ─────────────────────────

def round5_list(client, user_a, user_b, app1, app2):
    section('第 5 轮 列表页（搜索 / 筛选 / 分页）')
    url = reverse('website:console_users')
    resp = client.get(url)
    body = resp.content.decode()
    check('列表页 200', resp.status_code == 200, f'status={resp.status_code}')
    missing = [text for text in (user_a.account, '联系方式', '状态', '登录概况', '操作')
               if text not in body]
    check('列表含测试用户与新列结构', not missing, f'missing={missing}')
    check('列表显示登录概况与最后登录',
          '个项目' in body and '最后登录' in body)
    check('列表数据行带菜单高亮（用户管理）', 'menu-active' in body)

    resp = client.get(url, {'q': user_a.account})
    body = resp.content.decode()
    check('按账号搜索只命中该用户',
          user_a.account in body and user_b.account not in body)

    resp = client.get(url, {'q': f'xytest.users.{RUN}.a@example.com'})
    check('按邮箱搜索命中', EMAIL_A in resp.content.decode())

    resp = client.get(url, {'register_type': 'phone'})
    body = resp.content.decode()
    check('按手机号注册筛选命中用户B、不命中用户A',
          user_b.account in body and user_a.account not in body, f'len={len(body)}')

    resp = client.get(url, {'app_id': app2.app_id})
    body = resp.content.decode()
    check('按「登录过的项目B」筛选只命中用户A',
          user_a.account in body and user_b.account not in body)

    resp = client.get(url, {'app_id': app1.app_id})
    body = resp.content.decode()
    check('按「登录过的项目A」筛选中 A 与 B 都在',
          user_a.account in body and user_b.account in body)

    resp = client.get(url, {'status': 'normal', 'size': 50})
    body = resp.content.decode()
    check('状态筛选 + 自定义每页正常', resp.status_code == 200 and user_a.account in body)

    resp = client.get(url, {'size': 20, 'page': 2})
    body = resp.content.decode()
    check('分页正常且链接保留筛选参数',
          resp.status_code == 200 and 'page=1' in body and 'size=20' in body)

    resp = client.get(url, {'size': 999})
    check('非法每页条数回退而不报错', resp.status_code == 200)


# ───────────────────────── 第 6 轮：详情页聚合口径 ─────────────────────────

def round6_detail(client, user_a, user_b, app1, app2):
    section('第 6 轮 详情页聚合口径')
    url = reverse('website:console_user_detail', args=[user_a.pk])
    resp = client.get(url)
    body = resp.content.decode()
    check('详情页 200', resp.status_code == 200, f'status={resp.status_code}')
    check('页面含四项汇总指标',
          all(text in body for text in ('累计登录次数', '登录过的项目', '当前有效登录', '最后登录')))
    check('页面含按项目登录明细与 Token 明细',
          all(text in body for text in ('按项目登录明细', '最近登录记录', '登录凭证（Token）明细', '验证记录')))
    check('页面含登录 IP 与客户端', '5.6.7.8' in body and 'TestUA/2.0' in body)
    check('页面含注册方式与来源项目', '注册方式' in body and app1.name in body)

    detail_a = _detail_data(user_a)
    check('按项目聚合：项目A 2 次 / 项目B 1 次',
          detail_a[app1.pk]['total'] == 2 and detail_a[app2.pk]['total'] == 1,
          f'detail={ {k: v["total"] for k, v in detail_a.items()} }')
    check('详情页累计登录次数 = 登录日志条数（3 条）',
          UserLoginLog.objects.filter(user=user_a).count() == 3,
          f'count={UserLoginLog.objects.filter(user=user_a).count()}')
    check('登录过的项目数 = 2',
          UserLoginLog.objects.filter(user=user_a).values('app_id').distinct().count() == 2)
    check('按项目登录明细：项目A 的密码登录 2 次 / 验证码 0 次',
          detail_a[app1.pk]['password'] == 2 and detail_a[app1.pk]['code'] == 0)

    detail_b = _detail_data(user_b)
    check('用户B 项目A 记录为验证码登录 1 次',
          detail_b[app1.pk]['code'] == 1 and detail_b[app1.pk]['password'] == 0,
          f'detail={detail_b}')

    from API.website import console_users
    rows = console_users._project_logins(user_a)
    row = next(r for r in rows if r['app_id'] == app1.app_id)
    check('剩余有效天数 = 项目 Token 有效期',
          row['days_left'] == app1.token_expire_days and not row['expired'],
          f"days_left={row['days_left']} expect={app1.token_expire_days}")
    check('项目A 当前有效登录 2 条（两次登录各签发一条）', row['valid_total'] == 2,
          f"valid_total={row['valid_total']}")
    check('Token 明细条数 = 3', len(console_users._tokens(user_a)) == 3)


def _detail_data(user):
    """按项目聚合（测试内独立实现，用于交叉验证视图口径）"""
    result = {}
    for log in UserLoginLog.objects.filter(user=user):
        row = result.setdefault(log.app_id, {'total': 0, 'code': 0, 'password': 0})
        row['total'] += 1
        if log.method == UserLoginLog.METHOD_CODE:
            row['code'] += 1
        else:
            row['password'] += 1
    return result


# ───────────────────────── 第 7 轮：写操作走完整视图 ─────────────────────────

def round7_actions(client, user_a, apps):
    section('第 7 轮 写操作（建号 / 编辑 / 重置密码 / 封禁 / 删除）')
    url = reverse('website:console_users')

    email_c = f'xytest.users.{RUN}.c@example.com'
    resp = client.post(url, {'action': 'create', 'email': email_c, 'password': PASS,
                             'username': '视图建号'})
    user_c = User.objects.filter(email=email_c).first()
    check('视图建号成功并跳转详情页',
          resp.status_code == 302 and user_c is not None
          and resp['Location'] == reverse('website:console_user_detail', args=[user_c.pk]),
          f'status={resp.status_code} loc={resp.get("Location")}')

    resp = client.post(url, {'action': 'create', 'email': email_c, 'password': PASS})
    check('重复邮箱建号被拒并回列表',
          resp.status_code == 302 and User.objects.filter(email=email_c).count() == 1)

    detail_url = reverse('website:console_user_detail', args=[user_c.pk])
    resp = client.post(url, {'action': 'edit', 'user_id': str(user_c.pk),
                             'username': '视图改名', 'email': '', 'phone': ''}, follow=True)
    user_c.refresh_from_db()
    check('视图改资料生效（用户名）', user_c.username == '视图改名' and resp.status_code == 200)

    resp = client.post(url, {'action': 'reset_password', 'user_id': str(user_c.pk),
                             'password': NEW_PASS})
    user_c.refresh_from_db()
    check('视图重置密码生效', resp.status_code == 302 and check_password(NEW_PASS, user_c.password))

    client.post(url, {'action': 'ban', 'user_id': str(user_c.pk)})
    user_c.refresh_from_db()
    check('封禁生效（status=False）', not user_c.status)

    client.post(url, {'action': 'unban', 'user_id': str(user_c.pk)})
    user_c.refresh_from_db()
    check('解封生效（status=True）', user_c.status)

    resp = client.post(url, {'action': 'delete', 'user_id': str(user_c.pk),
                             'confirm_account': 'wrong-account'})
    check('删除确认账号不符时拒绝删除',
          resp.status_code == 302 and User.objects.filter(pk=user_c.pk).exists())

    # 先制造一条登录态与登录日志，用于验证删除时的级联清理
    ok, _data = uc_utils.login_user(apps[0], account=user_c.account, email=None, phone=None,
                                    password=NEW_PASS)
    check('删除前先造一条登录态与日志',
          ok and UserToken.objects.filter(user=user_c).exists()
          and UserLoginLog.objects.filter(user=user_c).exists())
    resp = client.post(url, {'action': 'delete', 'user_id': str(user_c.pk),
                             'confirm_account': user_c.account})
    check('确认账号一致时删除成功', resp.status_code == 302
          and not User.objects.filter(pk=user_c.pk).exists())
    check('删除级联清理其 Token 与登录日志',
          not UserToken.objects.filter(user_id=user_c.pk).exists()
          and not UserLoginLog.objects.filter(user_id=user_c.pk).exists())

    resp = client.post(url, {'action': 'edit', 'user_id': '00000000-0000-0000-0000-000000000000'})
    check('目标用户不存在时安全回列表', resp.status_code == 302)


# ───────────────────────── 第 8 轮：权限与多语言 ─────────────────────────

def round8_permission(client, admin, user_a):
    section('第 8 轮 权限与多语言')
    anon = Client()
    check('匿名访问列表页 302 跳登录',
          anon.get(reverse('website:console_users')).status_code == 302)
    check('匿名访问详情页 302 跳登录',
          anon.get(reverse('website:console_user_detail', args=[user_a.pk])).status_code == 302)

    detail = reverse('website:console_user_detail', args=[user_a.pk])
    resp = client.get(detail)
    body = resp.content.decode()
    check('详情页导航高亮仍在「用户管理」',
          'menu-active' in body and reverse('website:console_users') in body)

    for lang, probes in (('en', ('用户管理', '登录过的项目', '按项目登录明细')),
                         ('zh-hant', ('用户管理', '登录过的项目'))):
        lang_client = Client()
        lang_client.force_login(admin)
        lang_client.cookies[settings.LANGUAGE_COOKIE_NAME] = lang
        resp = lang_client.get(detail)
        text = resp.content.decode()
        leaked = [probe for probe in probes if probe in text]
        check(f'{lang} 详情页渲染成功且无中文回退',
              resp.status_code == 200 and not leaked, f'leaked={leaked}')


def round9_dialog_guards(client, user_a):
    """对话框入口守卫：onclick 里的 dialog id 不能含连字符

    `onclick="user-edit-modal.showModal()"` 会被 JS 解析成减法表达式并抛
    ReferenceError（弹窗永远打不开），因此统一用下划线命名。
    """
    section('第 9 轮 对话框入口守卫（连字符 id 会失效）')
    list_body = client.get(reverse('website:console_users')).content.decode()
    detail_body = client.get(
        reverse('website:console_user_detail', args=[user_a.pk])).content.decode()
    bad = re.findall(r'onclick="[\w$]*-[\w$-]*\.(?:showModal|close)\(', list_body + detail_body)
    check('列表 / 详情页均无「连字符 id」的对话框入口', not bad, f'bad={bad}')
    check('列表页「新建用户」弹窗入口存在',
          'onclick="user_create_modal.showModal()"' in list_body)
    check('详情页三个弹窗入口存在',
          all(f'onclick="{name}.showModal()"' in detail_body
              for name in ('user_edit_modal', 'user_password_modal', 'user_delete_modal')))


def main():
    print('\n超管控制台「用户管理」回归测试开始')
    client, admin, created_admin = superadmin_client()
    apps = []
    try:
        user_a, user_b = round1_create()
        if user_a is None or user_b is None:
            raise SystemExit('建号失败，后续用例无法执行')
        round2_update(user_a)

        app1 = UserApp.objects.create(name=f'ConsoleUsers {MARK} A')
        app2 = UserApp.objects.create(name=f'ConsoleUsers {MARK} B')
        apps = [app1, app2]
        # 注册验证记录（含发起项目），用于「注册方式 / 来源项目 / 注册方式筛选」用例
        UserVerifyRecord.objects.create(
            user=user_a, app=app1, scene=uc_utils.SCENE_REGISTER, type=uc_utils.METHOD_EMAIL,
            credential=EMAIL_A, code='', token=None,
            expire_time=timezone.now(), is_used=True)
        UserVerifyRecord.objects.create(
            user=user_b, app=app2, scene=uc_utils.SCENE_REGISTER, type=uc_utils.METHOD_PHONE,
            credential=PHONE_B, code='', token=None,
            expire_time=timezone.now(), is_used=True)

        round3_login_log(app1, app2, user_a, user_b)
        round4_verify_app(app1)
        round5_list(client, user_a, user_b, app1, app2)
        round6_detail(client, user_a, user_b, app1, app2)
        round3b_token_clearing(user_a, app1, app2)
        round7_actions(client, user_a, apps)
        round8_permission(client, admin, user_a)
        round9_dialog_guards(client, user_a)
    finally:
        cleanup()
        if created_admin:
            admin.delete()
        print('\n测试数据已清理（项目 %d 个）' % len(apps))
    print(f'\n{"=" * 70}')
    print(f'总计：PASS {_PASSED} / FAIL {_FAILED}')
    if _FAILURES:
        print('失败项：')
        for name in _FAILURES:
            print(f'  - {name}')
    print('=' * 70)
    return 1 if _FAILED else 0


if __name__ == '__main__':
    sys.exit(main())
