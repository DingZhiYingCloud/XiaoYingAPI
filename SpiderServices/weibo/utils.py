"""微博爬虫 - 常量与工具

只放常量与纯函数，不发起网络请求（请求都在 main.py）。
"""
import json
from datetime import datetime
from html import unescape
import re

BASE_URL = 'https://weibo.com'
# 频道分类（「我的频道」+「频道推荐」）：带登录 Cookie 返回该账号的频道，
# 不带也能返回游客默认频道（所以这个接口本身不校验登录态）。
ALL_GROUPS_API = f'{BASE_URL}/ajax/feed/allGroups'
# 按频道取内容（热门流）。注意两个 id 都要传且**取值不同**：
#   group_id    = 频道 gid        （如 明星 1028034288）
#   containerid = 频道 containerid（如 明星 102803_ctg1_4288_-_ctg1_4288）
HOT_TIMELINE_API = f'{BASE_URL}/ajax/feed/hottimeline'
# 长文「展开全文」：isLongText 且正文确实被截断时用它取全文
LONGTEXT_API = f'{BASE_URL}/ajax/statuses/longtext'
# 单条微博详情：按 id 现场解析视频直链（微博直链带 Expires 签名会过期，播放时要现取）
SHOW_API = f'{BASE_URL}/ajax/statuses/show'

USER_AGENT = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
              '(KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36')

DEFAULT_TIMEOUT = 20
# 取视频流用的超时（连接, 读取）：视频是大文件，读超时给宽一点
VIDEO_TIMEOUT = (10, 60)
# 需求方给的就是 /hot/weibo/102803 —— 102803 是「热门」频道的 gid
DEFAULT_CHANNEL = '102803'
DEFAULT_LIMIT = 20
# 微博单页实测 12~20 条，给个上限避免调用方一次要太多（翻页用 since_id）
MAX_LIMIT = 50
# 微博未登录时的哨兵值：HTTP 200 + {"ok": -100, "url": ".../login.php..."}
NOT_LOGIN_OK = -100
# 频道分类里只有 group_type == 1 的才是「频道」；其余是关注分组（不是内容分类）
CHANNEL_GROUP_TYPE = 1
# 图片尺寸优先级（取第一个有 url 的）
PIC_SIZES = ('largest', 'large', 'original', 'mw2000', 'bmiddle', 'thumbnail')
# 转义清理用
TAG_RE = re.compile(r'<[^>]+>')


def build_headers(referer=f'{BASE_URL}/'):
    """构造请求头（Cookie 由调用方单独带上）"""
    return {
        'User-Agent': USER_AGENT,
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'zh-CN,zh;q=0.9',
        'Referer': referer,
    }


def channel_page_url(channel_id) -> str:
    """频道 gid → 频道网页地址（如 https://weibo.com/hot/weibo/102803）"""
    return f'{BASE_URL}/hot/weibo/{channel_id}'


def status_url(uid, mblogid) -> str:
    """微博网页地址：https://weibo.com/{用户ID}/{微博短ID}"""
    if not uid or not mblogid:
        return ''
    return f'{BASE_URL}/{uid}/{mblogid}'


def profile_url(uid) -> str:
    """用户主页地址"""
    return f'{BASE_URL}/u/{uid}' if uid else ''


def https_url(url) -> str:
    """把 http:// 的媒体地址升级成 https://

    微博视频直链给的是 `http://f.video.weibocdn.com/...`，在 https 页面里会被浏览器
    当成「混合内容」直接拦掉（连请求都不发）；实测同一地址换成 https 依然可播。
    """
    text = (url or '').strip()
    if text.startswith('http://'):
        return 'https://' + text[len('http://'):]
    return text


def strip_html(text) -> str:
    """去掉 HTML 标签并还原实体（微博正文里的 <a> 链接 / @ / 话题标签）"""
    if not text:
        return ''
    return unescape(TAG_RE.sub('', str(text))).strip()


def pick_pic_url(pic_info) -> str:
    """从 pic_infos[pid] 里取一张图的地址（大图优先）"""
    info = pic_info if isinstance(pic_info, dict) else {}
    for size in PIC_SIZES:
        node = info.get(size)
        if isinstance(node, dict) and (node.get('url') or '').strip():
            return node['url'].strip()
        if isinstance(node, str) and node.strip():
            return node.strip()
    return ''


def parse_created_at(raw):
    """微博时间文案 → Unix 秒

    形如 'Fri Oct 02 19:47:22 +0800 2026'；解析失败返回 None。
    """
    text = ' '.join((raw or '').split())
    if not text:
        return None
    try:
        return int(datetime.strptime(text, '%a %b %d %H:%M:%S %z %Y').timestamp())
    except ValueError:
        return None


def next_since_id(payload) -> str:
    """从响应里取「下一页的 since_id」

    微博把它塞在一个 JSON 字符串里，形如
        "since_id": "{\"ul_sid\":\"\",\"ul_hid\":\"\",\"since_id\":\"5349919528584086\"}"
    """
    raw = (payload or {}).get('since_id')
    if isinstance(raw, dict):
        return str(raw.get('since_id') or '').strip()
    if isinstance(raw, str):
        text = raw.strip()
        if text.startswith('{'):
            try:
                return str((json.loads(text) or {}).get('since_id') or '').strip()
            except ValueError:
                return ''
        return text
    return str(raw or '').strip()
