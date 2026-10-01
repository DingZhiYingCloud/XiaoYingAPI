"""海角社区 爬虫 - 常量与解码工具

站点为前后端分离的 SPA，数据全部走 /api/ 接口。响应体统一为「信封 + 三重 base64」：

    {"isEncrypted": true, "errorCode": 0, "message": "", "success": true, "data": "<base64>"}

success 为 true 时，data 是「标准 base64 连续编码 3 次」的 UTF-8 JSON 字符串，
连续 b64decode 三次再 json.loads 即可拿到明文数据（见 decode_payload）。

注意：帖内图片另有一套混淆（附件地址形如 .../<hash>_mini.jpg.txt，内容是自定义字母表
base64 编码的 data URI），用 decode_image() 解码。

视频另有一套自定义保护：播放列表里 #EXT-X-KEY 指向的 enc_xxx.key 是「假密钥」，真实
AES-128 密钥需用源站自带的 jquery.wasm 由 jquery_key(假key, 盐) 还原（盐取自同名
<m3u8>.jpg），见 derive_key.js。
"""
import base64
import json
import os
import re
import time
from pathlib import Path
from urllib.parse import quote, urlencode

import requests
from django.conf import settings
from django.core.cache import caches

# 站点根地址（页面 {BASE_URL}/home，接口同域 /api/...）
# ⚠️ 海角的大陆可访问域名**每日变动**，源站用配置接口公布当日可用域名。
#    本值只作「探测失败时的兜底」：爬虫每次新建会话前会调 current_base_url() 自动跟随
#    今日域名（见文件末尾「今日域名」一节），跟随成功后会一并改写下面 BASE_URL 与由它
#    派生的全部地址常量、以及请求头里的 origin / referer。
#    爬虫的全部接口地址、头像与图片地址都由它拼出来；前端发帖页的帖子链接也从它取值。
BASE_URL = 'https://dbaa49fb2c7091.top'

# 基础请求头：pcver 为 PC 端版本标记，缺省会按非 PC 端处理，故必须携带
UA_STRING = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
             '(KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36')

API_HEADERS = {
    'accept': 'application/json, text/plain, */*',
    'accept-language': 'zh-CN,zh;q=0.9',
    'origin': BASE_URL,
    'referer': f'{BASE_URL}/home',
    'pcver': '2',
    'user-agent': UA_STRING,
}

REQUEST_TIMEOUT = 20   # 单次请求超时（秒）
MAX_RETRIES = 3        # 失败重试次数（源站偶发连接抖动）
RETRY_DELAY = 1.0      # 重试间隔（秒）

# 内容列表模块 -> 源站接口路径（取自站点前端 JS 的首页栏目映射 HomeTabs）
# 除热帖外，其余栏目共用「node/topics」接口，靠 type / nodeId 区分。
TOPIC_TABS = {
    'hot': '/api/topic/hot/topics',                        # 热帖
    'news': '/api/topic/node/news',                        # 新闻
    'events': '/api/topic/node/topics?type=1&nodeId=258',  # 大事记
    'original': '/api/topic/node/topics?type=7',           # 原创
    'essence': '/api/topic/node/topics?type=3&nodeId=0',   # 精华
    'latest': '/api/topic/node/topics?type=1&nodeId=0',    # 最新
}


def build_topics_url(tab: str, page: int) -> str:
    """按模块拼装内容列表接口地址（源站每页 20 条）"""
    path = TOPIC_TABS[tab]
    # 部分模块的接口路径本身带查询串（type/nodeId），page 需用 & 续接
    sep = '&' if '?' in path else '?'
    return f'{BASE_URL}{path}{sep}page={page}'


def build_detail_url(topic_id) -> str:
    """帖子详情接口地址"""
    return f'{BASE_URL}/api/topic/{topic_id}'


# 帖子评论每页条数（与源站默认一致，页面不暴露 limit）
COMMENT_PAGE_SIZE = 20

# 二级评论（某条主评论下的子评论）：源站另一个接口，按 replyId 分页取
COMMENT_REPLIES_URL = f'{BASE_URL}/api/comment/comment_list'
COMMENT_REPLIES_PAGE_SIZE = 20


def build_comment_replies_url(reply_id, page: int) -> str:
    """二级评论列表接口地址（replyId 为主评论 ID，即评论列表里的 comment_id）"""
    return (f'{COMMENT_REPLIES_URL}?replyId={reply_id}'
            f'&page={page}&limit={COMMENT_REPLIES_PAGE_SIZE}')


def build_comments_url(topic_id, page: int, search_type: int) -> str:
    """帖子评论列表接口地址

    :param search_type: 0=全部，1=只看楼主（对应源站评论区「看全部 / 看楼主」两个 tab）
    """
    return (f'{BASE_URL}/api/comment/reply_list'
            f'?page={page}&limit={COMMENT_PAGE_SIZE}&topic_id={topic_id}'
            f'&search_type={search_type}')


def build_search_url(key: str, page: int, node_id: int = 0) -> str:
    """帖子搜索接口地址（关键词需 URL 编码；node_id=0 表示不限板块）"""
    return f'{BASE_URL}/api/topic/searchV2?key={quote(key)}&page={page}&node_id={node_id}'


# 视频附件播放地址解析接口（POST，请求体需带 resource_id / resource_type）
# 例：{"id": 附件ID, "resource_id": 帖子ID, "resource_type": "topic", "line": ""}
ATTACHMENT_URL = f'{BASE_URL}/api/attachment'

# 注册相关接口
CAPTCHA_URL = f'{BASE_URL}/api/captcha/request?t=signupCaptcha'   # 取注册验证码
SIGNUP_URL = f'{BASE_URL}/api/login/signup'                        # 提交注册
LOGIN_URL = f'{BASE_URL}/api/login/signin'                         # 登录

# 每日金币任务 / 签到
TASK_STATUS_URL = f'{BASE_URL}/api/task/getTaskStatus'   # 任务状态（含 goldSignIn 签到状态）
SIGN_IN_URL = f'{BASE_URL}/api/user/user_sign_in'        # 金币签到（POST，无请求体，靠登录头鉴权）

# 发帖相关接口
NODES_URL = f'{BASE_URL}/api/topic/nodes_by_ver/v2'          # 板块列表（不带 ver 即返回全量）
TAGS_URL = f'{BASE_URL}/api/tag/tags'                        # 标签池（分页，每页 20，最新在前）
UPLOAD_URL = f'{BASE_URL}/api/upload'                        # 媒体上传（multipart：entity_id/entity_type/image）
TOPIC_CREATE_URL = f'{BASE_URL}/api/topic/create'            # 发帖（JSON 请求体）
TOPIC_CAPTCHA_URL = f'{BASE_URL}/api/captcha/request?t=topicCaptcha'   # 发帖风控人机验证
MY_TOPICS_URL = f'{BASE_URL}/api/topic/mine/topics'          # 我的帖子（按审核状态筛选）

# 我的帖子：审核状态取值（取自源站 /post/release 页三个 tab）与每页条数
MY_TOPIC_STATUS_PUBLISHED = 3   # 审核通过
MY_TOPIC_STATUS_PENDING = 2     # 审核中
MY_TOPIC_STATUS_REJECTED = 4    # 审核失败
MY_TOPICS_PAGE_SIZE = 10


def build_my_topics_url(status: int, page: int) -> str:
    """我的帖子接口地址（status: 3=审核通过 2=审核中 4=审核失败）"""
    return f'{MY_TOPICS_URL}?page={page}&status={status}'


# 礼物（打赏）相关接口
STORE_LIST_URL = f'{BASE_URL}/api/store/list'        # 礼物列表（itemType=gift）
BUY_GIVE_URL = f'{BASE_URL}/api/store/buy_give'      # 买下礼物并赠送（打赏）

# 礼物类型：gold=金币礼物（默认）/ diamond=钻石礼物；对应源站的计价字段 moneyType
GIFT_KINDS = ('gold', 'diamond')
GIFT_KIND_MONEY_TYPE = {'gold': 1, 'diamond': 2}
# 打赏来源标识（源站 sourceType）：1=帖子，sourceId 传帖子 ID
GIVE_SOURCE_TOPIC = 1
# 单次赠送数量上限（与源站前端 el-input-number 的 1~99 一致）
GIVE_MAX_QUANTITY = 99
# 礼物列表一次取满：源站礼物总数很少，站点弹窗也是一次要 100 条
GIFT_LIST_PAGE_SIZE = 100


# 关注 / 取消关注（个人主页的「关注」按钮）
FOLLOW_URL = f'{BASE_URL}/api/user/favorite'
# opt 取值：add=关注 rm=取消关注（与源站前端 onFavorite 里的 opt 一致）
FOLLOW_OPT_ADD = 'add'
FOLLOW_OPT_RM = 'rm'


def build_follow_url(target_user_id, opt: str) -> str:
    """关注 / 取消关注接口地址（opt: add=关注 rm=取消关注）"""
    return f'{FOLLOW_URL}?targetId={target_user_id}&opt={opt}'


# 用户信息 / 钱包 / 社交（关注、粉丝、点赞）
USER_INFO_URL = f'{BASE_URL}/api/user/info'              # 用户主页信息（路径带用户 ID）
WEALTH_URL = f'{BASE_URL}/api/user/wealth'               # 当前账号余额（金币 / 钻石）
WEALTH_LOG_URL = {'gold': f'{BASE_URL}/api/user/wealth_gold_log',
                  'diamond': f'{BASE_URL}/api/user/wealth_diamond_log'}
FOLLOWING_URL = f'{BASE_URL}/api/user/favorite/users'    # 我关注的人（源站一次全给，不分页）
FANS_URL = f'{BASE_URL}/api/user/fans'                   # 我的粉丝（分页）
LIKE_URL = f'{BASE_URL}/api/topic/like'                  # 点赞：GET 查状态 / POST <帖子ID> 点赞取关
LIKED_TOPICS_URL = f'{BASE_URL}/api/topic/like/topics'   # 我点赞过的帖子（分页）

# 收藏（源站 /post/collection 页，走 /api/favorite/v2/...，读写都需登录态）
FAVORITE_FOLDER_LIST_URL = f'{BASE_URL}/api/favorite/v2/folderList'   # 我的收藏夹（含每个夹子的帖子数）
FAVORITE_TOPICS_URL = f'{BASE_URL}/api/favorite/v2/topics'            # 收藏的帖子（可按收藏夹筛选）
FAVORITE_ADD_URL = f'{BASE_URL}/api/favorite/v2/add'                  # 收藏帖子
FAVORITE_DELETE_URL = f'{BASE_URL}/api/favorite/v2/delete'            # 取消收藏帖子
FAVORITE_FOLDER_ADD_URL = f'{BASE_URL}/api/favorite/v2/folderAdd'     # 新建 / 编辑收藏夹
FAVORITE_FOLDER_DEL_URL = f'{BASE_URL}/api/favorite/v2/folderDel'     # 删除收藏夹

# 收藏对象类型：topic=帖子（源站另有 videoCenter=站内视频，本服务未开放）
FAVORITE_ENTITY_TOPIC = 'topic'

# folderId 取该值时表示「全部收藏」（跨所有收藏夹）。
# 实测：不传 folderId 与传 0 返回结果完全一致（都跨夹返回），传具体夹 id 才只返回该夹。
# 写操作里该值同样表示「默认收藏夹」（收藏时不传 folderId 与传 0 等效）。
FAVORITE_ALL_FOLDERS = 0
# 收藏列表每页条数（与源站默认一致）
FAVORITE_PAGE_SIZE = 20
# 收藏夹名称长度（源站校验文案：收藏夹名称为 1-12 位字符）
FAVORITE_FOLDER_NAME_MAX = 12
# 单次批量取消收藏的帖子数上限。
# 源站的原生批量（entityIds 逗号多值）是「按顺序删、遇到没收藏的就报错中止、**已删的不回滚**」，
# 会返回「失败但实际删了一半」的误导结果，故服务层改为逐条串行调用（见 API 层 remove_favorite_batch）；
# 逐条串行每次约 1~2 秒，这里用上限挡住「一次传上千个」把请求长时间挂住。
FAVORITE_BATCH_MAX = 50

# 社交类列表每页条数（与源站默认一致）
SOCIAL_PAGE_SIZE = 20
# 点赞的 entityType（帖子；源站视频用 videoCenter，本服务未开放）
LIKE_ENTITY_TOPIC = 'topic'


def build_user_info_url(user_id) -> str:
    """用户主页信息接口地址（用户 ID 走路径）"""
    return f'{USER_INFO_URL}/{user_id}'


def build_wealth_log_url(kind: str, page: int, limit: int) -> str:
    """金币 / 钻石流水接口地址（kind: gold / diamond）"""
    return f'{WEALTH_LOG_URL[kind]}?page={page}&limit={limit}'


def build_fans_url(page: int, limit: int) -> str:
    """粉丝列表接口地址"""
    return f'{FANS_URL}?page={page}&limit={limit}'


def build_liked_topics_url(page: int, limit: int) -> str:
    """我点赞过的帖子接口地址"""
    return f'{LIKED_TOPICS_URL}?page={page}&limit={limit}'


def build_favorite_topics_url(folder_id, page: int, limit: int) -> str:
    """我收藏的帖子接口地址

    :param folder_id: 收藏夹 ID；FAVORITE_ALL_FOLDERS（0）表示全部收藏（跨收藏夹）
    """
    return f'{FAVORITE_TOPICS_URL}?folderId={folder_id}&page={page}&limit={limit}'


def build_favorite_add_url(folder_id, topic_id) -> str:
    """收藏帖子接口地址（folder_id=FAVORITE_ALL_FOLDERS 表示默认收藏夹）

    源站同一地址重复提交不会报错（收藏已收藏的帖子仍是成功），故调用方无需先查再收藏。
    """
    return (f'{FAVORITE_ADD_URL}?entityType={FAVORITE_ENTITY_TOPIC}'
            f'&folderId={folder_id}&entityId={topic_id}')


def build_favorite_delete_url(topic_id) -> str:
    """取消收藏接口地址（entityIds 源站支持逗号分隔的多值，本服务只开放单个）"""
    return (f'{FAVORITE_DELETE_URL}?entityType={FAVORITE_ENTITY_TOPIC}'
            f'&entityIds={topic_id}')


def build_favorite_folder_add_url(folder_name: str,
                                  folder_id=FAVORITE_ALL_FOLDERS) -> str:
    """新建 / 重命名收藏夹接口地址（源站两个操作复用同一地址）

    folder_id 为 FAVORITE_ALL_FOLDERS（0）时是「新建」；传已有收藏夹 id 时是「重命名」。

    注意：重命名成功时源站返回的是个**假对象**（id 恒为 0、createdAt 为 0001-01-01），
    不能用它回传 folder_id，调用方按传入值回传即可。
    """
    return (f'{FAVORITE_FOLDER_ADD_URL}?folderId={folder_id}'
            f'&folderName={quote(folder_name)}')


def build_favorite_folder_delete_url(folder_id) -> str:
    """删除收藏夹接口地址（源站要求夹内为空，非空会拒绝）"""
    return f'{FAVORITE_FOLDER_DEL_URL}?folderId={folder_id}'


def build_like_url(topic_id) -> str:
    """点赞 / 取消点赞接口地址（POST，body 为 multipart 表单）"""
    return f'{LIKE_URL}/{topic_id}'


# 排行榜（首页「排行榜」模块，一次返回整张榜单、不翻页）
RANKING_URL = f'{BASE_URL}/api/ranking/rank'


# 站点默认头像的编号范围（前端 headicon 组件：0~80 的编号对应一张内置头像）
DEFAULT_AVATAR_MAX = 80


def resolve_avatar(avatar):
    """把源站的头像字段补成完整地址（源站规则见前端 headicon 组件）

    :return: (完整地址, 是否是混淆地址)
        - 0~80 的数字编号 → 站点默认头像，补成 .../images/common/avatar/<编号>.jpg，False（可直接引用）
        - http 开头的地址 → 用户自定义头像，真实图片要取「地址 + .txt」再按图片混淆规则解码，True
        - 其它异常值 → 回落到默认头像 0.jpg，False
    """
    text = str(avatar or '')
    if 'http' in text:
        return (text if text.endswith('.txt') else text + '.txt', True)
    index = int(text) if text.isdigit() else -1
    if not 0 <= index <= DEFAULT_AVATAR_MAX:
        index = 0
    return (f'{BASE_URL}/images/common/avatar/{index}.jpg', False)


def build_ranking_url(key: str, type_value) -> str:
    """排行榜接口地址

    :param key: 维度 fans=粉丝 / liked=点赞 / wealth=人气（源站另有 consume=消费，本服务未开放）
    :param type_value: 周期 all=总榜 / 30=月榜 / 7=周榜
    """
    return f'{RANKING_URL}?type={type_value}&key={key}'


def build_gift_list_url(kind: str, page: int, limit: int) -> str:
    """礼物列表接口地址（kind: gold 金币礼物 / diamond 钻石礼物）"""
    return f'{STORE_LIST_URL}?itemType=gift&type={kind}&page={page}&limit={limit}'


def build_buy_give_url(item_id, quantity: int, kind: str, user_id,
                       source_type: int = 0, source_id=0) -> str:
    """买下礼物并赠送（打赏）的接口地址

    :param item_id: 礼物 ID（取自礼物列表的 item_id）
    :param quantity: 赠送数量（1~GIVE_MAX_QUANTITY）
    :param kind: 礼物类型 gold / diamond
    :param user_id: 收礼人用户 ID（给帖子打赏时为帖子作者）
    :param source_type: 来源类型（GIVE_SOURCE_TOPIC=帖子）；与 source_id 同时非空才会带上
    :param source_id: 来源 ID（帖子 ID）
    """
    params = {'itemId': item_id, 'quantity': quantity,
              'moneyType': GIFT_KIND_MONEY_TYPE[kind], 'userId': user_id}
    if source_type and source_id:
        params['sourceType'] = source_type
        params['sourceId'] = source_id
    return f'{BUY_GIVE_URL}?{urlencode(params)}'


# 发帖可上传的媒体类型（与源站前端 accept 一致，当前只开放图片与视频）
MEDIA_IMAGE_EXTS = ('.png', '.jpg', '.jpeg', '.gif', '.bmp')
MEDIA_VIDEO_EXTS = ('.mp4',)
# 源站对图片的体积限制（前端校验值：图片 ≤10MB）
MEDIA_IMAGE_MAX_BYTES = 10 * 1024 * 1024
# 上传接口超时（大文件较慢）
UPLOAD_TIMEOUT = 600

# 视频密钥派生器（node + 源站 jquery.wasm，见 derive_key.js）
# node 可执行文件：默认取 PATH 里的 node；服务器上若装在别处，用 .env 的
# HAIJIAO_NODE_BIN 指定绝对路径（两种情况都由 shutil.which 统一判定可用性）。
NODE_BIN = (os.getenv('HAIJIAO_NODE_BIN', '') or '').strip() or 'node'
DERIVE_CLI = Path(__file__).resolve().parent / 'derive_key.js'
DERIVE_TIMEOUT = 30   # 单次 node 调用超时（秒）


def decode_payload(encoded: str) -> dict:
    """解密响应信封里的 data 字段：标准 base64 连续解码 3 次 → UTF-8 JSON

    :param encoded: 响应信封的 data 字段（base64 字符串）
    :return: 解析后的明文数据
    """
    raw = encoded
    for _ in range(3):
        raw = base64.b64decode(raw)
    return json.loads(raw.decode('utf-8'))


# 源站图片混淆用的自定义字母表（标准 base64 字符集的变体：用 * 与 # 替换 + 与 /）
IMAGE_ALPHABET = 'ABCD*EFGHIJKLMNOPQRSTUVWX#YZabcdefghijklmnopqrstuvwxyz1234567890'
# 单张图片抓取体积上限（字节）：超出即拒绝，避免被当作大流量代理
IMAGE_MAX_BYTES = 5 * 1024 * 1024


def decode_image(text: str) -> str:
    """解码源站混淆图片地址的内容，返回 data URI（形如 data:image/jpeg;base64,...）

    源站把图片以「自定义字母表的 base64」写进 .../<hash>.jpg.txt：
      ① 去掉所有不属于字母表的字符（等号等一律丢弃）；
      ② 用 IMAGE_ALPHABET 按下标取 6bit 值，每 4 个字符还原为 3 字节；
      ③ 还原出的字节按 UTF-8 解码，即 data URI。

    :param text: .txt 文件内容
    :return: 解码后的 data URI 文本
    """
    cleaned = re.sub(r'[^A-Za-z0-9*#]', '', text or '')
    # 末尾不足 4 字符时按下标 0（字母表首字符 A）补齐，与源站前端实现一致
    if len(cleaned) % 4:
        cleaned += IMAGE_ALPHABET[0] * (4 - len(cleaned) % 4)
    out = bytearray()
    for i in range(0, len(cleaned), 4):
        a, b, c, d = (IMAGE_ALPHABET.index(ch) for ch in cleaned[i:i + 4])
        out.append(((a << 2) | (b >> 4)) & 0xFF)
        if c != 64:
            out.append((((b & 15) << 4) | (c >> 2)) & 0xFF)
        if d != 64:
            out.append((((c & 3) << 6) | d) & 0xFF)
    return out.decode('utf-8', 'replace')


# ==================== 今日域名 ====================
# 海角的大陆可访问域名**每日变动**，源站用配置接口公布当日可用域名。站点首页加载时就请求它：
#     GET {任意海角域名}/api/login/conf
# 返回的 domain 即「今日大陆直接访问网址」（源站首页弹窗提示取的就是这个字段），
# 另有备用域名 / 海外永久域名 / 影视站域名与客服邮箱（域名失效时用客服邮箱取最新）。

# 配置接口路径
DOMAIN_CONF_PATH = '/api/login/conf'

# 源站配置字段 -> 对外字段名（对外统一下划线命名，与项目其它接口风格一致）
DOMAIN_FIELDS = {
    'domain': 'domain',                      # 今日大陆可直接访问域名
    'backupDomain': 'backup_domain',         # 备用域名
    'domainAbroad': 'abroad_domain',         # 海外永久域名（需科学上网）
    'hjMovie': 'movie_domain',               # 影视站域名
    'customerService': 'customer_service',   # 客服邮箱
}

# 探测入口：先问当前 BASE_URL（多数时候它还能用），失败再依次问这些永久入口。
# www.haijiao.com 是源站公布的海外永久域名，域名轮换期间通常仍可访问。
DOMAIN_PROBE_FALLBACKS = ('https://www.haijiao.com',)

# 今日域名缓存 TTL（秒，可由 .env 的 HAIJIAO_DOMAIN_CACHE_TTL 覆盖，默认 30 分钟）
DOMAIN_TTL = int(getattr(settings, 'HAIJIAO_DOMAIN_CACHE_TTL', 30)) * 60
# 探测失败后的重试间隔（秒）：源站抖动时避免每次请求都去探测
DOMAIN_RETRY_TTL = 60
# 探测请求超时（秒）：与常规请求分开，源站不通时也不至于把接口拖住
DOMAIN_PROBE_TIMEOUT = 5

# 探测请求头：不带 origin / referer——探测时新域名尚未确定，带上旧域名可能被源站拒绝
_PROBE_HEADERS = {k: v for k, v in API_HEADERS.items() if k not in ('origin', 'referer')}

_cache = caches['haijiao']
_DOMAIN_CACHE_KEY = 'domain:config'
# 进程内失败时间戳：仅用于失败后的短暂节流（成功即清零）
_domain_failed_at = 0.0


def _fetch_domain_config(entry: str) -> dict:
    """从指定入口请求配置接口并解析出域名配置

    :param entry: 入口站点根地址
    :return: {domain, backup_domain, abroad_domain, movie_domain, customer_service}
    """
    resp = requests.get(f'{entry.rstrip("/")}{DOMAIN_CONF_PATH}',
                        headers=_PROBE_HEADERS, timeout=DOMAIN_PROBE_TIMEOUT)
    resp.raise_for_status()
    envelope = resp.json()
    if not envelope.get('success'):
        raise RuntimeError(f'源站返回失败: {envelope.get("message") or envelope.get("errorCode")}')
    payload = decode_payload(envelope['data'])
    config = {out: str(payload.get(src) or '').strip() for src, out in DOMAIN_FIELDS.items()}
    if not config['domain']:
        raise RuntimeError('源站未返回今日域名（domain）')
    return config


def resolve_domain_config() -> dict:
    """获取今日域名配置（成功结果缓存 DOMAIN_TTL）

    缓存未命中时依次探测「当前 BASE_URL → DOMAIN_PROBE_FALLBACKS」；全部失败抛
    RuntimeError，并在 DOMAIN_RETRY_TTL 内直接失败（不重复探测，避免拖慢接口）。

    :return: {domain, backup_domain, abroad_domain, movie_domain, customer_service}
    """
    global _domain_failed_at
    cached = _cache.get(_DOMAIN_CACHE_KEY)
    if cached:
        return cached

    now = time.time()
    if now - _domain_failed_at < DOMAIN_RETRY_TTL:
        raise RuntimeError('今日域名探测失败（稍后自动重试）')

    error = None
    for entry in (BASE_URL,) + DOMAIN_PROBE_FALLBACKS:
        try:
            config = _fetch_domain_config(entry)
        except Exception as e:      # noqa: BLE001 - 逐个入口尝试，全部失败才算失败
            error = e
            continue
        _cache.set(_DOMAIN_CACHE_KEY, config, DOMAIN_TTL)
        _domain_failed_at = 0.0
        return config

    _domain_failed_at = now
    raise RuntimeError(f'今日域名探测失败: {error}')


def set_base_url(base: str) -> None:
    """把站点根地址切到 base，并改写由它派生的全部地址常量与请求头

    海角域名每日变动，故 BASE_URL 不能只当模块级常量用——依赖它的 20 余个地址常量
    在模块导入时就已求值，必须在这里一并换掉前缀，否则会出现「域名换了、地址还是旧的」。

    :param base: 站点根地址（结尾斜杠可有可无）
    """
    global BASE_URL
    base = base.rstrip('/')
    old = BASE_URL
    if not base or base == old:
        return

    BASE_URL = base
    # 模块内所有「以旧域名开头」的字符串常量（含 WEALTH_LOG_URL 这类字典的值、
    # 以及 API_HEADERS 里的 origin / referer）统一换前缀；不依赖它的常量不受影响。
    for name, value in list(globals().items()):
        if name.startswith('_'):
            continue
        if isinstance(value, str) and value.startswith(old):
            globals()[name] = base + value[len(old):]
        elif isinstance(value, dict):
            for key, item in value.items():
                if isinstance(item, str) and item.startswith(old):
                    value[key] = base + item[len(old):]


def current_base_url() -> str:
    """当前应使用的站点根地址（爬虫每次新建会话前调用，自动跟随今日域名）

    探测失败时沿用现有值（含模块加载时的兜底地址），保证接口不会因为「取不到新域名」而整体不可用。

    :return: 站点根地址，形如 https://xxx.top
    """
    try:
        config = resolve_domain_config()
    except RuntimeError:
        return BASE_URL
    set_base_url(config['domain'])
    return BASE_URL
