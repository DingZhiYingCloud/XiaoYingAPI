"""线路价格与计费回归测试（独立价格表 + 控制台页 + 文档标价 + 落库结算）

覆盖范围：
    第 1 轮 三级继承（纯逻辑）：服务 / 线路 / 端点逐级覆写、兜底 DEFAULT_PRICE、
             与「服务策略」解耦（策略表已无 price 字段）
    第 2 轮 缓存失效：新增 / 改动单价后立即生效，显式失效函数可用
    第 3 轮 落库结算：api_stats.flush() 只对成功调用按当时单价写入 cost_points，
             并原子扣减项目余额；失败调用记 0 点、不扣费
    第 4 轮 控制台页面（/console/prices/）：未登录被拦、超管可访问、服务树全量列出、
             逐条填价保存、清空恢复跟随上级、非法 / 树外前缀被拒
    第 5 轮 文档中心标价：每个端点显示生效单价与来源（端点价 / 线路价 / 服务价 / 默认价）
    第 6 轮 三语渲染（zh-hans / zh-hant / en）

隔离策略：价格行的路径前缀一律用真实前缀（价格表必须挂在真实前缀上才有意义），
因此测试期间会临时改动真实前缀的单价，结束后按「测试前快照」原样还原；
测试项目 / 统计行用随机后缀并在结束时删除。

运行方式：
    .venv\\Scripts\\python.exe scripts\\test_prices.py
"""
import os
import sys
import time
from decimal import Decimal

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'XiaoYingAPI.settings')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import django

django.setup()

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from API.common import StatusCode, api_stats
from API.common.credit_guard import (
    invalidate_api_price_cache,
    resolve_price,
    resolve_price_detail,
)
from API.models import ApiCallStat, ApiPricePolicy, ApiServicePolicy, UserApp
from API.models.Credit.price import DEFAULT_PRICE

from _test_support import grant_credit

RUN = str(int(time.time()))
MARK = f'xyprice{RUN}'

# 用于控制台 / 文档页验证的真实前缀（服务树里一定存在）
REAL_SERVICE = '/api/ai/'
DOC_SLUG = 'ai'

# 提交给价格页的字段名前缀（与 console_prices.FIELD_PREFIX 一致）
FIELD = 'price::'

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


def superadmin_client():
    """返回 (已登录超管的客户端, 是否临时创建)"""
    user_model = get_user_model()
    admin = user_model.objects.filter(is_superuser=True, is_active=True).first()
    created = False
    if admin is None:
        admin = user_model.objects.create_superuser(
            username=f'xytest_price_{RUN}', email=f'xytest.price.{RUN}@example.com',
            password='xytest-admin-pass')
        created = True
    client = Client()
    client.force_login(admin)
    return client, created


def snapshot(prefixes):
    """记录这些前缀当前的显式单价（None 表示没有行），结束后还原"""
    snap = {}
    for prefix in prefixes:
        row = ApiPricePolicy.objects.filter(path_prefix=prefix).first()
        snap[prefix] = (row.level, row.price) if row else None
    return snap


def restore(snap):
    for prefix, value in snap.items():
        ApiPricePolicy.objects.filter(path_prefix=prefix).delete()
        if value is not None:
            level, price = value
            ApiPricePolicy.objects.create(path_prefix=prefix, level=level, price=price)
    invalidate_api_price_cache()


# ───────────────────────── 第 1 轮：三级继承 ─────────────────────────

def round1_inherit():
    section('第 1 轮 三级继承（服务 / 线路 / 端点覆写 + 兜底价）')
    base = f'/api/{MARK}/'
    ApiPricePolicy.objects.create(path_prefix=base, level='service', price=Decimal('5'))
    ApiPricePolicy.objects.create(path_prefix=f'{base}ch/', level='channel', price=Decimal('8'))
    ApiPricePolicy.objects.create(path_prefix=f'{base}ch/ep', level='endpoint',
                                  price=Decimal('0'))
    invalidate_api_price_cache()

    check('服务级单价生效', resolve_price(f'{base}other') == Decimal('5'))
    check('线路级覆盖服务级', resolve_price(f'{base}ch/probe') == Decimal('8'))
    check('端点级覆盖线路级（0 = 免费）', resolve_price(f'{base}ch/ep') == Decimal('0'))
    check('端点级不影响同线路其它路径', resolve_price(f'{base}ch/other') == Decimal('8'))
    detail = resolve_price_detail(f'{base}ch/probe')
    check('来源标注为线路级', detail['source'] == 'channel' and detail['prefix'] == f'{base}ch/')
    check('未配置时兜底 DEFAULT_PRICE', resolve_price(f'/api/{MARK}none/x') == DEFAULT_PRICE)
    detail = resolve_price_detail(f'/api/{MARK}none/x')
    check('兜底来源标注为 default', detail['source'] == 'default')

    check('价格表与服务策略解耦（策略表已无 price 字段）',
          not any(f.name == 'price' for f in ApiServicePolicy._meta.get_fields()))


# ───────────────────────── 第 2 轮：缓存失效 ─────────────────────────

def round2_cache():
    section('第 2 轮 缓存失效（改动立即生效）')
    prefix = f'/api/{MARK}cache/'
    check('初始未配置 → 兜底价', resolve_price(f'{prefix}probe') == DEFAULT_PRICE)

    row = ApiPricePolicy.objects.create(path_prefix=prefix, level='service', price=Decimal('100'))
    check('新增单价后立即生效（信号使缓存失效）',
          resolve_price(f'{prefix}probe') == Decimal('100'))

    row.price = Decimal('2')
    row.save(update_fields=['price', 'updated_time'])
    check('改价后立即生效', resolve_price(f'{prefix}probe') == Decimal('2'))

    ApiPricePolicy.objects.filter(path_prefix=prefix).delete()
    check('删除行后立即回落到兜底价',
          resolve_price(f'{prefix}probe') == DEFAULT_PRICE)

    invalidate_api_price_cache()
    check('显式失效函数可用', isinstance(resolve_price(f'{prefix}probe'), Decimal))


# ───────────────────────── 第 3 轮：落库结算 ─────────────────────────

def round3_settlement(app):
    section('第 3 轮 落库结算（只扣成功调用，按当时单价）')
    path = f'/api/{MARK}settle/ep'
    ApiPricePolicy.objects.create(path_prefix=path, level='endpoint', price=Decimal('3.5'))
    invalidate_api_price_cache()

    before = UserApp.objects.get(pk=app.pk).balance

    # 成功调用 2 次 + 失败调用 3 次：只有成功计数扣费
    api_stats._buffer.clear()
    api_stats._hour_buffer.clear()
    for _ in range(2):
        api_stats.record(path, 10, StatusCode.SUCCESS, app.app_id)
    for _ in range(3):
        api_stats.record(path, 10, StatusCode.INTERNAL_ERROR, app.app_id)
    api_stats.flush()

    # 成功与失败各占一行（聚合键含状态码）
    ok_row = ApiCallStat.objects.filter(app_id=app.app_id, path=path,
                                       status_code=StatusCode.SUCCESS).first()
    fail_row = ApiCallStat.objects.filter(app_id=app.app_id, path=path,
                                          status_code=StatusCode.INTERNAL_ERROR).first()
    check('成功与失败各落一行统计', ok_row is not None and fail_row is not None)
    check('成功调用 2 次 / 失败调用 3 次',
          ok_row.call_count == 2 and fail_row.call_count == 3)
    check('消耗点数只算成功调用（2 × 3.5 = 7）', ok_row.cost_points == Decimal('7'))
    check('失败调用行 cost_points = 0', fail_row.cost_points == Decimal('0'))
    after = UserApp.objects.get(pk=app.pk).balance
    check('余额按成功调用扣减 7 点', after == before - Decimal('7'), f'{before} -> {after}')

    # 再成功调用一次：继续按 3.5 扣费
    api_stats._buffer.clear()
    api_stats._hour_buffer.clear()
    api_stats.record(path, 5, StatusCode.SUCCESS, app.app_id)
    api_stats.flush()
    check('再次成功调用继续按 3.5 扣费',
          UserApp.objects.get(pk=app.pk).balance == before - Decimal('10.5'))

    ApiCallStat.objects.filter(app_id=app.app_id, path__contains=MARK).delete()


# ───────────────────────── 第 4 轮：控制台页面 ─────────────────────────

def round4_console(client):
    section('第 4 轮 控制台「线路价格」页（/console/prices/）')
    url = reverse('website:console_prices')

    anon = Client().get(url)
    check('匿名访问被拦（隐身 404 / 否则 302）', anon.status_code in (302, 404),
          f'status={anon.status_code}')

    resp = client.get(url)
    body = resp.content.decode()
    check('超管可访问（200）', resp.status_code == 200, f'status={resp.status_code}')
    check('服务树全量列出（含真实服务前缀）', REAL_SERVICE in body)
    check('每个节点一个价格输入框（字段名带前缀）',
          f'name="{FIELD}{REAL_SERVICE}"' in body)
    check('页面含保存按钮与规则说明', '保存全部' in body and '兜底' in body)
    check('菜单高亮「线路价格」', 'menu-active' in body and url in body)

    # 填价保存（服务级）
    resp = client.post(url, {f'{FIELD}{REAL_SERVICE}': '2.5'})
    row = ApiPricePolicy.objects.filter(path_prefix=REAL_SERVICE).first()
    check('保存成功（302）并写入价格行',
          resp.status_code == 302 and row is not None
          and row.price == Decimal('2.5') and row.level == 'service')

    # 清空即恢复跟随上级
    resp = client.post(url, {f'{FIELD}{REAL_SERVICE}': ''})
    check('清空输入即删除该行（恢复跟随上级）',
          resp.status_code == 302
          and not ApiPricePolicy.objects.filter(path_prefix=REAL_SERVICE).exists())

    # 非法 / 树外前缀
    resp = client.post(url, {f'{FIELD}/api/{MARK}not-in-tree/': '1'})
    check('服务树外的前缀被拒（不写库）',
          not ApiPricePolicy.objects.filter(path_prefix=f'/api/{MARK}not-in-tree/').exists())
    resp = client.post(url, {f'{FIELD}{REAL_SERVICE}': 'abc'})
    check('非数字被拒', not ApiPricePolicy.objects.filter(path_prefix=REAL_SERVICE).exists())
    resp = client.post(url, {f'{FIELD}{REAL_SERVICE}': '-3'})
    check('负数被拒', not ApiPricePolicy.objects.filter(path_prefix=REAL_SERVICE).exists())


# ───────────────────────── 第 5 轮：文档中心标价 ─────────────────────────

def round5_docs():
    section('第 5 轮 文档中心端点标价（生效单价 + 来源）')
    url = reverse('website:docs_service', args=[DOC_SLUG])
    client = Client()
    client.cookies[settings.LANGUAGE_COOKIE_NAME] = 'zh-hans'

    ApiPricePolicy.objects.filter(path_prefix=REAL_SERVICE).delete()
    invalidate_api_price_cache()
    body = client.get(url).content.decode()
    check('文档页正常渲染（200）', '点/次' in body)
    check('未配置单价时标注为「默认价」', '默认价' in body)

    ApiPricePolicy.objects.create(path_prefix=REAL_SERVICE, level='service',
                                  price=Decimal('3.3333'))
    invalidate_api_price_cache()
    body = client.get(url).content.decode()
    check('服务级设价后文档页显示该单价', '3.3333' in body)
    check('来源标注为「服务价」', '服务价' in body)

    ApiPricePolicy.objects.filter(path_prefix=REAL_SERVICE).delete()
    invalidate_api_price_cache()


# ───────────────────────── 第 6 轮：三语渲染 ─────────────────────────

def round6_i18n():
    section('第 6 轮 三语渲染（zh-hans / zh-hant / en）')
    url = reverse('website:console_prices')
    admin = get_user_model().objects.filter(is_superuser=True, is_active=True).first()
    for lang, must in (('zh-hans', '线路价格'), ('zh-hant', '線路價格'), ('en', 'Route Pricing')):
        lang_client = Client()
        lang_client.cookies[settings.LANGUAGE_COOKIE_NAME] = lang
        lang_client.force_login(admin)
        resp = lang_client.get(url)
        text = resp.content.decode()
        check(f'{lang} 页面可渲染且含标题「{must}」',
              resp.status_code == 200 and must in text, f'status={resp.status_code}')
        if lang != 'zh-hans':
            check(f'{lang} 无中文回退', '线路价格' not in text)


def main():
    section('线路价格与计费回归测试')
    app = grant_credit(UserApp.objects.create(name=f'PriceApp{MARK}'))
    client, created_admin = superadmin_client()

    snap = snapshot([REAL_SERVICE])
    try:
        round1_inherit()
        round2_cache()
        round3_settlement(app)
        round4_console(client)
        round5_docs()
        round6_i18n()
    finally:
        # 清测试数据 + 还原真实前缀的单价
        ApiPricePolicy.objects.filter(path_prefix__contains=MARK).delete()
        restore(snap)
        ApiCallStat.objects.filter(app_id=app.app_id).delete()
        UserApp.objects.filter(pk=app.pk).delete()
        if created_admin:
            get_user_model().objects.filter(username__startswith='xytest_price_').delete()

    print(f'\n{"=" * 70}\n总计：PASS {_PASSED} / FAIL {_FAILED}\n{"=" * 70}')
    if _FAILURES:
        print('失败项：')
        for name in _FAILURES:
            print(f'  - {name}')
    return 1 if _FAILED else 0


if __name__ == '__main__':
    sys.exit(main())
