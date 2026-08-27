"""UA 特征库（独立维护文件）

集中维护浏览器 / 搜索引擎蜘蛛 / 脚本爬虫 三类 User-Agent 特征正则，
供 API.apis.request_detect.utils 导入使用。

分类说明:
    BROWSER_UA_PATTERNS - 真人浏览器特征（Chrome/Edge/Firefox/Safari），判定为 type=human
    SPIDER_UA_PATTERNS  - 搜索引擎蜘蛛特征（Googlebot/bingbot 等），判定为 type=spider
    SCRIPT_UA_PATTERNS  - 脚本/恶意爬虫特征（python-requests/curl 等），判定为 type=unknown

特征来源:
    项目自建 + 参考 static/js/beacon.min.js 的爬虫特征列表补充
    （yandexbot/duckduckbot/sosospider/360spider/slurp/mj12bot/ahrefsbot/semrushbot/seznambot/dotbot 等）

匹配顺序（由调用方保证）: 蜘蛛 -> 脚本 -> 浏览器，命中即停。
"""

# 浏览器特征: (识别名称, 正则)，按优先级排列
# Chrome/Edge/Firefox 均带自身标识；Safari 需排除 Chrome 伪装（Chrome UA 也含 Safari 字样）
BROWSER_UA_PATTERNS = [
    ('Chrome', r'Chrome/[\d.]+'),
    ('Edge', r'Edg/[\d.]+'),
    ('Firefox', r'Firefox/[\d.]+'),
    ('Safari', r'Safari/[\d.]+'),
]

# 搜索引擎蜘蛛特征: (识别名称, 正则)
SPIDER_UA_PATTERNS = [
    ('Googlebot', r'googlebot'),
    ('bingbot', r'bingbot'),
    ('Baiduspider', r'baiduspider'),
    ('YandexBot', r'yandexbot'),
    ('DuckDuckBot', r'duckduckbot'),
    ('Sogou 蜘蛛', r'sogou\s*(web\s*)?spider'),
    ('SosoSpider', r'sosospider'),
    ('360Spider', r'360spider'),
    ('Bytespider', r'bytespider'),
    ('YisouSpider', r'yisouspider'),
    ('Yahoo Slurp', r'slurp'),
    ('MJ12bot', r'mj12bot'),
    ('AhrefsBot', r'ahrefsbot'),
    ('SemrushBot', r'semrushbot'),
    ('SeznamBot', r'seznambot'),
    ('DotBot', r'dotbot'),
    # 兜底: 通用爬虫标识（放在最后，避免误伤浏览器 UA）
    ('通用爬虫标识', r'(crawler|spider)'),
]

# 脚本/恶意爬虫特征: (识别名称, 正则)
SCRIPT_UA_PATTERNS = [
    ('python-requests', r'python-requests'),
    ('urllib', r'python-urllib'),
    ('httpx', r'(^|[\s/])httpx'),
    ('scrapy', r'scrapy'),
    ('curl', r'curl/'),
    ('wget', r'wget/'),
    ('Go http', r'Go-http-client'),
    ('Java', r'(Java/|okhttp|httpclient)'),
    ('node-fetch', r'node-fetch'),
    ('axios', r'axios'),
    ('Postman', r'PostmanRuntime'),
    ('无头浏览器', r'HeadlessChrome'),
    ('PhantomJS', r'PhantomJS'),
]
