import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

# S-08 整改：SECRET_KEY 必须通过 .env 提供，拒绝公开已知兜底值
# （SECRET_KEY 现同时用于 app_secret 密文派生密钥，缺失即视为配置错误直接退出）
SECRET_KEY = os.getenv('SECRET_KEY')
if not SECRET_KEY:
    raise ImproperlyConfigured(
        '缺少 SECRET_KEY：请在项目 .env 中配置 SECRET_KEY 后启动。'
        '该密钥用于 Django 签名及 S-06 凭据加密派生，请使用 50+ 位随机串并妥善备份。'
    )

DEBUG = os.getenv('DEBUG', 'False').lower() in ('true', '1', 'yes')

# S-08 整改：ALLOWED_HOSTS 缺省不再使用通配 '*'（生产必须显式声明访问域名/IP），
# 未配置时仅允许本机回环，避免错误 Host 头被放行
_ALLOWED_RAW = os.getenv('ALLOWED_HOSTS', '')
if _ALLOWED_RAW:
    ALLOWED_HOSTS = [h.strip() for h in _ALLOWED_RAW.split(',') if h.strip()]
else:
    ALLOWED_HOSTS = ['127.0.0.1', 'localhost']

# 跨域设置
SECURE_CROSS_ORIGIN_OPENER_POLICY = "None"
# 跨域请求配置，允许所有源的跨域请求（由 .env 中 CORS_ORIGIN_ALLOW_ALL 控制）
CORS_ORIGIN_ALLOW_ALL = os.getenv('CORS_ORIGIN_ALLOW_ALL', 'False').lower() in ('true', '1', 'yes')


# 应用定义配置
# https://docs.djangoproject.com/en/5.2/ref/settings/#installed-apps

INSTALLED_APPS = [
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'corsheaders', # 跨域请求中间件
    'API.apps.ApiConfig', # 自定义API应用配置,用来处理API服务相关的请求和响应
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware', # 全站批量设置安全相关 HTTP 响应头，防御多种浏览器层面攻击，是全站安全第一道防线
    'whitenoise.middleware.WhiteNoiseMiddleware', # 生产模式静态文件服务（Django 5.1+ 的 serve() 视图在 DEBUG=False 时返回 400，WhiteNoise 为官方推荐替代）
    'django.contrib.sessions.middleware.SessionMiddleware', # 实现 Django 会话（Session）机制，维护用户服务端状态。
    'django.middleware.locale.LocaleMiddleware', # 国际化：按 URL 参数/Cookie 激活当前语言（必须在 Session 之后、Common 之前）
    'corsheaders.middleware.CorsMiddleware', # 跨域请求中间件
    'django.middleware.common.CommonMiddleware', # 用来处理如日志记录、请求计数等通用任务的中间件
    'API.common.middleware.ApiCsrfExemptMiddleware', # CSRF 防护（S-07 整改）：/admin/ 等非 API 页面恢复校验，/api/ 前缀豁免（走签名认证）
    'django.contrib.auth.middleware.AuthenticationMiddleware', # 认证中间件,用来处理用户认证相关的请求和响应
    # 文档中心：/docs/* 请求自动生成左侧服务菜单（注入 request.docs_menu）。
    # 必须排在 AuthenticationMiddleware 之后：菜单需按查看者身份过滤「仅专属管理员」的服务 / 端点。
    'API.website.docs_menu.DocsMenuMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware', # 消息中间件,用来处理消息相关的请求和响应
    'django.middleware.clickjacking.XFrameOptionsMiddleware', # 用来处理点击劫持攻击的中间件
    'API.common.middleware.ApiRequestLogMiddleware', # 请求日志（A-05）+ 调用统计（A-03）：必须在认证中间件之前，认证被拒的请求也要记录
    'API.common.middleware.IPBanMiddleware', # IP 封禁：/api/ 命中即返回「IP 已被封禁」，网页侧只标记（顶部横幅提示）；在认证之前，被封请求不走签名校验
    'API.common.middleware.ApiAuthMiddleware', # API 服务认证中间件：按服务策略（服务→线路→端点，逐级继承）决定哪些 /api/ 服务需用户中心签名认证
    'API.common.middleware.ApiJsonErrorMiddleware', # /api/ 路径 404 / 405 统一返回 JSON（兜底）
]


# ==================== API 服务策略缓存（认证判定） ====================
# ApiAuthMiddleware 每个 /api/ 请求都要做一次服务策略前缀匹配，故用进程内 TTL 缓存
# 避免请求级 DB 查询（默认 60s）。后台保存/删除策略、改动白名单后由 API/apps.py 的信号
# 立即失效，改动对鉴权即时生效，无需等 TTL。设为 0 可关闭缓存（不推荐，会逐请求查库）。
API_SERVICE_POLICY_CACHE_TTL = 60


# ==================== 环境模式与安全 Cookie 配置（单一开关） ====================
# 通过 .env 的 XYAPI_COOKIE_ISOLATION 一个参数同时控制"本地/生产"两种模式：
#   - 开启（XYAPI_COOKIE_ISOLATION=true）→ 本地开发模式：
#       本机多项目共存时使用独立 Cookie 名（xyapi_sessionid/xyapi_csrftoken），
#       避免与其它监听 127.0.0.1 的服务互相覆盖导致后台被迫重新登录；
#       Cookie 不强制 Secure（本地 HTTP 访问）
#   - 关闭（默认，生产部署不设置该参数）→ 生产模式：
#       单项目部署无 Cookie 冲突，使用标准 Cookie 名；
#       强制 HTTPS(Secure Cookie)，防止会话被中间人窃取劫持
COOKIE_ISOLATION = os.getenv('XYAPI_COOKIE_ISOLATION', 'false').lower() in ('true', '1', 'yes')

# 全局会话安全基线（Django 默认值，显式声明以明确行为）
SESSION_COOKIE_HTTPONLY = True   # 会话 Cookie 禁止 JS 读取（防 XSS 窃取会话）
SESSION_COOKIE_SAMESITE = 'Lax'  # 限制跨站请求携带会话 Cookie
CSRF_COOKIE_SAMESITE = 'Lax'     # 限制跨站请求携带 CSRF Cookie
# 注：CSRF_COOKIE_HTTPONLY 保持 Django 默认 False——csrftoken 非会话凭证，
# 前端 JS 可能需要读取以用于 AJAX 请求，强制 HttpOnly 反而破坏正常功能。

if COOKIE_ISOLATION:
    # 本地开发：多项目共存时使用独立 Cookie 名，避免互相覆盖
    SESSION_COOKIE_NAME = 'xyapi_sessionid'
    CSRF_COOKIE_NAME = 'xyapi_csrftoken'
else:
    # 生产模式：标准 Cookie 名 + 强制 HTTPS Cookie，防会话劫持
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    # 部署于 nginx 反代之后时，声明可信来源协议头（nginx 需设置 X-Forwarded-Proto: https）
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    # 若 Django 直接对外（无 nginx 反代），可开启强制 HTTPS 跳转；反代场景由 nginx 负责跳转
    # SECURE_SSL_REDIRECT = True

ROOT_URLCONF = 'XiaoYingAPI.urls'

# ==================== 国际化（i18n）：界面与 API 文档多语言 ====================
# 语言来源：?lang=xx（切换视图会写入 Cookie 记住选择），默认简体中文。
# 新增语言的完整步骤见 locale/多语言开发指南.md，要点：
#   1) LANGUAGES 增加一项；
#   2) 新建 locale/<to_locale 形式>/LC_MESSAGES/{django.po,djangojs.po} 提供译文
#      （语言码连字符变下划线、地区首字母大写，如 zh-hant → zh_Hant、pt-br → pt_BR）；
#   3) 执行 python scripts/compile_locale.py 编译出 .mo（Django 运行时只读 .mo）。
# 注：页头语言下拉的名称取 name_local（语言的本族语写法），不使用此处的中文名。
USE_I18N = True
LANGUAGE_CODE = 'zh-hans'
LANGUAGES = [
    ('zh-hans', '简体中文'),
    ('zh-hant', '繁體中文'),
    ('en', 'English'),
]
# 语言 Cookie 名跟随 Cookie 隔离开关，避免本机多项目互相覆盖语言选择
LANGUAGE_COOKIE_NAME = 'xyapi_language' if COOKIE_ISOLATION else 'django_language'
LANGUAGE_COOKIE_AGE = 60 * 60 * 24 * 365
LOCALE_PATHS = [BASE_DIR / 'locale']

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        # 全局模板目录:用于覆盖 Django 内置模板(如 admin/base_site.html 自定义 favicon)
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                # 官网前台登录态（会话驱动），供全站模板（导航/页脚等）判断是否已登录
                'API.website.context.website_user',
                # 页脚友情链接（取自 SEO 友情链接模块的启用项）
                'API.website.context.friend_links',
                # 页脚「联系我们」（取自官网接入项目在后台「联系方式」模块里维护的平台与值）
                'API.website.context.footer_contacts',
                # 官网外观（视觉气质预设 + 首页 Hero 文案覆盖），超管在 /console/appearance/ 维护
                'API.website.context.site_appearance',
                # IP 封禁提示条（命中封禁时前台顶部显示原因与到期时间，见 API/common/ip_guard.py）
                'API.website.context.ip_ban_notice',
                # 文档中心左侧服务菜单（仅 /docs/* 由中间件注入）
                'API.website.docs_menu.docs_menu_context',
                # 控制台左侧导航（仅 /console/* 注入，菜单在 console_menu.py 一处声明）
                'API.website.console_menu.console_menu_context',
            ],
        },
    },
]

WSGI_APPLICATION = 'XiaoYingAPI.wsgi.application'


# 数据库配置
# https://docs.djangoproject.com/en/5.2/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
        # 提升 SQLite 并发写容错：等待写锁最长 20 秒，避免批量/并发导入时报 database is locked
        'OPTIONS': {'timeout': 20},
        # 单元测试使用独立文件库：Django 默认的内存共享库在并发写场景下会立即报锁错误（不走等待），
        # 文件库的写锁排队行为正常，保证并发导入测试稳定
        'TEST': {'NAME': BASE_DIR / 'test_db.sqlite3'},
    }
}


# 密码验证配置
# https://docs.djangoproject.com/en/5.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# 时区配置（界面语言/国际化见上方「国际化（i18n）」配置块）
# https://docs.djangoproject.com/en/5.2/topics/i18n/

TIME_ZONE = 'Asia/Shanghai' # 上海时间

USE_TZ = True # 开启时区支持


# 静态文件配置,比如CSS,JavaScript,Images等
# https://docs.djangoproject.com/en/5.2/howto/static-files/

STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'static')

# ==================== 静态文件交付（性能优化） ====================
# Django 默认的 StaticFilesStorage 既不压缩也不加内容哈希：
#   - output.css 以 660KB 原样下发（gzip 后仅 68KB，压缩比 10.3%）；
#   - 文件名无哈希时 WhiteNoise 只给 max-age=60s，浏览器几乎每次切页都要回源校验。
# 换成 CompressedManifestStaticFilesStorage 后：
#   - 预压缩并优先下发 .gz（本机未装 brotli，故只有 gzip；装了 brotli 会自动多出 .br）；
#   - 文件名带内容哈希 → 可安全长期缓存（immutable），改文件即换 URL，无需再手工改 ?v=。
# 注意：**部署必须执行 python manage.py collectstatic --noinput --clear**，
#       否则线上找不到哈希清单会直接报错（清册见 .gitignore 第 66-70 行的说明）。
# DEBUG=True 时 Django 会跳过哈希（{% static %} 仍返回原文件名），本地开发不受影响。
STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage'},
}


# 默认主键字段类型配置
# https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# 媒体文件配置
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# 站点对外基础地址（scheme://host，不要带结尾斜杠），如 https://xiaoyingapi.com
# 用途：在没有 request 的场景（后台线程）把站内相对地址（如 /media/uploads/...）拼成
# 公网可访问的绝对地址 —— 目前只作为「问题反馈」送审附件的兜底：反馈附件默认从本地读出
# 后内联给审核模型（见 API/apis/feedback/ai.py 的 _read_attachment），只有体积超过内联上限
# 的超大视频才需要拼公网地址让上游抓取。留空不会退化成「不审附件」，只是那类超大视频会被跳过。
SITE_URL = (os.getenv('XYAPI_SITE_URL') or '').strip().rstrip('/')


# ==================== 影视爬虫缓存（按「服务 + 线路」分目录） ====================
# 缓存根目录：cache/<服务>/<线路>/，各服务与线路的缓存互不干扰。
# 例如电影服务的 555 线路：cache/movies/movie_555/
# 后续新增线路（movie_iqiyi / movie_tencent 等）时，在 CACHES 中新增一个同结构项即可。
XYAPI_CACHE_ROOT = Path(os.getenv('XYAPI_CACHE_ROOT') or BASE_DIR / 'cache')

# 电影 - 555 线路缓存过期时间（分钟），可由 .env 覆盖
# 数据类（片名 / 详情 / 简介 / 集数等固定信息）：默认 1440 分钟（24 小时）
MOVIE_555_DATA_CACHE_TTL = int(os.getenv('MOVIE_555_DATA_CACHE_TTL', '1440'))
# 媒体类（m3u8 播放地址等有时效的资源）：默认 30 分钟
MOVIE_555_MEDIA_CACHE_TTL = int(os.getenv('MOVIE_555_MEDIA_CACHE_TTL', '30'))

# 短剧 - 红果线路缓存过期时间（分钟），可由 .env 覆盖
# 数据类（榜单 / 分类列表 / 搜索 / 详情等固定信息）：默认 1440 分钟（24 小时）
HONGGUO_DATA_CACHE_TTL = int(os.getenv('HONGGUO_DATA_CACHE_TTL', '1440'))
# 媒体类（播放直链等有时效的资源）：默认 30 分钟
HONGGUO_MEDIA_CACHE_TTL = int(os.getenv('HONGGUO_MEDIA_CACHE_TTL', '30'))

# 海角社区 数据缓存过期时间（分钟），可由 .env 覆盖
# 热门帖按热度排序、随时间变动，缓存不宜过长
HAIJIAO_DATA_CACHE_TTL = int(os.getenv('HAIJIAO_DATA_CACHE_TTL', '60'))
# 海角社区 视频播放列表缓存过期时间（分钟）：派生真密钥开销较大（多次请求 + node），缓存稍长
HAIJIAO_MEDIA_CACHE_TTL = int(os.getenv('HAIJIAO_MEDIA_CACHE_TTL', '30'))
# 海角社区 今日域名缓存过期时间（分钟）：大陆可访问域名每日变动，
# 爬虫据此自动跟随；缓存期内不再探测源站配置接口
HAIJIAO_DOMAIN_CACHE_TTL = int(os.getenv('HAIJIAO_DOMAIN_CACHE_TTL', '30'))
# 海角社区 默认登录凭据（x-user-id / x-user-token，可选）：用于取帖内视频等需登录态的内容；
# 调用方可用请求参数 user_id / user_token 覆盖为自己的账号，留空则匿名请求。
HAIJIAO_USER_ID = os.getenv('HAIJIAO_USER_ID', '')
HAIJIAO_USER_TOKEN = os.getenv('HAIJIAO_USER_TOKEN', '')

# 短剧 - 红果线路「签名服务」配置
# 背景：源站只对每部剧前 3 集下发明文直链，第 4 集及以后是 DRM 加密的 H.265，浏览器
# 无法直接播放。故由服务端按需解密 + 转 H.264 后出流（见下方「网页直出」配置）——
# 取加密直链要调 App 内部接口，该接口强制校验 metasec 安全头。
# 签名服务地址：项目自带的 unidbg 离线签名器（生成 metasec 安全头）。
# 指向本机时由转码进程按需自动拉起（见 SpiderServices/dramas/hongguo/sign_service.py），
# 无需单独启动；指向远端签名服务时只做客户端、不自动拉起。
HONGGUO_SIGN_URL = os.getenv('HONGGUO_SIGN_URL', 'http://127.0.0.1:9099')
# 签名服务运行物目录（unidbg-sign.jar、capture/fq_oversea/ 与内置 jre/）
HONGGUO_SIGN_DIR = os.getenv('HONGGUO_SIGN_DIR') or str(BASE_DIR / 'scripts' / 'hongguo_sign')
# 拉起签名服务用的 java（需 JDK 17+）；留空则优先用内置 jre/，其次 PATH 上的 java
# （此处仅作覆盖用，正常情况下无需配置本机已装 Java）
HONGGUO_JAVA_BIN = os.getenv('HONGGUO_JAVA_BIN') or 'java'
# 等待签名服务就绪的超时（秒；JVM + unidbg 初始化较慢）
HONGGUO_SIGN_START_TIMEOUT = int(os.getenv('HONGGUO_SIGN_START_TIMEOUT', '90'))
# 签名服务 / App 接口单次请求超时（秒）
# 注：签名服务的端口会早于 unidbg 初始化完成就绪，首次签名请求会排队等初始化，
#     故这里给得宽一些，避免开机首个请求误判超时。
HONGGUO_SIGN_TIMEOUT = int(os.getenv('HONGGUO_SIGN_TIMEOUT', '60'))
HONGGUO_APP_TIMEOUT = int(os.getenv('HONGGUO_APP_TIMEOUT', '20'))
# ffmpeg 可执行文件（CENC 解密 + 转 H.264 都要用；留空用 PATH 上的 ffmpeg）
HONGGUO_FFMPEG_BIN = os.getenv('HONGGUO_FFMPEG_BIN') or 'ffmpeg'

# 短剧 - 红果线路「网页直出」配置
# 背景：源站第 4 集及以后只有 DRM 加密的 H.265，而浏览器（原生 / MSE / WebCodecs）
# 在多数机器上都无法解 HEVC（实测 Chrome 三者全为 false），所以「网页能播」只能出
# H.264 —— 服务端解密 + 转码一次，产物落盘永久复用，按需转、不用全量预处理。
# 转码产物根目录（每部剧 / 每个画质一个子目录，随 /cache/ 一起不入库）
HONGGUO_STREAM_DIR = os.getenv('HONGGUO_STREAM_DIR') or str(
    XYAPI_CACHE_ROOT / 'dramas' / 'hongguo_stream')
# 默认出流画质 = 输出**宽度**上限（短剧是竖屏 1080×1920，日常说的 1080p / 720p 就指宽度）。
# 请求方可用 play 接口的 q 参数按次覆盖；可选档位与各档码率上限见
# API/apis/dramas/hongguo/utils.py 的 QUALITY_WIDTHS 与
# SpiderServices/dramas/hongguo/transcode.py 的 _RATE_BY_WIDTH。
# 默认 1080 = 源站最高档（不缩放）：源站本身只有 ~540 kbps，此前默认缩到 720 后
# 竖屏宽度只剩 408px，全屏看明显发虚 —— 这是「画质差」的主因，不是源站没有高清。
HONGGUO_STREAM_QUALITY = int(os.getenv('HONGGUO_STREAM_QUALITY', '1080'))
# 转码优先使用的硬件编码器（按顺序探测，都不可用则回退 libx264）
HONGGUO_STREAM_HW_ENCODERS = [
    e.strip() for e in os.getenv('HONGGUO_STREAM_HW_ENCODERS', 'h264_nvenc,h264_qsv,h264_amf').split(',')
    if e.strip()
]
# 软件编码兜底 preset 与质量（体积/耗时折中）：CRF 20 对已压缩片源基本不再掉画质
HONGGUO_STREAM_X264_PRESET = os.getenv('HONGGUO_STREAM_X264_PRESET', 'veryfast')
HONGGUO_STREAM_X264_CRF = int(os.getenv('HONGGUO_STREAM_X264_CRF', '20'))
# 单集转码最长耗时（秒），超时判失败，默认 900
HONGGUO_STREAM_TIMEOUT = int(os.getenv('HONGGUO_STREAM_TIMEOUT', '900'))
# 网页直出：全局并发转码上限（同时最多几集在转）。每集 ffmpeg 默认会把多核吃满，不设上限时
# 多集被同时点播即可把整机 CPU 打满（线上事故），故默认 1（串行转码）；机器核多、负载低时可调大。
HONGGUO_STREAM_MAX_CONCURRENT = int(os.getenv('HONGGUO_STREAM_MAX_CONCURRENT', '1'))
# 网页直出：单次 ffmpeg 转码可用的最大线程数。默认取「CPU 核数的一半」（8 核 → 4），
# 给同机其它服务留余量；可用 .env 覆盖。
HONGGUO_STREAM_FFMPEG_THREADS = int(os.getenv(
    'HONGGUO_STREAM_FFMPEG_THREADS', str(max(1, (os.cpu_count() or 2) // 2))))
# 播放地址时效令牌有效期（秒），过期需重新调 play 接口换新地址
HONGGUO_STREAM_TOKEN_TTL = int(os.getenv('HONGGUO_STREAM_TOKEN_TTL', '7200'))

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    },
    # 电影 - 555 线路缓存
    'movie_555': {
        'BACKEND': 'django.core.cache.backends.filebased.FileBasedCache',
        'LOCATION': str(XYAPI_CACHE_ROOT / 'movies' / 'movie_555'),
        'TIMEOUT': MOVIE_555_MEDIA_CACHE_TTL * 60,
    },
    # 短剧 - 红果线路缓存
    'hongguo': {
        'BACKEND': 'django.core.cache.backends.filebased.FileBasedCache',
        'LOCATION': str(XYAPI_CACHE_ROOT / 'dramas' / 'hongguo'),
        'TIMEOUT': HONGGUO_MEDIA_CACHE_TTL * 60,
    },
    # 海角社区缓存
    'haijiao': {
        'BACKEND': 'django.core.cache.backends.filebased.FileBasedCache',
        'LOCATION': str(XYAPI_CACHE_ROOT / 'haijiao'),
        'TIMEOUT': HAIJIAO_DATA_CACHE_TTL * 60,
    },
}


# ==================== SimpleUI 后台主题配置 ====================
# 隐藏后台主页中的 "Simpleui 主页" 信息卡片（版本号/报告问题/Gitee/Github 链接）
SIMPLEUI_HOME_INFO = False


# ==================== 邮箱 SMTP 配置 ====================
# 使用 QQ 邮箱作为默认发件邮箱
# 凭据从项目根目录的 .env 文件读取:
#   QQ_MAIL_ACCOUNT     - QQ邮箱地址(发件人)
#   QQ_MAIL_AUTH_CODE   - QQ邮箱SMTP授权码(非登录密码,需在QQ邮箱设置中开启SMTP服务后获取)
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'  # 使用SMTP后端发送真实邮件
EMAIL_HOST = 'smtp.qq.com'          # QQ邮箱SMTP服务器地址
EMAIL_PORT = 465                    # QQ邮箱SMTP SSL端口
EMAIL_USE_SSL = True                # 启用SSL加密传输
EMAIL_HOST_USER = os.getenv('QQ_MAIL_ACCOUNT', '')        # 发件邮箱账号
EMAIL_HOST_PASSWORD = os.getenv('QQ_MAIL_AUTH_CODE', '')  # 发件邮箱授权码
DEFAULT_FROM_EMAIL = EMAIL_HOST_USER  # 默认发件人地址(与发件账号一致)
# SMTP 超时（秒）：不设的话底层 socket **没有超时**，SMTP 服务器半挂/不可达时，
# 发信会一直卡在请求线程里占住 uwsgi worker（注册 / 登录 / 重置密码都走发信）。
EMAIL_TIMEOUT = 10


# ==================== 邮箱验证/登录配置 ====================
# 邮箱注册验证形式: 'link' 仅验证链接 / 'code' 仅验证码 / 'both' 链接+验证码都提供
# （后续可扩展为后台页面配置，当前用环境变量控制）
EMAIL_VERIFY_MODE = os.getenv('EMAIL_VERIFY_MODE', 'both')
# 邮箱验证有效期(分钟)
EMAIL_VERIFY_EXPIRE_MINUTES = int(os.getenv('EMAIL_VERIFY_EXPIRE_MINUTES', '30'))


# ==================== 手机号验证配置 ====================
# 手机号短信验证码有效期(分钟)，与阿里云 SendSmsVerifyCode 的 valid_time 联动
PHONE_VERIFY_EXPIRE_MINUTES = int(os.getenv('PHONE_VERIFY_EXPIRE_MINUTES', '5'))


# ==================== 官网前台接入配置 ====================
# 官网作为用户中心的一个「接入项目」，注册/登录由服务端代理完成、登录态存 Django 会话。
# XYAPI_WEB_APP_NAME：官网在「接入项目」中的应用名称，首次使用自动创建（不存在时）。
# 官网会话中签发的 Token 即绑定在该项目下，与用户中心契约保持一致。
WEB_APP_NAME = os.getenv('XYAPI_WEB_APP_NAME', '小影API官网')

# 「计算程序」模块的内容根目录（前台 /programs/ 展示与下载的唯一数据源）。
# 目录约定：一级子目录 = 分类，其下每个「含 README.md 且含普通文件」的目录 = 一个程序条目。
# 该目录下的文件会被前台直接对外提供下载，请勿放入密钥、Cookie 等敏感文件。
# 用 or 而非 getenv 默认值兜底：.env 里留空（XYAPI_PROGRAMS_ROOT=）时 getenv 返回空串，
# 而 Path('') 会解析成当前工作目录（即项目根），把整个项目当成内容目录扫描并对外提供下载。
PROGRAMS_ROOT = Path(os.getenv('XYAPI_PROGRAMS_ROOT') or BASE_DIR / 'CalculationProgram')


# ==================== 文件上传配置 ====================
# 单次上传请求体最大大小(110MB，预留10MB余量给表单字段)
DATA_UPLOAD_MAX_MEMORY_SIZE = 110 * 1024 * 1024  # 115343360 字节
# 内存中允许的最大文件大小，超过则写入临时文件(110MB)
FILE_UPLOAD_MAX_MEMORY_SIZE = 110 * 1024 * 1024  # 115343360 字节


# ==================== 阿里云 AccessKey 配置 ====================
# 账号级通用凭据，不限定具体服务，后续阿里云其他服务可复用
# 凭据从项目根目录 .env 文件读取:
#   ALIYUN_ACCESS_KEY_ID       - AccessKey ID
#   ALIYUN_ACCESS_KEY_SECRET   - AccessKey Secret
ALIYUN_ACCESS_KEY_ID = os.getenv('ALIYUN_ACCESS_KEY_ID', '')
ALIYUN_ACCESS_KEY_SECRET = os.getenv('ALIYUN_ACCESS_KEY_SECRET', '')


# ==================== 日志配置（A-05 整改） ====================
# 统一结构化日志落盘：所有请求（含耗时/状态码/request_id/app）进 app.log，
# ERROR 及以上单独分流 error.log，便于按日志文件监控错误；
# request_id 由 ApiRequestLogMiddleware 生成并回写响应头 X-Request-Id，
# 一次故障可通过 request_id 关联 app.log/error.log 全链路追溯。
LOG_DIR = BASE_DIR / 'logs'
os.makedirs(LOG_DIR, exist_ok=True)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'standard': {
            'format': '{asctime} [{levelname}] {name} {message}',
            'style': '{',
        },
        'request': {
            # 请求日志行：request_id 置于行首，便于按 id grep 整条链路
            'format': '{asctime} [{levelname}] {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'standard',
        },
        'app_file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOG_DIR / 'app.log',
            'maxBytes': 10 * 1024 * 1024,
            'backupCount': 5,
            'encoding': 'utf-8',
            'formatter': 'request',
        },
        'error_file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOG_DIR / 'error.log',
            'maxBytes': 10 * 1024 * 1024,
            'backupCount': 5,
            'encoding': 'utf-8',
            'formatter': 'standard',
            'level': 'ERROR',
        },
    },
    'loggers': {
        '': {
            'handlers': ['console', 'app_file', 'error_file'],
            'level': 'INFO',
        },
        # 第三方库默认 WARNING，避免刷屏
        'django': {'level': 'WARNING'},
    },
}

