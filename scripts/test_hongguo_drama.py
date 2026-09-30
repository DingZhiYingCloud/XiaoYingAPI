"""短剧（红果线路）「详情合并已登记外链」回归测试

需求来源：BugAndRepair/短剧详情接口-合并外链-需求说明.md

要守住的契约：
    episodes[].playable   单集能否播放的**唯一依据** = 源站直链 or 已登记外链
    playable_cnt          源站直链的**连续**范围（前 N 集），保持原义，不得改口径
    listed_cnt            实际可播集数（源站直链 + 已登记外链，可能不连续）
    detail 与 play 对同一集的可用性判断必须始终一致

同时自证「不污染爬虫缓存」：登记 / 删除登记行后**不清缓存**也能立刻反映，
且爬虫层的原始结果（缓存对象）始终不被就地修改。

隔离策略：只在「源站直链范围之外的第一集」上临时登记一条测试链接；
该集原本已有登记行时直接 SKIP（绝不覆盖真实数据），结束时必删。

运行方式：
    .venv\\Scripts\\python.exe scripts\\test_hongguo_drama.py
    .venv\\Scripts\\python.exe scripts\\test_hongguo_drama.py --series 7686894628578020414
"""
import argparse
import os
import secrets
import sys
import time

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'XiaoYingAPI.settings')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import django

django.setup()

from django.test import Client

from API.apis.dramas.hongguo import utils
from API.apis.user_center.sign import build_sign
from API.common import StatusCode
from API.models import HongguoEpisodeVideo, UserApp
from SpiderServices.dramas.hongguo.main import HongguoDramaSpider

DEFAULT_SERIES = '7686894628578020414'

RUN = str(int(time.time()))
MARK = f'xydramalink{RUN}'

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
    print('（源站不可达或剧集不存在时跳过；不影响判定）')
    return 0


def _signed(app, extra=None):
    params = {
        'app_id': app.app_id,
        'timestamp': str(int(time.time())),
        'nonce': secrets.token_hex(8),
    }
    params.update(extra or {})
    params['sign'] = build_sign(params, app.app_secret)
    return params


def _ep_state(detail, ep):
    """取某集的 playable 值（无该集时返回 None）"""
    return next((item.get('playable') for item in detail.get('episodes') or []
                 if item.get('ep') == ep), None)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--series', default=DEFAULT_SERIES, help='短剧剧集 ID')
    args = parser.parse_args()
    series = str(args.series).strip()

    print('\n短剧「详情合并已登记外链」回归测试开始')
    print(f'剧集：{series}    标记：{MARK}')

    ok, detail = utils.get_detail(series)
    if not ok or detail is None:
        return skip(f'取详情失败（{detail}）')

    playable_cnt = detail.get('playable_cnt')
    episode_cnt = detail.get('episode_cnt')
    listed_cnt = detail.get('listed_cnt')
    ep = (playable_cnt or 0) + 1            # 源站直链范围之外的第一集（实测为第 4 集）

    section('测试 1：字段契约与基线')
    check('detail 同时给出 episode_cnt / playable_cnt / listed_cnt',
          isinstance(episode_cnt, int) and isinstance(playable_cnt, int)
          and isinstance(listed_cnt, int),
          f'episode_cnt={episode_cnt} playable_cnt={playable_cnt} listed_cnt={listed_cnt}')
    check('episodes 为全量集列表', len(detail.get('episodes') or []) == episode_cnt,
          f'episodes={len(detail.get("episodes") or [])} episode_cnt={episode_cnt}')
    check('playable_cnt 未超过总集数', playable_cnt <= episode_cnt)
    check('源站直链范围内每集 playable=True',
          all(_ep_state(detail, i) is True for i in range(1, playable_cnt + 1)))

    pre_row = HongguoEpisodeVideo.objects.filter(series_id=series, ep=ep).first()
    if pre_row is not None:
        return skip(f'第 {ep} 集已有真实登记行（{pre_row.url}），不覆盖，跳过本次测试')

    check(f'基线：第 {ep} 集未登记 → playable=False', _ep_state(detail, ep) is False,
          f'playable={_ep_state(detail, ep)}')
    check('基线：listed_cnt == playable_cnt（无登记时）', listed_cnt == playable_cnt,
          f'listed_cnt={listed_cnt} playable_cnt={playable_cnt}')

    url = f'https://example.com/{MARK}/ep{ep}.m3u8'
    app = UserApp.objects.create(name=f'DramaLink{MARK}')
    client = Client()
    try:
        section('测试 2：登记外链（走服务层，登记无对外接口）')
        ok, result = utils.save_episode_videos(series, f'{ep} {url}', 'm3u8',
                                              series_name=f'回归测试 {MARK}')
        check('登记成功且为新增', ok and result.get('created') == 1, f'result={result}')

        section('测试 3：detail 立即合并（不清缓存）')
        ok, merged = utils.get_detail(series)
        check('取详情成功', ok and merged is not None, f'{merged}')
        check(f'第 {ep} 集 playable 变为 True', _ep_state(merged, ep) is True,
              f'playable={_ep_state(merged, ep)}')
        check('listed_cnt = 基线 + 1', merged.get('listed_cnt') == listed_cnt + 1,
              f'listed_cnt={merged.get("listed_cnt")}')
        check('playable_cnt 口径不变（仍为源站直链范围）',
              merged.get('playable_cnt') == playable_cnt,
              f'playable_cnt={merged.get("playable_cnt")}')
        check('episode_cnt 不变', merged.get('episode_cnt') == episode_cnt)
        check('源站直链范围内各集仍然是 playable=True',
              all(_ep_state(merged, i) is True for i in range(1, playable_cnt + 1)))

        section('测试 4：不污染爬虫缓存（§2.3）')
        raw = HongguoDramaSpider().get_detail(series)
        check('爬虫层原始结果未被就地修改（该集仍为 False）',
              _ep_state(raw, ep) is False, f'raw playable={_ep_state(raw, ep)}')
        check('爬虫层 playable_cnt 未变', raw.get('playable_cnt') == playable_cnt)

        section('测试 5：play 与 detail 口径一致（§2.4）')
        status, payload = utils.get_play(series, ep)
        check('play 返回可播', status == utils.PLAY_OK, f'status={status}')
        check('play 标记为外链来源且地址一致',
              isinstance(payload, dict) and payload.get('source') == 'external'
              and payload.get('url') == url and payload.get('url_type') == 'm3u8',
              f'payload={payload}')
        check('play 的 playable 与 detail 一致（都为 True）',
              isinstance(payload, dict) and payload.get('playable') is True)

        section('测试 6：对外接口返回体（签名请求真实 HTTP）')
        resp = client.get('/api/dramas/hongguo/detail', _signed(app, {'series_id': series}))
        body = resp.json()
        data = body.get('data') or {}
        check('detail 接口 200 且业务码成功',
              resp.status_code == 200 and body.get('code') == StatusCode.SUCCESS,
              f'code={body.get("code")}')
        check('响应体含 listed_cnt 且已合并', data.get('listed_cnt') == listed_cnt + 1,
              f'listed_cnt={data.get("listed_cnt")}')
        check('响应体 playable_cnt 保持原义', data.get('playable_cnt') == playable_cnt)
        check(f'响应体 episodes 第 {ep} 集 playable=True',
              _ep_state(data, ep) is True, f'playable={_ep_state(data, ep)}')

        resp = client.get('/api/dramas/hongguo/play',
                          _signed(app, {'series_id': series, 'ep': ep}))
        body = resp.json()
        play_data = body.get('data') or {}
        check('play 接口返回外链地址',
              body.get('code') == StatusCode.SUCCESS
              and play_data.get('source') == 'external' and play_data.get('url') == url,
              f'body={body}')
    finally:
        section('测试 7：删除登记行后还原（不清缓存）')
        HongguoEpisodeVideo.objects.filter(series_id=series, ep=ep, url=url).delete()
        ok, restored = utils.get_detail(series)
        check('取详情成功', ok and restored is not None, f'{restored}')
        check(f'第 {ep} 集 playable 回到 False', _ep_state(restored, ep) is False,
              f'playable={_ep_state(restored, ep)}')
        check('listed_cnt 回到基线', restored.get('listed_cnt') == listed_cnt,
              f'listed_cnt={restored.get("listed_cnt")}')
        # 删掉登记行后，该集不再返回外链，而是回落到「本站直出」（source=stream）
        status, payload = utils.get_play(series, ep)
        check('play 不再返回外链（回落到本站直出）',
              status == utils.PLAY_OK and isinstance(payload, dict)
              and payload.get('source') == 'stream',
              f'status={status} payload={payload}')
        check('测试数据已清理',
              not HongguoEpisodeVideo.objects.filter(series_id=series, ep=ep).exists())
        app.delete()

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
