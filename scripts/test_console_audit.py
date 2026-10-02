"""控制台操作日志（审计留痕）回归测试

覆盖范围：
    第 1 轮 写操作留痕：POST 保存安全设置后新增一行，且字段齐全（谁 / 何时 / 功能 / 动作 / 说明 / 结果 / 来源）
    第 2 轮 读操作不记：GET 列表页与设置页都不产生新记录
    第 3 轮 失败也留痕、说明为空：POST 一个不存在的 action（视图 messages.error + 302）
    第 4 轮 非超管不留痕：匿名 POST 被拦（404 隐身 / 302 跳登录）且不产生记录
    第 5 轮 列表页：展示 / 三种筛选 / 菜单高亮 / 三语渲染无中文回退
    第 6 轮 动作码翻成人话：prompt_delete → 删除提示词（原始码留在悬停提示）、
             未知码原样显示、按中文说法可搜到、英文页显示英文动作名

隔离策略：审计表是只追加的事实表，故**记录测试前的最大 id**，结束时删掉之后新增的全部行；
期间被改动的安全开关按快照还原。

运行方式：
    .venv\\Scripts\\python.exe scripts\\test_console_audit.py
"""
import os
import re
import sys
import time

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'XiaoYingAPI.settings')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import django

django.setup()

from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from API.models import ConsoleAuditLog, SecuritySetting

RUN = str(int(time.time()))
URL = reverse('website:console_audit')
SECURITY_URL = reverse('website:console_security')
QUOTA_URL = reverse('website:console_quotas')

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


def latest():
    """最后一条留痕（测试期间只有本脚本在写）"""
    return ConsoleAuditLog.objects.order_by('-id').first()


def _menu_active(html, url):
    """侧边栏里指向 url 的那个菜单项是否带高亮类（属性顺序不作假设）"""
    pattern = (r'<a[^>]+href="%s"[^>]*menu-active|<a[^>]+menu-active[^>]*href="%s"'
               % (re.escape(url), re.escape(url)))
    return bool(re.search(pattern, html))


def superadmin_client():
    """返回 (已登录超管的客户端, 超管对象, 是否临时创建)"""
    user_model = get_user_model()
    admin = user_model.objects.filter(is_superuser=True, is_active=True).first()
    created = False
    if admin is None:
        admin = user_model.objects.create_superuser(
            username=f'xytest_audit_{RUN}', email=f'xytest.audit.{RUN}@example.com',
            password='xytest-admin-pass')
        created = True
    client = Client()
    client.force_login(admin)
    return client, admin, created


# ───────────────────────── 第 1 轮：写操作留痕 ─────────────────────────

def round1_write(client, admin):
    section('第 1 轮 写操作留痕（保存安全设置）')
    before = ConsoleAuditLog.objects.count()
    # 按当前值原样提交：验证留痕的同时不改动真实配置
    payload = {'hide_console': 'on'} if SecuritySetting.get_solo().hide_console else {}

    resp = client.post(SECURITY_URL, payload, HTTP_USER_AGENT='xytest-audit-agent',
                       HTTP_X_FORWARDED_FOR='203.0.113.9, 10.0.0.1')

    check('保存返回 302', resp.status_code == 302, f'status={resp.status_code}')
    check('新增 1 条留痕', ConsoleAuditLog.objects.count() == before + 1)

    log = latest()
    check('操作者为当前超管', log.operator == admin.username, f'operator={log.operator}')
    check('功能为 console_security', log.view_name == 'console_security', log.view_name)
    check('路径与请求方法正确',
          log.path == SECURITY_URL and log.method == 'POST', f'{log.method} {log.path}')
    check('动作取自表单 action 字段（本页无 action，记为空）', log.action == '', repr(log.action))
    check('说明为操作者看到的那句成功提示', log.note == '安全设置已保存', repr(log.note))
    check('响应状态码已记录', log.status_code == 302, f'code={log.status_code}')
    check('来源 IP 取 X-Forwarded-For 首段', log.ip == '203.0.113.9', f'ip={log.ip}')
    check('User-Agent 已记录', log.user_agent == 'xytest-audit-agent', log.user_agent)
    check('操作者主键已记录', log.operator_id == admin.pk, f'operator_id={log.operator_id}')


# ───────────────────────── 第 2 轮：读操作不记 ─────────────────────────

def round2_read(client):
    section('第 2 轮 读操作不记')
    before = ConsoleAuditLog.objects.count()
    client.get(URL)
    client.get(SECURITY_URL)
    client.get(QUOTA_URL)
    check('三次 GET 后仍无新记录', ConsoleAuditLog.objects.count() == before,
          f'before={before} after={ConsoleAuditLog.objects.count()}')


# ───────────────────────── 第 3 轮：失败也留痕 ─────────────────────────

def round3_failed_write(client):
    section('第 3 轮 失败的操作也留痕（说明为空）')
    before = ConsoleAuditLog.objects.count()
    # 余量页对未知 action 的处理是 messages.error + 302，属于「被拒绝的写操作」
    resp = client.post(QUOTA_URL, {'action': 'xytest_no_such_action'})
    check('未知动作返回 302', resp.status_code == 302, f'status={resp.status_code}')
    check('被拒绝的写操作仍留痕（新增 1 条）', ConsoleAuditLog.objects.count() == before + 1)

    log = latest()
    check('动作已记录', log.action == 'xytest_no_such_action', log.action)
    check('失败时说明为空（没有成功提示）', log.note == '', repr(log.note))
    check('功能为 console_quotas', log.view_name == 'console_quotas', log.view_name)


# ───────────────────────── 第 4 轮：非超管不留痕 ─────────────────────────

def round4_anonymous():
    section('第 4 轮 非超管不留痕')
    before = ConsoleAuditLog.objects.count()
    anon = Client()
    resp = anon.post(SECURITY_URL, {})
    expected = 404 if SecuritySetting.get_solo().hide_console else 302
    check('匿名 POST 被拦截（404 隐身 / 302 跳登录）',
          resp.status_code == expected, f'status={resp.status_code} expect={expected}')
    check('被拦的请求不产生留痕', ConsoleAuditLog.objects.count() == before)


# ───────────────────────── 第 5 轮：列表页 ─────────────────────────

def round5_list(client, admin):
    section('第 5 轮 列表页（展示 / 筛选 / 菜单高亮 / 三语）')
    resp = client.get(URL)
    check('页面 200', resp.status_code == 200, f'status={resp.status_code}')
    html = resp.content.decode('utf-8')
    check('页面含刚写入的说明与操作者',
          '安全设置已保存' in html and admin.username in html)
    check('菜单含本页入口且已高亮', _menu_active(html, URL))

    resp = client.get(URL, {'operator': admin.username, 'view': 'console_security'})
    check('按操作者 + 功能筛选可命中',
          resp.status_code == 200 and '安全设置已保存' in resp.content.decode('utf-8'))
    resp = client.get(URL, {'view': 'console_security', 'q': '不存在的关键词xyz'})
    check('关键词无命中时给出空态',
          '暂无记录' in resp.content.decode('utf-8'))
    check('筛选条件下拉含出现过的取值（功能用菜单中文名）',
          '安全设置' in client.get(URL).content.decode('utf-8'))

    html = client.get(URL, HTTP_ACCEPT_LANGUAGE='en').content.decode('utf-8')
    check('英文页已翻译（无中文回退 / 无模板标记泄漏）',
          'Audit Log' in html and 'Operator' in html and '暂无记录' not in html
          and '{%' not in html and '{{' not in html)
    html = client.get(URL, HTTP_ACCEPT_LANGUAGE='zh-hant').content.decode('utf-8')
    check('繁体页已翻译（无简体回退）', '操作日誌' in html and '操作者' in html)


# ───────────────── 第 6 轮：动作码翻成人话 ─────────────────

def round6_action_labels(client):
    section('第 6 轮 动作码翻成人话（prompt_delete → 删除提示词）')
    # 造一条带已知动作码的留痕（第 3 轮那条是未知码，用于验证「兜底原样显示」）
    log = ConsoleAuditLog.objects.create(
        operator='xytest-audit', method='POST', path='/console/ai/', view_name='console_ai',
        action='prompt_delete', target='', note='提示词「测试」已删除', status_code=302,
        ip='127.0.0.1', user_agent='xytest-audit-agent')

    body = client.get(URL).content.decode('utf-8')
    check('动作码已翻成中文', '删除提示词' in body and '>prompt_delete<' not in body)
    check('原始动作码留在悬停提示里（便于对照代码）', 'title="prompt_delete"' in body)
    check('未知动作码原样显示（绝不丢信息）', 'xytest_no_such_action' in body)
    check('来源列也翻成人话（提交 · 成功，不再是 POST · 302）',
          '提交 · 成功' in body and 'POST · 302' not in body)

    resp = client.get(URL, {'q': '删除提示词'})
    check('按中文说法搜索能命中（按动作中文名反查）',
          resp.status_code == 200 and log.path in resp.content.decode('utf-8'))

    html = client.get(URL, HTTP_ACCEPT_LANGUAGE='en').content.decode('utf-8')
    check('英文页显示英文动作名', 'Delete prompt' in html and 'Submit · Succeeded' in html,
          '未找到英文动作名')


def main():
    max_id = ConsoleAuditLog.objects.order_by('-id').values_list('id', flat=True).first() or 0
    hide_console = SecuritySetting.get_solo().hide_console
    created_admin = None
    try:
        client, admin, created_admin = superadmin_client()
        round1_write(client, admin)
        round2_read(client)
        round3_failed_write(client)
        round4_anonymous()
        round5_list(client, admin)
        round6_action_labels(client)
    finally:
        created = ConsoleAuditLog.objects.filter(id__gt=max_id).count()
        ConsoleAuditLog.objects.filter(id__gt=max_id).delete()
        setting = SecuritySetting.get_solo()
        setting.hide_console = hide_console
        setting.save()
        if created_admin:
            created_admin.delete()
        print(f'\n测试数据已清理（删掉本次产生的留痕 {created} 条，安全开关已还原）')

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
