"""
555电影 线路 - 常量与 URL 构建

站点为苹果CMS10（MacCMS）模板的影视站，服务端渲染，无官方 API，需解析 HTML。
本模块集中管理域名、分类映射、URL 模板与 XPath 选择器，便于站点改版时统一维护。
"""

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

# 榜单分类（衍生页）
RANK_CATEGORIES = {
    13: "连续剧排行榜",
    15: "港台剧排行榜",
    44: "日韩剧排行榜",
    45: "欧美剧排行榜",
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

# ==================== URL 构建 ====================

# maccms10 列表页 URL 字段以「空段 + 横线」占位，页码位于第 9 字段：
#   第1页全部： /vodshow/1-----------.html
#   第2页：     /vodshow/1--------2---.html
#   按年份：    /vodshow/1-----------2026.html
#   按排序：    /vodshow/1--hits---------.html（time=时间 / hits=人气 / score=评分）


def build_list_url(type_id: int, page: int = 1) -> str:
    """构建分类列表页 URL（含分页）"""
    page_part = "" if page <= 1 else str(page)
    return f"{BASE_URL}/vodshow/{type_id}--------{page_part}---.html"


def build_sort_url(type_id: int, order: str, page: int = 1) -> str:
    """构建排序列表页 URL。order: time(时间) / hits(人气) / score(评分)"""
    page_part = "" if page <= 1 else str(page)
    return f"{BASE_URL}/vodshow/{type_id}--{order}-------{page_part}--.html"


def build_year_url(type_id: int, year: int, page: int = 1) -> str:
    """构建按年份筛选的列表页 URL"""
    page_part = "" if page <= 1 else str(page)
    return f"{BASE_URL}/vodshow/{type_id}---------{page_part}--{year}.html"


def build_detail_url(vod_id) -> str:
    """构建详情页 URL"""
    return f"{BASE_URL}/voddetail/{vod_id}.html"


def build_play_url(vod_id, sid, nid) -> str:
    """构建播放页 URL"""
    return f"{BASE_URL}/vodplay/{vod_id}-{sid}-{nid}.html"


def build_search_url(keyword: str) -> str:
    """构建搜索页 URL（关键词需 URL 编码，尾部固定 13 个横线）"""
    from urllib.parse import quote
    return f"{BASE_URL}/vodsearch/{quote(keyword)}-------------.html"


def build_label_url(label: str) -> str:
    """构建 label 专题页 URL（netflix / new / hot / week / topic）"""
    return f"{BASE_URL}/label/{label}.html"
