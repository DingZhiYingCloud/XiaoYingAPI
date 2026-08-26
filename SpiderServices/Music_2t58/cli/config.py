"""小影音乐爬虫 CLI 配置（常量集中管理，不硬编码在业务逻辑中）"""
import os

# 目录定位: cli/ -> Music_2t58/
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(BASE_DIR, 'output')

# ---------- 站点域名（统一变量，全项目共用，禁止写死） ----------
# 站点为同款多域名部署（2t58.com 曾崩溃，现用 aat.cx），切换方式任选其一:
#   1. 环境变量:  set MUSIC_SITE=https://www.xxx.com
#   2. CLI 参数:  python cli/main.py crawl --start 1 --end 1 --site https://www.xxx.com
#   3. 改本行
SITE_BASE = os.environ.get('MUSIC_SITE', 'https://www.aat.cx')


def set_site(url):
    """运行时切换站点域名（CLI --site 使用），返回更新后的域名"""
    global SITE_BASE
    SITE_BASE = url.strip().rstrip('/')
    return SITE_BASE

# 歌手列表第 1 页（后续页为 /singerlist/index/index/index/index/{page}.html）
SINGER_LIST_FIRST = '/singerlist/index/index/index/index.html'
SINGER_LIST_PAGE_TMPL = '/singerlist/index/index/index/index/{page}.html'
# 歌手列表最大页数（站点分页上限，超出直接报错）
SINGER_LIST_MAX_PAGE = 259

# 默认文件路径（均可通过命令行 --out / --log 覆盖）
DEFAULT_OUT = os.path.join(OUTPUT_DIR, 'music_singers.json')          # 抓取结果输出文件
DEFAULT_LOG = os.path.join(OUTPUT_DIR, 'crawler.log')                 # 日志（错误统一堆此文件）
DEFAULT_CACHE = os.path.join(OUTPUT_DIR, '.play_url_cache.json')      # 播放源断点缓存

# 抓取行为
DEFAULT_RETRY = 3        # 单步失败自动重试次数
RETRY_INTERVAL = 2       # 重试基础间隔秒（指数递增: 2, 4, 6...）
DEFAULT_THREADS = 4      # 并发抓播放源默认线程数（CLI 可配 1-32）
MAX_THREADS = 32         # 线程数上限

# 小影导入接口校验规则（导入格式预检用）
MAX_NAME_LEN = 200        # name 最大长度
MAX_URL_LEN = 500         # 播放源 url 最大长度
