"""微博爬虫

对外能力：
    `WeiboSpider.get_channels()`   频道分类（「我的频道」+「频道推荐」）
    `WeiboSpider.get_feed(...)`    按频道取内容（图片 / 视频直链 / 转发原微博 / 长文展开）
    `WeiboSpider.check_cookie()`   判断这份 Cookie 还登录着没

以及供「账号托管底层」调用的模块级函数（注册在 `API/common/platform_accounts.py`）：
    `check_credential(cookie) -> (bool, str)`

错误约定：抓取失败统一抛 `WeiboError`，消息是可直接展示给调用方的中文说明，
由 API 层负责映射成统一响应码（`{code, msg, data}`）。

登录态判定（实测，很关键）：微博 ajax 接口在未登录 / 凭据失效时**仍返回 HTTP 200**，
body 是 `{"ok": -100, "url": "https://weibo.com/login.php?..."}`；所以不能只看状态码。
"""
import logging

import requests

from . import utils

logger = logging.getLogger('api.weibo')


class WeiboError(Exception):
    """微博抓取失败（消息可直接展示给调用方）"""


class WeiboCredentialExpired(WeiboError):
    """登录凭据已过期 / 失效 —— 需要重新登录后更新 Cookie

    单独一个类型，好让上层能把「托管账号」的状态自动标成「已过期」。
    """


class WeiboSpider:
    """微博抓取器：一个实例 = 一份登录凭据（Cookie）"""

    def __init__(self, cookie='', timeout=None):
        self.cookie = (cookie or '').strip()
        self.timeout = timeout or utils.DEFAULT_TIMEOUT
        self.session = requests.Session()

    # ==================== 内部 ====================
    @staticmethod
    def _check_payload(payload):
        """把微博的业务错误翻译成异常（HTTP 200 也可能是失败）"""
        if not isinstance(payload, dict):
            raise WeiboError('微博返回结构异常')
        ok = payload.get('ok')
        if ok == utils.NOT_LOGIN_OK:
            raise WeiboCredentialExpired('微博登录凭据已过期或无效，请重新登录后更新 Cookie')
        if ok != 1:
            message = (payload.get('message') or payload.get('msg') or '').strip()
            raise WeiboError(f'微博返回异常：{message}' if message else '微博返回异常')
        return payload

    def _get_json(self, url, params=None, referer=f'{utils.BASE_URL}/'):
        """请求并解析 JSON；异常统一转成 WeiboError"""
        headers = utils.build_headers(referer)
        if self.cookie:
            headers['Cookie'] = self.cookie
        try:
            resp = self.session.get(url, params=params, headers=headers,
                                    timeout=self.timeout)
        except requests.RequestException as exc:
            raise WeiboError(f'请求微博失败: {exc}') from exc
        if resp.status_code != 200:
            raise WeiboError(f'微博返回异常状态码 {resp.status_code}')
        try:
            payload = resp.json()
        except ValueError as exc:
            raise WeiboError('微博返回的不是合法 JSON（可能被风控拦截）') from exc
        return self._check_payload(payload)

    def _containerid_of(self, channel_id):
        """按频道 gid 查配套的 containerid

        微博要求 `group_id` 传 gid、`containerid` 传 containerid，两者对多数频道**并不相同**
        （如 明星 gid=1028034288 / containerid=102803_ctg1_4288_-_ctg1_4288），
        所以只给了 gid 时得从频道分类里查一次。
        """
        for group in self.get_channels():
            for channel in group['channels']:
                if channel_id in (channel['id'], channel['containerid']):
                    return channel['id'], channel['containerid']
        return '', ''

    # ==================== 对外 ====================
    def get_channels(self):
        """频道分类：返回「我的频道」与「频道推荐」两组

        :return: [{section, count, channels: [{id, name, containerid, url}]}, ...]
            —— `id` 即网页 /hot/weibo/{id} 里的数字，`containerid` 取内容时要一起用
        """
        data = self._get_json(utils.ALL_GROUPS_API,
                              params={'is_new_segment': 1, 'fetch_hot': 1},
                              referer=f'{utils.BASE_URL}/')
        groups = data.get('groups')
        if not isinstance(groups, list):
            raise WeiboError('微博频道分类返回结构异常')

        result = []
        for group in groups:
            if not isinstance(group, dict):
                continue
            # 只要「频道」（group_type=1）；「默认分组 / 我的分组」是关注分组，不是内容分类
            if group.get('group_type') != utils.CHANNEL_GROUP_TYPE:
                continue
            channels = []
            for item in group.get('group') or []:
                if not isinstance(item, dict):
                    continue
                channel_id = str(item.get('gid') or '').strip()
                if not channel_id:
                    continue
                channels.append({
                    'id': channel_id,
                    'name': (item.get('title') or '').strip(),
                    'containerid': str(item.get('containerid') or '').strip(),
                    'url': utils.channel_page_url(channel_id),
                })
            if channels:
                result.append({
                    'section': (group.get('title') or '').strip(),
                    'count': len(channels),
                    'channels': channels,
                })
        return result

    def get_feed(self, channel=utils.DEFAULT_CHANNEL, containerid='',
                 limit=utils.DEFAULT_LIMIT, since_id='0'):
        """按频道取内容（热门流）

        :param channel: 频道 gid（网页 /hot/weibo/{id} 里的数字），默认 102803（热门）
        :param containerid: 频道 containerid；留空则按 channel 自动解析
        :param limit: 返回条数，1~MAX_LIMIT
        :param since_id: 翻页游标，首次传 0；下一页传上次返回的 next_since_id
        :return: {channel, containerid, count, total, since_id, next_since_id, has_more, list}
        """
        channel_id = str(channel or utils.DEFAULT_CHANNEL).strip() or utils.DEFAULT_CHANNEL
        try:
            limit = int(limit)
        except (TypeError, ValueError):
            limit = utils.DEFAULT_LIMIT
        limit = max(1, min(limit, utils.MAX_LIMIT))
        since = str(since_id or '0').strip() or '0'

        container = str(containerid or '').strip()
        if not container:
            channel_id, container = self._containerid_of(channel_id)
            if not channel_id:
                raise WeiboError('未找到该频道，请先用 /api/weibo/channels 获取分类')

        data = self._get_json(
            utils.HOT_TIMELINE_API,
            params={'since_id': since, 'refresh': 0, 'group_id': channel_id,
                    'containerid': container, 'extparam': 'discover|new_feed',
                    'max_id': 0, 'count': limit},
            referer=utils.channel_page_url(channel_id))
        statuses = data.get('statuses')
        if not isinstance(statuses, list):
            raise WeiboError('微博频道内容返回结构异常')

        items = [self._norm_status(item) for item in statuses[:limit]
                 if isinstance(item, dict)]
        nxt = utils.next_since_id(data)
        has_more = bool(items) and bool(nxt) and nxt != since
        return {
            'channel': channel_id,
            'containerid': container,
            'count': len(items),
            'total': data.get('total_number') or 0,
            'since_id': since,
            'next_since_id': nxt if has_more else None,
            'has_more': has_more,
            'list': items,
        }

    def get_video_url(self, status_id):
        """按微博 id 解析**当前可用**的视频直链

        视频直链带 `Expires` 签名会过期，所以「代理播放」每次播放都要现取一次；
        `statuses/show` 支持数字 id / mid / 短 id（mblogid）三种标识。

        :return: https 的 mp4 直链
        """
        status_id = str(status_id or '').strip()
        if not status_id:
            raise WeiboError('缺少微博 ID')
        data = self._get_json(utils.SHOW_API, params={'id': status_id},
                              referer=f'{utils.BASE_URL}/')
        page_info = data.get('page_info')
        if not (isinstance(page_info, dict) and page_info.get('object_type') == 'video'):
            # 转发微博：视频在原微博上
            retweeted = data.get('retweeted_status')
            page_info = retweeted.get('page_info') if isinstance(retweeted, dict) else None
        video = self._norm_video(page_info)
        if not video or not video['url']:
            raise WeiboError('该微博没有可播放的视频')
        return video['url']

    def open_video_stream(self, url, range_header=''):
        """打开视频流（供「代理播放」转发用）

        微博视频 CDN 有 **Referer 防盗链**：只认微博系域名，无 Referer 或第三方域名一律 403，
        所以这里必须显式带上 `Referer`。`Range` 原样透传，让浏览器能拖动进度条 / 断点续传。

        :return: requests.Response（stream=True）；调用方负责 close()
        """
        headers = utils.build_headers(f'{utils.BASE_URL}/')
        headers['Referer'] = f'{utils.BASE_URL}/'
        headers['Accept'] = '*/*'
        if range_header:
            headers['Range'] = range_header
        try:
            resp = self.session.get(url, headers=headers, stream=True,
                                    timeout=utils.VIDEO_TIMEOUT)
        except requests.RequestException as exc:
            raise WeiboError(f'拉取视频流失败: {exc}') from exc
        if resp.status_code not in (200, 206):
            code = resp.status_code
            resp.close()
            raise WeiboError(f'视频源返回异常状态码 {code}')
        return resp

    def check_cookie(self):
        """校验当前凭据是否有效

        :return: (ok, message)   ok=False 时 message 说明原因（人话，可直接展示）
        """
        try:
            self._get_json(
                utils.HOT_TIMELINE_API,
                params={'since_id': '0', 'refresh': 0,
                        'group_id': utils.DEFAULT_CHANNEL,
                        'containerid': utils.DEFAULT_CHANNEL,
                        'extparam': 'discover|new_feed', 'max_id': 0, 'count': 1},
                referer=utils.channel_page_url(utils.DEFAULT_CHANNEL))
        except WeiboError as exc:
            return False, str(exc)
        return True, '凭据有效'

    # ==================== 归一化 ====================
    def _get_long_text(self, status_id):
        """长文「展开全文」：返回 (纯文本, HTML)；取不到返回 ('', '')

        单条失败不影响整页（只记日志），但凭据失效要往上抛。
        """
        try:
            data = self._get_json(utils.LONGTEXT_API, params={'id': status_id},
                                  referer=f'{utils.BASE_URL}/')
        except WeiboCredentialExpired:
            raise
        except WeiboError as exc:
            logger.warning('微博长文展开失败 id=%s: %s', status_id, exc)
            return '', ''
        payload = data.get('data') if isinstance(data.get('data'), dict) else {}
        html = (payload.get('longTextContent') or '').strip()
        plain = (payload.get('longTextContent_raw') or '').strip()
        return (plain or utils.strip_html(html)), html

    @staticmethod
    def _norm_user(raw):
        """作者归一化"""
        raw = raw if isinstance(raw, dict) else {}
        uid = str(raw.get('idstr') or raw.get('id') or '')
        return {
            'id': uid,
            'name': (raw.get('screen_name') or '').strip(),
            'url': utils.profile_url(uid),
            'avatar': (raw.get('avatar_hd') or raw.get('avatar_large')
                       or raw.get('profile_image_url') or '').strip(),
            'verified': bool(raw.get('verified')),
            'verified_type': raw.get('verified_type'),
            'description': (raw.get('description') or '').strip(),
        }

    @staticmethod
    def _norm_images(item):
        """图片地址列表（大图优先、去重保序）"""
        infos = item.get('pic_infos') if isinstance(item.get('pic_infos'), dict) else {}
        urls = []
        for pic_id in item.get('pic_ids') or []:
            url = utils.pick_pic_url(infos.get(pic_id))
            if url and url not in urls:
                urls.append(url)
        return urls

    @staticmethod
    def _norm_video(page_info):
        """视频信息（没有视频返回 None）

        视频在 `page_info`（object_type=video）里，`media_info` 才带直链。
        """
        info = page_info if isinstance(page_info, dict) else {}
        if info.get('object_type') != 'video':
            return None
        media = info.get('media_info') if isinstance(info.get('media_info'), dict) else {}
        url = (media.get('stream_url_hd') or media.get('stream_url')
               or media.get('mp4_720p_mp4') or media.get('mp4_hd_url')
               or media.get('mp4_sd_url') or '').strip()
        cover = info.get('page_pic')
        return {
            # 直链统一升级成 https（微博给的是 http，https 页面里会被按混合内容拦掉）
            'url': utils.https_url(url),
            'cover': utils.https_url(cover) if isinstance(cover, str) else '',
            'title': (info.get('page_title') or '').strip(),
            'duration': media.get('duration') or 0,
            'page_url': (media.get('h5_url') or '').strip(),
        }

    def _norm_retweeted(self, raw):
        """被转发的原微博（裁剪版，不再递归展开它的转发与长文）"""
        raw = raw if isinstance(raw, dict) else {}
        if not raw:
            return None
        uid = str((raw.get('user') or {}).get('idstr') or '')
        return {
            'id': str(raw.get('idstr') or raw.get('id') or ''),
            'mblogid': (raw.get('mblogid') or '').strip(),
            'url': utils.status_url(uid, raw.get('mblogid')),
            'content': (raw.get('text_raw') or '').strip(),
            'content_html': (raw.get('text') or '').strip(),
            'images': self._norm_images(raw),
            'video': self._norm_video(raw.get('page_info')),
            'author': self._norm_user(raw.get('user')),
            'reposts_count': raw.get('reposts_count') or 0,
            'comments_count': raw.get('comments_count') or 0,
            'attitudes_count': raw.get('attitudes_count') or 0,
            'created_at': utils.parse_created_at(raw.get('created_at')),
        }

    def _norm_status(self, item):
        """一条微博 → 统一结构"""
        item = item if isinstance(item, dict) else {}
        text_raw = (item.get('text_raw') or '').strip()
        text_html = (item.get('text') or '').strip()
        is_long = bool(item.get('isLongText'))
        # 长文：回源取全文，只有确实更长时才替换
        # —— `isLongText` 对短微博也可能为 true，且 `textLength` 口径与正文字数不一致
        #    （还可能是 null），所以「比长度」比读 textLength 可靠。
        if is_long:
            full_text, full_html = self._get_long_text(str(item.get('idstr') or ''))
            if full_text and len(full_text) > len(text_raw):
                text_raw, text_html = full_text, (full_html or text_html)

        user = item.get('user') if isinstance(item.get('user'), dict) else {}
        uid = str(user.get('idstr') or user.get('id') or '')
        mblogid = (item.get('mblogid') or '').strip()
        return {
            'id': str(item.get('idstr') or item.get('id') or ''),
            'mid': str(item.get('mid') or ''),
            'mblogid': mblogid,
            'url': utils.status_url(uid, mblogid),
            'content': text_raw,
            'content_html': text_html,
            'is_long_text': is_long,
            'images': self._norm_images(item),
            'video': self._norm_video(item.get('page_info')),
            'retweeted': self._norm_retweeted(item.get('retweeted_status')),
            'author': self._norm_user(user),
            'reposts_count': item.get('reposts_count') or 0,
            'comments_count': item.get('comments_count') or 0,
            'attitudes_count': item.get('attitudes_count') or 0,
            'created_at': utils.parse_created_at(item.get('created_at')),
            'source': (item.get('source') or '').strip(),
            'region': (item.get('region_name') or '').strip(),
            'is_ad': bool(item.get('isAd')),
        }


def check_credential(cookie):
    """账号托管底层的平台校验入口（签名见 API/common/platform_accounts.py）"""
    return WeiboSpider(cookie=cookie).check_cookie()
