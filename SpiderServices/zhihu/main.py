"""知乎爬虫

对外能力：
    `ZhihuSpider.get_hot(limit)`        知乎热榜（规范化后的列表）
    `ZhihuSpider.get_question(...)`     问题详情（正文 / 回答 / 评论 / 相关问题 / 大家都在搜）
    `ZhihuSpider.get_article(...)`      专栏文章详情（正文 / 评论 / 大家都在搜）
    `ZhihuSpider.get_search(...)`       综合搜索（结果自带完整正文 / 大家都在搜）
    `ZhihuSpider.check_cookie()`        用 `/api/v4/me` 判断这份 Cookie 还有没有效

以及供「账号托管底层」调用的模块级函数（注册在 `API/common/platform_accounts.py`）：
    `check_credential(cookie) -> (bool, str)`

错误约定：抓取失败统一抛 `ZhihuError`，消息是可直接展示给调用方的中文说明，
由 API 层负责映射成统一响应码（`{code, msg, data}`）。
"""
import json
import logging
import re

import requests

from . import utils

logger = logging.getLogger('api.zhihu')

# 问题页内嵌的初始数据（`<script id="js-initialData">`）：问题正文只能从这里取，
# 原因见 `_get_embedded_entity()`。
INITIAL_DATA_RE = re.compile(r'<script id="js-initialData" type="text/json">(.*?)</script>',
                             re.S)
# 知乎错误码（实测）：100 / 101 = 凭据失效；40362 = 风控拦截（临时的，与凭据无关）
CREDENTIAL_ERROR_CODES = (100, 101)
RISK_CONTROL_CODE = 40362


def _zhihu_error(resp):
    """从知乎的错误响应里取出 (code, message)；取不到返回 (None, '')"""
    try:
        payload = resp.json()
    except ValueError:
        return None, ''
    error = payload.get('error') if isinstance(payload, dict) else None
    if not isinstance(error, dict):
        return None, ''
    return error.get('code'), (error.get('message') or '').strip()


class ZhihuError(Exception):
    """知乎抓取失败（消息可直接展示给调用方）"""


class ZhihuCredentialExpired(ZhihuError):
    """登录凭据已过期 / 失效 —— 需要重新登录后更新凭据

    单独一个类型，好让上层能把「托管账号」的状态自动标成「已过期」。
    """


class ZhihuSpider:
    """知乎抓取器：一个实例 = 一份登录凭据（Cookie）"""

    def __init__(self, cookie='', timeout=None):
        self.cookie = (cookie or '').strip()
        self.timeout = timeout or utils.DEFAULT_TIMEOUT
        self.session = requests.Session()

    # ==================== 内部 ====================
    @staticmethod
    def _raise_for_response(resp):
        """把非 200 响应翻译成异常

        实测的区分（很关键）：**401 / code 100、101**（`ERR_TICKET_NOT_EXIST`）才是凭据失效；
        **403 + code 40362** 是风控拦截（临时限流，与凭据无关）—— 若把它当成凭据失效，
        会把好好的托管账号误标成「已过期」，并向调用方谎报「请重新登录」。
        """
        if resp.status_code == 200:
            return
        code, message = _zhihu_error(resp)
        if resp.status_code == 401 or code in CREDENTIAL_ERROR_CODES:
            raise ZhihuCredentialExpired('知乎登录凭据已过期或无效，请重新登录后再试')
        if code == RISK_CONTROL_CODE:
            raise ZhihuError('知乎风控拦截了本次访问，请稍后重试或更换凭据')
        if message:
            raise ZhihuError(f'知乎返回异常：{message}')
        raise ZhihuError(f'知乎返回异常状态码 {resp.status_code}')

    def _get_json(self, url, params=None, referer='https://www.zhihu.com/hot'):
        """请求并解析 JSON；异常统一转成 ZhihuError"""
        headers = utils.build_headers(referer)
        if self.cookie:
            headers['Cookie'] = self.cookie
        try:
            resp = self.session.get(url, params=params, headers=headers,
                                    timeout=self.timeout)
        except requests.RequestException as exc:
            raise ZhihuError(f'请求知乎失败: {exc}') from exc

        self._raise_for_response(resp)
        try:
            return resp.json()
        except ValueError as exc:
            raise ZhihuError('知乎返回的不是合法 JSON（可能被风控拦截）') from exc

    @staticmethod
    def _cover_of(item, target):
        """封面图：优先子条目缩略图，其次 target 自带图片"""
        children = item.get('children') or []
        if children and isinstance(children[0], dict):
            thumb = children[0].get('thumbnail')
            if thumb:
                return thumb
        return (target.get('image_url') or '').strip()

    # ==================== 对外 ====================
    def get_hot(self, limit=utils.MAX_LIMIT):
        """知乎热榜（带排名）

        :param limit: 条数，1~50（知乎接口上限）
        :return: [{rank, title, url, excerpt, hot, answer_count, question_id, cover}, ...]
        """
        try:
            limit = max(1, min(int(limit or utils.MAX_LIMIT), utils.MAX_LIMIT))
        except (TypeError, ValueError):
            limit = utils.MAX_LIMIT

        data = self._get_json(utils.HOT_API,
                              params={'limit': limit, 'desktop': 'true'})
        items = data.get('data')
        if not isinstance(items, list):
            raise ZhihuError('知乎热榜返回结构异常')

        result = []
        for index, item in enumerate(items, 1):
            target = item.get('target') or {}
            result.append({
                'rank': index,
                'title': (target.get('title') or item.get('title') or '').strip(),
                'url': utils.web_url(target),
                'excerpt': (target.get('excerpt') or '').strip(),
                'hot': (item.get('detail_text') or '').strip(),
                'answer_count': (target.get('answer_count')
                                 or (item.get('feedSpecific') or {}).get('answerCount')
                                 or 0),
                'question_id': target.get('id'),
                'cover': self._cover_of(item, target),
            })
        # 知乎这个接口会忽略 limit、把当期榜单整份返回，因此按调用方要求的条数本地截断
        return result[:limit]

    def check_cookie(self):
        """校验当前凭据是否有效

        :return: (ok, message)   ok=False 时 message 说明原因（人话，可直接展示）
        """
        try:
            data = self._get_json(utils.ME_API, referer='https://www.zhihu.com/')
        except ZhihuError as exc:
            return False, str(exc)
        if isinstance(data, dict) and data.get('id'):
            name = (data.get('name') or data.get('url_token') or '').strip()
            return True, (f'凭据有效（登录用户：{name}）' if name else '凭据有效')
        return False, '知乎未返回登录用户信息，凭据可能已失效'

    # ==================== 问题详情 ====================
    def _get_text(self, url, referer='https://www.zhihu.com/'):
        """请求 HTML 页面；异常统一转成 ZhihuError"""
        headers = utils.build_headers(referer)
        headers['Accept'] = 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
        if self.cookie:
            headers['Cookie'] = self.cookie
        try:
            resp = self.session.get(url, headers=headers, timeout=self.timeout)
        except requests.RequestException as exc:
            raise ZhihuError(f'请求知乎失败: {exc}') from exc

        self._raise_for_response(resp)
        # 风控有时以「200 + 一段报错 JSON」的形式返回，此时页面里没有真正的内嵌数据
        code, _message = _zhihu_error(resp)
        if code == RISK_CONTROL_CODE:
            raise ZhihuError('知乎风控拦截了本次访问，请稍后重试或更换凭据')
        return resp.text

    def _get_embedded_entity(self, page_url, kind, entity_id, label):
        """从页面 HTML 内嵌的 `js-initialData` 里取实体（问题 / 文章）

        为什么不走 `/api/v4/questions|articles/{id}`：这两个接口都被知乎签名校验拦截，
        带登录 Cookie 也返回 403（`code 10003 请求参数异常`），所以标题 / 正文（含图片）/
        话题 / 各计数只能从页面内嵌数据里取。
        """
        html_text = self._get_text(page_url)
        matched = INITIAL_DATA_RE.search(html_text or '')
        if not matched:
            raise ZhihuError(f'未能从{label}页解析出数据（页面结构可能已变化）')
        try:
            payload = json.loads(matched.group(1))
        except ValueError as exc:
            raise ZhihuError(f'{label}页内嵌数据不是合法 JSON') from exc
        entity = (((payload.get('initialState') or {}).get('entities') or {})
                  .get(kind) or {}).get(str(entity_id))
        if not isinstance(entity, dict):
            raise ZhihuError(f'{label}不存在或不可见')
        return entity

    def _get_page_question(self, question_id):
        """问题实体（取数原因见 _get_embedded_entity）"""
        return self._get_embedded_entity(utils.question_url(question_id),
                                         'questions', question_id, '问题')

    def _get_page_article(self, article_id):
        """专栏文章实体（取数原因见 _get_embedded_entity）"""
        return self._get_embedded_entity(utils.article_url(article_id),
                                         'articles', article_id, '文章')

    @staticmethod
    def _norm_author(raw):
        """作者归一化

        v4 回答 / v5 评论的作者字段是平铺的（下划线），文章实体是驼峰（urlToken / avatarUrl），
        v4 评论则是 `{member: {...}, role: ...}` —— 这里统一兼容。
        """
        raw = raw if isinstance(raw, dict) else {}
        member = raw.get('member') if isinstance(raw.get('member'), dict) else raw
        url_token = (member.get('url_token') or member.get('urlToken') or '').strip()
        profile = ''
        if url_token:
            profile = f'{utils.BASE_URL}/people/{url_token}'
        elif (member.get('url') or '').startswith('/people/'):
            profile = utils.BASE_URL + member['url']
        return {
            'name': (member.get('name') or '').strip(),
            'url_token': url_token,
            'headline': (member.get('headline') or '').strip(),
            'avatar_url': (member.get('avatar_url') or member.get('avatarUrl') or '').strip(),
            'url': profile,
        }

    def _norm_comment(self, item, depth=0):
        """评论归一化（含内联的子评论；最多两层、每层最多 MAX_CHILD_COMMENTS 条）"""
        item = item if isinstance(item, dict) else {}
        reply_tag = item.get('reply_author_tag')
        children = item.get('child_comments') or []
        return {
            'id': str(item.get('id') or ''),
            'content': (item.get('content') or '').strip(),
            'author': self._norm_author(item.get('author')),
            'like_count': item.get('like_count') or 0,
            'child_comment_count': item.get('child_comment_count') or 0,
            'reply_to_author': (reply_tag.get('name') or '').strip()
                               if isinstance(reply_tag, dict) else '',
            'created_time': item.get('created_time'),
            'child_comments': ([self._norm_comment(child, depth + 1)
                                for child in children[:utils.MAX_CHILD_COMMENTS]
                                if isinstance(child, dict)]
                               if depth < 1 else []),
        }

    @staticmethod
    def _norm_topics(entity):
        """话题列表归一化（问题与文章共用）"""
        topics = []
        for topic in entity.get('topics') or []:
            if not isinstance(topic, dict):
                continue
            topic_id = str(topic.get('id') or '')
            topics.append({
                'id': topic_id,
                'name': (topic.get('name') or '').strip(),
                'url': utils.topic_url(topic_id) if topic_id else '',
            })
        return topics

    def _norm_question(self, question_id, entity):
        """问题实体（页面内嵌数据是驼峰命名）→ 统一结构"""
        detail = (entity.get('detail') or '').strip()
        return {
            'id': str(entity.get('id') or question_id),
            'title': (entity.get('title') or '').strip(),
            'url': utils.question_url(question_id),
            'detail': detail,
            'images': utils.extract_images(detail),
            'excerpt': (entity.get('excerpt') or '').strip(),
            'topics': self._norm_topics(entity),
            'answer_count': entity.get('answerCount') or 0,
            'follower_count': entity.get('followerCount') or 0,
            'comment_count': entity.get('commentCount') or 0,
            'visit_count': entity.get('visitCount') or 0,
            'created_time': entity.get('created'),
            'updated_time': entity.get('updatedTime'),
        }

    def _norm_article(self, article_id, entity):
        """专栏文章实体（页面内嵌数据是驼峰命名）→ 统一结构"""
        content = (entity.get('content') or '').strip()
        return {
            'id': str(entity.get('id') or article_id),
            'title': (entity.get('title') or '').strip(),
            'url': utils.article_url(article_id),
            'content': content,
            'images': utils.extract_images(content),
            'excerpt': (entity.get('excerpt') or '').strip(),
            'topics': self._norm_topics(entity),
            'author': self._norm_author(entity.get('author')),
            'voteup_count': entity.get('voteupCount') or 0,
            'comment_count': entity.get('commentCount') or 0,
            'liked_count': entity.get('likedCount') or 0,
            'favlists_count': entity.get('favlistsCount') or 0,
            # 知乎内嵌正文偶尔会截断（超长文章），如实标出来让调用方知道是否拿到全文
            'content_truncated': bool(entity.get('contentNeedTruncated')),
            'created_time': entity.get('created'),
            'updated_time': entity.get('updated'),
        }

    def _get_comments(self, kind, target_id, limit, referer):
        """取根评论

        评论属于「详情里的一个模块」，取不到不应该拖垮整次详情，故非凭据类异常
        只记日志并返回空列表（`ZhihuCredentialExpired` 例外，要如实上报）。
        """
        if limit <= 0:
            return []
        try:
            data = self._get_json(utils.root_comment_api(kind, target_id),
                                  params={'order_by': 'score', 'limit': limit, 'offset': ''},
                                  referer=referer)
        except ZhihuCredentialExpired:
            raise
        except ZhihuError as exc:
            logger.warning('取评论失败 [%s/%s]: %s', kind, target_id, exc)
            return []
        items = data.get('data') if isinstance(data, dict) else None
        if not isinstance(items, list):
            return []
        return [self._norm_comment(item) for item in items[:limit]]

    def _get_answers(self, question_id, limit, comment_limit):
        data = self._get_json(utils.question_answers_api(question_id),
                              params={'include': utils.ANSWERS_INCLUDE, 'limit': limit,
                                      'offset': 0, 'order': 'default', 'platform': 'desktop'},
                              referer=utils.question_url(question_id))
        items = data.get('data') if isinstance(data, dict) else None
        if not isinstance(items, list):
            raise ZhihuError('知乎回答列表返回结构异常')

        answers = []
        for item in items[:limit]:
            item = item if isinstance(item, dict) else {}
            answer_id = str(item.get('id') or '')
            content = (item.get('content') or '').strip()
            answers.append({
                'id': answer_id,
                'url': utils.answer_url(question_id, answer_id),
                'content': content,
                'images': utils.extract_images(content),
                'excerpt': (item.get('excerpt') or '').strip(),
                'author': self._norm_author(item.get('author')),
                'voteup_count': item.get('voteup_count') or 0,
                'comment_count': item.get('comment_count') or 0,
                'created_time': item.get('created_time'),
                'updated_time': item.get('updated_time'),
                'comments': self._get_comments(
                    'answers', answer_id, comment_limit,
                    referer=utils.answer_url(question_id, answer_id)),
            })
        return answers

    def _get_similar_questions(self, question_id, limit):
        """相关问题"""
        data = self._get_json(utils.similar_questions_api(question_id),
                              params={'include': utils.SIMILAR_INCLUDE, 'limit': limit},
                              referer=utils.question_url(question_id))
        items = data.get('data') if isinstance(data, dict) else None
        if not isinstance(items, list):
            return []
        result = []
        for item in items[:limit]:
            item = item if isinstance(item, dict) else {}
            similar_id = str(item.get('id') or '')
            result.append({
                'id': similar_id,
                'title': (item.get('title') or '').strip(),
                'url': utils.question_url(similar_id) if similar_id else '',
                'answer_count': item.get('answer_count') or 0,
                'follower_count': item.get('follower_count') or 0,
            })
        return result

    def _get_hot_search(self, limit, referer, content_type='', target_id=''):
        """「大家都在搜」：返回热搜词（每项自带搜索页地址）

        · 带 content_type + target_id → 与该内容相关的搜索词（问题页 / 文章页）
        · 都不带 → 全局热搜词（搜索页底部那个模块）
        """
        params = ({'content_type': content_type, 'content_token': target_id}
                  if content_type and target_id else None)
        data = self._get_json(utils.HOT_SEARCH_API, params=params, referer=referer)
        items = data.get('hot_search_queries') if isinstance(data, dict) else None
        if not isinstance(items, list):
            return []
        result = []
        for item in items[:limit]:
            item = item if isinstance(item, dict) else {}
            query = (item.get('query') or '').strip()
            if not query:
                continue
            result.append({
                'query': query,
                'hot': item.get('hot') or 0,
                'hot_show': (item.get('hot_show') or '').strip(),
                'label': (item.get('label') or '').strip(),
                'index': item.get('index'),
                'url': utils.search_url(query),
            })
        return result

    def get_question(self, question_id, answer_limit=5, comment_limit=3,
                     question_comment_limit=10):
        """问题详情：问题本体 + 回答（含图片、评论）+ 问题评论 + 相关问题 + 大家都在搜

        :param question_id: 知乎问题 ID
        :param answer_limit: 返回多少条回答（1~MAX_ANSWERS）
        :param comment_limit: 每条回答返回多少条评论（0~MAX_COMMENTS，0 = 不取）
        :param question_comment_limit: 问题本身返回多少条评论（0~MAX_COMMENTS）
        :return: {question, answers, related_questions, hot_searches}
            —— 「相关问题」固定 5 条、「大家都在搜」固定 10 条（与知乎页面模块一致）
        """
        question_id = str(question_id)
        answer_limit = max(1, min(int(answer_limit), utils.MAX_ANSWERS))
        comment_limit = max(0, min(int(comment_limit), utils.MAX_COMMENTS))
        question_comment_limit = max(0, min(int(question_comment_limit),
                                            utils.MAX_COMMENTS))

        question = self._norm_question(question_id,
                                       self._get_page_question(question_id))
        question['comments'] = self._get_comments(
            'questions', question_id, question_comment_limit,
            referer=utils.question_url(question_id))
        return {
            'question': question,
            'answers': self._get_answers(question_id, answer_limit, comment_limit),
            'related_questions': self._get_similar_questions(question_id, 5),
            'hot_searches': self._get_hot_search(10, utils.question_url(question_id),
                                                 'question', question_id),
        }

    def get_article(self, article_id, comment_limit=10):
        """专栏文章详情：文章本体（完整正文与图片）+ 评论 + 大家都在搜

        与问题不同，文章页**没有**「回答列表」与「相关问题」两个模块，故只返回这三块。

        :param article_id: 知乎专栏文章 ID
        :param comment_limit: 返回多少条评论（0~MAX_COMMENTS，0 = 不取）
        :return: {article, hot_searches}
            —— 「大家都在搜」固定 10 条（与知乎页面模块一致）
        """
        article_id = str(article_id)
        comment_limit = max(0, min(int(comment_limit), utils.MAX_COMMENTS))

        article = self._norm_article(article_id, self._get_page_article(article_id))
        article['comments'] = self._get_comments(
            'articles', article_id, comment_limit,
            referer=utils.article_url(article_id))
        return {
            'article': article,
            'hot_searches': self._get_hot_search(10, utils.article_url(article_id),
                                                 'article', article_id),
        }

    def _norm_search_item(self, item, index):
        """搜索结果里的一条

        `object` 是 answer / article / zvideo（字段为下划线命名），里面**直接带完整正文**，
        所以「阅读全文」不需要再逐条回源。
        """
        item = item if isinstance(item, dict) else {}
        obj = item.get('object') if isinstance(item.get('object'), dict) else {}
        kind = (obj.get('type') or '').strip()
        target_id = str(obj.get('id') or '')
        question = obj.get('question') if isinstance(obj.get('question'), dict) else {}
        question_id = str(question.get('id') or '')
        content = (obj.get('content') or '').strip()
        return {
            'index': index,
            'type': kind,
            'id': target_id,
            'title': utils.strip_html(obj.get('title')),
            'url': utils.search_result_url(kind, target_id, question_id),
            'content': content,
            'images': utils.extract_images(content),
            'excerpt': utils.strip_html(obj.get('excerpt')),
            'author': self._norm_author(obj.get('author')),
            'voteup_count': obj.get('voteup_count') or 0,
            'comment_count': obj.get('comment_count') or 0,
            'created_time': obj.get('created_time'),
            'updated_time': obj.get('updated_time'),
            'question': ({'id': question_id,
                          'title': (question.get('name') or '').strip(),
                          'url': utils.question_url(question_id)}
                         if question_id else None),
        }

    def get_search(self, keyword, limit=20, offset=0):
        """知乎综合搜索：结果列表（每条自带完整正文与图片）+「大家都在搜」

        结果类型有 `answer`（回答）/ `article`（专栏文章）/ `zvideo`（视频，没有正文）；
        评论只给 `comment_count`（数量），不逐条回源，避免一次搜索打几十个请求。

        :param keyword: 搜索关键词
        :param limit: 返回多少条（1~MAX_SEARCH_LIMIT，知乎单页上限 20）
        :param offset: 翻页偏移（从 0 开始）
        :return: {count, is_end, next_offset, list, hot_searches}
        """
        keyword = (keyword or '').strip()
        if not keyword:
            raise ZhihuError('搜索关键词不能为空')
        limit = max(1, min(int(limit), utils.MAX_SEARCH_LIMIT))
        offset = max(0, int(offset))

        data = self._get_json(
            utils.SEARCH_API,
            params={'t': 'general', 'q': keyword, 'correction': 1, 'offset': offset,
                    'limit': limit, 'filter_fields': '', 'lc_idx': offset,
                    'show_all_topics': 0, 'search_source': 'Normal'},
            referer=utils.search_url(keyword))
        items = data.get('data') if isinstance(data, dict) else None
        if not isinstance(items, list):
            raise ZhihuError('知乎搜索返回结构异常')

        results = [self._norm_search_item(item, index + 1)
                   for index, item in enumerate(items[:limit])]
        paging = data.get('paging') if isinstance(data.get('paging'), dict) else {}
        is_end = bool(paging.get('is_end'))
        return {
            'count': len(results),
            'is_end': is_end,
            # 下一页的 offset；到底了就是 null（调用方据此停止翻页）
            'next_offset': None if (is_end or not results) else offset + len(results),
            'list': results,
            'hot_searches': self._get_hot_search(10, utils.search_url(keyword)),
        }


def check_credential(cookie):
    """账号托管底层的平台校验入口（签名见 API/common/platform_accounts.py）"""
    return ZhihuSpider(cookie=cookie).check_cookie()
