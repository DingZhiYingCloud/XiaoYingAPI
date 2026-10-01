"""海角社区 爬虫 - HaijiaoSpider

站点为前后端分离的 SPA，数据全部走 /api/ 接口，响应体为「信封 + 三重 base64」
（见 utils.decode_payload）。

提供能力:
    get_domain_config()                      今日域名配置（大陆可访问域名 / 备用 / 海外 / 影视站 + 客服邮箱）
    get_topics(tab='hot', page=1)            内容列表（热帖 / 新闻 / 大事记 / 原创 / 精华 / 最新）
    search_topics(key, page=1, node_id=0)    搜索帖子（分页，按关键词）
    get_topic_detail(topic_id)               帖子详情（正文 / 原图 / 视频附件 / 互动数据）
    get_topic_comments(topic_id, page)       帖子评论列表（分页，可按「只看楼主」筛选）
    get_comment_replies(comment_id, page)    二级评论列表（某条主评论下的子评论，分页）
    fetch_image(url)                         解码混淆图片（返回 data URI）
    get_video_playlist(topic_id, attachment_id)  可直接播放的 m3u8（还原真密钥，标准播放器可播）
    register_captcha(provider)               取注册验证码（可选经代理；源站注册有 IP 限制）
    submit_register(...)                     提交注册
    login(username, password)                账号登录（返回 token）
    get_sign_in_status()                     每日金币签到状态（是否已签到 / 可得金币）
    sign_in()                                每日金币签到（幂等，已签到不重复提交）
    get_nodes()                              板块列表（按层级组装 children）
    get_tags(page)                           标签池（分页）
    upload_media(filename, data)             上传图片 / 视频，返回附件 ID 与正文片段
    get_post_captcha()                       发帖是否触发风控人机验证
    create_topic(...)                        发帖（标题 / 正文 / 板块 / 标签 / 媒体）
    get_my_topics(status, page)              我的帖子（审核通过 / 审核中 / 审核失败）
    get_gift_list(kind, page)                礼物列表（打赏用：金币 / 钻石礼物）
    give_topic_gift(topic_id, item_id, ...)  给帖子打赏（买礼物送给帖子作者）
    set_follow(target_user_id, follow)       关注 / 取消关注某个用户
    get_ranking(key, type_value)             排行榜（粉丝 / 点赞 / 人气；总榜 / 月榜 / 周榜）

今日域名（自动跟随）：
    海角的大陆可访问域名每日变动，每次新建实例时会自动跟随当天的可用域名（见
    utils.current_base_url）：命中缓存零开销，未命中则探测源站配置接口，探测失败
    沿用现有域名（含 utils.BASE_URL 兜底），不会让调用方整体不可用。

登录凭据（x-user-id / x-user-token）：
    取帖内视频等受限内容需要登录态。构造器可传 user_id / user_token（调用方自定义账号），
    不传则回退到 settings 里的默认凭据（.env 的 HAIJIAO_USER_ID / HAIJIAO_USER_TOKEN），
    两者都没有则匿名请求。注册走匿名会话，不带登录凭据。

运行依赖：`get_video_playlist` 需本机有 node（调 derive_key.js 还原视频真密钥）；
Linux 服务器要自行安装 Node.js（`derive_key.js` 只用 fs / path / Buffer / WebAssembly，
无 npm 依赖，装个 node 二进制即可），装在非默认位置时用 `.env` 的 `HAIJIAO_NODE_BIN` 指定。

使用示例:
    spider = HaijiaoSpider()
    spider.get_topics(tab='hot', page=1)
    spider.search_topics('学生妹', page=1)
    spider.get_topic_detail(2271635)
    spider.get_video_playlist(2271635, 14141834)
    HaijiaoSpider(user_id='xxx', user_token='yyy').get_topic_detail(2271635)
    HaijiaoSpider(user_id='xxx', user_token='yyy').sign_in()
"""
import base64
import hashlib
import mimetypes
import os
import re
import secrets
import shutil
import subprocess
import time
from html import unescape
from urllib.parse import quote, urljoin, urlsplit

import requests
from django.conf import settings

from . import utils as U
from .cache import DATA_TTL, MEDIA_TTL, get_or_fetch

# 注册可用的代理出口线路（控制台「出口」下拉的取值来源，加线路时只改这一处；
# 直连不在此表内，用 None / 'direct' 表示）
PROXY_PROVIDERS = ('51daili', 'juliang', 'relay')

# 「relay」= 经国内中转（scripts/hj_relay）：51代理 的代理 IP 只在国内可达，
# 生产服务器（海外）直连一律 TCP 超时，故由国内那台机器去连 51代理 再回传数据。
RELAY_URL = (os.getenv('PROXY_RELAY_URL', '') or '').strip()
RELAY_SECRET = (os.getenv('PROXY_RELAY_SECRET', '') or '').strip()


class HaijiaoSpider:
    """海角社区 爬虫"""

    def __init__(self, user_id: str = None, user_token: str = None):
        """
        :param user_id: 覆盖默认凭据的账号 ID（可选，需与 user_token 成对）
        :param user_token: 覆盖默认凭据的登录 token（可选）
        """
        # 先跟随今日域名（海角大陆可访问域名每日变动）：缓存命中时零开销；
        # 必须在建会话之前调用——接口地址常量与请求头 origin / referer 都由它决定。
        U.current_base_url()
        self.session = requests.Session()
        headers = dict(U.API_HEADERS)
        # 调用方传入优先，其次 .env 默认凭据；都没有则匿名请求
        uid = user_id or getattr(settings, 'HAIJIAO_USER_ID', '')
        token = user_token or getattr(settings, 'HAIJIAO_USER_TOKEN', '')
        if uid and token:
            headers['x-user-id'] = uid
            headers['x-user-token'] = token
        self.session.headers.update(headers)

    def get_domain_config(self) -> dict:
        """获取今日域名配置

        :return: {'domain'(今日大陆可直接访问域名), 'backup_domain'(备用域名),
                  'abroad_domain'(海外永久域名), 'movie_domain'(影视站域名),
                  'customer_service'(客服邮箱)}
        """
        return U.resolve_domain_config()

    # ==================== 基础请求 ====================

    def _request_json(self, method: str, url: str, payload: dict = None,
                      session: requests.Session = None, retry_business: bool = True,
                      retry_network: bool = True, files: dict = None) -> dict:
        """
        带重试的请求，返回解密后的明文数据。

        源站偶发连接抖动，故做有限次重试；响应信封 success=false 视为业务失败。
        session 不传时使用主会话（带登录凭据）；注册流程传匿名会话。

        两个重试开关都给「有副作用的写操作」用（如注册 / 发帖 / 打赏）：
        - retry_business=False：业务失败直接抛出，不再重试；
        - retry_network=False：网络异常 / 非 200 / 解析失败也只请求一次，
          避免「请求其实已经生效、只是响应丢了」被重试成重复注册 / 重复发帖 / 重复扣费。
        幂等的写操作（如金币签到：同一天重复提交源站只会回「今天已签到」）可保持默认重试。

        :return: 解密后的明文数据；源站成功但没回数据时（如关注 / 取关）返回 None
        """
        client = session or self.session
        # 显式代理必须走**请求级**传入：Windows 上 requests 会读取注册表里的系统代理，
        # 并在合并时用环境代理覆盖 session.proxies（请求级优先），显式代理会被静默忽略。
        # 没有显式代理时传 None，让系统代理照常生效（源站在大陆要靠它才能访问）。
        req_proxies = dict(client.proxies) or None
        attempts = U.MAX_RETRIES if retry_network else 1
        last_err = None
        for i in range(attempts):
            is_last = i == attempts - 1     # 最后一次尝试失败就直接抛出，不再空等重试间隔
            last_err = None
            try:
                if files:
                    # 源站少数接口（如点赞）只认 multipart 表单，字段用 {名: (None, 值)} 构造纯文本
                    resp = client.request(method, url, files=files,
                                          timeout=U.REQUEST_TIMEOUT, proxies=req_proxies)
                else:
                    resp = client.request(method, url, json=payload,
                                          timeout=U.REQUEST_TIMEOUT, proxies=req_proxies)
            except Exception as e:          # noqa: BLE001 - 网络类异常重试
                last_err = e
                if is_last:
                    break
                time.sleep(U.RETRY_DELAY)
                continue

            if resp.status_code != 200:
                last_err = RuntimeError(f'HTTP {resp.status_code}')
                if is_last:
                    break
                time.sleep(U.RETRY_DELAY)
                continue

            try:
                envelope = resp.json()
            except Exception as e:          # noqa: BLE001 - 响应不是 JSON 才重试
                last_err = e
                if is_last:
                    break
                time.sleep(U.RETRY_DELAY)
                continue

            if envelope.get('success'):
                # 成功时 data 可能为 null（关注 / 取关这类只回状态的写操作就是这种）：
                # 没有可解密的内容，直接返回 None，不能当成解析失败去重试
                if not envelope.get('data'):
                    return None
                try:
                    return U.decode_payload(envelope['data'])
                except Exception as e:      # noqa: BLE001 - 解密失败重试
                    last_err = e
                    if is_last:
                        break
                    time.sleep(U.RETRY_DELAY)
                    continue

            # 业务失败：源站明确拒绝（如验证码错误 / 用户名已存在）
            message = envelope.get('message') or '接口返回失败'
            if not retry_business:
                raise RuntimeError(message)
            last_err = RuntimeError(message)
            if is_last:
                break
            time.sleep(U.RETRY_DELAY)
        raise RuntimeError(f'请求失败（已尝试 {attempts} 次）: {url} -> {last_err}')

    def _get_text(self, url: str) -> str:
        """GET 文本（用于 CDN 上的 m3u8 与密钥盐文件）"""
        resp = self.session.get(url, timeout=U.REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp.text

    def _get_bytes(self, url: str) -> bytes:
        """GET 二进制（用于 CDN 上的密钥文件）"""
        resp = self.session.get(url, timeout=U.REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp.content

    # ==================== 解析工具 ====================

    @staticmethod
    def _parse_item(item: dict) -> dict:
        """把源站帖子条目规整为对外契约（图片为混淆地址，原样透出）"""
        user = item.get('user') or {}
        node = item.get('node') or {}
        attachments = item.get('attachments') or []
        return {
            'topic_id': item.get('topicId'),
            'title': item.get('title') or '',
            'excerpt': item.get('liteContent') or '',
            'node': {'id': node.get('nodeId'), 'name': node.get('name') or ''},
            'tags': [{'id': t.get('tagId'), 'name': t.get('tagName') or ''}
                     for t in (item.get('tags') or [])],
            'author': {'id': user.get('id'), 'nickname': user.get('nickname') or '',
                       'vip': user.get('vip', 0)},
            # 列表下发的是缩略图（文件名带 _mini），地址为源站混淆地址（.txt），需调用方自行解密
            'images': [a.get('remoteUrl') for a in attachments
                       if a.get('category') == 'images' and a.get('remoteUrl')],
            'has_video': any(a.get('category') == 'video' for a in attachments),
            'money_type': item.get('money_type', 0),
            'view_count': item.get('viewCount', 0),
            'comment_count': item.get('commentCount', 0),
            'like_count': item.get('likeCount', 0),
            'create_time': item.get('createTime') or '',
            'last_comment_time': item.get('lastCommentTime') or '',
        }

    @staticmethod
    def _parse_detail(item: dict) -> dict:
        """把源站帖子详情规整为对外契约"""
        user = item.get('user') or {}
        node = item.get('node') or {}
        attachments = item.get('attachments') or []
        avatar, avatar_encrypted = U.resolve_avatar(user.get('avatar'))
        return {
            'topic_id': item.get('topicId'),
            'title': item.get('title') or '',
            'excerpt': item.get('liteContent') or '',
            'node': {'id': node.get('nodeId'), 'name': node.get('name') or ''},
            'tags': [{'id': t.get('tagId'), 'name': t.get('tagName') or ''}
                     for t in (item.get('tags') or [])],
            'author': {'id': user.get('id'), 'nickname': user.get('nickname') or '',
                       'vip': user.get('vip', 0), 'avatar': avatar,
                       'avatar_encrypted': avatar_encrypted},
            # 正文 HTML：原样返回（内含混淆图片地址与 <video src=""> 占位）
            'content': item.get('content') or '',
            # 详情下发的是原图（列表则是 _mini 缩略图）
            'images': [a.get('remoteUrl') for a in attachments
                       if a.get('category') == 'images' and a.get('remoteUrl')],
            # 视频播放地址（url）需源站授权：匿名与普通账号通常为空串，只能拿到封面（cover）
            'videos': [{'id': a.get('id'), 'cover': a.get('coverUrl') or '',
                        'url': a.get('remoteUrl') or ''}
                       for a in attachments if a.get('category') == 'video'],
            'has_video': any(a.get('category') == 'video' for a in attachments),
            'money_type': item.get('money_type', 0),
            'purchased': bool(item.get('currentUserPurchased')),
            'view_count': item.get('viewCount', 0),
            'comment_count': item.get('commentCount', 0),
            'like_count': item.get('likeCount', 0),
            'is_cream': bool(item.get('is_cream')),
            'is_top': bool(item.get('is_top')),
            'is_original': bool(item.get('is_original')),
            'create_time': item.get('createTime') or '',
            'last_comment_time': item.get('lastCommentTime') or '',
            # 详情页的「相关推荐」（源站字段 doors）
            'related': [{
                'topic_id': d.get('id'),
                'title': d.get('title') or '',
                'description': d.get('description') or '',
                'cover': d.get('img_url') or '',
                'view_count': d.get('view_count', 0),
                'comment_count': d.get('comment_count', 0),
                'buy_count': d.get('buy_count', 0),
            } for d in (item.get('doors') or [])],
        }

    # ==================== 公开能力 ====================

    @staticmethod
    def _plain_text(html: str) -> str:
        """把评论正文转成纯文本（去掉全部 HTML 标签）

        源站评论正文是「HTML 外壳 + 语义标签」的富文本，形如
        <html><head></head><body><p>文字<img src="…"/></p></body></html>。
        这里把标签全部去掉、还原 HTML 实体，只留可读文字（块级标签与 <br> 转成换行）；
        正文里的配图地址不会丢——同一条评论的 images 字段单独给出。
        """
        text = html or ''
        # 先让块级/换行标签留下分隔，避免 <p>a</p><p>b</p> 粘连成 ab
        text = re.sub(r'(?i)<\s*(br|/p|/div|/li|/h[1-6]|/blockquote)\s*/?\s*>', '\n', text)
        text = re.sub(r'<[^>]*>', '', text)     # 其余标签一律去掉
        text = unescape(text)                    # 还原 &nbsp; / &amp; 等实体
        text = re.sub(r'[ \t\u3000]+', ' ', text)
        text = re.sub(r'\s*\n\s*', '\n', text)
        return text.strip()

    @staticmethod
    def _parse_comment_author(item: dict) -> dict:
        """评论作者信息（评论与子回复共用同一批字段，仅大小写不同）"""
        avatar, avatar_encrypted = U.resolve_avatar(item.get('avatar'))
        return {
            'id': item.get('user_id'),
            'nickname': item.get('nickname') or '',
            # 头像：完整地址；avatar_encrypted=True 表示是混淆地址，需用「图片解码」接口换真实图片
            'avatar': avatar,
            'avatar_encrypted': avatar_encrypted,
            'vip': item.get('vip', 0),
            'famous': bool(item.get('famous')),
            'certified': bool(item.get('certified')),
        }

    @classmethod
    def _parse_reply(cls, item: dict) -> dict:
        """把源站子评论规整为对外契约（正文为纯文本）

        源站的子评论是「扁平列表 + 父级指针」：同一主评论下的所有层级混在一起返回，
        靠 top_comment_id 指向它直接回复的那条评论（0 = 直接回复主评论，即标准二级评论），
        层级关系由调用方按这两个 ID 自行组装。
        """
        return {
            'comment_id': item.get('commentId'),
            # 所属主评论 ID（即本接口的查询键 replyId，同一主评论下所有层级都相同）
            'root_comment_id': item.get('reply_id'),
            # 直接回复的那条评论 ID；0 表示直接回复主评论
            'parent_comment_id': item.get('top_comment_id'),
            'author': cls._parse_comment_author(item),
            'content': cls._plain_text(item.get('content')),
            # 引用的评论内容（回复某条子评论时源站下发，通常为 null）
            'quote': cls._plain_text(item['quote']) if isinstance(item.get('quote'), str) else '',
            'like_count': item.get('like_count', 0),
            'liked': bool(item.get('is_like')),
            # 它自己的子回复数（源站字段 count）
            'reply_count': item.get('count', 0),
            # 源站内联下发的「最新一条子回复」预览（通常为 null）
            'last_replies': [cls._parse_reply(r) for r in (item.get('last_comment_list') or [])],
            'create_time': item.get('createTime') or '',
            'pretty_time': item.get('pretty_time') or '',
        }

    @classmethod
    def _parse_comment(cls, item: dict) -> dict:
        """把源站评论条目规整为对外契约（正文为纯文本，配图地址另见 images）"""
        return {
            'comment_id': item.get('reply_id'),
            'floor': item.get('floor'),
            'content': cls._plain_text(item.get('content')),
            'images': [a.get('remoteUrl') for a in (item.get('attachments') or [])
                       if a.get('category') == 'images' and a.get('remoteUrl')],
            'author': cls._parse_comment_author(item),
            'like_count': item.get('like_count', 0),
            'liked': bool(item.get('is_like')),
            # 子回复总数；replies 为源站随本条一并内联下发的子回复列表
            'reply_count': item.get('comment_count', 0),
            'replies': [cls._parse_reply(r) for r in (item.get('commend_list') or [])],
            'is_sale': bool(item.get('is_sale')),
            'price': item.get('price', 0),
            'buy_count': item.get('buyCount', 0),
            'create_time': item.get('create_time') or '',
            'pretty_time': item.get('pretty_time') or '',
        }

    def get_topics(self, tab: str = 'hot', page: int = 1) -> dict:
        """
        获取内容列表（分页）。

        :param tab: 模块（hot 热帖 / news 新闻 / events 大事记 / original 原创 /
                    essence 精华 / latest 最新）
        :param page: 页码，从 1 开始（源站每页 20 条）
        :return: {
            tab,
            pagination: {page, page_size, total, total_page},
            results: [{topic_id, title, excerpt, node, tags, author, images,
                       has_video, money_type, view_count, comment_count,
                       like_count, create_time, last_comment_time}],
        }
        """
        key = f'topics:{tab}:{page}'

        def fetch():
            data = self._request_json('GET', U.build_topics_url(tab, page))
            src_page = data.get('page') or {}
            limit = src_page.get('limit') or 20
            total = src_page.get('total') or 0
            return {
                'tab': tab,
                'pagination': {
                    'page': src_page.get('page', page),
                    'page_size': limit,
                    'total': total,
                    'total_page': (total + limit - 1) // limit if limit else 0,
                },
                'results': [self._parse_item(it) for it in (data.get('results') or [])],
            }

        return get_or_fetch(key, fetch, DATA_TTL)

    def search_topics(self, key: str, page: int = 1, node_id: int = 0) -> dict:
        """
        搜索帖子（分页）。

        :param key: 搜索关键词
        :param page: 页码，从 1 开始（源站每页 20 条）
        :param node_id: 板块 ID，0 表示不限板块
        :return: {
            key, node_id,
            pagination: {page, page_size, total, total_page},
            results: [...（字段与内容列表一致）],
        }
        """
        key = (key or '').strip()
        cache_key = f'search:{key}:{node_id}:{page}'

        def fetch():
            data = self._request_json('GET', U.build_search_url(key, page, node_id))
            src_page = data.get('page') or {}
            limit = src_page.get('limit') or 20
            total = src_page.get('total') or 0
            return {
                'key': key,
                'node_id': node_id,
                'pagination': {
                    'page': src_page.get('page', page),
                    'page_size': limit,
                    'total': total,
                    'total_page': (total + limit - 1) // limit if limit else 0,
                },
                'results': [self._parse_item(it) for it in (data.get('results') or [])],
            }

        return get_or_fetch(cache_key, fetch, DATA_TTL)

    def get_topic_detail(self, topic_id) -> dict:
        """
        获取帖子详情（正文 / 原图附件 / 视频附件 / 互动数据 / 相关推荐）。

        :param topic_id: 帖子 ID（取自内容列表 results[].topic_id）
        :return: 见 _parse_detail()；视频附件的 videos[].url 为可播放的 m3u8 地址

        不做缓存：详情携带随登录凭据变化的字段（视频地址），逐调用方缓存会串数据。
        """
        data = self._request_json('GET', U.build_detail_url(topic_id))
        if not data.get('topicId'):
            raise RuntimeError(f'帖子不存在: topic_id={topic_id}')
        detail = self._parse_detail(data)
        # 视频播放地址需单独解析（源站接口要求登录态；解析失败保持空串，不影响详情返回）
        for video in detail['videos']:
            video['url'] = self._resolve_video_url(video['id'], topic_id)
        return detail

    def _resolve_video_url(self, attachment_id, topic_id) -> str:
        """
        解析视频附件的播放地址（m3u8）。

        源站接口 POST /api/attachment，请求体需带 resource_id / resource_type，
        仅有 id 会返回失败。地址随登录态下发：匿名拿不到（返回空串）。

        :return: 可播放的 m3u8 地址；拿不到时返回空串
        """
        try:
            data = self._request_json('POST', U.ATTACHMENT_URL, {
                # 注意：id / resource_id 必须是整数，传字符串源站会直接返回「请求错误」
                'id': int(attachment_id),
                'resource_id': int(topic_id),
                'resource_type': 'topic',
                'line': '',
            })
        except Exception:       # noqa: BLE001 - 视频地址属可选增强，拿不到不应影响详情
            return ''
        return data.get('remoteUrl') or ''

    def get_topic_comments(self, topic_id, page: int = 1, search_type: int = 0) -> dict:
        """
        获取帖子评论列表（分页，源站每页 20 条，按楼层倒序 = 最新在前）。

        评论正文里的 <img> 与 images 都是源站混淆图片地址（形如 …/<hash>.jpg.txt），
        需用 fetch_image 解码后才能展示。

        不做缓存：评论含随登录凭据变化的字段（liked），逐调用方缓存会串数据。

        :param topic_id: 帖子 ID
        :param page: 页码，从 1 开始
        :param search_type: 0=全部，1=只看楼主（与源站评论区两个 tab 一致）
        :return: {topic_id, search_type, pagination: {page, page_size, total, total_page},
                  results: [...]}
        """
        data = self._request_json('GET', U.build_comments_url(topic_id, page, search_type))
        src_page = data.get('page') or {}
        limit = src_page.get('limit') or U.COMMENT_PAGE_SIZE
        total = src_page.get('total') or 0
        return {
            'topic_id': topic_id,
            'search_type': search_type,
            'pagination': {
                'page': src_page.get('page', page),
                'page_size': limit,
                'total': total,
                'total_page': (total + limit - 1) // limit if limit else 0,
            },
            'results': [self._parse_comment(it) for it in (data.get('results') or [])],
        }

    def get_comment_replies(self, comment_id, page: int = 1) -> dict:
        """
        获取某条主评论下的二级评论（子评论）列表，分页。

        源站走的是另一个接口 /api/comment/comment_list?replyId=<主评论ID>；主评论列表里
        内联下发的 replies 只适合预览，需要完整 / 翻页时用本接口。

        返回的是**扁平列表**（同一主评论下的各层级混在一起），层级关系看每条自身的
        root_comment_id（所属主评论）与 parent_comment_id（直接回复的那条，0 = 回复主评论）。

        :param comment_id: 主评论 ID（评论列表 results[].comment_id）
        :param page: 页码，从 1 开始（源站每页 20 条）
        :return: {comment_id, pagination: {page, page_size, total, total_page}, results}
        """
        data = self._request_json('GET', U.build_comment_replies_url(comment_id, page))
        src_page = data.get('page') or {}
        limit = src_page.get('limit') or U.COMMENT_REPLIES_PAGE_SIZE
        total = src_page.get('total') or 0
        return {
            'comment_id': comment_id,
            'pagination': {
                'page': src_page.get('page', page),
                'page_size': limit,
                'total': total,
                'total_page': (total + limit - 1) // limit if limit else 0,
            },
            'results': [self._parse_reply(it) for it in (data.get('results') or [])],
        }

    @staticmethod
    def _derive_key(fake_key_hex: str, salt_hex: str) -> str:
        """
        调 node + 源站 jquery.wasm 还原视频真密钥。

        源站清单里的 .key 是假密钥，真 AES-128 密钥 = jquery_key(假key, 盐)，
        盐取自同名 <m3u8>.jpg 的内容（见 derive_key.js）。

        :return: 真密钥十六进制字符串
        """
        # 先把「node 不可用」与「node 跑起来后报错」分开报：PATH 里若混进了当前用户
        # 不可访问的目录（如 root 启动 uwsgi 时带上的 /root/bin），Linux 会把「找不到」
        # 误报成 `[Errno 13] Permission denied: 'node'` —— 照那条信息去「补可执行权限」
        # 会查错方向（线上真踩过，见变更记录）。
        if shutil.which(U.NODE_BIN) is None:
            raise RuntimeError(
                f'视频密钥派生失败: 未找到可执行的 node（NODE_BIN={U.NODE_BIN!r}）。'
                f'请在服务器安装 Node.js，或用 .env 的 HAIJIAO_NODE_BIN 指定 node 的绝对路径')
        try:
            proc = subprocess.run(
                [U.NODE_BIN, str(U.DERIVE_CLI), fake_key_hex, salt_hex],
                capture_output=True, text=True, encoding='utf-8', timeout=U.DERIVE_TIMEOUT,
            )
        except (OSError, subprocess.SubprocessError) as e:
            raise RuntimeError(f'视频密钥派生失败（node 调用异常）: {e}')

        for line in (proc.stdout or '').splitlines():
            if line.startswith('REAL_KEY='):
                return line[len('REAL_KEY='):].strip()
        raise RuntimeError(f'视频密钥派生失败: {(proc.stderr or "")[-300:]}')

    def fetch_image(self, url: str) -> str:
        """
        抓取混淆图片地址并解码，返回 data URI（形如 data:image/jpeg;base64,...）。

        源站把图片以自定义字母表的 base64 写进 .../<hash>.jpg.txt，直接访问拿到的是文本。
        出于安全：不跟随重定向、限制体积（见 utils.IMAGE_MAX_BYTES）。

        :param url: 混淆图片地址
        :return: 解码后的 data URI
        """
        with self.session.get(url, timeout=U.REQUEST_TIMEOUT,
                              allow_redirects=False, stream=True) as resp:
            if resp.status_code != 200:
                raise RuntimeError(f'图片地址不可用（HTTP {resp.status_code}）')
            chunks = []
            size = 0
            for chunk in resp.iter_content(65536):
                size += len(chunk)
                if size > U.IMAGE_MAX_BYTES:
                    raise RuntimeError('图片体积超过限制')
                chunks.append(chunk)
        return U.decode_image(b''.join(chunks).decode('utf-8', 'replace'))

    def get_video_playlist(self, topic_id, attachment_id) -> str:
        """
        生成可直接播放的 m3u8（自包含真密钥，标准 HLS 播放器即可播放）。

        源站清单里的密钥是假的，标准播放器会因分片解密失败报 fragParsingError；这里按源站
        播放器的同一套逻辑还原真密钥，并把清单改写为：
          - #EXT-X-KEY 的 URI 换成内嵌真密钥的 data: URI（播放器无需再取密钥）；
          - 分片地址补成绝对地址（清单可能以 blob / 相对地址方式被加载）。

        :param topic_id: 帖子 ID
        :param attachment_id: 视频附件 ID（详情接口 videos[].id）
        :return: 改写后的 m3u8 文本
        """
        cache_key = f'playlist:{topic_id}:{attachment_id}'

        def fetch():
            cdn_url = self._resolve_video_url(attachment_id, topic_id)
            if not cdn_url:
                raise RuntimeError('未取到视频地址（需配置可用的登录凭据）')

            manifest = self._get_text(cdn_url)
            matched = re.search(r'URI="([^"]+)"', manifest)
            if not matched:
                raise RuntimeError('播放列表缺少密钥声明（源站格式可能已变更）')

            # 假密钥 + 盐（同名 .jpg 的内容）→ 真密钥
            fake_key_hex = self._get_bytes(urljoin(cdn_url, matched.group(1))).hex()
            salt_text = self._get_text(cdn_url.replace('.m3u8', '.jpg'))
            salt_hex = base64.b64decode(salt_text.strip()).hex()
            real_key = bytes.fromhex(self._derive_key(fake_key_hex, salt_hex))
            key_uri = 'data:application/octet-stream;base64,' + base64.b64encode(real_key).decode()

            rewritten = manifest.replace(matched.group(0), f'URI="{key_uri}"')
            lines = []
            for line in rewritten.splitlines():
                item = line.strip()
                # 非注释行即分片地址：相对地址补全为绝对地址
                lines.append(urljoin(cdn_url, item) if item and not item.startswith('#') else line)
            return '\n'.join(lines)

        return get_or_fetch(cache_key, fetch, MEDIA_TTL)

    # ==================== 注册 ====================

    @staticmethod
    def _new_session(proxies: dict = None, referer: str = '/register') -> requests.Session:
        """注册 / 登录用独立会话（匿名头，可选走代理；不带登录凭据）

        注意：**不要**在这里设 trust_env=False。源站在大陆直连不通，本机是靠系统代理
        （Windows 注册表的 127.0.0.1:8800 之类）才能访问它的；关掉 trust_env 会让请求
        绕过系统代理直连，直接 ConnectTimeout。

        另一个坑：Windows 上 requests 会读取注册表里的系统代理，并在合并时**以环境代理
        覆盖 session.proxies**，导致显式设置的代理被静默忽略（用一个不存在的代理也能"成功"）。
        所以显式代理必须在**请求级**传（见 _request_json 的 proxies 参数），不能只挂在 session 上。
        """
        session = requests.Session()
        session.headers.update(U.API_HEADERS)
        session.headers['referer'] = f'{U.BASE_URL}{referer}'
        if proxies:
            session.proxies.update(proxies)
        return session

    @staticmethod
    def _pick_proxy(provider: str = None):
        """
        按需取一条动态代理（源站对注册有 IP 限制）。

        注意一个曾经误判的结论：早前观测到的「代理出口大量被 302 到备用域名后 404」，
        并非平台差异，而是 register_captcha 下载图片时漏传请求级代理、导致**取码与取图走了
        两个出口 IP**，源站按 captchaId 校验出口后把图片 302 走（详见该方法的注释）。
        修好后两个平台取码都恢复正常：实测巨量 5/8、51代理 8/8，失败多为代理自身网络抖动。

        51代理 的地址里带上账号密码：它支持「IP 白名单」与「账密」两种认证，本机出口 IP
        恰好在白名单里（不带账密也能通），但线上服务器不一定——账密是真校验项
        （实测故意传错密码，10/10 全部被网关拒绝）。

        「relay」线路另有一套地址（.env 的 PROXY_RELAY_URL / PROXY_RELAY_SECRET）：
        51代理 的**代理 IP 只在国内网络可达**，生产服务器（海外）直连它们一律 TCP 超时
        （实测 0/5，而同一台机器上巨量 4/5 可用）。relay 由国内那台机器去连 51代理
        （见 scripts/hj_relay），挂载时用一次性的「会话键」当代理用户名：同一次
        「取码 → 提交注册」复用同一份 proxies、即同一个出口 IP，换重试则换键换出口。

        :param provider: 代理线路，取值见 PROXY_PROVIDERS；None / 'direct' = 直连
        :return: (代理描述, requests 的 proxies 参数)；不走代理时为 (None, None)
        """
        if not provider or provider == 'direct':
            return None, None

        if provider == 'relay':
            if not (RELAY_URL and RELAY_SECRET):
                raise RuntimeError(
                    '未配置国内中转出口: 请在 .env 里设置 PROXY_RELAY_URL 与 PROXY_RELAY_SECRET')
            host = urlsplit(RELAY_URL).netloc
            if not host:
                raise RuntimeError(
                    f'PROXY_RELAY_URL 格式不对（应形如 http://ip:port）: {RELAY_URL!r}')
            key = secrets.token_urlsafe(9)
            url = f'http://{key}:{quote(RELAY_SECRET, safe="")}@{host}'
            return f'{host}（经国内中转）', {'http': url, 'https': url}

        if provider == '51daili':
            # 懒导入：只有走代理注册时才依赖代理线路的实现
            from SpiderServices.ProxyIp.ProxyIP_51daili.home import ProxyIP51Daili
            from SpiderServices.ProxyIp.ProxyIP_51daili.utils import (
                DEFAULT_ACCESS_NAME, DEFAULT_ACCESS_PASSWORD)
            entry = HaijiaoSpider._first_proxy_entry(
                ProxyIP51Daili().get_proxies(qty=1), provider)
            auth = ''
            if DEFAULT_ACCESS_NAME and DEFAULT_ACCESS_PASSWORD:
                auth = (f'{quote(DEFAULT_ACCESS_NAME, safe="")}:'
                        f'{quote(DEFAULT_ACCESS_PASSWORD, safe="")}@')
            desc, url = f'{entry["ip"]}:{entry["port"]}', f'http://{auth}{entry["ip"]}:{entry["port"]}'
        elif provider == 'juliang':
            from SpiderServices.ProxyIp.ProxyIP_juliang.home import ProxyIPJuliang
            entry = HaijiaoSpider._first_proxy_entry(
                ProxyIPJuliang().get_proxies(num=1), provider)
            # 巨量的返回值自带拼好的 proxy（含账密）
            desc = f'{entry["ip"]}:{entry["port"]}'
            url = entry.get('proxy') or f'http://{entry["ip"]}:{entry["port"]}'
        else:
            raise RuntimeError(
                f'未知的代理线路: {provider!r}（可选 {" / ".join(PROXY_PROVIDERS)}）')

        return desc, {'http': url, 'https': url}

    @staticmethod
    def _first_proxy_entry(result: dict, provider: str) -> dict:
        """从代理线路的返回值里取第一条条目（无条目 / ip 端口不合法都直接报错）"""
        entries = ((result or {}).get('data') or {}).get('proxies') or []
        if not entries:
            raise RuntimeError(
                f"取代理失败（{provider}）: {(result or {}).get('message') or '未返回可用代理'}")
        entry = entries[0]
        ip = str(entry.get('ip') or '').strip()
        port = str(entry.get('port') or '').strip()
        # 代理接口偶尔会返回畸形条目（实测见过端口是负的 int64 溢出值），
        # 这里挡一道，避免下游拼出无效地址报 InvalidURL
        if not ip or not port.isdigit() or not 0 < int(port) < 65536:
            raise RuntimeError(f'取代理失败（{provider}）: 返回的代理条目缺少合法的 ip / 端口')
        return entry

    def register_captcha(self, provider: str = None) -> dict:
        """
        取注册验证码（图片交由人工识别；后续接入验证码识别后即可自动化）。

        :param provider: 代理线路，取值见 PROXY_PROVIDERS；None / 'direct' = 直连
        :return: {'captcha_id', 'captcha_image'(bytes), 'proxy'(代理描述或 None),
                  'proxies'(提交注册时复用的代理参数或 None), 'cookies'(取码会话 Cookie)}
        """
        proxy, proxies = self._pick_proxy(provider)
        session = self._new_session(proxies)
        data = self._request_json('GET', U.CAPTCHA_URL, session=session)
        image_url = urljoin(U.BASE_URL, data.get('captchaUrl') or '')

        # 下载验证码图片。
        #
        # 代理必须走**请求级**（同 _request_json，见 _new_session 的说明）：Windows 上 requests
        # 会用注册表里的系统代理覆盖 session.proxies，只挂 session 会让「取码」与「取图」走成
        # 两个不同的出口 IP —— 源站按 captchaId 绑定取码时的出口校验，IP 对不上就把图片 302 到
        # 备用域名，而备用域名这条路由不稳定（实测大量 404）。之前这里的 404 大多源于此。
        #
        # 另一个已知现象：即便出口一致，源站边缘仍会偶发把图片地址 302 到备用域名。重发同一地址
        # 多能正常返回，故这里仍重试几次再放弃。
        req_proxies = dict(session.proxies) or None
        image = None
        last_err = None
        for attempt in range(U.MAX_RETRIES):
            try:
                resp = session.get(image_url, timeout=U.REQUEST_TIMEOUT, proxies=req_proxies)
                resp.raise_for_status()
                image = resp.content
                break
            except Exception as e:      # noqa: BLE001 - 404 / 网络抖动都值得重取
                last_err = e
                if attempt < U.MAX_RETRIES - 1:
                    time.sleep(U.RETRY_DELAY)
        if image is None:
            raise RuntimeError(f'获取验证码图片失败（已尝试 {U.MAX_RETRIES} 次）: {last_err}')

        return {'captcha_id': data.get('captchaId'), 'captcha_image': image,
                'proxy': proxy, 'proxies': proxies, 'cookies': session.cookies}

    def submit_register(self, username: str, password: str, email: str,
                        captcha_id: str, captcha_code: str, proxies: dict = None,
                        cookies=None) -> dict:
        """
        提交注册。

        :param username: 用户名
        :param password: 密码（RPassword 由本方法补齐为同值）
        :param email: 邮箱
        :param captcha_id: 取验证码时返回的 captchaId
        :param captcha_code: 验证码（人工识别结果）
        :param proxies: 与取验证码同一出口 IP 的代理参数（走代理注册时必传）
        :param cookies: 取验证码时的会话 Cookie（验证码若与会话绑定则必须复用）
        :return: 源站返回的 {'token', 'user'}
        """
        session = self._new_session(proxies)
        if cookies is not None:
            session.cookies.update(cookies)
        return self._request_json('POST', U.SIGNUP_URL, payload={
            'Username': username,
            'Password': password,
            'RPassword': password,
            'Email': email,
            'CaptchaCode': captcha_code,
            'CaptchaId': captcha_id,
            'Ref': '/',
        }, session=session, retry_business=False, retry_network=False)

    def login(self, username: str, password: str) -> dict:
        """
        账号登录（源站 POST /api/login/signin）。

        签名与源站前端一致：Sign = md5(Username + Password + User-Agent)（UA 必须与请求头一致）。
        正常风控下无需图形验证码，故 CaptchaCode / CaptchaId 传空串。

        :return: 源站返回的 {'token', 'user', ...}
        """
        sign = hashlib.md5((username + password + U.UA_STRING).encode()).hexdigest()
        return self._request_json('POST', U.LOGIN_URL, payload={
            'Username': username,
            'Password': password,
            'CaptchaCode': '',
            'CaptchaId': '',
            'Ref': '/',
            'Sign': sign,
            'CaptchaImg': 'e',
        }, session=self._new_session(referer='/login'), retry_business=False)

    # ==================== 金币签到 ====================

    def get_sign_in_status(self) -> dict:
        """
        每日金币签到状态（源站 GET /api/task/getTaskStatus 的 goldSignIn 字段）。

        源站的 goldSignIn.status 语义是「是否可签到」：true=今日未签到，false=今日已签到，
        故对外统一翻转为更直观的 signed。

        :return: {'open': 任务是否开放, 'signed': 今日是否已签到, 'reward': 签到可得金币}
        """
        data = self._request_json('GET', U.TASK_STATUS_URL)
        gold = data.get('goldSignIn') or {}
        return {
            'open': bool(gold.get('open')),
            'signed': not bool(gold.get('status')),
            'reward': gold.get('num') or 0,
        }

    def sign_in(self) -> dict:
        """
        每日金币签到（源站 POST /api/user/user_sign_in，无请求体）。

        幂等：先查任务状态，今日已签到 / 任务未开放时不重复提交（源站重复签到会返回
        「今天已签到」业务失败）。

        :return: {'state': signed|already|closed, 'amount': 本次到账金币, 'message': 说明}
        """
        status = self.get_sign_in_status()
        if not status['open']:
            return {'state': 'closed', 'amount': 0, 'message': '签到任务未开放'}
        if status['signed']:
            return {'state': 'already', 'amount': 0, 'message': '今天已签到'}
        data = self._request_json('POST', U.SIGN_IN_URL, retry_business=False)
        return {'state': 'signed', 'amount': data.get('amount') or 0, 'message': ''}

    # ==================== 发帖 ====================

    def get_nodes(self) -> dict:
        """
        获取板块列表（源站 GET /api/topic/nodes_by_ver/v2）。

        源站下发的是扁平列表（parentId 指父板块），这里按层级组装出 children，方便前端做联动下拉。

        :return: {'ver': 版本号, 'list': [顶层板块...]}，
                 板块字段：node_id / parent_id / name / icon / description / vip_limit / display / children
        """
        def fetch():
            data = self._request_json('GET', U.NODES_URL)
            nodes = [{
                'node_id': n.get('nodeId'),
                'parent_id': n.get('parentId') or 0,
                'name': n.get('name') or '',
                'icon': n.get('icon') or '',
                'description': n.get('description') or '',
                'vip_limit': n.get('vipLimit') or 0,
                'display': n.get('display') or 0,
                'children': [],
            } for n in (data.get('list') or [])]
            by_id = {n['node_id']: n for n in nodes}
            roots = []
            for node in nodes:
                parent = by_id.get(node['parent_id'])
                (parent['children'] if parent else roots).append(node)
            return {'ver': data.get('ver') or 0, 'list': roots}

        return get_or_fetch('topic_nodes', fetch, DATA_TTL)

    def get_tags(self, page: int = 1) -> dict:
        """
        获取标签池（源站 GET /api/tag/tags，分页，每页 20 条，最新创建的在前）。

        注意：源站该接口不支持关键词搜索（前端是在已加载的一页里本地过滤的）。

        :param page: 页码，从 1 开始
        :return: {'pagination': {page, page_size, total, total_page},
                  'results': [{tag_id, tag_name}]}
        """
        def fetch():
            data = self._request_json('GET', f'{U.TAGS_URL}?page={page}')
            src_page = data.get('page') or {}
            limit = src_page.get('limit') or 20
            total = src_page.get('total') or 0
            return {
                'pagination': {
                    'page': src_page.get('page', page),
                    'page_size': limit,
                    'total': total,
                    'total_page': (total + limit - 1) // limit if limit else 0,
                },
                'results': [{'tag_id': t.get('tagId'), 'tag_name': t.get('tagName') or ''}
                            for t in (data.get('results') or [])],
            }

        return get_or_fetch(f'tags:{page}', fetch, DATA_TTL)

    @staticmethod
    def media_html(category: str, url: str, attachment_id) -> str:
        """按源站正文格式生成媒体片段

        图片：正文里存真实地址 + data-id；视频：源站正文只留空 src 的占位，靠 data-id 关联附件。
        """
        if category == 'video':
            return f'<video src="" data-id="{attachment_id}"></video>'
        return f'<img src="{url}" data-id="{attachment_id}"/>'

    def upload_media(self, filename: str, data: bytes, content_type: str = None) -> dict:
        """
        上传图片 / 视频（源站 POST /api/upload，multipart）。

        源站前端把图片与视频都放在同一个 image 字段提交，靠返回的 category 区分类型；
        上传只产生附件，不会带进帖子，发帖时由正文里的 data-id 关联。

        :param filename: 原始文件名（用于推断 MIME 与扩展名）
        :param data: 文件二进制
        :param content_type: 可选 MIME，不传按文件名推断
        :return: {'attachment_id', 'category', 'url', 'html'}
                 url：图片为真实地址（已去掉源站下发的 _mini 缩略图后缀）；视频没有地址，为空串
        """
        ext = os.path.splitext(filename or '')[1].lower()
        if ext in U.MEDIA_IMAGE_EXTS:
            if len(data) > U.MEDIA_IMAGE_MAX_BYTES:
                limit_mb = U.MEDIA_IMAGE_MAX_BYTES // 1024 // 1024
                raise RuntimeError(f'图片体积超过源站限制（{limit_mb}MB）')
        elif ext not in U.MEDIA_VIDEO_EXTS:
            exts = ' / '.join(U.MEDIA_IMAGE_EXTS + U.MEDIA_VIDEO_EXTS)
            raise RuntimeError(f'不支持的媒体类型（仅支持 {exts}）: {filename}')

        files = {'image': (filename, data, content_type or mimetypes.guess_type(filename)[0])}
        resp = self.session.post(U.UPLOAD_URL,
                                 data={'entity_id': '', 'entity_type': 'topic'},
                                 files=files, timeout=U.UPLOAD_TIMEOUT)
        if resp.status_code != 200:
            raise RuntimeError(f'上传失败（HTTP {resp.status_code}）')
        envelope = resp.json()
        if not envelope.get('success'):
            raise RuntimeError(envelope.get('message') or '上传失败')
        info = U.decode_payload(envelope['data']) or {}
        attachment_id = info.get('id')
        category = info.get('category') or 'images'
        # 源站下发的是 _mini 缩略图地址，正文里用的是去掉 _mini 的原图地址
        url = (info.get('remoteUrl') or '').replace('_mini', '')
        return {'attachment_id': attachment_id, 'category': category, 'url': url,
                'html': self.media_html(category, url, attachment_id)}

    def get_post_captcha(self) -> dict:
        """
        查询发帖是否触发风控人机验证（源站 GET /api/captcha/request?t=topicCaptcha）。

        源站前端在发布前先问一次：需要验证时弹滑块拼图，人工通过后才真正发帖。

        :return: {'is_captcha': 是否需要人机验证, 'captcha_id': 验证 ID（不需要时为空串）}
        """
        data = self._request_json('GET', U.TOPIC_CAPTCHA_URL)
        return {'is_captcha': bool(data.get('isCaptcha')),
                'captcha_id': data.get('captchaId') or ''}

    def create_topic(self, node_id: int, title: str, content: str, tags: list,
                     topic_type: int = 0, money_type: int = 0, amount: int = 0,
                     reward_hours: int = 0) -> dict:
        """
        发帖（源站 POST /api/topic/create，JSON 请求体）。

        先按源站前端的做法问一次人机验证：需要验证时直接报错——源站用的是滑块拼图，
        必须人工完成，本服务无法代过。

        源站对发布有风控：短时间内重复发帖会被限流（如「请勿灌水，耐心等待4分钟再操作吧」），
        新账号还可能进入人工审核——此时源站仍算成功，但返回的帖子 ID 为空、pending 为 True。

        :param node_id: 板块 ID（取自板块列表的叶子节点 node_id）
        :param title: 标题（源站上限 36 字）
        :param content: 正文 HTML（媒体片段用 media_html 生成）
        :param tags: 标签名列表（源站按名称关联，不存在的名称会被当作新标签）
        :param topic_type: 0=普通 1=出售 2=悬赏
        :param money_type: 0=金币 1=钻石（仅出售 / 悬赏有意义）
        :param amount: 出售价格 / 悬赏金额（源站前端按金币 ×100 换算）
        :param reward_hours: 悬赏时长（源站要求 72-240 的整数）
        :return: {'topic_id': 帖子 ID 或 None, 'pending': 是否待审核（拿不到 ID 即待审核）}
        """
        if self.get_post_captcha()['is_captcha']:
            raise RuntimeError('源站已触发风控：需要完成滑块人机验证，请换账号或稍后重试')
        # 源站前端换算：金币（0）按 ×100 提交，钻石（1）按原值提交
        raw_amount = amount if money_type == 1 else amount * 100
        data = self._request_json('POST', U.TOPIC_CREATE_URL, payload={
            'type': topic_type,
            'money_type': money_type,
            'amount': raw_amount,
            'reward_hours': reward_hours,
            'content': content,
            'ats': [],
            'title': title,
            'node_id': node_id,
            'tags': tags,
            'isPublisher': True,
        }, retry_business=False, retry_network=False)
        topic_id = int(data) if isinstance(data, int) and data else None
        return {'topic_id': topic_id, 'pending': topic_id is None}

    @classmethod
    def _parse_my_topic(cls, item: dict) -> dict:
        """我的帖子条目：在列表条目基础上补充审核相关信息"""
        data = cls._parse_item(item)
        data.update({
            # 审核失败 / 审核中的条目没有帖子 ID，只有待审 ID（topic_pending_id）
            'pending_id': item.get('topic_pending_id'),
            # 源站条目自带的状态码：已发布的条目为 0，审核失败的为 4
            'source_status': item.get('status'),
            # 审核失败原因（审核通过与审核中时为空串）
            'remarks': (item.get('remarks') or '').strip(),
            'has_pic': bool(item.get('hasPic')),
            'has_video': bool(item.get('hasVideo')),
            'has_audio': bool(item.get('hasAudio')),
            'is_top': bool(item.get('is_top')),
            'is_cream': bool(item.get('is_cream')),
            'is_original': bool(item.get('is_original')),
        })
        return data

    def get_my_topics(self, status: int = U.MY_TOPIC_STATUS_PUBLISHED, page: int = 1) -> dict:
        """
        获取当前登录账号的帖子列表（「我的帖子」，按审核状态筛选）。

        源站对应 /post/release 页的三个 tab；审核失败 / 审核中的条目拿不到帖子 ID，
        只有 pending_id，失败原因见每条 remarks。该接口必须带登录态。

        :param status: 3=审核通过 2=审核中 4=审核失败
        :param page: 页码，从 1 开始（源站每页 10 条）
        :return: {status, pagination: {page, page_size, total, total_page}, results}
        """
        data = self._request_json('GET', U.build_my_topics_url(status, page))
        src_page = data.get('page') or {}
        limit = src_page.get('limit') or U.MY_TOPICS_PAGE_SIZE
        total = src_page.get('total') or 0
        return {
            'status': status,
            'pagination': {
                'page': src_page.get('page', page),
                'page_size': limit,
                'total': total,
                'total_page': (total + limit - 1) // limit if limit else 0,
            },
            'results': [self._parse_my_topic(it) for it in (data.get('results') or [])],
        }

    # ==================== 礼物 / 打赏 ====================

    @staticmethod
    def _parse_gift(item: dict) -> dict:
        """把源站礼物条目规整为对外契约（价格按礼物类型取金币 / 钻石字段）"""
        is_gold = item.get('moneyType') != U.GIFT_KIND_MONEY_TYPE['diamond']
        return {
            'item_id': item.get('itemId'),
            'name': item.get('name') or '',
            'desc': item.get('desc') or '',
            'money_type': item.get('moneyType', 0),      # 1=金币 2=钻石
            'kind': 'gold' if is_gold else 'diamond',
            # 原价 / 售价：实际扣费 = sale_price × 数量（与源站前端一致）
            'price': item.get('goldPrice' if is_gold else 'diamondPrice', 0),
            'sale_price': item.get('goldSalePrice' if is_gold else 'diamondSalePrice', 0),
            'img': item.get('img') or '',
            'expire_time': item.get('expireTime') or '',
            'vip_limit': item.get('vip', 0),
        }

    def get_gift_list(self, kind: str = 'gold', page: int = 1) -> dict:
        """
        获取礼物列表（打赏时用来挑礼物）。

        :param kind: gold=金币礼物（默认） / diamond=钻石礼物
        :param page: 页码，从 1 开始
        :return: {kind, pagination: {page, page_size, total, total_page}, results}
        """
        data = self._request_json('GET', U.build_gift_list_url(kind, page, U.GIFT_LIST_PAGE_SIZE))
        src_page = data.get('page') or {}
        limit = src_page.get('limit') or U.GIFT_LIST_PAGE_SIZE
        total = src_page.get('total') or 0
        return {
            'kind': kind,
            'pagination': {
                'page': src_page.get('page', page),
                'page_size': limit,
                'total': total,
                'total_page': (total + limit - 1) // limit if limit else 0,
            },
            'results': [self._parse_gift(it) for it in (data.get('results') or [])],
        }

    def give_topic_gift(self, topic_id, item_id=None, quantity: int = 1, kind: str = 'gold') -> dict:
        """
        给帖子打赏：买下礼物送给帖子作者。

        源站 /api/store/buy_give 只认「收礼人用户 ID」，所以先取帖子详情拿到作者 ID，
        再带上来源标识（sourceType=1 帖子 + sourceId=帖子 ID）提交，与站点打赏弹窗完全一致；
        礼物是「现买现送」，不需要事先拥有。该接口必须带登录态。

        :param topic_id: 帖子 ID
        :param item_id: 礼物 ID（取自 get_gift_list）；不传则自动选该类型里最便宜的一个
        :param quantity: 赠送数量，1~GIVE_MAX_QUANTITY
        :param kind: gold=金币礼物（默认） / diamond=钻石礼物
        :return: {topic_id, item, quantity, total_cost, receiver, money}
        """
        if kind not in U.GIFT_KINDS:
            raise ValueError('礼物类型仅支持 ' + ' / '.join(U.GIFT_KINDS))
        if not isinstance(quantity, int) or not 1 <= quantity <= U.GIVE_MAX_QUANTITY:
            raise ValueError(f'赠送数量必须为 1~{U.GIVE_MAX_QUANTITY} 的整数')

        gifts = self.get_gift_list(kind=kind)['results']
        if not gifts:
            raise RuntimeError(f'没有可赠送的{kind}礼物')
        if item_id:
            gift = next((g for g in gifts if g['item_id'] == item_id), None)
            if gift is None:
                raise RuntimeError(f'礼物不存在: item_id={item_id}')
        else:
            gift = min(gifts, key=lambda g: g['sale_price'] or g['price'])

        # 收礼人 = 帖子作者（源站打赏弹窗传的就是作者的用户 ID）
        receiver = (self.get_topic_detail(topic_id).get('author') or {})
        if not receiver.get('id'):
            raise RuntimeError('未能获取帖子作者，无法打赏')

        unit_price = gift['sale_price'] or gift['price']
        url = U.build_buy_give_url(gift['item_id'], quantity, kind, receiver['id'],
                                   source_type=U.GIVE_SOURCE_TOPIC, source_id=topic_id)
        # 打赏是写操作且会扣费：业务失败与网络异常都不重试，避免重复赠送
        money = self._request_json('GET', url, retry_business=False, retry_network=False)
        return {
            'topic_id': topic_id,
            'item': gift,
            'quantity': quantity,
            'total_cost': unit_price * quantity,
            'receiver': {'user_id': receiver.get('id'), 'nickname': receiver.get('nickname') or ''},
            'money': money,      # 源站返回的赠送后余额
        }

    # ==================== 关注 / 取消关注 ====================

    def set_follow(self, target_user_id, follow: bool = True) -> dict:
        """
        关注 / 取消关注某个用户。

        源站接口 /api/user/favorite?targetId=<用户ID>&opt=add|rm（个人主页的「关注」按钮），
        成功时只回状态（信封 data 为 null）。必须带登录态，且不能关注自己；
        重复关注 / 取关会被源站拒绝（"你已关注此用户" / "用户并未关注被取消的用户"）。

        :param target_user_id: 目标用户 ID（个人主页 /homepage/<user_id> 里的那段数字）
        :param follow: True=关注 False=取消关注
        :return: {target_user_id, action, followed}
        """
        opt = U.FOLLOW_OPT_ADD if follow else U.FOLLOW_OPT_RM
        # 写操作：业务失败与网络异常都不重试（重复关注本身就会被源站拒）
        self._request_json('GET', U.build_follow_url(target_user_id, opt),
                           retry_business=False, retry_network=False)
        return {
            'target_user_id': target_user_id,
            'action': 'follow' if follow else 'unfollow',
            'followed': bool(follow),
        }

    # ==================== 排行榜 ====================

    @staticmethod
    def _parse_ranking_item(item: dict) -> dict:
        """把源站榜单条目规整为对外契约（value 为该榜单的数值：粉丝数 / 点赞数 / 人气值）"""
        title = item.get('title') or {}
        avatar, avatar_encrypted = U.resolve_avatar(item.get('avatar'))
        return {
            'rank': item.get('rank'),
            'user_id': item.get('user_id'),
            'nickname': item.get('nickname') or '',
            'avatar': avatar,
            # True = 自定义头像给的是混淆地址（…/<hash>.txt），要用「图片解码」接口换真实图片
            'avatar_encrypted': avatar_encrypted,
            'vip': item.get('vip', 0),
            'famous': bool(item.get('famous')),
            'certified': bool(item.get('certified')),
            'value': item.get('value', 0),
            # 用户头衔（等级徽章），可能为空
            'title': {'id': title.get('id'), 'name': title.get('name') or '',
                      'icon': title.get('icon') or ''},
        }

    def get_ranking(self, key: str = 'fans', type_value='all') -> dict:
        """
        获取排行榜（首页「排行榜」模块）。

        源站一次返回整张榜单（不翻页，实测前三名维度约 101 条，冷门维度更少）。

        :param key: 维度 fans=粉丝 / liked=点赞 / wealth=人气
        :param type_value: 周期 all=总榜 / 30=月榜 / 7=周榜
        :return: {key, total, results: [{rank, user_id, nickname, avatar, avatar_encrypted,
                 vip, famous, certified, value, title}]}
                 （avatar 为完整地址；avatar_encrypted=True 表示该地址是混淆地址，需解码）
        """
        data = self._request_json('GET', U.build_ranking_url(key, type_value)) or []
        return {
            'key': key,
            'total': len(data),
            'results': [self._parse_ranking_item(it) for it in data],
        }

    # ==================== 用户信息 / 钱包 / 社交 ====================

    @staticmethod
    def _parse_user_card(item: dict) -> dict:
        """把源站的「用户名片」规整为对外契约（主页信息 / 关注列表 / 粉丝列表共用）"""
        avatar, avatar_encrypted = U.resolve_avatar(item.get('avatar'))
        return {
            'user_id': item.get('id') or item.get('userId'),
            'nickname': item.get('nickname') or '',
            'avatar': avatar,
            'avatar_encrypted': avatar_encrypted,
            'description': item.get('description') or '',
            'fans_count': item.get('fansCount', 0),
            'vip': item.get('vip', 0),
            'famous': bool(item.get('famous')),
            'certified': bool(item.get('certified')),
            # 相对**调用方账号**：我是否已关注 TA
            'is_followed': bool(item.get('isFavorite')),
        }

    @staticmethod
    def _parse_wealth_log(item: dict) -> dict:
        """把源站钱包流水条目规整为对外契约（amount 正负表示收入 / 支出）"""
        return {
            'amount': item.get('amount', 0),
            'balance_after': item.get('after'),
            'time': item.get('log_time') or '',
            'description': item.get('description') or '',
        }

    def get_user_info(self, user_id) -> dict:
        """
        获取某个用户的主页信息（谁？多少人关注？我关注了没？）。

        :param user_id: 目标用户 ID（个人主页 /homepage/<user_id> 里的数字）
        :return: {user_id, nickname, avatar, avatar_encrypted, description, fans_count,
                 vip, famous, certified, is_followed, topic_count, video_count,
                 comment_count, favorite_count, like_count}
        """
        data = self._request_json('GET', U.build_user_info_url(user_id)) or {}
        user = data.get('user') or {}
        info = self._parse_user_card(user)
        # 注意：主页信息里的 isFavorite 在**外层**（不在 user 对象里），用它覆盖名片里的同名字段
        info['is_followed'] = bool(data.get('isFavorite'))
        info.update({
            'topic_count': user.get('topicCount', 0),
            'video_count': user.get('videoCount', 0),
            'comment_count': user.get('commentCount', 0),
            'favorite_count': user.get('favoriteCount', 0),
            # TA 主页里被点赞的总数（相对调用方账号的点赞数见 like_state）
            'like_count': data.get('likeCount', 0),
        })
        return info

    def get_wealth(self) -> dict:
        """获取当前登录账号的余额（金币 / 钻石）。必须带登录态。"""
        return self._request_json('GET', U.WEALTH_URL) or {}

    def get_wealth_log(self, kind: str = 'gold', page: int = 1) -> dict:
        """
        获取金币 / 钻石流水（分页，最新在前）。

        :param kind: gold=金币 / diamond=钻石
        :param page: 页码，从 1 开始
        :return: {kind, pagination: {page, page_size, total, total_page}, results}
        """
        data = self._request_json(
            'GET', U.build_wealth_log_url(kind, page, U.SOCIAL_PAGE_SIZE)) or {}
        src = data.get('page') or {}
        limit = src.get('limit') or U.SOCIAL_PAGE_SIZE
        total = src.get('total') or 0
        return {
            'kind': kind,
            'pagination': {
                'page': src.get('page', page),
                'page_size': limit,
                'total': total,
                'total_page': (total + limit - 1) // limit if limit else 0,
            },
            'results': [self._parse_wealth_log(it) for it in (data.get('results') or [])],
        }

    def get_following(self) -> dict:
        """获取我关注的人（源站一次返回全部、不分页）。必须带登录态。"""
        data = self._request_json('GET', U.FOLLOWING_URL) or []
        return {'total': len(data), 'results': [self._parse_user_card(it) for it in data]}

    def get_fans(self, page: int = 1) -> dict:
        """
        获取我的粉丝（分页）。

        :param page: 页码，从 1 开始
        :return: {pagination, results}
        """
        data = self._request_json(
            'GET', U.build_fans_url(page, U.SOCIAL_PAGE_SIZE)) or {}
        src = data.get('page') or {}
        limit = src.get('limit') or U.SOCIAL_PAGE_SIZE
        total = src.get('total') or 0
        return {
            'pagination': {
                'page': src.get('page', page),
                'page_size': limit,
                'total': total,
                'total_page': (total + limit - 1) // limit if limit else 0,
            },
            'results': [self._parse_user_card(it) for it in (data.get('results') or [])],
        }

    def get_like_state(self, topic_id) -> dict:
        """查询**当前账号**是否已给该帖子点赞（点赞前先查可避免重复提交）"""
        data = self._request_json(
            'GET', f'{U.LIKE_URL}?entityType={U.LIKE_ENTITY_TOPIC}&entityId={topic_id}') or {}
        return {'topic_id': topic_id, 'liked': bool(data.get('like'))}

    def set_topic_like(self, topic_id, like: bool = True) -> dict:
        """
        给帖子点赞 / 取消点赞。

        源站 POST /api/topic/like/<帖子ID>，body 是 multipart 表单：
        entityType=topic + status=<点赞后的目标状态>（true=点赞 false=取消，不是「切换」）。
        必须带登录态。

        :return: {topic_id, action, liked}
        """
        files = {
            'entityType': (None, U.LIKE_ENTITY_TOPIC),
            'status': (None, 'true' if like else 'false'),
        }
        # 写操作：业务失败与网络异常都不重试（重复点赞没有意义，且状态由 status 明确指定）
        self._request_json('POST', U.build_like_url(topic_id), files=files,
                           retry_business=False, retry_network=False)
        return {
            'topic_id': topic_id,
            'action': 'like' if like else 'unlike',
            'liked': bool(like),
        }

    def get_liked_topics(self, page: int = 1) -> dict:
        """
        获取我点赞过的帖子（分页）。

        :param page: 页码，从 1 开始
        :return: {pagination, results}（results 与「内容列表」的帖子结构一致）
        """
        data = self._request_json(
            'GET', U.build_liked_topics_url(page, U.SOCIAL_PAGE_SIZE)) or {}
        src = data.get('page') or {}
        limit = src.get('limit') or U.SOCIAL_PAGE_SIZE
        total = src.get('total') or 0
        return {
            'pagination': {
                'page': src.get('page', page),
                'page_size': limit,
                'total': total,
                'total_page': (total + limit - 1) // limit if limit else 0,
            },
            'results': [self._parse_item(it) for it in (data.get('results') or [])],
        }

    # ==================== 收藏 ====================

    def add_favorite(self, topic_id, folder_id: int = U.FAVORITE_ALL_FOLDERS) -> dict:
        """
        把帖子收藏到指定收藏夹（不传 folder_id 即默认收藏夹）。源站对应 /post/collection 的收藏按钮。

        写操作：业务失败与网络异常都不重试（重复收藏虽幂等，但重试没有意义）。
        重复收藏同一帖子源站仍回成功，故调用方无需先查再收藏。

        :return: {topic_id, folder_id, action}
        """
        self._request_json('GET', U.build_favorite_add_url(folder_id, topic_id),
                           retry_business=False, retry_network=False)
        return {'topic_id': topic_id, 'folder_id': folder_id, 'action': 'add'}

    def remove_favorite(self, topic_id) -> dict:
        """
        取消收藏帖子（未收藏的帖子源站会拒绝：「无法删除无效的数据」）。

        写操作：业务失败与网络异常都不重试。

        :return: {topic_id, action}
        """
        self._request_json('GET', U.build_favorite_delete_url(topic_id),
                           retry_business=False, retry_network=False)
        return {'topic_id': topic_id, 'action': 'remove'}

    def create_favorite_folder(self, name: str) -> dict:
        """
        新建收藏夹（源站校验：名称 1-12 位字符、同名会拒绝）。

        写操作：业务失败与网络异常都不重试（重试可能建出重复的夹子）。

        :return: {folder_id, name, count}（新建出来的收藏夹）
        """
        data = self._request_json('GET', U.build_favorite_folder_add_url(name),
                                  retry_business=False, retry_network=False) or {}
        return self._parse_favorite_folder(data)

    def rename_favorite_folder(self, folder_id, name: str) -> dict:
        """
        重命名收藏夹（源站复用「新建」接口，传已有 folder_id 即为重命名）。

        源站校验：名称 1-12 位字符、不可与已有收藏夹同名（改成自己当前的名字同样会被拒）、
        不可改成保留名「默认收藏夹」。

        写操作：业务失败与网络异常都不重试。源站成功时返回的是假对象（id 恒为 0），
        故这里按调用方传入的值回传，不回传源站那个对象。

        :return: {folder_id, name, action}
        """
        self._request_json('GET', U.build_favorite_folder_add_url(name, folder_id),
                           retry_business=False, retry_network=False)
        return {'folder_id': folder_id, 'name': name, 'action': 'rename'}

    def delete_favorite_folder(self, folder_id) -> dict:
        """
        删除收藏夹（源站要求夹内为空，非空会拒绝：「不能删除非空收藏夹」）。

        写操作：业务失败与网络异常都不重试。

        :return: {folder_id, action}
        """
        self._request_json('GET', U.build_favorite_folder_delete_url(folder_id),
                           retry_business=False, retry_network=False)
        return {'folder_id': folder_id, 'action': 'delete'}

    @staticmethod
    def _parse_favorite_folder(item: dict) -> dict:
        """收藏夹条目：源站字段转对外契约（下划线命名）"""
        return {
            'folder_id': item.get('id'),
            'name': item.get('name') or '',
            # 该收藏夹里的帖子数（源站提供；「全部收藏」这个伪夹子的数值不可靠，忽略即可）
            'count': item.get('count') or 0,
        }

    def get_favorite_folders(self) -> dict:
        """
        获取当前登录账号的收藏夹列表（「我的收藏」页左侧的收藏夹）。

        源站对应 /post/collection 页；一个收藏都没有时源站回空（data 为 null），本方法归一为
        空列表。必须带登录态。

        :return: {total, results: [{folder_id, name, count}]}
        """
        data = self._request_json('GET', U.FAVORITE_FOLDER_LIST_URL) or []
        return {
            'total': len(data),
            'results': [self._parse_favorite_folder(it) for it in data],
        }

    def get_favorite_topics(self, page: int = 1,
                            folder_id: int = U.FAVORITE_ALL_FOLDERS) -> dict:
        """
        获取当前登录账号收藏的帖子（分页，可按收藏夹筛选）。

        :param page: 页码，从 1 开始（源站每页 20 条）
        :param folder_id: 收藏夹 ID（取自 get_favorite_folders 的 folder_id）；
                          U.FAVORITE_ALL_FOLDERS（0）= 全部收藏（跨收藏夹）
        :return: {pagination: {page, page_size, total, total_page}, results}
                 （results 与「内容列表」的帖子结构一致）
        """
        data = self._request_json(
            'GET', U.build_favorite_topics_url(folder_id, page, U.FAVORITE_PAGE_SIZE)) or {}
        src = data.get('page') or {}
        limit = src.get('limit') or U.FAVORITE_PAGE_SIZE
        total = src.get('total') or 0
        return {
            'pagination': {
                'page': src.get('page', page),
                'page_size': limit,
                'total': total,
                'total_page': (total + limit - 1) // limit if limit else 0,
            },
            'results': [self._parse_item(it) for it in (data.get('results') or [])],
        }
