"""
红果短剧 线路 - 常量与 URL 构建

站点 https://hongguoduanju.com 为服务端渲染（SSR）的短剧 H5 站点，无对外 API。
页面数据以 JSON 内嵌在 HTML 的 <script> 脚本里（变量 _ROUTER_DATA），
且字符串中的 "/" 被转义为 "\\u002F"（少数为 "\\/"），解析前需统一反转义。

本模块集中管理域名、榜单类型、分类映射、URL 模板、SSR JSON 提取工具与解析用正则/选择器，
站点改版时优先改这里，避免散落到 main.py。

以下均为 2026-09 实际抓取验证的结论：
    榜单 /rank/{type}
        服务端渲染为 <ol class="pc-list-*"> 排名列表，每项含排名、剧名、/detail?series_id=xxx
        链接、热度文本（如 "8675万热度"）、评分、收藏数、点赞数、标签、简介。
        分页为查询串 ?page=N（第 1 页可省略），实测换页数据不同（每页 20 条）。
    分类 /category/{slug}
        列表数据内嵌在 JSON 的 "recommendList" 数组中（每页 24 条），
        分页同为 ?page=N，实测换页数据不同。
    搜索 /search/{关键词}
        关键词位于「路径段」需 URL 编码；结果内嵌在 JSON 的 "searchList" 数组中
        （每项剧集详情在 video_data 里）。实测 ?page=2 与第 1 页完全相同 →
        站点不支持搜索分页，故 get_search 只取单页。
    详情 /detail?series_id={sid}
        主剧集对象内嵌在 JSON 的 "seriesDetail" 键下；同页还含推荐位对象
        （"recommendList" / "videoList"，字段结构相似），必须按 series_id 精确取主对象，
        否则会误取到推荐剧集。
    播放 /player/{sid}/{vid}
        SSR 内嵌 "video_player_info"（main_url / duration / width / height / poster_url）。
        仅前 3 集可访问（accessible_episode_cnt=3），第 4 集起服务端直接返回 404。
"""

import json
import re
from urllib.parse import quote

# ==================== 基础配置 ====================

# 站点域名
BASE_URL = "https://hongguoduanju.com"

# 请求 UA
UA_STRING = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/153.0.0.0 Safari/537.36"
)

# 请求超时（秒）
REQUEST_TIMEOUT = 15
# 请求失败重试次数
MAX_RETRIES = 3
# 重试间隔（秒）
RETRY_DELAY = 0.5

# ==================== 榜单类型 ====================

# 榜单类型（取值即 /rank/{type} 的路径段）
RANK_TYPES = ("hot-drama", "hot-real-drama", "hot-ai-drama", "hot-comic-drama")

# ==================== 分类树 ====================

# 漫剧 / AI剧 的题材筛选条完全一致，共用一份（改一处即可，不会两边写歪）
_COMIC_AI_CHILDREN = {
    "creative": "脑洞",
    "fantasy": "玄幻",
    "drama": "剧情",
    "apocalypse": "末世",
    "wealthy-family": "豪门",
    "wonder": "奇幻",
    "sci-fi": "科幻",
    "adventure": "冒险",
}

# 两级分类树：一级 slug -> {name, children: {二级 slug -> 中文名}}
#
# 由站点各级 /category/* 页面的筛选条实际枚举所得（2026-10-01 核对）：
#   一级 4 个（真人剧 / 漫剧 / AI剧 / 漫画）；二级共 40 个（真人剧 24 + 漫剧 8 + AI剧 8 + 漫画 0）。
# 站点新增分类时需同步维护。
#
# 对外取值：一级直接给 slug（`real-drama`）；二级用「一级/二级」（`real-drama/romance`）——
# 该值同样可直接拼进 /category/{slug} 的路径。
# 二级页与一级页结构完全相同（同一个 SSR 键 recommendList），故 get_list 对两种取值走同一套解析。
CATEGORIES = {
    "real-drama": {
        "name": "真人剧",
        "children": {
            "romance": "爱情",
            "period": "年代",
            "comeback": "逆袭",
            "legend": "传奇",
            "growth": "成长",
            "family": "家庭",
            "clan": "家族",
            "cute-kids": "萌宝",
            "suspense": "悬疑",
            "thriller": "惊悚",
            "horror": "恐怖",
            "supernatural": "志怪",
            "costume": "古装",
            "fantasy": "玄幻",
            "wonder": "奇幻",
            "urban": "都市",
            "youth": "青春",
            "comedy": "喜剧",
            "sci-fi": "科幻",
            "disaster": "灾难",
            "action-adventure": "动作冒险",
            "war": "战争",
            "variety": "综艺",
            "drama": "剧情",
        },
    },
    "comic-drama": {"name": "漫剧", "children": _COMIC_AI_CHILDREN},
    "ai-drama": {"name": "AI剧", "children": _COMIC_AI_CHILDREN},
    "comic": {"name": "漫画", "children": {}},
}


def _category_options():
    """(取值, 显示名) 列表：一级用自身名，二级用「一级 · 二级」

    二级之所以带一级前缀：`剧情` / `玄幻` / `奇幻` / `科幻` 在多个一级下同时存在，
    只给二级名在文档页下拉里会分不清是哪个一级的。
    """
    options = []
    for slug, node in CATEGORIES.items():
        options.append((slug, node["name"]))
        options.extend((f"{slug}/{child}", f'{node["name"]} · {child_name}')
                       for child, child_name in node["children"].items())
    return tuple(options)


# 分类取值 -> 显示名（供文档页下拉与提示文案用）
CATEGORY_OPTIONS = _category_options()
# 全部合法 category 取值（一级 slug +「一级/二级」），供视图层做参数校验
CATEGORY_VALUES = tuple(value for value, _ in CATEGORY_OPTIONS)

# ==================== SSR 解析 ====================

# 详情页主剧集对象在 SSR JSON 中的键名（同页推荐位用 recommendList / videoList）。
# 站点改版若换键名，需同步修改 find_series_object。
SSR_KEY_DETAIL = "seriesDetail"
# 分类列表页数据数组键名
SSR_KEY_RECOMMEND_LIST = "recommendList"
# 搜索页结果数组键名
SSR_KEY_SEARCH_LIST = "searchList"
# 播放页播放信息对象键名
SSR_KEY_PLAYER_INFO = "video_player_info"

# 分页参数正则（用于从分页器链接中取最大页码作为总页数；[[?&]page=N]）
RE_PAGE_NUM = re.compile(r"[?&]page=(\d+)")

# 播放页可播集数兜底值：页面未给 accessible_episode_cnt 时使用
PLAYABLE_LIMIT_FALLBACK = 3

# ---- 榜单页 XPath 选择器 ----
# 站点用 CSS Modules，类名形如 pc-title-LHxn_J（前缀稳定、hash 后缀随构建变动），
# 故统一用 contains(@class,"pc-xxx") 匹配；站点换皮需在此维护。
#
# 注意：榜单页头部的**面包屑**是 `<ol class="pc-list-…">`，也含 "pc-list" 前缀，
# 只按 ol 的 class 取 li 会把面包屑的 2 个 <li>（首页 / 榜单名）当成第 1、2 名混进来
# （它们没有详情链接，解析出来就是 rank=1/2 且字段全空）。
# 故这里再限定「li 下必须有指向 /detail?series_id= 的链接」——榜单条目必有，面包屑必无。
_HREF_DETAIL = 'contains(@href,"/detail?series_id=")'
XP_RANK_LIST = f'//ol[contains(@class,"pc-list")]/li[.//a[{_HREF_DETAIL}]]'
XP_RANK_LINK = f'.//a[{_HREF_DETAIL}]'
XP_RANK_COVER = './/img[contains(@class,"pc-cover")]/@src'
XP_RANK_TITLE = './/h2[contains(@class,"pc-title")]//text()'
XP_RANK_HEAT = './/p[contains(@class,"pc-metrics")]//text()'
XP_RANK_ENGAGEMENT = './/ul[contains(@class,"pc-engagement")]/li'
XP_RANK_TAG = './/p[contains(@class,"pc-categories")]/span//text()'
XP_RANK_INTRO = './/p[contains(@class,"pc-description")]//text()'

# 详情页链接里的 series_id
RE_SERIES_ID = re.compile(r"/detail\?series_id=(\d+)")


# ==================== URL 构建 ====================


def build_rank_url(rank_type: str, page: int = 1) -> str:
    """构建榜单页 URL；第 1 页省略 page 参数"""
    base = f"{BASE_URL}/rank/{rank_type}"
    return base if not page or page <= 1 else f"{base}?page={page}"


def build_category_url(slug: str, page: int = 1) -> str:
    """构建分类列表页 URL；第 1 页省略 page 参数

    ``slug`` 既可是一级分类（``real-drama``），也可是「一级/二级」（``real-drama/romance``）。
    """
    base = f"{BASE_URL}/category/{slug}"
    return base if not page or page <= 1 else f"{base}?page={page}"


def build_search_url(keyword: str, page: int = 1) -> str:
    """构建搜索页 URL（关键词为路径段，需 URL 编码）；第 1 页省略 page 参数"""
    base = f"{BASE_URL}/search/{quote(keyword or '')}"
    return base if not page or page <= 1 else f"{base}?page={page}"


def build_detail_url(series_id) -> str:
    """构建详情页 URL"""
    return f"{BASE_URL}/detail?series_id={series_id}"


def build_player_url(series_id, vid) -> str:
    """构建播放页 URL（vid 取自详情页 vid_list 对应集号）"""
    return f"{BASE_URL}/player/{series_id}/{vid}"


# ==================== SSR JSON 提取工具 ====================


def unescape_ssr(text: str) -> str:
    """还原 SSR JSON 中被转义的斜杠："\\u002F" 与 "\\/" 统一还原为 "/" """
    return text.replace("\\u002F", "/").replace("\\/", "/")


def _balanced(text: str, start: int, open_ch: str, close_ch: str):
    """
    从 start（须指向 open_ch）起按括号配平截取一段 JSON 子串。

    逐字符扫描并跟踪「是否处于字符串字面量内」，可正确处理字符串里出现的括号；
    扫描到最外层括号闭合即返回。失败返回 None。
    """
    depth = 0
    in_str = False
    escaped = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == open_ch:
                depth += 1
            elif ch == close_ch:
                depth -= 1
                if depth == 0:
                    return text[start:i + 1]
    return None


def _extract_json(html: str, key: str, open_ch: str, close_ch: str):
    """按 "key":{...} / "key":[...] 形式提取并解析 JSON；找不到或解析失败返回 None"""
    text = unescape_ssr(html)
    pos = text.find(f'"{key}"')
    if pos < 0:
        return None
    start = text.find(open_ch, pos)
    if start < 0:
        return None
    raw = _balanced(text, start, open_ch, close_ch)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def extract_json_object(html: str, key: str):
    """提取形如 "key":{...} 的 JSON 对象"""
    return _extract_json(html, key, "{", "}")


def extract_json_array(html: str, key: str):
    """提取形如 "key":[...] 的 JSON 数组"""
    return _extract_json(html, key, "[", "]")


def find_series_object(html: str, series_id):
    """
    从详情页 HTML 中定位指定 series_id 的剧集对象。

    详情页主对象挂在 SSR_KEY_DETAIL（seriesDetail）键下，同页推荐位（recommendList /
    videoList）字段结构相似，因此取到后还需校验 series_id 一致，避免误取推荐剧集。
    页面不存在该剧（如无效 id，服务端返回 404 页）时返回 None。
    """
    obj = extract_json_object(html, SSR_KEY_DETAIL)
    if obj and str(obj.get("series_id")) == str(series_id):
        return obj
    return None


def extract_vid_list(obj: dict):
    """取剧集对象的全量集号数组 vid_list（统一转字符串）"""
    return [str(v) for v in (obj.get("vid_list") or [])]


def max_page(html: str):
    """从分页器链接中取最大页码作为总页数；无分页返回 None"""
    nums = [int(n) for n in RE_PAGE_NUM.findall(html)]
    return max(nums) if nums else None


# ==================== App 内部接口（H5 未下发直链的集数走这里） ====================
#
# H5 站点对每部剧只渲染前若干集（accessible_episode_cnt），第 4 集起服务端直接 404；
# 这些集只能走 App 使用的 fqnovel 内部接口。实测结论（2026-09）：
#   - 接口强制校验 metasec 安全头（X-Argus / X-Gorgon / X-Khronos / X-Ladon / X-Helios /
#     X-Medusa 等）：不带签名时 HTTP 200 但响应体为空，带合法签名返回 code=0 真实数据。
#   - 签名由本机常驻的 unidbg 签名服务生成（settings.HONGGUO_SIGN_URL），
#     不依赖模拟器 / frida。
#   - 接口对游客开放：随机但自洽的设备指纹 + 有效签名即可，无需账号登录。
#   - 返回的直链是 CENC(AES-128-CTR) 加密流，content key 由 encrypt_info.spade_a 本地解出。
# 站点/接口改版时优先改这里。

# App 接口域名
APP_API_BASE = "https://api5-normal-sinfonlinea.fqnovel.com"
# 取剧集列表（返回每集 vid）
APP_PATH_EPISODES = "/novel/player/multi_video_detail/v1/"
# 取视频轨道（返回加密直链 + encrypt_info.spade_a + kid）
APP_PATH_VIDEO_MODEL = "/novel/player/multi_video_model/v1/"

# App 版本（与签名服务内置的 aid/版本保持一致，不要随意改）
APP_VERSION_CODE = "72232"
APP_VERSION_NAME = "7.2.2.32"

# 设备指纹（游客态随机自洽值；aid=8662 为红果）
APP_QUERY = {
    "iid": "738492015682739",
    "device_id": "7384920156827390145",
    "aid": "8662",
    "app_name": "novelread",
    "version_code": APP_VERSION_CODE,
    "version_name": APP_VERSION_NAME,
    "channel": "huawei_8662_64",
    "device_platform": "android",
    "device_type": "ELS-AN00",
    "device_brand": "HUAWEI",
    "os_version": "10",
    "os_api": "29",
    "rom_version": "HUAWEIELS-AN00 release-keys",
    "resolution": "1080*2340",
    "host_abi": "arm64-v8a",
    "dpi": "480",
    "update_version_code": APP_VERSION_CODE,
    "manifest_version_code": APP_VERSION_CODE,
    "cdid": "3f0d9a52-8c41-4f2b-9e77-1a6c5d8b2e34",
    "klink_egdi": "0f1e2d3c4b5a69788796a5b4c3d2e1f0",
    "language": "zh",
}

# 固定会话头（游客态，无 cookie / x-tt-token）
APP_HEADERS = {
    "user-agent": (f"com.phoenix.read/{APP_VERSION_CODE} (Linux; U; Android 10; zh_CN; "
                   "ELS-AN00; Build/HUAWEIELS-AN00;tt-ok/3.12.13.20)"),
    "x-tt-store-region": "cn-gd",
    "x-tt-store-region-src": "did",
    "passport-sdk-version": "5051452",
    "sdk-version": "2",
}

# 取剧集列表的请求体（biz_param 为 App 抓包固定值）
APP_EPISODES_BIZ_PARAM = {
    "detail_page_version": 0, "disable_digg_stat": False, "disable_video_relate_book": False,
    "need_all_video_definition": False, "need_mp4_align": False, "screen_width_px": "900",
    "source": 7, "use_os_player": False, "use_server_dns": False,
}

# 取视频轨道的请求体（need_all_video_definition=True 才会下发全部清晰度）
APP_MODEL_BIZ_PARAM = {
    "detail_page_version": 0, "device_level": 3, "disable_digg_stat": False,
    "disable_video_relate_book": False, "need_all_video_definition": True,
    "need_mp4_align": False, "use_os_player": False, "use_server_dns": False,
    "video_platform": 1024,
}

# 单次批量取的 vid 数量（App 真实批量大小；过大易触发风控）
APP_VID_BATCH = 5
