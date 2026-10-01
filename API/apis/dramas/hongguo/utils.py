"""红果短剧网页版 线路 服务层封装

对 SpiderServices.dramas.hongguo.main 中的 HongguoDramaSpider 做统一异常处理，
返回 (是否成功, 数据或错误信息) 二元组。

播放能力边界：源站 H5 只对每部剧的**前若干集**（实测 3 集）下发明文直链；第 4 集及以后
源站只给 DRM 加密的 H.265（CENC AES-CTR + 自定义 spade 密钥包装），桌面浏览器无法直接
播放（多数平台不支持 HEVC），且源站不提供明文/m3u8 通道。

因此第 4 集及以后走**服务端「网页直出」**：/api/dramas/hongguo/stream 按需解密 + 转
H.264 后出流。浏览器在多数机器上完全解不了源站的 HEVC（原生 / MSE / WebCodecs 实测
三条路全断），故只能转码；产物落盘永久复用，只有被点播过的集才会转。
"""
from django.conf import settings
from django.core import signing

from SpiderServices.dramas.hongguo.main import HongguoDramaSpider
from SpiderServices.dramas.hongguo.utils import (
    CATEGORY_OPTIONS,   # noqa: F401  （文档页下拉用，经本模块转出）
    CATEGORY_VALUES,
    RANK_TYPES,
)

# 「网页直出」播放地址的时效令牌：<video> 标签没法带项目签名，故用 Django 签名令牌自证，
# 令牌里只放 series_id / ep / 画质，过期时间由 max_age 控制（见 settings.HONGGUO_STREAM_TOKEN_TTL）。
STREAM_TOKEN_SALT = 'hongguo.stream'
STREAM_PATH = '/api/dramas/hongguo/stream'

# 「网页直出」可选画质：值 = 输出**宽度**上限（短剧是竖屏 1080×1920，日常说的 1080p / 720p
# 就指宽度），档位与源站轨道一一对应。转码侧的码率上限表在
# SpiderServices/dramas/hongguo/transcode.py 的 _RATE_BY_WIDTH，两处必须同步。
QUALITY_WIDTHS = (1080, 720, 540, 480, 360)
# 默认画质（不传 q 时用）：可在 .env 用 HONGGUO_STREAM_QUALITY 覆盖
DEFAULT_QUALITY = int(getattr(settings, 'HONGGUO_STREAM_QUALITY', 1080))

# 参数白名单（均与爬虫同源，供视图层做参数校验）：
#   榜单 RANK_TYPE_VALUES  —— hot-drama / hot-real-drama / hot-ai-drama / hot-comic-drama
#   分类 CATEGORY_VALUES   —— 一级 slug（real-drama）或「一级/二级」（real-drama/romance）
RANK_TYPE_VALUES = RANK_TYPES

# get_play 的结果标记：调用方（视图层）据此选择状态码
PLAY_OK = 'ok'                       # 可直接播放（源站直链 / 本站网页直出）
PLAY_OUT_OF_RANGE = 'out_of_range'   # 集号越界
PLAY_NOT_LISTED = 'not_listed'       # 第 4 集及以后且本站直出不可用
PLAY_ERROR = 'error'                 # 取数失败

# 「尚未上架」时的提示文案
NOT_LISTED_MSG = ('该集暂未上架：暂无可用播放地址。我们正在扩展存储空间，'
                  '后续会上架更多短剧，敬请期待。')


def parse_quality(raw):
    """校验「网页直出」画质参数（q）

    空值用默认档；非白名单值一律拒绝 —— 画质会进产物路径，放任任意数值等于让人
    用不同 q 把我们磁盘刷满。
    :return: (True, width) 或 (False, 错误提示)
    """
    raw = (raw or '').strip()
    if not raw:
        return True, DEFAULT_QUALITY
    try:
        width = int(raw)
    except (TypeError, ValueError):
        return False, f'参数格式错误: q 必须为整数（可选 {" / ".join(str(w) for w in QUALITY_WIDTHS)}）'
    if width not in QUALITY_WIDTHS:
        return False, f'参数值非法: q 只支持 {" / ".join(str(w) for w in QUALITY_WIDTHS)}'
    return True, width


def make_stream_token(series_id, ep, width):
    """生成「网页直出」播放地址的时效令牌（<video> 无法携带项目签名，故用签名令牌自证）

    画质写进令牌：出流端点只有 token 一个参数，画质跟着令牌走就不会被 URL 上的手工改写影响。
    """
    return signing.dumps({'sid': str(series_id), 'ep': int(ep), 'w': int(width)},
                         salt=STREAM_TOKEN_SALT, compress=True)


def parse_stream_token(token):
    """校验并解出令牌内容

    :return: (payload, None) 或 (None, 错误提示)
    """
    if not token:
        return None, '缺少播放令牌'
    try:
        data = signing.loads(token, salt=STREAM_TOKEN_SALT,
                             max_age=int(getattr(settings, 'HONGGUO_STREAM_TOKEN_TTL', 7200)))
    except signing.SignatureExpired:
        return None, '播放地址已过期，请重新获取'
    except signing.BadSignature:
        return None, '播放地址无效'
    series_id, ep = data.get('sid'), data.get('ep')
    if not series_id or not ep:
        return None, '播放地址无效'
    # 老令牌（本次改动之前签发的）没有 w，按默认画质处理即可 —— 它们 2 小时内自然过期
    return {'series_id': str(series_id), 'ep': int(ep),
            'w': int(data.get('w') or DEFAULT_QUALITY)}, None


def _run(action, fn):
    """
    执行爬虫操作，统一异常处理。

    :param action: 操作名称（用于错误提示前缀）
    :param fn: 接收爬虫实例的回调
    :return: tuple[bool, Any] (True, data) 或 (False, message)
    """
    spider = HongguoDramaSpider()
    try:
        return True, fn(spider)
    except Exception as e:
        return False, f"{action}失败: {e}"


def get_rank(rank_type='hot-drama', page=1):
    """获取榜单（热播榜 / 真人剧榜 / AI剧榜 / 漫剧榜，分页）"""
    return _run("获取榜单", lambda s: s.get_rank(rank_type, page=page))


def get_categories():
    """获取分类树（一级 -> 二级题材，每个节点都是一个可用的 category 取值）"""
    return _run("获取分类", lambda s: s.get_categories())


def get_list(category, page=1):
    """获取分类列表（分页）

    :param category: 一级取值（real-drama）或「一级/二级」（real-drama/romance）
    """
    return _run("获取列表", lambda s: s.get_list(category, page=page))


def get_search(keyword, page=1):
    """关键词搜索（站点不支持分页，仅返回单页）"""
    return _run("搜索", lambda s: s.get_search(keyword, page=page))


def get_detail(series_id):
    """获取剧集详情（全量集号 + 可播集数）；剧集不存在时返回 None

    ``episodes[].playable`` 的口径与 :func:`get_play` **完全一致** —— 两条路任一可用即为
    true，并额外用 ``source`` 标出走的哪条路：

        origin    源站明文直链（前若干集）
        stream    本站「网页直出」（按需解密 + 转 H.264）

    爬虫层只认源站 H5 直链范围（前 3 集），所以这里要把直出能力补进去。少这一步
    就会出现「detail 说不能播、play 说能播」的自相矛盾：调用方给该集打上锁标记、点不进去，
    接口明明有能力，前端却接不住。

    两个计数含义不同，别混用：
        playable_cnt  源站直链的**连续**范围（前 N 集），保持原义，避免影响既有调用方
        listed_cnt    **实际可播集数**（= playable 为 true 的集数）
    """
    ok, data = _run("获取详情", lambda s: s.get_detail(series_id))
    if not ok or data is None:
        return ok, data

    # 本站「网页直出」是否可用。settings 里 HONGGUO_STREAM_DIR 有默认值，正常部署恒为可用；
    # 取不到目录（如测试环境显式清空）时不下发 stream，免得承诺一个给不出的地址。
    stream_enabled = bool(getattr(settings, 'HONGGUO_STREAM_DIR', ''))

    # 重新构造而不是就地改：爬虫的返回值来自缓存，就地改可能把结果写回缓存对象
    episodes = []
    for item in data.get('episodes') or []:
        item = dict(item)
        if item.get('playable'):
            item['source'] = 'origin'
        elif stream_enabled:
            item['playable'], item['source'] = True, 'stream'
        episodes.append(item)

    data = dict(data, episodes=episodes,
                listed_cnt=sum(1 for item in episodes if item.get('playable')))
    return True, data


def get_play(series_id, ep, quality=None):
    """
    获取某集播放地址。

    前若干集（H5 可播范围）返回源站明文直链；第 4 集及以后返回本站「网页直出」地址
    （画质由 quality 指定，见 QUALITY_WIDTHS）。

    payload 的 ``source`` 标注走的哪条路（取值与 detail 的 episodes[].source 一致）：
    ``origin`` 源站直链 / ``stream`` 本站直出。

    :return: (status, payload)
        - PLAY_OK           payload 为播放数据 dict
        - PLAY_OUT_OF_RANGE payload 为 None（集号越界）
        - PLAY_NOT_LISTED   payload 为提示文案
        - PLAY_ERROR        payload 为错误信息
    """
    width = int(quality or DEFAULT_QUALITY)
    ok, data = _run("获取播放地址", lambda s: s.get_play(series_id, ep))
    if not ok:
        return PLAY_ERROR, data
    if data is None:                      # 爬虫对超出总集数的集号返回 None
        return PLAY_OUT_OF_RANGE, None
    if data.get('playable'):              # 源站下发明文直链（前若干集）
        # source 与 detail 的 episodes[].source 同一套取值，调用方不必两处各判一套
        return PLAY_OK, {**data, 'source': 'origin'}

    # 第 4 集及以后：源站只给 DRM 加密的 H.265，走服务端「网页直出」
    #（按需解密 + 转 H.264，产物永久复用）
    from SpiderServices.dramas.hongguo import transcode
    if not getattr(settings, 'HONGGUO_STREAM_DIR', ''):
        return PLAY_NOT_LISTED, NOT_LISTED_MSG
    token = make_stream_token(series_id, ep, width)
    return PLAY_OK, {
        'series_id': str(series_id),
        'ep': int(ep),
        'playable': True,
        'source': 'stream',
        'url': f'{STREAM_PATH}?token={token}',
        'url_type': 'mp4',
        # 出流画质（输出宽度上限，竖屏即 1080/720… 档）；换画质要重新调本接口换新地址
        'quality': width,
        # False 表示该画质首次被点播、服务端正在转码（约数十秒），前端轮询 HEAD 该地址，
        # 返回 200 即可播放
        'ready': transcode.is_ready(series_id, ep, width),
    }

