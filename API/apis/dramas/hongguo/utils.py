"""红果短剧网页版 线路 服务层封装

对 SpiderServices.dramas.hongguo.main 中的 HongguoDramaSpider 做统一异常处理，
返回 (是否成功, 数据或错误信息) 二元组。

播放能力边界：源站 H5 只对每部剧的**前若干集**（实测 3 集）下发明文直链；第 4 集及以后
源站只给 DRM 加密的 H.265（CENC AES-CTR + 自定义 spade 密钥包装），桌面浏览器无法直接
播放（多数平台不支持 HEVC），且源站不提供明文/m3u8 通道。

因此第 4 集及以后有两条出路（play 按顺序择优）：
    1) 外部托管 + 链接登记（零成本，优先）：预处理工具解密导出 → 人工上传到外部平台
       → 超管控制台 /console/dramas/hongguo/ 登记链接（仅后台内部使用，无对外接口）
    2) 服务端「网页直出」（免人工）：/api/dramas/hongguo/stream 按需解密 + 转 H.264
       后出流。浏览器在多数机器上完全解不了源站的 HEVC（原生 / MSE / WebCodecs 实测
       三条路全断），故只能转码；产物落盘永久复用，只有被点播过的集才会转。
"""
from urllib.parse import urlparse

from django.conf import settings
from django.core import signing
from django.db import transaction

from API.models import HongguoEpisodeVideo
from SpiderServices.dramas.hongguo.main import HongguoDramaSpider
from SpiderServices.dramas.hongguo.utils import CATEGORIES, RANK_TYPES

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

# 榜单合法类型（与爬虫 RANK_TYPES 同步，供视图层做参数校验）
RANK_TYPE_VALUES = RANK_TYPES
# 分类合法 slug（取自爬虫 CATEGORIES 的键，供视图层做参数校验）
CATEGORY_VALUES = tuple(CATEGORIES)
# 允许登记的外链类型（视图层校验用）
URL_TYPES = ('mp4', 'm3u8')

# get_play 的结果标记：调用方（视图层）据此选择状态码
PLAY_OK = 'ok'                       # 可直接播放（前 3 集源站直链 / 第 4 集+ 已登记外链）
PLAY_OUT_OF_RANGE = 'out_of_range'   # 集号越界
PLAY_NOT_LISTED = 'not_listed'       # 第 4 集及以后：尚未上架外链
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
    """获取榜单（热播榜 / 真人剧榜 / AI剧榜，分页）"""
    return _run("获取榜单", lambda s: s.get_rank(rank_type, page=page))


def get_categories():
    """获取分类列表（slug -> 中文名）"""
    return _run("获取分类", lambda s: s.get_categories())


def get_list(category, page=1):
    """获取分类列表（分页）"""
    return _run("获取列表", lambda s: s.get_list(category, page=page))


def get_search(keyword, page=1):
    """关键词搜索（站点不支持分页，仅返回单页）"""
    return _run("搜索", lambda s: s.get_search(keyword, page=page))


def get_detail(series_id):
    """获取剧集详情（全量集号 + 可播集数）；剧集不存在时返回 None

    第 4 集及以后能否播，取决于**是否已登记外部链接**（见 get_play），而爬虫层只认源站
    H5 直链范围（playable_cnt 恒为前 3 集），所以在这里把登记表合并进每集的 playable。
    少了这一步：调用方会把已上架的集当成未上架 —— 给出锁标记、点不进去，
    接口新上线的能力等于接不住。

    返回的两个计数含义不同，别混用：
        playable_cnt  源站直链的**连续**范围（前 N 集），保持原义，避免影响既有调用方
        listed_cnt    **实际可播集数**（源站直链 + 已登记外链，可能不连续）
    """
    ok, data = _run("获取详情", lambda s: s.get_detail(series_id))
    if not ok or data is None:
        return ok, data

    listed = set(HongguoEpisodeVideo.objects.filter(
        series_id=str(series_id), enabled=True).values_list('ep', flat=True))

    # 重新构造而不是就地改：爬虫的返回值来自缓存，就地改可能把结果写回缓存对象
    episodes = []
    for item in data.get('episodes') or []:
        item = dict(item)
        if item.get('ep') in listed:
            item['playable'] = True
        episodes.append(item)

    data = dict(data, episodes=episodes,
                listed_cnt=sum(1 for item in episodes if item.get('playable')))
    return True, data


def get_play(series_id, ep, quality=None):
    """
    获取某集播放地址。

    前若干集（H5 可播范围）返回源站明文直链；第 4 集及以后返回已登记的外部播放地址，
    没登记则回落到本站「网页直出」（画质由 quality 指定，见 QUALITY_WIDTHS）。

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
        return PLAY_OK, data

    # 第 4 集及以后：源站只给 DRM 加密的 H.265
    # ① 已登记外部链接：优先返回（零成本，流量不经过本站）
    row = HongguoEpisodeVideo.objects.filter(
        series_id=str(series_id), ep=int(ep), enabled=True).first()
    if row is not None:
        return PLAY_OK, {
            'series_id': str(series_id),
            'ep': int(ep),
            'playable': True,
            'source': 'external',
            'url': row.url,
            'url_type': row.url_type,
        }
    # ② 未登记：走服务端「网页直出」（按需解密 + 转 H.264，产物永久复用）
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


def _parse_items(raw):
    """
    解析批量登记文本，返回 (items, errors)。

    每行一条「集号 + 分隔符 + 链接」，分隔符为 Tab / 空格 / 逗号中的**第一个**出现的，
    因此链接内部含逗号不受影响。空行忽略。
    """
    items, errors = [], []
    for lineno, line in enumerate(raw.splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        seps = [i for i in (line.find('\t'), line.find(' '), line.find(',')) if i >= 0]
        if not seps:
            errors.append(f'第 {lineno} 行缺少分隔符（应为「集号+分隔符+链接」）')
            continue
        ep_raw, url = line[:min(seps)].strip(), line[min(seps) + 1:].strip()
        if not ep_raw.isdigit() or int(ep_raw) < 1:
            errors.append(f'第 {lineno} 行集号非法: {ep_raw!r}')
            continue
        if urlparse(url).scheme not in ('http', 'https'):
            errors.append(f'第 {lineno} 行链接非法（需以 http/https 开头）')
            continue
        items.append((int(ep_raw), url))
    if not items and not errors:
        errors.append('未解析到任何有效行')
    return items, errors


def save_episode_videos(series_id, raw, url_type, series_name=''):
    """
    批量登记外部播放地址（按 series_id + ep 幂等 upsert）。

    校验采取「全量通过才写入」：任一行非法则整批不落库，避免出现半截的登记结果。

    :param raw: 批量登记文本（见 _parse_items）
    :param url_type: mp4 / m3u8
    :param series_name: 可选；为空时保留库中已有剧集名
    :return: (True, {total, created, updated}) 或 (False, 错误信息)
    """
    items, errors = _parse_items(raw)
    if errors:
        head = errors[:5]
        suffix = f'（共 {len(errors)} 处问题）' if len(errors) > len(head) else ''
        return False, '登记内容有误: ' + '；'.join(head) + suffix

    created = updated = 0
    with transaction.atomic():
        for ep, url in items:
            defaults = {'url': url, 'url_type': url_type, 'enabled': True}
            if series_name:
                defaults['series_name'] = series_name
            _, is_created = HongguoEpisodeVideo.objects.update_or_create(
                series_id=str(series_id), ep=ep, defaults=defaults)
            created += 1 if is_created else 0
            updated += 0 if is_created else 1
    return True, {'total': len(items), 'created': created, 'updated': updated}
