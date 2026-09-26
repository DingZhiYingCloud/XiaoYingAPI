"""
555电影 线路 - 常量与 URL 构建

站点为苹果CMS10（MacCMS）模板的影视站，服务端渲染，无官方 API，需解析 HTML。
本模块集中管理域名、分类映射、URL 模板与 XPath 选择器，便于站点改版时统一维护。
"""
import re
from urllib.parse import quote, unquote

# ==================== 基础配置 ====================

# 站点域名
BASE_URL = "https://5dy4.vip"

# 请求 UA
UA_STRING = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/153.0.0.0 Safari/537.36"
)

# 请求超时（秒）
REQUEST_TIMEOUT = 15
# 请求失败重试次数（站点多 IP 轮询，偶发连接中断需重试）
MAX_RETRIES = 3
# 重试间隔（秒）
RETRY_DELAY = 0.5

# ==================== 分类映射 ====================

# 主分类（影视四大类 + 福利 + 擦边短剧）
MAIN_CATEGORIES = {
    1: "电影",
    2: "连续剧",
    3: "综艺纪录",
    4: "动漫",
    124: "福利",
    126: "擦边短剧",
}

# 连续剧的子分类：站点导航里挂在连续剧下，本质也是「列表」接口可直接用的 type_id
SUB_CATEGORIES = {
    13: "热门连续剧",
    15: "港台剧",
    44: "日韩剧",
    45: "欧美剧",
    125: "短剧",
}

# 首页 label 专题页
LABELS = {
    "netflix": "Netflix 专区",
    "new": "今日更新",
    "hot": "排行榜",
    "week": "追剧周表",
    "topic": "专题列表",
}

# 播放页 URL 中的 sid 顺序不可预测，集数链接以详情页 HTML 中的 href 为准

# ==================== XPath 选择器 ====================

# ---- 列表页（.module-poster-item）----
XP_LIST_ITEM = '//a[contains(@class,"module-poster-item")]'
XP_ITEM_PIC = './/div[contains(@class,"module-item-pic")]/img'
XP_ITEM_NOTE = './/div[contains(@class,"module-item-note")]'
XP_ITEM_DOUBAN = './/div[contains(@class,"module-item-douban")]'
XP_ITEM_TITLE = './/div[contains(@class,"module-poster-item-title")]'

# ---- 搜索页（.module-card-item，与列表页选择器不同）----
# 仅取卡片容器的直接子项，避免匹配到 .module-card-items（外层）
XP_SEARCH_ITEM = ('//div[contains(@class,"module-card-items")]'
                  '/div[contains(@class,"module-card-item")]')
XP_SEARCH_LINK = './/a[contains(@class,"module-card-item-poster")]'
XP_SEARCH_TITLE = './/div[contains(@class,"module-card-item-title")]//text()'
XP_SEARCH_CLASS = './/div[contains(@class,"module-card-item-class")]'

# ---- 详情页 ----
XP_DETAIL_TITLE = '//h1/text()'
XP_DETAIL_INTRO = '//div[contains(@class,"module-info-introduction")]//text()'
# 仅取 info 容器的直接子项，避免匹配到 .module-info-items（外层）与 .module-info-item-content（值）
XP_DETAIL_INFO_ITEM = ('//div[contains(@class,"module-info-items")]'
                       '/div[contains(@class,"module-info-item")]')
# 选集：每个播放源一个容器，内含该源的剧集链接
XP_PLAY_SOURCES = '//div[contains(@class,"module-play-list-content")]'
XP_PLAY_LINK = './/a[contains(@class,"module-play-list-link")]'
XP_PLAY_TAB = '//div[contains(@class,"module-tab-item") and contains(@class,"tab-item")]'

# ---- 分页 ----
XP_PAGE_LINK = '//a[contains(@class,"page-link")]'

# ---- 筛选区（列表页顶部的 分类/地区/题材/语言/年份/排序 选项）----
XP_FILTER_LINK = '//div[contains(@class,"module-class-item")]//a[contains(@href,"/vodshow/")]'

# ==================== URL 构建 ====================

# 列表页字段布局：
# 苹果CMS10 的 /vodshow/ 列表页把筛选条件压进一串横线分段，共 12 段（第 1 段是分类 id）。
# 2026-09 实测（type 1/2/3/4/126 一致）：只有下面这些段承载筛选，其余段恒空。
URL_FIELD_COUNT = 12
FIELD_TYPE = 1      # 分类 id（主分类，或 13/125 这类子分类）
FIELD_AREA = 2      # 地区
FIELD_ORDER = 3     # 排序：time 时间 / hits 人气 / score 评分
FIELD_GENRE = 4     # 题材
FIELD_LANG = 5      # 语言
FIELD_PAGE = 9      # 页码（第 1 页留空）
FIELD_YEAR = 12     # 年份

# 对外暴露的筛选分组：(字段段号, 接口字段名, 中文名)；顺序即展示顺序。
# 「分类」组的值是分类 id，回传给 type_id；其余组的值回传给同名筛选参数。
FILTER_GROUPS = (
    (FIELD_TYPE, 'type', '分类'),
    (FIELD_AREA, 'area', '地区'),
    (FIELD_GENRE, 'genre', '题材'),
    (FIELD_LANG, 'lang', '语言'),
    (FIELD_YEAR, 'year', '年份'),
    (FIELD_ORDER, 'order', '排序'),
)

# 段号 -> 接口字段名（解析筛选链接时按「与基础 URL 的差异段」归类）
FIELD_KEYS = {idx: key for idx, key, _ in FILTER_GROUPS}
# 接口字段名 -> 中文名
FIELD_LABELS = {key: label for _, key, label in FILTER_GROUPS}

# ==================== URL 构建 ====================


def encode_value(value) -> str:
    """把筛选值编码进 URL（中文值需百分号编码，站点自身链接也是这种形式）"""
    return quote(str(value).strip()) if value else ''


def decode_value(value: str) -> str:
    """还原链接里的百分号编码（与 encode_value 互逆）"""
    return unquote(value or '')


def build_list_url(type_id, page: int = 1, order: str = None, year=None,
                   area=None, genre=None, lang=None) -> str:
    """构建分类列表页 URL；地区 / 题材 / 语言 / 年份 / 排序 / 页码 可任意组合"""
    parts = [''] * URL_FIELD_COUNT
    parts[FIELD_TYPE - 1] = str(type_id)
    parts[FIELD_AREA - 1] = encode_value(area)
    parts[FIELD_ORDER - 1] = order or ''
    parts[FIELD_GENRE - 1] = encode_value(genre)
    parts[FIELD_LANG - 1] = encode_value(lang)
    parts[FIELD_PAGE - 1] = str(page) if page and page > 1 else ''
    parts[FIELD_YEAR - 1] = str(year) if year else ''
    return f"{BASE_URL}/vodshow/{'-'.join(parts)}.html"


def split_list_url(href: str):
    """从 /vodshow/....html 链接里取出 12 段字段；不是该形态返回 None"""
    m = re.search(r"/vodshow/([^/?#]+?)\.html", href or "")
    if not m:
        return None
    parts = m.group(1).split('-')
    return parts if len(parts) == URL_FIELD_COUNT else None


def build_detail_url(vod_id) -> str:
    """构建详情页 URL"""
    return f"{BASE_URL}/voddetail/{vod_id}.html"


def build_play_url(vod_id, sid, nid) -> str:
    """构建播放页 URL"""
    return f"{BASE_URL}/vodplay/{vod_id}-{sid}-{nid}.html"


def build_search_url(keyword: str) -> str:
    """构建搜索页 URL（关键词需 URL 编码，尾部固定 13 个横线）"""
    return f"{BASE_URL}/vodsearch/{quote(keyword)}-------------.html"


def build_label_url(label: str) -> str:
    """构建 label 专题页 URL（netflix / new / hot / week / topic）"""
    return f"{BASE_URL}/label/{label}.html"
