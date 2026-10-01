"""短剧（红果线路）「详情 / 播放 口径一致」回归测试

要守住的契约：
    episodes[].playable   单集能否播放的**唯一依据** = 源站直链 or 本站「网页直出」
    episodes[].source     来源标注：origin（源站直链）/ stream（本站直出）
    play.data.source      与 episodes[].source 同一套取值，调用方不必两处各判一套
    playable_cnt          源站直链的**连续**范围（前 N 集），保持原义，不得改口径
    listed_cnt            实际可播集数（= playable 为 true 的集数）
    detail 与 play 对同一集的可用性判断必须始终一致
    stream 的 HTTP 契约    202=正在生成 / 503=生成失败 / 200·206=可播（失败不得用 200 伪装）

同时自证「不污染爬虫缓存」：服务层补的 playable / source 只加在返回副本上，
爬虫层的原始结果（缓存对象）始终不被就地修改。

运行方式：
    .venv\\Scripts\\python.exe scripts\\test_hongguo_drama.py
    .venv\\Scripts\\python.exe scripts\\test_hongguo_drama.py --series 7686894628578020414
"""
import argparse
import os
import secrets
import sys
import time
from unittest import mock

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'XiaoYingAPI.settings')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import django

django.setup()

from django.conf import settings
from django.test import Client

from API.apis.dramas.hongguo import utils
from API.apis.user_center.sign import build_sign
from API.common import StatusCode
from API.models import UserApp
from SpiderServices.dramas.hongguo import transcode
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
    # 只跳过依赖源站的用例，此前已跑完的用例（如视图层契约）结果照常生效
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


def _ep_field(detail, ep, field):
    """取某集的某个字段值（无该集时返回 None）"""
    return next((item.get(field) for item in detail.get('episodes') or []
                 if item.get('ep') == ep), None)


def _ep_state(detail, ep):
    return _ep_field(detail, ep, 'playable')


def check_stream_http_contract():
    """网页直出流的 HTTP 契约（不依赖源站 / 不启转码，纯视图层）

    历史问题：转码失败曾用 HTTP 200 + JSON 返回，文档却写「轮询到 200 即可播放」，
    客户端会把失败态误判成可播。现在固定为 202 / 503 / 200·206 三态。
    """
    section('测试 0：网页直出流的 HTTP 契约（不依赖源站）')
    client = Client()
    token = utils.make_stream_token('xytest-stream-contract', 1, 720)

    with mock.patch.object(transcode, 'is_ready', return_value=False), \
            mock.patch.object(transcode, 'ensure', return_value=False), \
            mock.patch.object(transcode, 'job_status', return_value={'state': 'pending'}):
        resp = client.get('/api/dramas/hongguo/stream', {'token': token})
        check('未就绪 -> 202 且带 Retry-After',
              resp.status_code == 202 and resp.json().get('code') == StatusCode.SUCCESS
              and resp.get('Retry-After') == '3', f'status={resp.status_code}')

    with mock.patch.object(transcode, 'is_ready', return_value=False), \
            mock.patch.object(transcode, 'ensure', return_value=False), \
            mock.patch.object(transcode, 'job_status',
                              return_value={'state': 'failed', 'error': '模拟失败'}):
        resp = client.get('/api/dramas/hongguo/stream', {'token': token})
        check('转码失败 -> 503（不再用 200 伪装成功）',
              resp.status_code == 503
              and resp.json().get('code') == StatusCode.SERVICE_UNAVAILABLE,
              f'status={resp.status_code}')
        check('失败响应不是 video/*（客户端不会误当可播）',
              not (resp.get('Content-Type') or '').startswith('video/'),
              resp.get('Content-Type'))

    resp = client.get('/api/dramas/hongguo/stream')
    check('无令牌 -> 403（鉴权失败不等于可播）',
          resp.status_code == 403 and resp.json().get('code') == StatusCode.FORBIDDEN,
          f'status={resp.status_code}')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--series', default=DEFAULT_SERIES, help='短剧剧集 ID')
    args = parser.parse_args()
    series = str(args.series).strip()

    stream_on = bool(getattr(settings, 'HONGGUO_STREAM_DIR', ''))

    print('\n短剧「详情 / 播放 口径一致」回归测试开始')
    print(f'剧集：{series}    标记：{MARK}    本站直出：{"可用" if stream_on else "不可用"}')

    # 先跑不依赖源站的视图层契约，源站不可达时它照样能守住这条线
    check_stream_http_contract()

    ok, detail = utils.get_detail(series)
    if not ok or detail is None:
        return skip(f'取详情失败（{detail}）')

    playable_cnt = detail.get('playable_cnt')
    episode_cnt = detail.get('episode_cnt')
    listed_cnt = detail.get('listed_cnt')
    episodes = detail.get('episodes') or []
    playable_total = sum(1 for item in episodes if item.get('playable'))
    ep = (playable_cnt or 0) + 1            # 源站直链范围之外的第一集（实测为第 4 集）

    section('测试 1：字段契约与基线')
    check('detail 同时给出 episode_cnt / playable_cnt / listed_cnt',
          all(isinstance(v, int) for v in (episode_cnt, playable_cnt, listed_cnt)),
          f'episode_cnt={episode_cnt} playable_cnt={playable_cnt} listed_cnt={listed_cnt}')
    check('episodes 为全量集列表', len(episodes) == episode_cnt,
          f'episodes={len(episodes)} episode_cnt={episode_cnt}')
    check('playable_cnt 未超过总集数', playable_cnt <= episode_cnt)
    check('源站直链范围内每集 playable=True 且 source=origin',
          all(_ep_state(detail, i) is True and _ep_field(detail, i, 'source') == 'origin'
              for i in range(1, playable_cnt + 1)))
    check('listed_cnt == 实际可播集数（自洽）', listed_cnt == playable_total,
          f'listed_cnt={listed_cnt} playable_total={playable_total}')
    check('source 取值只在 origin / stream 之内',
          all(item.get('source') in ('origin', 'stream')
              for item in episodes if item.get('playable')))

    # 本次修复的核心：源站直链范围之外的集，只要本站直出可用就必须判为可播，
    # 且与 play 的结论一致（此前 detail 恒为 false、play 却能拿到地址，属自相矛盾）
    if stream_on:
        check('listed_cnt == episode_cnt（直出可用时全部集数可播）',
              listed_cnt == episode_cnt, f'listed_cnt={listed_cnt} episode_cnt={episode_cnt}')
        check(f'基线：第 {ep} 集 playable=True 且 source=stream',
              _ep_state(detail, ep) is True and _ep_field(detail, ep, 'source') == 'stream',
              f'playable={_ep_state(detail, ep)} source={_ep_field(detail, ep, "source")}')
    else:
        check('直出不可用时第 %s 集判为不可播' % ep, _ep_state(detail, ep) is False,
              f'playable={_ep_state(detail, ep)}')

    section('测试 2：不污染爬虫缓存')
    raw = HongguoDramaSpider().get_detail(series)
    check('爬虫层原始结果未被就地修改（该集仍为 False）',
          _ep_state(raw, ep) is False, f'raw playable={_ep_state(raw, ep)}')
    check('爬虫层结果没有 source 字段（补标注只发生在服务层）',
          _ep_field(raw, ep, 'source') is None)
    check('爬虫层 playable_cnt 未变', raw.get('playable_cnt') == playable_cnt)

    section('测试 3：play 与 detail 口径一致')
    status, payload = utils.get_play(series, ep)
    if stream_on:
        check('play 返回可播', status == utils.PLAY_OK, f'status={status}')
        check('play 标记为本站直出且地址指向 stream 端点',
              isinstance(payload, dict) and payload.get('source') == 'stream'
              and str(payload.get('url', '')).startswith(utils.STREAM_PATH),
              f'payload={payload}')
        check('play 的 playable 与 detail 一致（都为 True）',
              isinstance(payload, dict) and payload.get('playable') is True)
        check('play 给出画质与就绪标记',
              isinstance(payload, dict) and isinstance(payload.get('quality'), int)
              and isinstance(payload.get('ready'), bool), f'payload={payload}')
    else:
        check('直出不可用时 play 返回未上架', status == utils.PLAY_NOT_LISTED,
              f'status={status} payload={payload}')

    app = UserApp.objects.create(name=f'DramaLink{MARK}')
    client = Client()
    try:
        section('测试 4：对外接口返回体（签名请求真实 HTTP）')
        resp = client.get('/api/dramas/hongguo/detail', _signed(app, {'series_id': series}))
        body = resp.json()
        data = body.get('data') or {}
        check('detail 接口 200 且业务码成功',
              resp.status_code == 200 and body.get('code') == StatusCode.SUCCESS,
              f'code={body.get("code")}')
        check('响应体 playable_cnt / listed_cnt 保持一致',
              data.get('playable_cnt') == playable_cnt
              and data.get('listed_cnt') == listed_cnt,
              f'playable_cnt={data.get("playable_cnt")} listed_cnt={data.get("listed_cnt")}')
        if stream_on:
            check(f'响应体 episodes 第 {ep} 集 source=stream',
                  _ep_field(data, ep, 'source') == 'stream',
                  f'source={_ep_field(data, ep, "source")}')

        resp = client.get('/api/dramas/hongguo/play',
                          _signed(app, {'series_id': series, 'ep': ep}))
        body = resp.json()
        play_data = body.get('data') or {}
        if stream_on:
            check('play 接口返回本站直出地址',
                  body.get('code') == StatusCode.SUCCESS
                  and play_data.get('source') == 'stream',
                  f'body={body}')
        else:
            check('play 接口返回未上架（503 + 提示文案）',
                  body.get('code') == StatusCode.SERVICE_UNAVAILABLE
                  and isinstance(body.get('msg'), str) and body.get('msg'),
                  f'body={body}')

        resp = client.get('/api/dramas/hongguo/play',
                          _signed(app, {'series_id': series, 'ep': 1}))
        first = (resp.json().get('data') or {})
        check('play 第 1 集 source=origin（与 detail 同一套取值）',
              resp.json().get('code') == StatusCode.SUCCESS and first.get('source') == 'origin',
              f'data={first}')
    finally:
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
