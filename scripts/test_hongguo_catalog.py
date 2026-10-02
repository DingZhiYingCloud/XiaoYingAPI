"""短剧（红果线路）「分类树 + 榜单」回归测试

要守住的契约：
    分类是两级的          一级＝内容形态（真人剧 / 漫剧 / AI剧 / 漫画），二级＝题材（爱情 / 年代 …）；
                          每个节点都是一个合法的 category 取值，一级给 `real-drama`，
                          二级给「一级/二级」`real-drama/romance`
    分类树是唯一来源      爬虫 CATEGORIES -> CATEGORY_VALUES（视图层白名单）/ CATEGORY_OPTIONS（文档页下拉），
                          三处必须是同一份，禁止各写一遍（否则「文档里能选、接口却报参数非法」）
    榜单 4 种             热播榜 / 真人剧榜 / AI剧榜 / 漫剧榜（hot-comic-drama）
    榜单页不得混入面包屑   榜单页头部是 `<ol class="pc-list-…">`，只有 class 前缀会连面包屑的
                          2 个 <li>（首页 / 榜单名）一起选中，解析出来就是「rank=1/2 且字段全空」的脏数据

隔离策略：文档一致性 / 分类树形状为**离线**断言，任何时候都跑；
联网断言（分类页、榜单页、签名 HTTP）在源站不可达时整段 SKIP，不影响判定。
测试只读源站数据，不写任何业务表（仅临时建一个接入项目用于签名请求，结束即删）。

运行方式：
    .venv\\Scripts\\python.exe scripts\\test_hongguo_catalog.py
"""
import os
import secrets
import sys
import time

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'XiaoYingAPI.settings')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import django

django.setup()

from django.test import Client

from API.apis.user_center.sign import build_sign
from API.common import StatusCode
from API.models import UserApp
from API.website.docs.drama import SERVICE

from _test_support import grant_credit
from SpiderServices.dramas.hongguo import utils as U
from SpiderServices.dramas.hongguo.main import HongguoDramaSpider

# 站点实际情况（2026-10-01 由各级 /category/* 页面实际枚举所得）；站点加分类时同步这里
EXPECTED_TOP = ['real-drama', 'comic-drama', 'ai-drama', 'comic']
EXPECTED_CHILD_COUNTS = {'real-drama': 24, 'comic-drama': 8, 'ai-drama': 8, 'comic': 0}

RUN = str(int(time.time()))
MARK = f'xydramacat{RUN}'

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


def skip(reason):
    print(f'\n[SKIP] {reason}')
    print('（源站不可达时跳过联网断言；此前的离线断言结果照常生效）')
    return 1 if _FAILED else 0


def _signed(app, extra=None):
    params = {
        'app_id': app.app_id,
        'timestamp': str(int(time.time())),
        'nonce': secrets.token_hex(8),
    }
    params.update(extra or {})
    params['sign'] = build_sign(params, app.app_secret)
    return params


def round1_tree_shape():
    """分类树形状（离线）：两级结构、取值唯一、URL 可拼"""
    section('第 1 轮 分类树形状（离线）')
    cats = U.CATEGORIES
    check('一级分类为真人剧 / 漫剧 / AI剧 / 漫画',
          list(cats) == EXPECTED_TOP, f'got={list(cats)}')

    counts = {slug: len(node['children']) for slug, node in cats.items()}
    check('二级题材数量与站点一致（真人剧 24 / 漫剧 8 / AI剧 8 / 漫画 0）',
          counts == EXPECTED_CHILD_COUNTS, f'got={counts}')

    check('分类取值共 44 个且无重复',
          len(U.CATEGORY_VALUES) == 44 and len(set(U.CATEGORY_VALUES)) == 44,
          f'n={len(U.CATEGORY_VALUES)}')
    check('二级取值一律是「一级/二级」且一级真实存在',
          all(value.split('/')[0] in cats
              for value in U.CATEGORY_VALUES if '/' in value))
    check('取值能直接拼出分类页 URL（一级与二级同一套规则）',
          U.build_category_url('comic') == f'{U.BASE_URL}/category/comic'
          and U.build_category_url('real-drama/romance')
          == f'{U.BASE_URL}/category/real-drama/romance')
    check('分类显示名互不重复（同名题材不会被混作一项）',
          len({label for _, label in U.CATEGORY_OPTIONS}) == len(U.CATEGORY_OPTIONS))
    check('榜单类型为 4 种（含漫剧热播榜）',
          'hot-comic-drama' in U.RANK_TYPES and len(U.RANK_TYPES) == 4,
          f'got={U.RANK_TYPES}')


def round2_docs_consistency():
    """文档声明与后端白名单一致（离线）——防「文档里能选、接口却报参数非法」"""
    section('第 2 轮 文档声明与后端一致（离线）')
    channel = next(c for c in SERVICE.channels if c.slug == 'hongguo')
    rank_ep = next(e for e in channel.endpoints if e.slug == 'rank')
    list_ep = next(e for e in channel.endpoints if e.slug == 'list')
    categories_ep = next(e for e in channel.endpoints if e.slug == 'categories')

    rank_options = [opt['value'] for opt in rank_ep.params[0].options]
    category_options = [opt['value'] for opt in list_ep.params[0].options]
    check('文档页榜单下拉 = 后端 RANK_TYPES',
          rank_options == list(U.RANK_TYPES), f'docs={rank_options}')
    check('文档页分类下拉 = 后端 CATEGORY_VALUES（44 项，取值与顺序都一致）',
          category_options == list(U.CATEGORY_VALUES), f'n={len(category_options)}')
    check('「分类清单」端点声明了二级 children 语义',
          any('children' in note for note in categories_ep.notes))


def round3_live_category():
    """源站分类页（联网）"""
    section('第 3 轮 源站分类页（联网）')
    spider = HongguoDramaSpider()

    data = spider.get_categories()
    nodes = data['categories']
    check('分类清单返回 4 个一级节点且都带 children',
          len(nodes) == 4 and all('children' in node for node in nodes),
          f'n={len(nodes)}')
    # 顺序与 CATEGORY_VALUES 一致：一级紧跟着它自己的二级（不是「全部一级 + 全部二级」）
    flat = []
    for node in nodes:
        flat.append(node['slug'])
        flat.extend(child['slug'] for child in node['children'])
    check('分类清单里的取值与 CATEGORY_VALUES 完全一致（含顺序）',
          flat == list(U.CATEGORY_VALUES), f'got={flat[:5]}…')
    check('每个节点都带可访问的 url',
          all(node['url'] == U.build_category_url(node['slug']) for node in nodes)
          and all(child['url'] == U.build_category_url(child['slug'])
                  for node in nodes for child in node['children']))

    for category in ('real-drama', 'real-drama/romance', 'comic'):
        res = spider.get_list(category, page=1)
        items = res['results']
        check(f'{category} 列表可抓（{len(items)} 条 / 共 {res["pagination"]["total"]} 页）',
              bool(items) and res['category'] == category and res['pagination']['total'] >= 1,
              f'category={res.get("category")} n={len(items)}')
        check(f'{category} 列表条目字段完整（series_id / name / url）',
              all(item['series_id'] and item['name'] and item['url'] for item in items),
              f'head={items[:1]}')

    # 二级题材确实起了作用：同一部剧的首屏结果与一级不是同一批
    top = spider.get_list('real-drama', page=1)
    romance = spider.get_list('real-drama/romance', page=1)
    overlap = ({i['series_id'] for i in top['results']}
               & {i['series_id'] for i in romance['results']})
    check('二级题材与一级返回的不是同一批数据（题材确实生效）',
          overlap != {i['series_id'] for i in romance['results']},
          f'overlap={len(overlap)}/{len(romance["results"])}')


def round4_live_rank():
    """4 个榜单（联网）：重点守「不得混入面包屑」"""
    section('第 4 轮 榜单（联网）')
    spider = HongguoDramaSpider()
    for rank_type in U.RANK_TYPES:
        res = spider.get_rank(rank_type, page=1)
        items = res['results']
        # 面包屑混入时的特征：条目 series_id / name 为空、rank 从 1 重新计数但字段全空
        check(f'榜单 {rank_type} 抓到 {len(items)} 条且无脏条目',
              len(items) >= 10
              and all(item['series_id'] and item['name'] for item in items)
              and [item['rank'] for item in items] == list(range(1, len(items) + 1)),
              f'n={len(items)} head={items[:2]}')


def round5_http_contract():
    """对外接口契约（联网 + 签名）"""
    section('第 5 轮 对外接口契约（联网 + 签名）')
    client = Client()
    app = UserApp.objects.create(name=f'DramaCat{MARK}')
    grant_credit(app)   # 新项目默认 0 点额度，签名调用会被 30012 拦掉，先补一笔
    try:
        resp = client.get('/api/dramas/hongguo/categories', _signed(app))
        body = resp.json()
        nodes = (body.get('data') or {}).get('categories') or []
        check('分类清单接口原样下发分类树（一级带 children）',
              body.get('code') == StatusCode.SUCCESS and len(nodes) == 4
              and sum(len(node['children']) for node in nodes) == 40,
              f'body={str(body)[:160]}')

        resp = client.get('/api/dramas/hongguo/list',
                          _signed(app, {'category': 'real-drama/romance'}))
        body = resp.json()
        check('二级分类取值被接口接受',
              body.get('code') == StatusCode.SUCCESS
              and (body.get('data') or {}).get('category') == 'real-drama/romance',
              f'body={str(body)[:160]}')

        resp = client.get('/api/dramas/hongguo/rank',
                          _signed(app, {'type': 'hot-comic-drama'}))
        body = resp.json()
        check('漫剧热播榜被接口接受',
              body.get('code') == StatusCode.SUCCESS
              and (body.get('data') or {}).get('type') == 'hot-comic-drama',
              f'body={str(body)[:160]}')

        resp = client.get('/api/dramas/hongguo/list',
                          _signed(app, {'category': 'real-drama/nope'}))
        check('非法二级取值被拒（PARAM_VALUE_INVALID）',
              resp.json().get('code') == StatusCode.PARAM_VALUE_INVALID,
              f'body={str(resp.json())[:160]}')

        resp = client.get('/api/dramas/hongguo/rank', _signed(app, {'type': 'nope'}))
        check('非法榜单类型被拒（PARAM_VALUE_INVALID）',
              resp.json().get('code') == StatusCode.PARAM_VALUE_INVALID,
              f'body={str(resp.json())[:160]}')
    finally:
        app.delete()


def main():
    print('\n短剧「分类树 + 榜单」回归测试开始')

    # 离线断言先跑完，源站不可达也不影响这几条
    round1_tree_shape()
    round2_docs_consistency()

    try:
        HongguoDramaSpider().get_categories()
    except Exception as exc:
        return skip(f'源站不可达：{exc}')

    round3_live_category()
    round4_live_rank()
    round5_http_contract()

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
