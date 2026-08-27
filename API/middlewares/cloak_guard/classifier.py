"""请求分类器：本地判定请求类型（Referer 优先）

判定类型 type:
    direct  - 无 Referer（直接访问），最高优先级：先看 Referer，无 Referer 即 direct
    spider  - 有 Referer 且 UA 命中搜索引擎蜘蛛（Googlebot/bingbot/baiduspider 等）
    human   - 有 Referer 且 UA 命中真实浏览器（Chrome/Firefox/Safari/Edge 等）
    unknown - 有 Referer 且 UA 命中脚本爬虫（python-requests/curl 等）或无法识别
"""
# 搜索引擎蜘蛛 UA 特征
SPIDER_UA_PATTERNS = [
    'googlebot', 'bingbot', 'baiduspider', 'yandexbot', 'duckduckbot',
    'sogou', 'sosospider', '360spider', 'bytespider', 'yisouspider',
    'slurp', 'mj12bot', 'ahrefsbot', 'semrushbot', 'seznambot', 'dotbot',
]

# 真实浏览器 UA 特征（需在脚本爬虫特征之前判断，Chrome/Edge 系 UA 均含 Chrome 字样）
HUMAN_UA_PATTERNS = [
    'chrome', 'firefox', 'safari', 'edge', 'opera', 'msie', 'trident',
]

# 脚本爬虫/程序 UA 特征
SCRIPT_UA_PATTERNS = [
    'python-requests', 'python-urllib', 'aiohttp', 'httpx', 'curl', 'wget',
    'go-http-client', 'okhttp', 'httpclient', 'java/', 'scrapy', 'urllib',
    'node-fetch', 'axios', 'postmanruntime', 'httpie', 'python',
]


def classify(request):
    """判定请求类型（Referer 优先），返回 'spider' / 'human' / 'direct' / 'unknown'"""
    ua = (request.META.get('HTTP_USER_AGENT') or '').lower()
    referer = request.META.get('HTTP_REFERER') or ''

    # 无 Referer → 直接访问（最高优先级）
    if not referer:
        return 'direct'

    # 有 Referer → 按 UA 判定
    if any(p in ua for p in SPIDER_UA_PATTERNS):
        return 'spider'
    if any(p in ua for p in HUMAN_UA_PATTERNS):
        return 'human'
    return 'unknown'
