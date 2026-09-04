"""API 服务认证分类树（ApiCategory + ApiAuthMiddleware）多轮测试

A-01 fail-closed 后的语义：
    认证判定沿父链取第一个非 inherit 的模式（auth=需认证 / open=开放）；
    未命中分类节点 / 整条链全为 inherit / 命中分类已停用 → 一律按「需要认证」处理。
    仅两类路径可匿名访问：分类树显式 open 的节点、PUBLIC_GET_PATHS 列出的公开 GET 路径。

覆盖范围：
    第一轮 根级认证（/api/user_center/ 分类 auth：无签名/错误/停用/有效签名）
    第二轮 fail-closed 默认（A-01：未匹配分类/全 inherit 需认证；显式 open、
            公开 GET 豁免可匿名访问）
    第三轮 层级覆盖与继承（核心：父级 auth + 子级 open；子级 auth 覆盖开放父级；三级链继承）
    第四轮 视图兜底（用户中心子分类被开放时，业务层仍拒绝，不崩溃）
    第五轮 并发认证与分类停用状态（停用后回落默认需认证，不再「恢复开放」）

说明：测试基于真实数据库的生产分类树（自动生成），所有被修改的分类
（auth_mode / status）在结束后自动恢复原值，不影响线上配置。

运行方式（使用真实数据库，测试结束后自动恢复分类配置）：
    .venv\\Scripts\\python.exe scripts\\test_api_auth_policy.py
"""
import os
import secrets
import sys
import time
from concurrent.futures import ThreadPoolExecutor

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'XiaoYingAPI.settings')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import django

django.setup()

from django.test import Client

from API.models import UserApp, ApiCategory
from API.apis.user_center.sign import build_sign

# ───────────────────────── 测试基础设施 ─────────────────────────

_PREFIX = f'AP{int(time.time())}'
_stats = {'pass': 0, 'fail': 0}
_created_apps = []          # UserApp id
_touched_categories = {}    # 分类 id -> (原 auth_mode, 原 status)
_LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'test_api_auth_policy_result.log')


def _log(msg):
    print(msg)
    with open(_LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(msg + '\n')


def _check(name, cond, extra=''):
    if cond:
        _stats['pass'] += 1
        _log(f'  [PASS] {name}')
    else:
        _stats['fail'] += 1
        _log(f'  [FAIL] {name} {extra}')


def _section(title):
    _log(f'\n===== {title} =====')


def _create_app(name=None):
    obj = UserApp.objects.create(name=name or f'{_PREFIX}项目{len(_created_apps)}', token_expire_days=7, status=True)
    _created_apps.append(obj.id)
    return obj


def _signed(app, extra=None):
    extra = {k: v for k, v in (extra or {}).items() if v is not None}
    params = {
        'app_id': app.app_id,
        'timestamp': str(int(time.time())),
        'nonce': secrets.token_hex(8),
    }
    if extra:
        params.update(extra)
    params['sign'] = build_sign(params, app.app_secret)
    return params


def _response(resp):
    import json
    return json.loads(resp.content.decode('utf-8'))


def _set_auth(path_prefix, mode, status=True):
    """修改分类的认证模式/状态，记录原值以便恢复"""
    cat = ApiCategory.objects.get(path_prefix=path_prefix)
    if cat.id not in _touched_categories:
        _touched_categories[cat.id] = (cat.auth_mode, cat.status)
    cat.auth_mode = mode
    cat.status = status
    cat.save(update_fields=['auth_mode', 'status'])
    return cat


def _restore_categories():
    for cid, (mode, status) in _touched_categories.items():
        ApiCategory.objects.filter(id=cid).update(auth_mode=mode, status=status)
    _log(f'  [清理] 恢复被修改的分类 {len(_touched_categories)} 个')


# ───────────────────────── 第一轮：根级认证 ─────────────────────────

def round1():
    _section('第一轮 根级认证（/api/user_center/ 分类为 auth）')
    app = _create_app()
    info = '/api/user_center/projects/info'

    r = _response(Client().get(info))
    _check('无签名请求被认证层拦截', r.get('code') == 20011, f'code={r.get("code")}')
    _check('拦截响应含原因提示', bool(r.get('msg')))

    r = _response(Client().get(info, _signed(app)))
    _check('有效签名请求通过认证', r.get('code') == 10000, f'code={r.get("code")} msg={r.get("msg")}')

    bad = _signed(app)
    bad['sign'] = '0' * 64
    r = _response(Client().get(info, bad))
    _check('错误签名被拦截', r.get('code') == 20011 and '不匹配' in r.get('msg', ''), f'msg={r.get("msg")}')

    app.status = False
    app.save()
    r = _response(Client().get(info, _signed(app)))
    _check('停用项目签名被拦截', r.get('code') == 20011 and '停用' in r.get('msg', ''), f'msg={r.get("msg")}')
    app.status = True
    app.save()


# ───────────────────────── 第二轮：fail-closed 默认（A-01） ─────────────────────────

def round2():
    _section('第二轮 fail-closed 默认（未匹配/全 inherit 需认证；显式 open 与公开 GET 可匿名）')

    # 2.1 未命中任何分类节点的路径 → 默认需认证（原为放行）
    r = _response(Client().get('/api/not_exists/foo'))
    _check('未匹配分类路径无签名被拦截(20011)', r.get('code') == 20011, f'code={r.get("code")}')

    # 2.2 全链 inherit 的服务 → 默认需认证（用 ddddocr POST，认证层先于业务层拦截）
    r = _response(Client().post('/api/ddddocr/ocr'))
    _check('全链 inherit 服务无签名被拦截(20011)', r.get('code') == 20011, f'code={r.get("code")}')

    # 2.3 显式 open 的分类可匿名访问（IndexNow 协议回调类服务保持开放）
    _set_auth('/api/bing/indexnow/', 'open')
    r = _response(Client().get('/api/bing/indexnow/generate-key'))
    _check('显式 open 节点匿名访问放行', r.get('code') != 20011, f'code={r.get("code")}')
    _set_auth('/api/bing/indexnow/', 'inherit')

    # 2.4 captcha_auth/aliyun 整体显式 open（开放集成：config/verify 均免签）
    r = _response(Client().get('/api/captcha_auth/aliyun/config'))
    _check('captcha open 节点-config 匿名放行', r.get('code') == 10000, f'code={r.get("code")}')
    _check('放行后正常返回 app_id', bool((r.get('data') or {}).get('app_id')))

    # 2.5 PUBLIC_GET_PATHS 公开 GET 豁免（user_center/users/methods 供客户端探测方式）
    r = _response(Client().get('/api/user_center/users/methods'))
    _check('公开 GET 豁免-匿名放行', r.get('code') == 10000, f'code={r.get("code")}')


# ───────────────────────── 第三轮：层级覆盖与继承 ─────────────────────────

def round3():
    _section('第三轮 层级覆盖与继承（最长前缀 + 沿父链取非 inherit）')
    app = _create_app()
    mail_v1 = '/api/email/v1/dummy-x'
    mail_vm = '/api/email/VMEmail/dummy-x'
    mail_min = '/api/email/VMEmail/minmail/dummy-x'

    # 重置本轮涉及的全部分类为「跟随上级」，保证测试前提一致、与线上配置解耦
    # （用户可能已在后台手动调整过这些分类的认证模式）
    for p in ('/api/email/', '/api/email/v1/', '/api/email/VMEmail/', '/api/email/VMEmail/minmail/'):
        _set_auth(p, 'inherit')

    # 3.1 fail-closed 默认 + 子级显式 open 覆盖：
    #     顶层全 inherit（默认需认证）+ 子级 open → 子级匿名放行，旁支继承默认被拦截
    _set_auth('/api/email/VMEmail/', 'open')
    _check('子级 open-匿名放行(到达 404 兜底而非认证拦截)', _response(Client().get(mail_min)).get('code') != 20011)
    _check('旁支继承顶层 inherit-默认需认证被拦截', _response(Client().get(mail_v1)).get('code') == 20011)
    _set_auth('/api/email/VMEmail/', 'inherit')

    # 3.2 父级 auth + 子级 open（用户强调的「父级认证、子级单独开放」）
    _set_auth('/api/email/', 'auth')
    _set_auth('/api/email/v1/', 'open')
    _check('父级 auth 子级 open-子级放行', _response(Client().get(mail_v1)).get('code') != 20011)
    _check('父级 auth 子级 open-同级未配置被拦截', _response(Client().get(mail_vm)).get('code') == 20011)
    _check('父级 auth 子级 open-孙级继承父级被拦截', _response(Client().get(mail_min)).get('code') == 20011)

    # 3.3 三级链：父级 open + 子级 auth + 孙级 inherit → 孙级继承子级 auth
    _set_auth('/api/email/', 'open')
    _set_auth('/api/email/VMEmail/', 'auth')
    _check('三级链-子级 auth 拦截', _response(Client().get(mail_vm)).get('code') == 20011)
    _check('三级链-孙级 inherit 继承子级 auth 拦截', _response(Client().get(mail_min)).get('code') == 20011)
    _check('三级链-旁支 v1 继承顶层 open 放行', _response(Client().get(mail_v1)).get('code') != 20011)

    # 3.4 更深节点覆盖：父级 open + 子级 auth + 孙级 open → 孙级放行
    _set_auth('/api/email/VMEmail/minmail/', 'open')
    _check('孙级 open 覆盖子级 auth 放行', _response(Client().get(mail_min)).get('code') != 20011)
    _check('子级仍 auth 拦截', _response(Client().get(mail_vm)).get('code') == 20011)

    # 3.5 最长前缀：孙级 auth 覆盖（同前缀命中更深节点优先）
    _set_auth('/api/email/VMEmail/minmail/', 'auth')
    _check('最长前缀-孙级 auth 拦截', _response(Client().get(mail_min)).get('code') == 20011)

    # 3.6 显式 auth 节点带有效签名 → 通过认证到达业务层（非 20011）
    _check('auth 节点带有效签名放行(到达404兜底)',
           _response(Client().get(mail_vm, _signed(app))).get('code') != 20011)


# ───────────────────────── 第四轮：视图兜底 ─────────────────────────

def round4():
    _section('第四轮 视图兜底（用户中心子分类被开放时不崩溃，业务仍拒绝）')
    _set_auth('/api/user_center/users/', 'open')
    r = _response(Client().post('/api/user_center/users/register', {'username': 'x', 'password': 'pass123'}))
    _check('开放接口无签名-业务层仍拒绝(非500)', r.get('code') == 20011, f'code={r.get("code")} msg={r.get("msg")}')
    _check('兜底提示明确', '项目认证' in r.get('msg', ''), r.get('msg', ''))
    r = _response(Client().get('/api/user_center/projects/info'))
    _check('未开放子分类仍被服务级认证拦截', r.get('code') == 20011, f'code={r.get("code")}')
    _set_auth('/api/user_center/users/', 'inherit')


# ───────────────────────── 第五轮：并发与分类状态 ─────────────────────────

def round5():
    _section('第五轮 并发认证与分类停用状态（停用后回落默认需认证）')
    app = _create_app()
    info = '/api/user_center/projects/info'
    mail_v1 = '/api/email/v1/dummy-x'

    # 重置 email 系分类，与线上配置解耦
    _set_auth('/api/email/', 'inherit')
    _set_auth('/api/email/v1/', 'inherit')

    def do_request(i):
        return _response(Client().get(info, _signed(app)))

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(do_request, range(10)))
    ok = all(r.get('code') == 10000 for r in results)
    _check('并发 10 次有效签名请求全部通过', ok, f'失败数={sum(1 for r in results if r.get("code") != 10000)}')

    # 分类 auth + 停用 status=False → A-01 后回落默认需认证（原为「恢复默认开放」）
    _set_auth('/api/email/', 'auth', status=True)
    r = _response(Client().get(mail_v1))
    _check('启用分类 auth-无签名请求被拦截', r.get('code') == 20011, f'code={r.get("code")}')
    cat = ApiCategory.objects.get(path_prefix='/api/email/')
    cat.status = False
    cat.save(update_fields=['status'])
    r = _response(Client().get(mail_v1))
    _check('停用分类-无签名回落默认需认证仍被拦截', r.get('code') == 20011, f'code={r.get("code")}')
    r = _response(Client().get(mail_v1, _signed(app)))
    _check('停用分类-带有效签名放行(到达404兜底)', r.get('code') != 20011, f'code={r.get("code")}')


# ───────────────────────── 清理与汇总 ─────────────────────────

def cleanup():
    deleted = UserApp.objects.filter(id__in=_created_apps).delete()
    _log(f'\n[清理] 删除测试项目 {deleted[0]} 个')
    _restore_categories()


def main():
    if os.path.exists(_LOG_FILE):
        os.remove(_LOG_FILE)
    _log(f'API 服务认证分类树测试开始（前缀 {_PREFIX}）')
    try:
        round1()
        round2()
        round3()
        round4()
        round5()
    finally:
        cleanup()

    total = _stats['pass'] + _stats['fail']
    _log(f'\n========== 测试汇总 ==========')
    _log(f'通过: {_stats["pass"]}  |  失败: {_stats["fail"]}  |  总计: {total}')
    if _stats['fail']:
        _log('结论: 存在失败用例，请检查 ❌')
        sys.exit(1)
    _log('结论: 全部用例通过 ✅')


if __name__ == '__main__':
    main()
